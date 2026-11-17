"""B0: legal prefix census, owner/family-first folds and deterministic features.

Scope (PM-RL1 V3.1 §6.1, task B0):

* Every EvoEmo session with ``chronological_rank >= 1`` (at least one strictly
  past session) contributes one candidate cut per position ``i`` where turn
  ``i`` is a seeker turn immediately followed by a supporter turn.  The prefix
  is exactly ``session.turns[:i + 1]``; nothing after ``i`` and no session with
  rank ``>= cutoff_rank`` contributes to any *visible* field.
* Owners are grouped by shared source families **before** folds are assigned;
  prefixes, training conditions, teacher samples and terminals inherit the
  owner's fold.  A family shared by two owners (e.g. the same ESConv seed
  transcript in both histories) forces both owners into the same fold.
* The census is the *natural* distribution (every legal cut, weight 1).  It is
  never resampled here.  Training-time oversampling (B1) must keep its own
  selection record and cannot be reported as a natural need rate.

Each census row separates ``visible`` (computable from the current prefix,
strictly past same-owner sessions and their timestamps) from ``eval_only``
(future-dependent or dataset-lineage facts).  Only ``visible`` may ever feed a
policy observation, and even then only through the frozen C0 Observation.

Hashing uses canonical JSON (sorted keys, compact separators, UTF-8,
``allow_nan=False``).  When C0 ``rl1v3/io.py`` is frozen this module must
switch to that implementation and re-emit identities under a new protocol
version rather than silently re-labelling old ones.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from metacom_pm.paper1.data.memory_source import (
    MemorySourceUser,
    Session,
    load_sanitized_runtime_users,
)

CENSUS_PROTOCOL = "pmrl1v3-b0-prefix-census-v1"
ROW_SCHEMA = "pmrl1v3-b0-prefix-census-row-v1"
FOLDS_SCHEMA = "pmrl1v3-b0-folds-v1"
DATASET = "es_memeval_evoemo_public_v1"

N_FOLDS = 6
FOLD_SIZE = 3
FIXED_HELDOUT_FOLD = 6
FIXED_HELDOUT_OWNERS = ("p4", "p7", "p14")  # historical test owners (V3.1 §6.1)
ORIGINAL_DEV_OWNERS = ("p1", "p15", "p18")  # historical dev owners (V3.1 §6.1)
G1_EXTRA_FOLD = 5
FOLD_SALT = "pmrl1v3|fold|"
SAMPLE_SALT = "pmrl1v3|sample|"
G1_EVAL_SALT = "pmrl1v3|g1-eval-fold|"

# Heuristic, outcome-blind surface cues on the *trailing seeker block* only.
# They describe text, not needs; B1 NeedCards are the only need labels.
_CUES: dict[str, re.Pattern[str]] = {
    "back_reference": re.compile(
        r"\b(last time|you (said|suggested|told me|mentioned)|as i (said|mentioned)|"
        r"i (told|mentioned to) you|remember|we (talked|discussed|spoke)|"
        r"(our|the) (last|previous) (chat|conversation|session|talk))\b", re.I),
    "temporal_marker": re.compile(
        r"\b(yesterday|last (week|month|year|night)|ago|recently|since|lately|"
        r"(this|next) (week|month)|tomorrow|these days)\b", re.I),
    "advice_request": re.compile(
        r"\b(what should i|any (advice|tips|suggestions)|how (can|do|should) i|"
        r"what can i|should i|do you think|can you (help|suggest)|what would you)\b", re.I),
    "question_mark": re.compile(r"\?"),
    "risk_keyword": re.compile(
        r"\b(suicid\w*|kill (myself|me)|end (my|it all)|self[- ]harm\w*|hurt(ing)? myself|"
        r"don'?t want to (live|be alive)|overdose)\b", re.I),
}


# --------------------------------------------------------------------- hashing

def canonical_json(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def digest(obj: object) -> str:
    return sha256_text(canonical_json(obj))


def turn_payload(turns: Sequence) -> list[list[str]]:
    return [[t.role, t.content] for t in turns]


def session_sha256(session: Session) -> str:
    """Identity of the complete session transcript (eval-side binding only)."""
    return digest(turn_payload(session.turns))


def fold_key(owner_id: str) -> str:
    return sha256_text(FOLD_SALT + owner_id)


def sample_key(prefix_id: str) -> str:
    return sha256_text(SAMPLE_SALT + prefix_id)


# ------------------------------------------------------------- legal positions

def legal_cut_positions(session: Session) -> tuple[int, ...]:
    """0-based positions whose seeker turn is answered by the next supporter turn."""
    turns = session.turns
    return tuple(i for i in range(len(turns) - 1)
                 if turns[i].role == "seeker" and turns[i + 1].role == "supporter")


def strictly_past_sessions(user: MemorySourceUser, cutoff_rank: int) -> tuple[Session, ...]:
    return tuple(sorted((s for s in user.sessions if s.chronological_rank < cutoff_rank),
                        key=lambda s: s.chronological_rank))


def prefix_turns(session: Session, cut: int) -> tuple:
    if cut not in legal_cut_positions(session):
        raise ValueError(f"illegal cut {cut} in {session.session_id}")
    return session.turns[:cut + 1]


def prefix_id_for(owner_id: str, session_id: str, cut: int, prefix_sha256: str) -> str:
    return digest(dict(protocol=CENSUS_PROTOCOL, dataset=DATASET, owner_id=owner_id,
                       session_id=session_id, cut_turn=cut, prefix_sha256=prefix_sha256))


def _words(text: str) -> int:
    return len(text.split())


def _trailing_seeker_block(turns: Sequence) -> str:
    block: list[str] = []
    for t in reversed(turns):
        if t.role != "seeker":
            break
        block.append(t.content)
    return "\n".join(reversed(block))


def surface_cues(text: str) -> dict[str, bool]:
    return {name: bool(rx.search(text)) for name, rx in _CUES.items()}


def visible_features(user: MemorySourceUser, session: Session, cut: int) -> dict:
    """Outcome-blind features from the prefix and strictly past sessions only."""
    turns = prefix_turns(session, cut)
    past = strictly_past_sessions(user, session.chronological_rank)
    past_turns = [t for s in past for t in s.turns]
    tail = _trailing_seeker_block(turns)
    cur = session.date
    prev = past[-1].date if past else None
    first = past[0].date if past else None
    return dict(
        n_prefix_turns=len(turns),
        n_prefix_seeker_turns=sum(t.role == "seeker" for t in turns),
        prefix_words=sum(_words(t.content) for t in turns),
        trailing_seeker_turns=len(tail.split("\n")) if tail else 0,
        trailing_seeker_words=_words(tail),
        n_past_sessions=len(past),
        past_turns=len(past_turns),
        past_words=sum(_words(t.content) for t in past_turns),
        past_seeker_words=sum(_words(t.content) for t in past_turns if t.role == "seeker"),
        days_since_prev_session=(cur - prev).days if prev else None,
        days_since_first_session=(cur - first).days if first else None,
        surface_cues=surface_cues(tail),
    )


# -------------------------------------------------------------------- families

def session_family(owner_id: str, session: Session) -> str:
    """Lineage family.  ESConv seeds keep their ESConv dialogue id; generated
    EvoEmo sessions belong to their owner's persona family."""
    sid = session.session_id
    if sid.startswith("esc") and sid[3:].isdigit():
        return f"esconv:esconv_{int(sid[3:]):04d}"
    return f"evoemo_owner:{owner_id}"


def source_kind(session: Session) -> str:
    sid = session.session_id
    return "esconv_seed" if sid.startswith("esc") and sid[3:].isdigit() else "evoemo_generated"


def owner_family_groups(users: Sequence[MemorySourceUser]) -> tuple[tuple[str, ...], ...]:
    """Union owners connected by a shared family id or an identical transcript."""
    parent = {u.owner_id: u.owner_id for u in users}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    holders: dict[str, set[str]] = defaultdict(set)
    for u in users:
        for s in u.sessions:
            holders["family:" + session_family(u.owner_id, s)].add(u.owner_id)
            holders["transcript:" + session_sha256(s)].add(u.owner_id)
    for owners in holders.values():
        first, *rest = sorted(owners)
        for o in rest:
            union(first, o)
    groups: dict[str, list[str]] = defaultdict(list)
    for u in users:
        groups[find(u.owner_id)].append(u.owner_id)
    return tuple(sorted((tuple(sorted(g, key=_owner_sort)) for g in groups.values()),
                        key=lambda g: _owner_sort(g[0])))


def shared_families(users: Sequence[MemorySourceUser]) -> list[dict]:
    holders: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for u in users:
        for s in u.sessions:
            holders[(session_family(u.owner_id, s), session_sha256(s))].append(
                dict(owner_id=u.owner_id, session_id=s.session_id,
                     chronological_rank=s.chronological_rank))
    out = []
    for (fam, sha), rows in sorted(holders.items()):
        if len({r["owner_id"] for r in rows}) > 1:
            out.append(dict(family_id=fam, transcript_sha256=sha, holders=rows))
    return out


def _owner_sort(owner_id: str) -> tuple:
    m = re.fullmatch(r"p(\d+)", owner_id)
    return (0, int(m.group(1)), owner_id) if m else (1, 0, owner_id)


# ----------------------------------------------------------------------- folds

def _first_fit(units: Sequence[tuple[str, ...]], fold_ids: Sequence[int],
               size: int) -> dict[str, int]:
    load = {f: 0 for f in fold_ids}
    out: dict[str, int] = {}
    for unit in units:
        for f in fold_ids:
            if load[f] + len(unit) <= size:
                for o in unit:
                    out[o] = f
                load[f] += len(unit)
                break
        else:
            raise ValueError(f"family group {unit} does not fit any fold of size {size}")
    return out


def _units(groups: Sequence[tuple[str, ...]], members: Iterable[str],
           salt: str) -> list[tuple[str, ...]]:
    members = set(members)
    units = []
    for g in groups:
        inside = tuple(o for o in g if o in members)
        if inside and len(inside) != len(g):
            raise ValueError(f"family group {g} straddles a fixed partition boundary")
        if inside:
            units.append(inside)
    return sorted(units, key=lambda u: min(sha256_text(salt + o) for o in u))


def assign_folds(users: Sequence[MemorySourceUser]) -> dict:
    owners = sorted((u.owner_id for u in users), key=_owner_sort)
    if len(owners) != N_FOLDS * FOLD_SIZE or len(set(owners)) != len(owners):
        raise ValueError("V3.1 folds require exactly 18 unique owners")
    if not set(FIXED_HELDOUT_OWNERS) <= set(owners):
        raise ValueError("fixed held-out owners missing")
    groups = owner_family_groups(users)
    rest = [o for o in owners if o not in FIXED_HELDOUT_OWNERS]
    _units(groups, FIXED_HELDOUT_OWNERS, FOLD_SALT)  # raises if a family straddles fold 6
    fold_of = {o: FIXED_HELDOUT_FOLD for o in FIXED_HELDOUT_OWNERS}
    fold_of.update(_first_fit(_units(groups, rest, FOLD_SALT),
                              [f for f in range(1, N_FOLDS + 1) if f != FIXED_HELDOUT_FOLD],
                              FOLD_SIZE))
    naive_order = sorted(rest, key=fold_key)
    naive = {o: 1 + i // FOLD_SIZE for i, o in enumerate(naive_order)}
    naive.update({o: FIXED_HELDOUT_FOLD for o in FIXED_HELDOUT_OWNERS})
    moved = sorted((o for o in owners if naive[o] != fold_of[o]), key=_owner_sort)

    # Candidate G1 owner partition (V3.1 §6.1; final combination is B10's manifest).
    seed = set(ORIGINAL_DEV_OWNERS) | {o for o, f in fold_of.items() if f == G1_EXTRA_FOLD}
    g1_train = {o for g in groups if seed & set(g) for o in g}
    if g1_train & set(FIXED_HELDOUT_OWNERS):
        raise ValueError("G1 training closure reaches fixed held-out owners")
    g1_rest = [o for o in owners if o not in g1_train and o not in FIXED_HELDOUT_OWNERS]
    n_eval_folds = (len(g1_rest) + FOLD_SIZE - 1) // FOLD_SIZE
    g1_eval = {o: 4 for o in FIXED_HELDOUT_OWNERS}  # last G0/G1×PM fold = historical test
    g1_eval.update(_first_fit(_units(groups, g1_rest, G1_EVAL_SALT),
                              list(range(1, n_eval_folds + 1)), FOLD_SIZE))
    eval_owners = sorted(g1_eval, key=_owner_sort)
    return dict(
        schema=FOLDS_SCHEMA,
        protocol=CENSUS_PROTOCOL,
        rule=("owner/family groups first; fold 6 fixed to historical test owners; remaining "
              "groups ordered by min sha256('pmrl1v3|fold|'+owner) and first-fit into folds "
              "1-5 of 3 owners (identical to plain hash chunking when every group is a singleton)"),
        n_folds=N_FOLDS,
        fold_of_owner={o: fold_of[o] for o in owners},
        folds={str(f): sorted((o for o in owners if fold_of[o] == f), key=_owner_sort)
               for f in range(1, N_FOLDS + 1)},
        family_groups=[list(g) for g in groups if len(g) > 1],
        naive_hash_chunk_fold_of_owner={o: naive[o] for o in owners},
        owners_moved_by_family_closure=moved,
        historical_rl1_split={o: ("test" if o in FIXED_HELDOUT_OWNERS else
                                  "dev" if o in ORIGINAL_DEV_OWNERS else "train") for o in owners},
        g1_partition_candidate=dict(
            status="CANDIDATE_FOR_B10_MANIFEST_NOT_FROZEN",
            rule=("G1-train = family closure of historical dev owners ∪ fold 5; remaining owners "
                  "in owner/family-first folds of 3, historical test owners kept as last fold"),
            g1_train_owners=sorted(g1_train, key=_owner_sort),
            n_g1_train_owners=len(g1_train),
            matches_plan_size_6=len(g1_train) == 6,
            eval_fold_of_owner={o: g1_eval[o] for o in eval_owners},
            n_eval_owners=len(eval_owners),
            matches_plan_size_12=len(eval_owners) == 12,
        ),
    )


# ---------------------------------------------------------------------- census

@dataclass(frozen=True)
class CensusResult:
    rows: tuple[dict, ...]
    folds: dict
    summary: dict


def build_rows(users: Sequence[MemorySourceUser], folds: Mapping) -> list[dict]:
    fold_of = folds["fold_of_owner"]
    g1 = folds["g1_partition_candidate"]
    rows = []
    for user in sorted(users, key=lambda u: _owner_sort(u.owner_id)):
        sessions = sorted(user.sessions, key=lambda s: s.chronological_rank)
        ranks = [s.chronological_rank for s in sessions]
        if ranks != list(range(len(sessions))):
            raise ValueError(f"{user.owner_id}: chronological ranks are not 0..n-1")
        for session in sessions:
            if session.chronological_rank < 1:
                continue
            past = strictly_past_sessions(user, session.chronological_rank)
            past_identity = digest([[s.session_id, session_sha256(s)] for s in past])
            for cut in legal_cut_positions(session):
                turns = prefix_turns(session, cut)
                psha = digest(turn_payload(turns))
                pid = prefix_id_for(user.owner_id, session.session_id, cut, psha)
                n = len(session.turns)
                rows.append(dict(
                    schema=ROW_SCHEMA,
                    prefix_id=pid,
                    dataset=DATASET,
                    owner_id=user.owner_id,
                    session_id=session.session_id,
                    cutoff_rank=session.chronological_rank,
                    cut_turn=cut,
                    cut_turn_source_idx=session.turns[cut].idx,
                    timestamp=session.timestamp,
                    prefix_sha256=psha,
                    past_history_sha256=past_identity,
                    visible=visible_features(user, session, cut),
                    eval_only=dict(
                        session_total_turns=n,
                        turns_after_cut=n - cut - 1,
                        cut_position_fraction=round((cut + 1) / n, 6),
                        source_kind=source_kind(session),
                        family_id=session_family(user.owner_id, session),
                        session_sha256=session_sha256(session),
                        n_legal_cuts_in_session=len(legal_cut_positions(session)),
                    ),
                    assignment=dict(
                        fold=fold_of[user.owner_id],
                        g1_role_candidate=("g1_train" if user.owner_id in g1["g1_train_owners"]
                                           else "g1_eval"),
                        g1_eval_fold_candidate=g1["eval_fold_of_owner"].get(user.owner_id),
                        historical_rl1_split=folds["historical_rl1_split"][user.owner_id],
                    ),
                    sampling=dict(
                        sample_key=sample_key(pid),
                        natural_weight=1.0,
                        selection="natural_census_all_legal_cuts",
                    ),
                ))
    rows.sort(key=lambda r: (_owner_sort(r["owner_id"]), r["cutoff_rank"], r["cut_turn"]))
    return rows


def materialize_prefix(row: Mapping, users_by_owner: Mapping[str, MemorySourceUser]) -> tuple:
    """Rebuild the visible prefix turns for a census row and verify its identity."""
    user = users_by_owner[row["owner_id"]]
    session = user.session_by_id(row["session_id"])
    if session.chronological_rank != row["cutoff_rank"]:
        raise ValueError("cutoff rank mismatch")
    turns = prefix_turns(session, row["cut_turn"])
    if digest(turn_payload(turns)) != row["prefix_sha256"]:
        raise ValueError("prefix content identity mismatch")
    if prefix_id_for(row["owner_id"], row["session_id"], row["cut_turn"],
                     row["prefix_sha256"]) != row["prefix_id"]:
        raise ValueError("prefix id mismatch")
    return turns


def audit_rows(rows: Sequence[Mapping], users: Sequence[MemorySourceUser]) -> dict:
    """Mechanical leakage/legality audit over the full census."""
    by_owner = {u.owner_id: u for u in users}
    seen: set[str] = set()
    failures: list[str] = []
    for r in rows:
        user = by_owner[r["owner_id"]]
        try:
            turns = materialize_prefix(r, by_owner)
        except Exception as exc:  # pragma: no cover - reported, never silenced
            failures.append(f"{r['prefix_id']}: {exc}")
            continue
        session = user.session_by_id(r["session_id"])
        if turns[-1].role != "seeker" or session.turns[r["cut_turn"] + 1].role != "supporter":
            failures.append(f"{r['prefix_id']}: cut is not seeker->supporter")
        past = strictly_past_sessions(user, r["cutoff_rank"])
        if any(s.chronological_rank >= r["cutoff_rank"] for s in past):
            failures.append(f"{r['prefix_id']}: non-past history")
        if r["visible"]["n_past_sessions"] != r["cutoff_rank"]:
            failures.append(f"{r['prefix_id']}: past session count mismatch")
        if visible_features(user, session, r["cut_turn"]) != r["visible"]:
            failures.append(f"{r['prefix_id']}: visible features not reproducible")
        if r["prefix_id"] in seen:
            failures.append(f"{r['prefix_id']}: duplicate prefix id")
        seen.add(r["prefix_id"])
    return dict(rows_checked=len(rows), failures=failures, passed=not failures)


def _quantiles(values: Sequence[float]) -> dict:
    v = sorted(values)
    if not v:
        return {}
    pick = lambda q: v[min(len(v) - 1, int(q * (len(v) - 1) + 0.5))]  # noqa: E731
    return dict(min=v[0], p25=pick(.25), p50=pick(.5), p75=pick(.75), p90=pick(.9), max=v[-1],
                mean=round(sum(v) / len(v), 3))


def _rank_bucket(rank: int) -> str:
    return "1" if rank == 1 else "2-4" if rank <= 4 else "5-9" if rank <= 9 else "10+"


def summarize(rows: Sequence[Mapping], users: Sequence[MemorySourceUser], folds: Mapping) -> dict:
    owners = sorted((u.owner_id for u in users), key=_owner_sort)
    per_owner = {}
    for u in sorted(users, key=lambda x: _owner_sort(x.owner_id)):
        rs = [r for r in rows if r["owner_id"] == u.owner_id]
        per_owner[u.owner_id] = dict(
            sessions=len(u.sessions),
            sessions_rank_ge1=sum(s.chronological_rank >= 1 for s in u.sessions),
            sessions_with_legal_cut=len({r["session_id"] for r in rs}),
            legal_cuts=len(rs),
            fold=folds["fold_of_owner"][u.owner_id],
            historical_rl1_split=folds["historical_rl1_split"][u.owner_id],
            es_memeval_targets=dict(
                qa=sum(len(g.items) for g in u.question_groups),
                summary=len(u.summaries), dialogue_generation=len(u.subsequent_topics)),
        )
    n = len(rows)
    owner_n = Counter(r["owner_id"] for r in rows)
    cue_names = list(_CUES)
    cues_natural = {c: round(sum(r["visible"]["surface_cues"][c] for r in rows) / n, 4)
                    for c in cue_names}
    cues_owner_balanced = {c: round(sum(
        sum(r["visible"]["surface_cues"][c] for r in rows if r["owner_id"] == o) / owner_n[o]
        for o in owners if owner_n[o]) / sum(1 for o in owners if owner_n[o]), 4) for c in cue_names}
    session_cuts = Counter((r["owner_id"], r["session_id"]) for r in rows)
    return dict(
        protocol=CENSUS_PROTOCOL,
        dataset=DATASET,
        distribution="natural: every legal seeker->supporter cut in sessions with rank>=1, weight 1",
        totals=dict(
            owners=len(users),
            sessions=sum(len(u.sessions) for u in users),
            sessions_rank_ge1=sum(s.chronological_rank >= 1 for u in users for s in u.sessions),
            sessions_with_legal_cut=len(session_cuts),
            legal_cuts=n,
            cuts_in_esconv_seed_sessions=sum(r["eval_only"]["source_kind"] == "esconv_seed"
                                             for r in rows),
            cuts_in_evoemo_generated_sessions=sum(
                r["eval_only"]["source_kind"] == "evoemo_generated" for r in rows),
            max_two_per_session_capacity=sum(min(2, c) for c in session_cuts.values()),
        ),
        per_owner=per_owner,
        per_fold={str(f): dict(owners=folds["folds"][str(f)],
                               legal_cuts=sum(r["assignment"]["fold"] == f for r in rows))
                  for f in range(1, N_FOLDS + 1)},
        cutoff_rank_buckets=dict(Counter(_rank_bucket(r["cutoff_rank"]) for r in rows)),
        cuts_per_session=_quantiles(list(session_cuts.values())),
        prefix_turns=_quantiles([r["visible"]["n_prefix_turns"] for r in rows]),
        past_sessions=_quantiles([r["visible"]["n_past_sessions"] for r in rows]),
        past_words=_quantiles([r["visible"]["past_words"] for r in rows]),
        trailing_seeker_words=_quantiles([r["visible"]["trailing_seeker_words"] for r in rows]),
        days_since_prev_session=_quantiles([r["visible"]["days_since_prev_session"] for r in rows
                                            if r["visible"]["days_since_prev_session"] is not None]),
        surface_cue_rate_natural=cues_natural,
        surface_cue_rate_owner_balanced=cues_owner_balanced,
        surface_cue_note=("regex surface cues on the trailing seeker block; outcome-blind text "
                          "descriptors, NOT need labels or need rates"),
        oversampling_rule=("B1 may oversample need strata for training (target history+both 50%, "
                           "method 20%, none 30%, max 2 cuts/session, order by sample_key); every "
                           "selected row must keep selection_reason and natural_weight so natural "
                           "evaluation is reported separately and never replaced by the training mix"),
    )


def build_census(users: Sequence[MemorySourceUser]) -> CensusResult:
    folds = assign_folds(users)
    rows = build_rows(users, folds)
    summary = summarize(rows, users, folds)
    summary["shared_families"] = shared_families(users)
    summary["audit"] = audit_rows(rows, users)
    return CensusResult(tuple(rows), folds, summary)


def load_users(path: Path) -> tuple[MemorySourceUser, ...]:
    return load_sanitized_runtime_users(path)


def date_or_none(text: str | None) -> date | None:
    return date.fromisoformat(text) if text else None
