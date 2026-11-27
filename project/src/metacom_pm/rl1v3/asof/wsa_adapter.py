"""Adapter: WS-A as-of sidecar snapshots (``pmrl1v3-asof-sidecar-1``) -> WS-B exchange cuts, plus
WS-B's own RAW-frontier oracle.  Read-only; WS-A code is never imported or executed here.

The sidecar materialises one view per (owner, cutoff, prefix context).  It carries no second writer
horizon for the same prefix, so X5a (horizon invariance) is not testable from the files and is
reported as ``not_testable_single_horizon``; X5b/X5c (no rewritten past, append-only) are tested
across the cutoffs of each owner.  The RAW oracle requires the readable MS_RAW records to be
exactly the registry's complete strictly-past sessions, each quoting every non-empty turn.
"""
from __future__ import annotations

from ..io import object_sha256
from . import check as CK

PROTOCOL = "pmrl1v3-wsb-wsa-sidecar-adapter-v1"
HEAD = {"MS_RAW": "MS", "MS_SUM": "MS", "ME": "ME", "MP": "MP"}


def find_prefix(registry, census_rows, as_of: dict):
    """The legal B0 prefix whose runtime context hash equals the sidecar's ``prefix_context_sha256``."""
    for c in census_rows:
        if c["owner_id"] == as_of["owner_id"] and c["cutoff_rank"] == as_of["cutoff_rank"]:
            p = registry.prefix(c["owner_id"], c["session_id"], c["cut_turn"])
            if p.runtime_sha256 == as_of["prefix_context_sha256"]:
                return p
    return None


def to_cut(snap: dict, registry, prefix) -> dict:
    recs = []
    for v in snap["views"]:
        r = v["record"]
        recs.append(dict(
            record_id=r["record_id"], head=HEAD[r["kind"]], kind=r["kind"], owner_id=r["owner_id"],
            content_sha256=object_sha256([r["text"], [(s["session_id"], s["turn_index"], s["start_char"], s["end_char"])
                                                      for s in r["source_refs"]]]),
            source_refs=[dict(owner_id=s["owner_id"], session_id=s["session_id"], source_rank=s["source_rank"],
                              turn_ordinal=s["turn_index"], start_char=s["start_char"], end_char=s["end_char"],
                              exact_quote=s["exact_quote"]) for s in r["source_refs"]],
            known_rank=r["known_at"]["session_rank"], ready_rank=r["ready_at"]["session_rank"],
            stage=r.get("stage"), event_time=r.get("event_time"), event_time_refs=r.get("event_time_refs"),
            supersedes=[r["target_id"]] if r.get("target_id") else [], disposition=v["disposition"],
            subject=r.get("subject")))
    frontier = []
    for s in snap["source_frontier"]["sources"]:
        e = registry.entry(s["owner_id"], s["session_id"])
        frontier.append(dict(source_id=e.source_id, session_id=s["session_id"], rank=s["chronological_rank"],
                             transcript_sha256=s["transcript_sha256"], ready_rank=s["ready_at"]["session_rank"]))
    return dict(owner_id=prefix.owner_id, session_id=prefix.session_id, cut_turn=prefix.cut_turn,
                prefix_id=prefix.prefix_id, cutoff_rank=prefix.cutoff_rank, horizon_rank=None,
                source_frontier=frontier, snapshot_sha256=CK.snapshot_sha256(recs), records=recs,
                wsa_snapshot_sha=snap["snapshot_sha"], wsa_writer=snap["writer_identity"])


def raw_oracle(cut: dict, registry, prefix) -> list[str]:
    """Readable RAW = exactly the complete strictly-past sessions; every non-empty turn quoted exactly."""
    p = []
    _, history = registry.context(prefix)
    legal = {s.session_id: s for s in history if s.complete}
    raws = [r for r in cut["records"] if r["kind"] == "MS_RAW" and r["disposition"] == "raw_available"]
    got = {}
    for r in raws:
        sids = {s["session_id"] for s in r["source_refs"]}
        if len(sids) != 1:
            p.append(f"R1_raw_spans_multiple_sessions:{r['record_id'][:20]}")
            continue
        got.setdefault(sids.pop(), []).append(r)
    if set(got) != set(legal):
        p.append(f"R2_raw_sessions_differ(missing={len(set(legal) - set(got))},extra={len(set(got) - set(legal))})")
    for sid, rs in got.items():
        if len(rs) != 1:
            p.append(f"R3_duplicate_raw:{sid}")
        s = legal.get(sid)
        if s is None:
            continue
        quoted = {(x["turn_ordinal"], x["exact_quote"]) for x in rs[0]["source_refs"]}
        want = {(i, t.text) for i, t in enumerate(s.turns) if t.text}
        if quoted != want:
            p.append(f"R4_raw_not_complete_or_inexact:{sid}")
    readable_other = [r for r in cut["records"] if r["kind"] != "MS_RAW" and r["disposition"] not in
                      ("quarantine", "unusable", "pending_review")]
    if readable_other:
        p.append(f"R5_unreviewed_semantic_records_readable:{len(readable_other)}")
    return p


def check_sidecar(snaps: list[dict], registry, census_rows) -> dict:
    rows, cuts = [], []
    for snap in snaps:
        prefix = find_prefix(registry, census_rows, snap["as_of"])
        if prefix is None:
            rows.append(dict(owner_id=snap["as_of"]["owner_id"], cutoff_rank=snap["as_of"]["cutoff_rank"],
                             problems=["prefix_context_not_a_legal_B0_prefix"]))
            continue
        cut = to_cut(snap, registry, prefix)
        probs = [x for x in CK.check_cutoff(cut, registry, prefix) if not x.startswith("X6_snapshot_sha")]
        probs += raw_oracle(cut, registry, prefix)
        rows.append(dict(owner_id=prefix.owner_id, cutoff_rank=prefix.cutoff_rank, prefix_id=prefix.prefix_id,
                         records=len(cut["records"]),
                         kinds={k: sum(r["kind"] == k for r in cut["records"]) for k in HEAD},
                         readable={k: sum(r["kind"] == k and r["disposition"] == "raw_available" for r in cut["records"])
                                   for k in HEAD},
                         problems=probs))
        cuts.append(cut)
    ext = CK.prefix_extension(cuts)
    return dict(protocol=PROTOCOL, snapshots=len(snaps), owners=sorted({r["owner_id"] for r in rows}),
                cutoffs_passed=sum(not r["problems"] for r in rows), x5a="not_testable_single_horizon",
                prefix_extension_problems=ext, passed=all(not r["problems"] for r in rows) and not ext,
                rows=rows, scope="mechanical: frontier, spans, owner, time fields, RAW completeness, append-only; "
                                 "semantic (subject/stage/validity) not verified")
