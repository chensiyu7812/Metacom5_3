"""Independent WS-B checker for as-of snapshots (``pmrl1v3-asof-exchange-v0.1``).  CPU, mechanical only.

Exchange format (what WS-A's chronological writer hands to B, one file per writer identity)::

  {"protocol": "pmrl1v3-asof-exchange-v0.1", "writer_identity": str,
   "cutoffs": [{"owner_id", "session_id", "cut_turn", "prefix_id", "cutoff_rank",
                "source_frontier": [{"source_id","session_id","rank","transcript_sha256","ready_rank"}],
                "horizon_rank", "snapshot_sha256", "batch_snapshot_sha256"?, "stream_snapshot_sha256"?,
                "records": [{"record_id","head","owner_id","content_sha256",
                             "source_refs": [{"owner_id","session_id","source_rank","turn_ordinal",
                                              "start_char","end_char","exact_quote"}],
                             "known_rank", "ready_rank", "stage"?, "event_time"?, "event_time_refs"?,
                             "supersedes"?: [record_id], "invalidated_by"?: record_id}]}]}

Checks (all fail closed; semantic correctness - subject, stage, validity - is never inferred here):
  X1 frontier equals the registry's legal frontier for the prefix (nothing more, nothing less)
  X2 every memory record: owner = prefix owner; each span verifies against the registry source,
     comes from a strictly-past completed session (rank < cutoff, ready <= cutoff), never the current one
  X3 known_rank >= max source rank of its spans; ready_rank >= known_rank; ready_rank <= cutoff
  X4 event_time only with its own evidence spans; stage in the C0 stage set or unknown
  X5 prefix extension (``horizon_rank`` = 1 + the last session rank the writer consumed):
     X5a the same prefix materialised at different horizons gives the identical snapshot
         (appending later sessions never changes an earlier view);
     X5b for cutoffs c1 < c2 of one owner, every c2 record ready by c1 is in c1 with the same content
         (no rewritten past);
     X5c every c1 record survives in c2 unchanged or is superseded by a c2 record ready after c1
         (append-only)
  X6 stream/batch snapshot hashes agree when both are given; snapshot_sha256 reproduces from records
  X7 RS records are external (no owner), and their family is outside the prefix family closure
"""
from __future__ import annotations

from collections import defaultdict

from ..io import object_sha256

PROTOCOL = "pmrl1v3-asof-exchange-v0.1"
STAGES = ("suggested", "intended", "attempted", "completed", "outcome_reported", "rejected", "unknown", None)


def snapshot_sha256(records) -> str:
    return object_sha256(sorted((r["head"], r["record_id"], r["content_sha256"]) for r in records))


def _ready(r) -> int:
    return int(r["ready_rank"])


def check_cutoff(cut: dict, registry, prefix) -> list[str]:
    from .binding import frontier_for
    p = []
    legal = [dict(source_id=e.source_id, session_id=e.session_id, rank=e.rank,
                  transcript_sha256=e.transcript_sha256, ready_rank=e.ready_rank) for e in frontier_for(registry, prefix)]
    if [{k: f[k] for k in ("source_id", "session_id", "rank", "transcript_sha256", "ready_rank")}
            for f in cut["source_frontier"]] != legal:
        p.append("X1_frontier_not_exact")
    c = prefix.cutoff_rank
    for r in cut["records"]:
        rid = r["record_id"][:24]
        if r["head"] == "RS":
            if r.get("owner_id"):
                p.append(f"X7_rs_has_owner:{rid}")
            fam = r.get("family_id")
            if fam and fam in set(prefix.ancestor_family_ids):
                p.append(f"X7_rs_family_overlap:{rid}")
            continue
        if r.get("owner_id") != prefix.owner_id:
            p.append(f"X2_owner:{rid}")
        if not r.get("source_refs"):
            p.append(f"X2_no_source:{rid}")
        ranks = []
        for s in r.get("source_refs", ()):
            if s["owner_id"] != prefix.owner_id or s["session_id"] == prefix.session_id:
                p.append(f"X2_span_owner_or_current:{rid}")
                continue
            e = registry.entry(s["owner_id"], s["session_id"])
            ranks.append(e.source.chronological_rank)
            if e.source.chronological_rank >= c or e.ready_at.session_rank > c or not e.source.complete:
                p.append(f"X2_span_future:{rid}")
            try:
                turn = e.source.turns[s["turn_ordinal"]]
                if turn.text[s["start_char"]:s["end_char"]] != s["exact_quote"]:
                    p.append(f"X2_span_text:{rid}")
            except IndexError:
                p.append(f"X2_span_turn:{rid}")
        if ranks and int(r["known_rank"]) < max(ranks):
            p.append(f"X3_known_before_report:{rid}")
        if _ready(r) < int(r["known_rank"]) or _ready(r) > c:
            p.append(f"X3_ready:{rid}")
        if r.get("event_time") is not None and not r.get("event_time_refs"):
            p.append(f"X4_event_time_without_evidence:{rid}")
        if r.get("stage") not in STAGES:
            p.append(f"X4_stage:{rid}")
    if cut.get("snapshot_sha256") != snapshot_sha256(cut["records"]):
        p.append("X6_snapshot_sha_not_reproduced")
    b, s = cut.get("batch_snapshot_sha256"), cut.get("stream_snapshot_sha256")
    if b is not None and s is not None and b != s:
        p.append("X6_stream_batch_differ")
    return p


def prefix_extension(cuts: list[dict]) -> list[str]:
    """X5a-c over all cutoffs of each owner."""
    p = []
    by_prefix = defaultdict(list)
    for c in cuts:
        by_prefix[c["prefix_id"]].append(c)
    for pid, cs in by_prefix.items():                                     # X5a
        if len({c["snapshot_sha256"] for c in cs}) > 1:
            hz = sorted(c.get("horizon_rank") for c in cs)
            p.append(f"X5a_horizon_changes_snapshot:{cs[0]['owner_id']}:{cs[0]['cutoff_rank']}:{pid[:12]}:{hz}")
    final = {}
    for pid, cs in by_prefix.items():                                     # one view per prefix (largest horizon)
        final[pid] = max(cs, key=lambda c: c.get("horizon_rank") or 0)
    by_owner = defaultdict(list)
    for c in final.values():
        by_owner[c["owner_id"]].append(c)
    mem = lambda c: [r for r in c["records"] if r["head"] != "RS"]
    for owner, cs in by_owner.items():
        cs = sorted(cs, key=lambda c: (c["cutoff_rank"], c["cut_turn"]))
        for i, c1 in enumerate(cs):
            r1 = {(r["record_id"], r["content_sha256"]) for r in mem(c1)}
            for c2 in cs[i + 1:]:
                m2 = mem(c2)
                if c2["cutoff_rank"] == c1["cutoff_rank"]:
                    if {(r["record_id"], r["content_sha256"]) for r in m2} != r1:
                        p.append(f"X5_same_cutoff_differs:{owner}:{c1['cutoff_rank']}")
                    continue
                early = {(r["record_id"], r["content_sha256"]) for r in m2 if _ready(r) <= c1["cutoff_rank"]}
                if not early <= r1:                                       # X5b
                    p.append(f"X5b_past_rewritten:{owner}:{c1['cutoff_rank']}->{c2['cutoff_rank']}")
                ids2 = {r["record_id"]: r["content_sha256"] for r in m2}
                for rid, h in r1:                                         # X5c
                    if ids2.get(rid) == h:
                        continue
                    if not any(rid in (r.get("supersedes") or ()) and _ready(r) > c1["cutoff_rank"] for r in m2):
                        p.append(f"X5c_record_vanished:{owner}:{c1['cutoff_rank']}->{c2['cutoff_rank']}")
                        break
    return sorted(set(p))


def run(exchange: dict, registry) -> dict:
    if exchange.get("protocol") != PROTOCOL:
        raise ValueError("unsupported exchange protocol")
    rows, ok = [], 0
    for cut in exchange["cutoffs"]:
        prefix = registry.prefix(cut["owner_id"], cut["session_id"], cut["cut_turn"])
        probs = ["prefix_id_mismatch"] if prefix.prefix_id != cut["prefix_id"] else check_cutoff(cut, registry, prefix)
        ok += not probs
        rows.append(dict(prefix_id=cut["prefix_id"], owner_id=cut["owner_id"], cutoff_rank=cut["cutoff_rank"],
                         records=len(cut["records"]), problems=probs))
    ext = prefix_extension(exchange["cutoffs"])
    return dict(protocol=PROTOCOL, writer_identity=exchange["writer_identity"], cutoffs=len(rows),
                cutoffs_passed=ok, prefix_extension_problems=ext,
                passed=ok == len(rows) and not ext, rows=rows,
                scope="mechanical source/time/owner/extension checks only; semantics not verified")


# ------------------------------------------------------- B-side controls on real bank-v0 data

def _record_entry(r, *, head, owner, refs, known, ready, content, stage=None, supersedes=()):
    return dict(record_id=r, head=head, owner_id=owner, content_sha256=content, source_refs=refs,
                known_rank=known, ready_rank=ready, stage=stage, supersedes=list(supersedes))


def _refs_of_record(rec) -> list[dict]:
    return [dict(owner_id=s.owner_id, session_id=s.session_id, source_rank=s.source_rank, turn_ordinal=s.turn_index,
                 start_char=s.start_char, end_char=s.end_char, exact_quote=s.exact_quote) for s in rec.source_refs]


def _unit_refs(unit, registry) -> list[dict]:
    e = registry.entry(unit["owner_id"], unit["source_session_id"])
    return [dict(owner_id=unit["owner_id"], session_id=unit["source_session_id"],
                 source_rank=unit["source_session_rank"], turn_ordinal=e.original_turn_indices.index(s["turn_index"]),
                 start_char=s["start_char"], end_char=s["end_char"], exact_quote=s["exact_text"])
            for s in unit["supporting_spans"]]


def build_exchange(kind: str, pools, bank, prefixes, *, horizons=("cutoff", "full")) -> dict:
    """``kind``: ``legacy_bank_v0`` (negative control: bank-v0's MP rule applied to a bank built from
    sessions < horizon) or ``reference_chronological`` (positive control: same compiled units,
    latest-before-cutoff MP, supersession recorded).  ME/MS records are bank-v0's, identical in both.
    ``horizons``: ``cutoff`` (writer saw sessions < cutoff only) and/or ``full`` (whole trajectory)."""
    from .binding import frontier_for
    registry = bank.registry
    max_rank = {}
    for e in registry.entries:
        if e.availability_scope == "personal_history":
            o = e.source.owner_id
            max_rank[o] = max(max_rank.get(o, -1), e.source.chronological_rank)
    cuts = []
    for prefix in prefixes:
        c = prefix.cutoff_rank
        base = []
        for r in bank.records:
            if r.head not in ("ME", "MS") or r.owner_id != prefix.owner_id or r.source_rank >= c:
                continue
            base.append(_record_entry(r.record_id, head=r.head, owner=r.owner_id, refs=_refs_of_record(r),
                                      known=r.source_rank, ready=r.ready_at.session_rank,
                                      content=object_sha256(r.reading_text), stage=r.stage))
        frontier = [dict(source_id=e.source_id, session_id=e.session_id, rank=e.rank,
                         transcript_sha256=e.transcript_sha256, ready_rank=e.ready_rank)
                    for e in frontier_for(registry, prefix)]
        for hz in horizons:
            h = c if hz == "cutoff" else max_rank[prefix.owner_id] + 1
            if kind == "legacy_bank_v0":
                mp = pools.legacy_at_horizon(prefix.owner_id, c, h)
            else:
                mp = pools.asof(prefix.owner_id, c)
            recs = list(base)
            for m in sorted(mp):
                u = pools.units[m]
                sup = ()
                if kind == "reference_chronological":
                    sup = tuple(sorted(x["memory_id"] for x in pools.by_slot[(u["owner_id"], u["profile_slot_key"])]
                                       if x["source_session_rank"] < u["source_session_rank"]
                                       and x["memory_id"] not in pools.moved_to_me))
                recs.append(_record_entry("mp::" + m, head="MP", owner=u["owner_id"], refs=_unit_refs(u, registry),
                                          known=u["source_session_rank"], ready=u["source_session_rank"] + 1,
                                          content=object_sha256(u["normalized_value"] + "|" + "|".join(
                                              s["exact_text"] for s in u["supporting_spans"])),
                                          supersedes=tuple("mp::" + x for x in sup)))
            cuts.append(dict(owner_id=prefix.owner_id, session_id=prefix.session_id, cut_turn=prefix.cut_turn,
                             prefix_id=prefix.prefix_id, cutoff_rank=c, horizon_rank=h, source_frontier=frontier,
                             snapshot_sha256=snapshot_sha256(recs), records=recs))
    return dict(protocol=PROTOCOL, writer_identity=f"wsb-control:{kind}", cutoffs=cuts)
