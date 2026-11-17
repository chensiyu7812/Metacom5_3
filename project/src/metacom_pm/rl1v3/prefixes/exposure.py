"""B0 exposure registry: which owners/sessions already appear in repo artifacts.

V3.1 `exposure_warning`: PRIVATE-named derivatives, blind maps and ratings were
published to the public repository, so historical confirmation sets cannot be
re-labelled as unexposed.  This module records a *mechanical lower bound* of
that exposure: every tracked file under the scanned roots is searched for exact
EvoEmo session ids, and the containing run/review directory is classified by
name.  Untracked local artifacts, chat transcripts and human memory are not
covered, so "absent here" never means "never seen".
"""
from __future__ import annotations

import re
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Mapping, Sequence

SESSION_ID_PATTERN = r"\bp[0-9]{1,2}_conv_[0-9]+\b|\besc[0-9]{1,4}\b"
SCAN_ROOTS = ("project/outputs/pm_rl1", "project/docs/reviews")
EXCLUDE_PREFIXES = ("project/outputs/pm_rl1/v3/",)  # never count V3.1 outputs as history

# First match wins; order goes from strongest to weakest exposure.  Keys match
# whole underscore/dash-delimited tokens of the run directory's basename (so
# "ppo" does not match "opportunity").
CATEGORY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("human_review", ("human", "rating", "calibration_form", "pair_review", "acceptance")),
    ("training", ("training", "learning", "supervision", "ppo", "handoff")),
    ("judge_or_feedback", ("judge", "feedback", "measurement", "calibration", "reference",
                           "qualification")),
    ("generation_or_probe", ("probe", "pilot", "executor", "generation", "comparison",
                             "value", "branches", "equivalence", "latency", "claude",
                             "trial", "completion", "bridges", "integration", "gain", "path")),
    ("census_or_diagnostic", ("census", "diagnostic", "coverage", "source", "evidence",
                              "organization", "reorganization", "dataset", "preparation",
                              "publication", "audit", "engineering", "decision", "repair",
                              "interface", "design")),
)
CATEGORIES = tuple(c for c, _ in CATEGORY_RULES) + ("other",)


def classify(run_dir: str) -> str:
    base = run_dir.rstrip("/").rsplit("/", 1)[-1].lower()
    name = "_" + re.sub(r"[^a-z0-9]+", "_", base).strip("_") + "_"
    for category, keys in CATEGORY_RULES:
        if any("_" + k + "_" in name for k in keys):
            return category
    return "other"


def run_dir_of(path: str) -> str | None:
    """Collapse a tracked file path to its run/review directory."""
    parts = path.split("/")
    if path.startswith(EXCLUDE_PREFIXES):
        return None
    if parts[:3] == ["project", "outputs", "pm_rl1"] and len(parts) >= 5:
        return "/".join(parts[:4])
    if parts[:3] == ["project", "docs", "reviews"] and len(parts) >= 6:
        return "/".join(parts[:5])
    return None


def scan_git(repo_root: Path, roots: Sequence[str] = SCAN_ROOTS) -> list[tuple[str, str]]:
    """Return sorted unique (run_dir, session_id) pairs from tracked text files."""
    proc = subprocess.run(
        ["git", "grep", "-o", "-I", "-E", SESSION_ID_PATTERN, "--", *roots],
        cwd=repo_root, capture_output=True, text=True, check=False)
    if proc.returncode not in (0, 1):
        raise RuntimeError(proc.stderr.strip() or "git grep failed")
    pairs = set()
    for line in proc.stdout.splitlines():
        path, _, match = line.rpartition(":")
        path = path.split(":", 1)[0]
        run_dir = run_dir_of(path)
        if run_dir:
            pairs.add((run_dir, match))
    return sorted(pairs)


def build_registry(pairs: Iterable[tuple[str, str]],
                   sessions_by_owner: Mapping[str, Sequence[str]],
                   historical_split: Mapping[str, str],
                   fold_of_owner: Mapping[str, int]) -> list[dict]:
    """Owner rows then session rows.  Unknown ids in the scan are ignored."""
    known = {sid for sids in sessions_by_owner.values() for sid in sids}
    seen: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for run_dir, sid in pairs:
        if sid in known:
            seen[sid][classify(run_dir)].add(run_dir)
    rows: list[dict] = []
    for owner, sids in sessions_by_owner.items():
        cats = {c: sorted({d for s in sids for d in seen[s].get(c, ())}) for c in CATEGORIES}
        rows.append(dict(
            record="owner",
            owner_id=owner,
            fold=fold_of_owner[owner],
            historical_rl1_split=historical_split[owner],
            public_benchmark_source=True,
            sessions_total=len(sids),
            sessions_in_tracked_artifacts=sum(1 for s in sids if seen.get(s)),
            sessions_in_human_review_artifacts=sum(1 for s in sids if seen[s].get("human_review")),
            run_dirs_by_category={c: v for c, v in cats.items() if v},
            unexposed_confirmation_eligible=False,
            note=("public ES-MemEval source and public repo derivatives; a fresh confirmation "
                  "set needs a new authorized source sealed until freeze (V3.1 §6.1)"),
        ))
    for owner, sids in sessions_by_owner.items():
        for sid in sids:
            rows.append(dict(
                record="session",
                owner_id=owner,
                session_id=sid,
                categories=sorted(seen[sid]) if sid in seen else [],
                run_dirs_by_category={c: sorted(v) for c, v in sorted(seen[sid].items())}
                if sid in seen else {},
            ))
    return rows


# ------------------------------------------------- prefix-level legacy exposure

STRONG_CATEGORIES = ("human_review", "training", "judge_or_feedback")
_HEX64 = re.compile(r"[0-9a-f]{64}")


def legacy_rl1_prefix_identity(owner_id: str, session_id: str, cutoff_rank: int, cut: int,
                               timestamp: str, historical_split: str, turns) -> str:
    """Identity the historical rl1 pipeline gave this exact prefix
    (``metacom_pm.rl1.schema.PrefixSpec.identity``)."""
    from metacom_pm.rl1.schema import PrefixSpec, PublicTurn
    return PrefixSpec(owner_id, session_id, cutoff_rank, cut, timestamp, historical_split,
                      tuple(PublicTurn(t.role, t.content) for t in turns)).identity


def scan_hex_identities(repo_root: Path, wanted: set[str],
                        categories: Sequence[str] = STRONG_CATEGORIES,
                        roots: Sequence[str] = SCAN_ROOTS) -> list[tuple[str, str]]:
    """Sorted unique (run_dir, identity) for wanted 64-hex ids found in tracked
    files of run dirs whose category is in ``categories``."""
    files = subprocess.run(["git", "ls-files", "--", *roots], cwd=repo_root,
                           capture_output=True, text=True, check=True).stdout.splitlines()
    pairs: set[tuple[str, str]] = set()
    for f in files:
        run_dir = run_dir_of(f)
        if not run_dir or classify(run_dir) not in categories:
            continue
        try:
            text = (repo_root / f).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for h in set(_HEX64.findall(text)) & wanted:
            pairs.add((run_dir, h))
    return sorted(pairs)


def prefix_exposure_records(census_rows: Sequence[Mapping], legacy_ids: Mapping[str, str],
                            hits: Iterable[tuple[str, str]]) -> list[dict]:
    """One record per census prefix whose legacy identity appears in a strong-category dir."""
    by_legacy: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for run_dir, h in hits:
        by_legacy[h][classify(run_dir)].add(run_dir)
    out = []
    for r in census_rows:
        h = legacy_ids[r["prefix_id"]]
        if h in by_legacy:
            out.append(dict(
                record="prefix", prefix_id=r["prefix_id"], owner_id=r["owner_id"],
                session_id=r["session_id"], cut_turn=r["cut_turn"],
                legacy_rl1_prefix_identity=h,
                categories=sorted(by_legacy[h]),
                run_dirs_by_category={c: sorted(v) for c, v in sorted(by_legacy[h].items())},
            ))
    return out
