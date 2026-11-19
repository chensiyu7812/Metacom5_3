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
import tempfile
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


def scan(repo: Path, refs: list[str], fps: dict, *, min_hits: int = 3) -> dict:
    """{path: {kind: {ref: distinct fingerprints matched}}} for files with >= min_hits distinct fingerprints."""
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write("\n".join(fps))
        pat = f.name
    hits = defaultdict(lambda: defaultdict(lambda: defaultdict(set)))
    try:
        for ref in refs:
            r = subprocess.run(["git", "grep", "-F", "-o", "-I", "-f", pat, ref, "--", "."], cwd=repo,
                               capture_output=True, text=True, errors="replace")
            for line in r.stdout.splitlines():
                head, _, match = line.rpartition(":")
                _ref, _, path = head.partition(":")
                k = fps.get(match)
                if k:
                    hits[path][k[0]][ref].add(k[1])
    finally:
        Path(pat).unlink()
    out = {}
    for path, kinds in hits.items():
        best = {kind: max(len(v) for v in by_ref.values()) for kind, by_ref in kinds.items()}
        if max(best.values()) >= min_hits:
            out[path] = {kind: {ref: len(v) for ref, v in by_ref.items()} for kind, by_ref in kinds.items()}
    return out


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
