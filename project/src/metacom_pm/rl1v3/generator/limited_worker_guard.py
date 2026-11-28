"""Linux-only worker launcher; stdlib only, before any model import.

A small sibling of the model's descendants survives supervisor death. It holds
pidfds for both supervisor and worker, stays in the worker's private process
group (pinning that group even after its leader exits), and kills that group on
either death or the absolute job deadline. No preexec_fn in a threaded parent.
"""
from __future__ import annotations
import math
import os
import ctypes
import select
import signal
import sys
import time


def pidfd_open(pid):
    if hasattr(os, "pidfd_open"):
        return os.pidfd_open(pid)
    # The pinned Python/libc were built before pidfd_open was exposed, although
    # this x86_64 Linux host's kernel supports it. No polling PID reuse fallback.
    if os.uname().sysname != "Linux" or os.uname().machine != "x86_64":
        raise RuntimeError("pidfd_open unavailable on this platform")
    libc = ctypes.CDLL(None, use_errno=True)
    libc.syscall.restype = ctypes.c_long
    fd = libc.syscall(ctypes.c_long(434), ctypes.c_int(pid), ctypes.c_uint(0))
    if fd < 0:
        err = ctypes.get_errno()
        raise OSError(err, os.strerror(err))
    return fd


def launch(argv):
    parent = int(os.environ["PMRL1_LIMITED_SUPERVISOR_PID"])
    deadline = float(os.environ["PMRL1_LIMITED_DEADLINE"])
    leader = os.getpid()
    if parent != os.getppid() or os.getpgrp() != leader or os.getsid(0) != leader:
        raise RuntimeError("guard requires the admitted parent's private worker session")
    if not argv or not math.isfinite(deadline) or not 0 < deadline - time.monotonic() <= 1200:
        raise RuntimeError("invalid guard deadline/command")
    parent_fd = pidfd_open(parent)
    worker_fd = pidfd_open(leader)
    ready_r, ready_w = os.pipe()
    guard = os.fork()  # this fresh stdlib-only launcher has no threads
    if guard == 0:
        os.close(ready_r)
        # TERM to the group may be ignored by a worker/descendant. This monitor
        # remains until leader death/deadline, then uses SIGKILL for the group.
        for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            signal.signal(sig, signal.SIG_IGN)
        for fd in (0, 1, 2):
            os.close(fd)
        try:
            watcher = select.poll()
            watcher.register(parent_fd, select.POLLIN)
            watcher.register(worker_fd, select.POLLIN)
            os.write(ready_w, b"R")
            os.close(ready_w)
            while True:
                left = deadline - time.monotonic()
                if left <= 0 or watcher.poll(max(1, math.ceil(left * 1000))):
                    break
        finally:
            # The monitor itself is still a member, so this PGID cannot have
            # been recycled into somebody else's job. Also kills this monitor.
            os.killpg(leader, signal.SIGKILL)
            os._exit(1)
    os.close(ready_w)
    try:
        ready, _, _ = select.select([ready_r], [], [], min(5, max(0, deadline - time.monotonic())))
        if not ready or os.read(ready_r, 1) != b"R" or os.getppid() != parent:
            raise RuntimeError("worker guard did not arm")
        for fd in (ready_r, parent_fd, worker_fd):
            os.close(fd)
        # exec preserves worker PID, process group, pipes and supervisor identity.
        os.execvpe(argv[0], argv, os.environ)
    except BaseException:
        os.killpg(leader, signal.SIGKILL)
        raise


if __name__ == "__main__":
    launch(sys.argv[1:])
