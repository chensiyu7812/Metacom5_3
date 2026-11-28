"""NAA worker launcher: the historical pidfd group guard with a manifest-derived bound.

The historical limited_worker_guard caps a job at 1200 s, which fits A0/GE2 but not
a multi-hour approved batch. This launcher reuses its pidfd primitive and the same
monitor semantics (kill the worker's private process group on supervisor death or at
the absolute deadline). The bound comes from the approved GPU-seconds cap and is
itself capped at 12 h. The historical guard is unchanged and still guards GE2.
"""
from __future__ import annotations

import math
import os
import select
import signal
import sys
import time

from ...rl1v3.generator.limited_worker_guard import pidfd_open

HARD_MAX_SECONDS = 43200


def launch(argv):
    parent = int(os.environ['PMRL1_LIMITED_SUPERVISOR_PID'])
    deadline = float(os.environ['PMRL1_LIMITED_DEADLINE'])
    bound = float(os.environ['NAA_GUARD_MAX_SECONDS'])
    leader = os.getpid()
    if parent != os.getppid() or os.getpgrp() != leader or os.getsid(0) != leader:
        raise RuntimeError("guard requires the admitted parent's private worker session")
    if not (argv and math.isfinite(deadline) and 0 < bound <= HARD_MAX_SECONDS
            and 0 < deadline - time.monotonic() <= bound):
        raise RuntimeError('invalid guard deadline/command')
    parent_fd = pidfd_open(parent)
    worker_fd = pidfd_open(leader)
    ready_r, ready_w = os.pipe()
    guard = os.fork()
    if guard == 0:
        os.close(ready_r)
        for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            signal.signal(sig, signal.SIG_IGN)
        for fd in (0, 1, 2):
            os.close(fd)
        try:
            watcher = select.poll()
            watcher.register(parent_fd, select.POLLIN)
            watcher.register(worker_fd, select.POLLIN)
            os.write(ready_w, b'R')
            os.close(ready_w)
            while True:
                left = deadline - time.monotonic()
                # pidfd readable == supervisor or worker exited; empty poll == timeout slice.
                if left <= 0 or watcher.poll(max(1, math.ceil(min(left, 3600) * 1000))):
                    break
        finally:
            os.killpg(leader, signal.SIGKILL)
            os._exit(1)
    os.close(ready_w)
    try:
        ready, _, _ = select.select([ready_r], [], [], min(5, max(0, deadline - time.monotonic())))
        if not ready or os.read(ready_r, 1) != b'R' or os.getppid() != parent:
            raise RuntimeError('worker guard did not arm')
        for fd in (ready_r, parent_fd, worker_fd):
            os.close(fd)
        os.execvpe(argv[0], argv, os.environ)
    except BaseException:
        os.killpg(leader, signal.SIGKILL)
        raise


if __name__ == '__main__':
    launch(sys.argv[1:])
