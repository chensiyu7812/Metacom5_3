"""Construction-domain prefix/as-of adapters. No future suffix enters PrefixSpec.

This is a development census, not a claim of unexposed test data. Exact shared
transcripts are reported for source-family adjudication before dataset freeze.
"""
from collections import defaultdict
from dataclasses import asdict
from hashlib import sha256

from metacom_pm.paper1.contracts import Head, TaskType
from metacom_pm.paper1.data.memory_source import Target
from metacom_pm.paper1.multi_view_memory.candidate_adapter import materialize_multi_view_candidates
from .schema import PrefixSpec, PublicTurn, Resource, digest


def stable_hash(text: str) -> str:
    return sha256(text.encode()).hexdigest()


def owner_split(users) -> dict[str, str]:
    owners = sorted((u.owner_id for u in users), key=lambda s: stable_hash("pmseq-v2-owner|" + s))
    if len(owners) != 18 or len(set(owners)) != 18:
        raise ValueError("the declared 12/3/3 split requires 18 unique owners")
    return {owner: "train" if i < 12 else "dev" if i < 15 else "test"
            for i, owner in enumerate(owners)}


def build_prefixes(users) -> tuple[tuple[PrefixSpec, ...], dict]:
    split = owner_split(users)
    all_prefixes, selected = [], []
    source_groups = defaultdict(list)
    for user in users:
        eligible = []
        for session in user.sessions:
            source_groups[digest([(t.role, t.content) for t in session.turns])].append(
                dict(owner=user.owner_id, split=split[user.owner_id], session=session.session_id,
                     rank=session.chronological_rank))
            if session.chronological_rank < 1:
                continue
            cuts = [i for i, t in enumerate(session.turns[:-1]) if
                    t.role == "seeker" and session.turns[i + 1].role == "supporter"]
            if not cuts:
                continue
            cut = min(cuts, key=lambda i: stable_hash(
                f"pm-rl1-census-prefix-v1|{user.owner_id}|{session.session_id}|{i}"))
            prefix = PrefixSpec(user.owner_id, session.session_id, session.chronological_rank,
                                cut, session.timestamp, split[user.owner_id],
                                tuple(PublicTurn(t.role, t.content) for t in session.turns[:cut + 1]))
            eligible.append(prefix)
        all_prefixes.extend(eligible)
        selected.extend(sorted(eligible, key=lambda p: stable_hash(
            "pm-rl1-census-session-v1|" + p.owner_id + "|" + p.session_id))[
                :16 if split[user.owner_id] == "test" else 8])
    shared = [rows for rows in source_groups.values() if len({r["owner"] for r in rows}) > 1]
    return tuple(selected), dict(status="DEVELOPMENT_CENSUS_NOT_FROZEN", owner_split=split,
        eligible_sessions=len(all_prefixes), selected_by_split={s: sum(p.split == s for p in selected)
        for s in ("train", "dev", "test")}, shared_transcript_groups=shared,
        pending=["fact-family grouping including descendants of shared sessions",
                 "historical exposure manifest and held-out interpretation",
                 "capacity census with RS before resource-budget freeze"])


def as_of_memory(prefix: PrefixSpec, *, user, units, token_counter):
    if user.owner_id != prefix.owner_id:
        raise ValueError("wrong source owner")
    target = Target(target_id=prefix.identity, task_type=TaskType.DIALOGUE_GENERATION,
                    owner_id=prefix.owner_id, primary_group_key=prefix.session_id,
                    cutoff_rank=prefix.cutoff_rank, visible_query_text=prefix.query)
    return materialize_multi_view_candidates(tuple(units), user=user, target=target,
                                             token_counter=token_counter)


def ranked_memory(prefix: PrefixSpec, candidates, vectors, query_vector):
    from metacom_pm.paper1.execution.packing import rank_candidates
    result = {}
    for head in (Head.MP, Head.MS, Head.ME):
        ranked = rank_candidates(query_vector=query_vector, candidates=candidates[head],
                                 candidate_vectors=vectors)
        resources = []
        for row in ranked:
            c = row.candidate
            rank = int(c.raw_descriptors["session_chronological_rank"])
            age = prefix.cutoff_rank - rank
            resources.append(Resource(c.candidate_id, head.value, c.content, row.similarity,
                c.token_count, c.lineage.owner_id, rank, c.lineage.observed_at,
                "previous_session" if age == 1 else "2_to_4_sessions" if age <= 4 else "5_plus_sessions",
                c.lineage.source_record_ids))
        result[head.value] = tuple(resources)
    return result
