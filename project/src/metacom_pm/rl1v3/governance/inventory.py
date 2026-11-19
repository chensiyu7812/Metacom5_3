"""Inventory of ESConv / EvoEmo RAW text in a git repository (all remote branches), by fingerprint.

Fingerprints are distinctive utterances (>= 50 characters of plain ASCII text) sampled deterministically from the
sanitized EvoEmo artifact (split into generated sessions and ESConv-derived sessions) and from ESConv dialogues
that are not part of EvoEmo.  `git grep -F -o` searches every branch tree without checking anything out.  Outputs
carry paths, counts and hashes only -- never the fingerprint text itself.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections import defaultdict
from pathlib import Path

SAFE = re.compile(r"^[A-Za-z0-9 ,.!?;()'\-]+$")


def _sha(t: str) -> str:
    return hashlib.sha256(t.encode()).hexdigest()


def fingerprints(artifact: dict, esconv: list, *, n_evo: int = 400, n_esc_in_evo: int = 150, n_esc: int = 300) -> dict:
    evo, esc_in_evo = set(), set()
    for u in artifact["users"]:
        for s in u["sessions"]:
            bucket = esc_in_evo if re.fullmatch(r"esc\d+", s["session_id"]) else evo
            for t in s["turns"]:
                x = t["content"].strip()
                if len(x) >= 50 and SAFE.match(x) and "  " not in x:
                    bucket.add(x)
    all_evo = evo | esc_in_evo
    esc_only = set()
    for d in esconv:
        for t in d["dialog"]:
            x = t["content"].strip()
            if len(x) >= 50 and SAFE.match(x) and "  " not in x and x not in all_evo:
                esc_only.add(x)
    pick = lambda pool, n: sorted(pool, key=_sha)[:n]                       # noqa: E731
    out = {}
    for kind, pool, n in (("evoemo_generated", evo, n_evo), ("esconv_in_evoemo", esc_in_evo, n_esc_in_evo),
                          ("esconv_only", esc_only, n_esc)):
        for x in pick(pool, n):
            out[x] = (kind, _sha(x)[:16])
            if "'" in x:
                out[x.replace("'", "&#x27;")] = (kind, _sha(x)[:16])         # html-escaped evidence blocks
    return out


WORD = re.compile(r"[a-z0-9']+")


def _words(text: str) -> list[str]:
    return WORD.findall(text.replace("&#x27;", "'").replace("\\u0027", "'").lower())


def _shingles(words: list[str], n: int = 8):
    return {" ".join(words[i:i + n]) for i in range(len(words) - n + 1)}


def scan(repo: Path, refs: list[str], fps: dict, *, min_hits: int = 3, max_bytes: int = 400 * 1024 ** 2) -> dict:
    """Blob-deduplicated scan: every unique blob of every ref is read once (git cat-file --batch) and matched by
    8-word shingles of the fingerprints.  Returns {path: {kind: {ref: distinct fingerprints}}} for files with
    >= min_hits distinct fingerprints of a kind."""
    sh = {}
    for text, (kind, fid) in fps.items():
        for s in _shingles(_words(text)):
            sh[s] = (kind, fid)
    where = defaultdict(set)                      # blob -> {(ref, path)}
    sizes = {}
    for ref in refs:
        r = subprocess.run(["git", "ls-tree", "-r", "-l", "-z", ref], cwd=repo, capture_output=True, check=True)
        for entry in r.stdout.decode("utf-8", "surrogateescape").split("\0"):
            if not entry:
                continue
            meta, path = entry.split("\t", 1)
            mode, typ, blob, size = meta.split()
            if typ == "blob" and size != "-":
                where[blob].add((ref, path))
                sizes[blob] = int(size)
    blobs = [b for b in where if sizes[b] <= max_bytes]
    found = {}
    p = subprocess.Popen(["git", "cat-file", "--batch"], cwd=repo, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    try:
        for b in blobs:
            p.stdin.write((b + "\n").encode())
            p.stdin.flush()
            header = p.stdout.readline().split()
            n = int(header[2])
            data = p.stdout.read(n)
            p.stdout.read(1)
            if b"\0" in data[:8192]:
                continue
            got = defaultdict(set)
            for s in _shingles(_words(data.decode("utf-8", "ignore"))):
                if s in sh:
                    k, fid = sh[s]
                    got[k].add(fid)
            if got and max(len(v) for v in got.values()) >= min_hits:
                found[b] = {k: len(v) for k, v in got.items()}
    finally:
        p.stdin.close()
        p.wait()
    out = defaultdict(lambda: defaultdict(dict))
    for b, kinds in found.items():
        for ref, path in where[b]:
            for k, n in kinds.items():
                out[path][k][ref] = n
    return {path: {k: dict(v) for k, v in kinds.items()} for path, kinds in out.items()}, \
        dict(unique_blobs=len(where), scanned_blobs=len(blobs), skipped_large=len(where) - len(blobs))


def git_history(repo: Path, path: str) -> dict:
    r = subprocess.run(["git", "log", "--remotes=origin", "--diff-filter=A", "--format=%h|%cs|%s", "--", path],
                       cwd=repo, capture_output=True, text=True)
    lines = [x for x in r.stdout.splitlines() if x]
    first = lines[-1].split("|", 2) if lines else None
    return dict(added_in=dict(commit=first[0], date=first[1], subject=first[2][:100]) if first else None,
                add_events=len(lines))


def classify(path: str) -> str:
    if path.startswith("project/data/external/"):
        return "原始数据集文件（上游原样）"
    if path.startswith("project/data/"):
        return "项目数据目录中的 RAW 或派生数据"
    if "/outputs/" in path:
        return "研究产出中的 RAW 派生内容（请求、背景、证据块、评审包等）"
    if "/tests/" in path:
        return "测试夹具"
    return "其他"


def json_dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=True)
