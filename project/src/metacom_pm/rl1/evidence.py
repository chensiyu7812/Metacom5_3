"""Construction/evaluator-only full legal evidence; never an actor observation."""
from dataclasses import asdict

from .schema import PrefixSpec, PublicTurn, digest


def prefix_from_dict(raw):
    return PrefixSpec(**{**raw, "turns": tuple(PublicTurn(**t) for t in raw["turns"])})


def legal_evidence(prefix, user):
    if prefix.owner_id != user.owner_id:
        raise ValueError("wrong evidence owner")
    current = user.session_by_id(prefix.session_id)
    if (current.chronological_rank != prefix.cutoff_rank or current.timestamp != prefix.timestamp
            or tuple(PublicTurn(t.role, t.content) for t in current.turns[:prefix.cut_after_turn_index + 1]) != prefix.turns
            or prefix.cut_after_turn_index + 1 >= len(current.turns)
            or current.turns[prefix.cut_after_turn_index + 1].role != "supporter"):
        raise ValueError("prefix is not the declared source cut")
    past, mapping = [], []
    for session in sorted(user.sessions, key=lambda s: s.chronological_rank):
        if session.chronological_rank >= prefix.cutoff_rank:
            continue
        sid = f"H{len(past) + 1:03d}"
        past.append(dict(id=sid, date=session.timestamp,
            turns=[dict(id=f"{sid}:T{i:03d}", role=t.role, text=t.content) for i, t in enumerate(session.turns)]))
        mapping.append(dict(blind_id=sid, session=session.session_id, rank=session.chronological_rank))
    evidence = dict(current_date=prefix.timestamp,
        current_prefix=[dict(id=f"C:T{i:03d}", role=t.role, text=t.content) for i, t in enumerate(prefix.turns)],
        legal_past_sessions=past)
    return evidence, dict(prefix=asdict(prefix), prefix_identity=prefix.identity, source_map=mapping,
                          evidence_identity=digest(evidence))


def evidence_turns(evidence):
    turns = list(evidence["current_prefix"])
    for session in evidence["legal_past_sessions"]:
        turns.extend(session["turns"])
    result = {t["id"]: t for t in turns}
    if len(result) != len(turns):
        raise ValueError("duplicate evidence ID")
    return result
