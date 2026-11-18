"""WS-B independent mechanical check of a WS-A E1 as-of bundle (``pmrl1v3-asof-sidecar-1`` + E1 previews).

Read-only.  No WS-A code is imported or executed.  Everything is recomputed from:
  * the public sanitized runtime artifact (RAW turns, ranks, dates) parsed here directly;
  * B0's prefix census and the B6e-v3 selection (WS-B artefacts);
  * the frozen G0e identity file of PR #10 (system prompt, decode).

Scope is mechanical only (source / time / owner / hash / horizon / Generator-visible projection).  Human
semantics, current applicability, licence and research qualification are reported as separate axes and are
never inferred from a mechanical pass.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
from collections import Counter

PROTOCOL = "pmrl1v3-wsb-e1-asof-receipt-v1"

# ------------------------------------------------------------------ canonical hash (own implementation)
_ESC = {'"': '\\"', "\\": "\\\\", "\n": "\\n", "\r": "\\r", "\t": "\\t", "\b": "\\b", "\f": "\\f"}


def _str(s: str) -> str:
    out = []
    for ch in s:
        if ch in _ESC:
            out.append(_ESC[ch])
        elif ord(ch) < 0x20:
            out.append("\\u%04x" % ord(ch))
        else:
            out.append(ch)
    return '"' + "".join(out) + '"'


def canon(v) -> str:
    """Compact, key-sorted (code point), non-normalised UTF-8 JSON text; ints/str/bool/null/list/dict only."""
    if v is None:
        return "null"
    if v is True:
        return "true"
    if v is False:
        return "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        raise ValueError("floats are outside the exchange spec")
    if isinstance(v, str):
        return _str(v)
    if isinstance(v, (list, tuple)):
        return "[" + ",".join(canon(x) for x in v) + "]"
    if isinstance(v, dict):
        if not all(isinstance(k, str) for k in v):
            raise ValueError("non-string key")
        return "{" + ",".join(_str(k) + ":" + canon(v[k]) for k in sorted(v)) + "}"
    raise ValueError(f"unsupported type {type(v).__name__}")


def digest(v) -> str:
    return hashlib.sha256(canon(v).encode("utf-8")).hexdigest()


def text_sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def strict_loads(text: str):
    def hook(pairs):
        d = {}
        for k, v in pairs:
            if k in d:
                raise ValueError(f"duplicate key {k}")
            d[k] = v
        return d

    def bad(x):
        raise ValueError(f"non-finite {x}")
    return json.loads(text, object_pairs_hook=hook, parse_constant=bad)


def check_vectors(vectors: list[dict]) -> list[str]:
    p = []
    for i, v in enumerate(vectors):
        t = canon(v["input"] if "snapshot_sha" not in v["input"] else
                  {k: x for k, x in v["input"].items() if k != "snapshot_sha"})
        if t != v["canonical_utf8_text"] or t.encode().hex() != v["canonical_utf8_hex"] or \
                text_sha(t) != v["sha256"]:
            p.append(f"V{i}_vector_mismatch")
    return p


# ------------------------------------------------------------------ RAW (public artifact) parsed here
def esconv_family(session_id: str) -> str | None:
    m = re.fullmatch(r"esc(\d+)", session_id)
    return f"esconv:esconv_{int(m.group(1)):04d}" if m else None


class Raw:
    """Owner sessions straight from the sanitized runtime artifact (turns: role/content, ordered by idx)."""

    def __init__(self, artifact: dict):
        self.sessions: dict[tuple[str, str], dict] = {}
        self.by_owner: dict[str, list[dict]] = {}
        for u in artifact["users"]:
            rows = []
            for s in u["sessions"]:
                turns = [dict(role=t["role"], text=t["content"]) for t in sorted(s["turns"], key=lambda t: t["idx"])]
                row = dict(owner_id=u["owner_id"], session_id=s["session_id"], rank=s["chronological_rank"],
                           date=s["timestamp"], turns=turns,
                           family_id=esconv_family(s["session_id"]) or f"evoemo_owner:{u['owner_id']}")
                self.sessions[(u["owner_id"], s["session_id"])] = row
                rows.append(row)
            self.by_owner[u["owner_id"]] = sorted(rows, key=lambda r: r["rank"])

    def transcript_sha(self, owner: str, sid: str) -> str:
        return digest([[t["role"], t["text"]] for t in self.sessions[(owner, sid)]["turns"]])

    def legal_past(self, owner: str, cutoff_rank: int, timestamp: str | None) -> list[dict]:
        return [s for s in self.by_owner[owner] if s["rank"] < cutoff_rank and
                (not timestamp or not s["date"] or s["date"] <= timestamp)]

    def families(self, owner: str) -> set[str]:
        return {s["family_id"] for s in self.by_owner[owner]}


# ------------------------------------------------------------------ per-prefix mechanical checks
CONTEXT_FIELDS = ("schema_version", "prefix_id", "prefix_protocol", "identity_scope", "owner_id", "session_id",
                  "cut_turn", "turns", "cutoff_rank", "timestamp", "dataset", "family_id", "ancestor_family_ids")
SOURCE_FIELDS = ("owner_id", "session_id", "dataset", "chronological_rank", "date", "family_id",
                 "ancestor_family_ids", "license", "complete", "transcript_sha256")


def materialize(ledger: list[dict], cutoff_rank: int) -> list[dict]:
    """B's own as-of rule: reported strictly before the current session and ready no later than its start."""
    keep = [r for r in ledger if r["reported_at"]["session_rank"] < cutoff_rank
            and r["ready_at"]["session_rank"] <= cutoff_rank]
    return sorted(keep, key=lambda r: (r["reported_at"]["session_rank"], r["record_id"]))


def check_prefix(b: dict, files: dict, raw: Raw, census_row: dict | None, selected: set[str]) -> dict:
    p: list[str] = []
    pre = files["prefix"]
    owner, cutoff = pre["owner_id"], pre["cutoff_rank"]
    # M2 prefix identity against B artefacts and RAW
    if b["prefix_id"] not in selected:
        p.append("M2_prefix_not_in_B6e_selection")
    if census_row is None:
        p.append("M2_prefix_not_in_B0_census")
    else:
        for k in ("owner_id", "session_id", "cut_turn", "cutoff_rank", "timestamp"):
            if census_row[k] != pre[k]:
                p.append(f"M2_census_{k}")
    cur = raw.sessions[(owner, pre["session_id"])]
    if cur["rank"] != cutoff:
        p.append("M2_cutoff_rank_vs_raw")
    want_turns = cur["turns"][: pre["cut_turn"] + 1]
    if [(t["role"], t["text"]) for t in pre["turns"]] != [(t["role"], t["text"]) for t in want_turns]:
        p.append("M2_prefix_turns_not_verbatim_raw")
    if pre["turns"][-1]["role"] != "seeker":
        p.append("M2_last_turn_not_seeker")
    if digest({k: pre[k] for k in CONTEXT_FIELDS}) != b["prefix_context_sha256"]:
        p.append("M2_prefix_context_sha")
    # as-of family closure: owner family + families of sessions up to and including the current one
    fam = {f"evoemo_owner:{owner}"} | {s["family_id"] for s in raw.by_owner[owner] if s["rank"] <= cutoff}
    if {pre["family_id"], *pre["ancestor_family_ids"]} != fam or pre["family_id"] != cur["family_id"]:
        p.append("M11_asof_family_closure_vs_raw")
    # M3 frontier
    legal = raw.legal_past(owner, cutoff, pre["timestamp"])
    fr = files["frontier"]
    srcs = fr["sources"]
    if [(s["session_id"], s["chronological_rank"], s["date"]) for s in srcs] != \
            [(s["session_id"], s["rank"], s["date"]) for s in legal]:
        p.append("M3_frontier_not_exact_legal_past")
    for s in srcs:
        if s["transcript_sha256"] != raw.transcript_sha(owner, s["session_id"]):
            p.append(f"M3_transcript_sha:{s['session_id']}")
        if s["owner_id"] != owner:
            p.append(f"M11_frontier_owner:{s['session_id']}")
        if s["family_id"] != raw.sessions[(owner, s["session_id"])]["family_id"]:
            p.append(f"M3_family:{s['session_id']}")
        if s["source_sha256"] != digest({k: s[k] for k in SOURCE_FIELDS}):
            p.append(f"M3_source_sha:{s['session_id']}")
    # M4 snapshot hashes, both horizons
    sa, sz = files["snapshot_past"], files["snapshot_future"]
    for tag, s in (("past", sa), ("future", sz)):
        if digest({k: v for k, v in s.items() if k != "snapshot_sha"}) != s["snapshot_sha"]:
            p.append(f"M4_snapshot_sha_not_reproduced:{tag}")
        if s["snapshot_sha"] != b["snapshot_sha"]:
            p.append(f"M4_snapshot_sha_vs_binding:{tag}")
        if digest(s["source_frontier"]) != s["source_frontier_sha256"] or \
                s["source_frontier_sha256"] != b["source_frontier_sha256"]:
            p.append(f"M4_frontier_sha:{tag}")
        if s["source_frontier"] != fr:
            p.append(f"M4_frontier_file_differs:{tag}")
        if s["as_of"]["prefix_context_sha256"] != b["prefix_context_sha256"]:
            p.append(f"M4_as_of_context:{tag}")
    if sa != sz:
        p.append("M5_X5a_snapshot_files_differ")
    # M5 ledgers: record ids, append-only, horizon invariance by own materialisation
    lp, lf = files["ledger_past"], files["ledger_future"]
    for tag, led in (("past", lp), ("future", lf)):
        for r in led:
            if r["record_id"] != "asof-record:" + digest(dict(r, record_id="pending")):
                p.append(f"M5_record_id:{tag}:{r['record_id'][:24]}")
    fid = {r["record_id"]: r for r in lf}
    if any(fid.get(r["record_id"]) != r for r in lp):
        p.append("M5_past_not_prefix_of_future")
    extra = [r for r in lf if r["record_id"] not in {x["record_id"] for x in lp}]
    if any(r["reported_at"]["session_rank"] < cutoff for r in extra):
        p.append("M5_future_rows_reported_before_cutoff")
    want = materialize(lp, cutoff)
    if materialize(lf, cutoff) != want:
        p.append("M5_X5a_materialisation_differs")
    if sa["ledger_prefix"] != want:
        p.append("M5_snapshot_not_own_materialisation")
    if [v["record"] for v in sa["views"]] != sa["ledger_prefix"]:
        p.append("M5_views_not_ledger_prefix")
    # M6 records: owner, spans, time
    legal_ids = {s["session_id"] for s in legal}
    kinds, disp = Counter(), Counter()
    for v in sa["views"]:
        r = v["record"]
        kinds[r["kind"]] += 1
        disp[(r["kind"], v["disposition"], r["review_status"])] += 1
        if r["owner_id"] != owner:
            p.append(f"M11_record_owner:{r['record_id'][:24]}")
        kr, rr, rep = r["known_at"]["session_rank"], r["ready_at"]["session_rank"], r["reported_at"]["session_rank"]
        if not (rep < kr <= rr <= cutoff):
            p.append(f"M6_time_order:{r['record_id'][:24]}")
        for s in r["source_refs"]:
            if s["owner_id"] != owner or s["session_id"] not in legal_ids:
                p.append(f"M6_span_outside_legal_past:{s['session_id']}")
                continue
            t = raw.sessions[(owner, s["session_id"])]["turns"][s["turn_index"]]
            if t["text"][s["start_char"]: s["end_char"]] != s["exact_quote"] or t["role"] != s["speaker"]:
                p.append(f"M6_span_not_exact:{s['source_key']}")
            if s["raw_turn_sha256"] != text_sha(t["text"]):
                p.append(f"M6_turn_sha:{s['source_key']}")
            if s["source_rank"] != raw.sessions[(owner, s["session_id"])]["rank"] or s["source_rank"] >= cutoff:
                p.append(f"M6_span_rank:{s['source_key']}")
        if r["kind"] == "MS_RAW" and v["disposition"] != "raw_available":
            p.append(f"M8_raw_not_readable:{r['record_id'][:24]}")
        if r["kind"] != "MS_RAW" and v["disposition"] not in ("quarantine", "unusable", "pending_review"):
            p.append(f"M8_unreviewed_semantic_readable:{r['record_id'][:24]}")
    # M7 RAW completeness
    raws = {}
    for r in sa["ledger_prefix"]:
        if r["kind"] == "MS_RAW":
            raws.setdefault(r["session_id"], []).append(r)
    if set(raws) != legal_ids or any(len(x) != 1 for x in raws.values()):
        p.append("M7_raw_records_not_one_per_legal_session")
    for sid, (r, *_) in raws.items():
        got = [(s["turn_index"], s["start_char"], s["end_char"]) for s in r["source_refs"]]
        turns = raw.sessions[(owner, sid)]["turns"]
        wantr = [(i, 0, len(t["text"])) for i, t in enumerate(turns) if t["text"]]
        if got != wantr:
            p.append(f"M7_raw_spans_incomplete:{sid}")
    if set(b["raw_record_ids"]) != {r[0]["record_id"] for r in raws.values()}:
        p.append("M7_binding_raw_ids")
    # M8 reading = latest legal complete session, rendered verbatim
    rd = files["reading"]
    latest = legal[-1] if legal else None
    ms = rd.get("MS", {})
    if latest is None or ms.get("reported_at", {}).get("session_rank") != latest["rank"]:
        p.append("M8_reading_not_latest_legal_session")
    elif ms.get("view") != "raw":
        p.append("M8_reading_view")
    else:
        body = ms["reading_text"].split("\n")[1:]
        if body != [f"{t['role']}: {t['text']}" for t in latest["turns"] if t["text"]]:
            p.append("M8_reading_text_not_verbatim_raw")
        if raws.get(latest["session_id"], [{}])[0].get("record_id") != b["selected_raw_id"]:
            p.append("M8_selected_raw_id")
    if any(rd.get(h, {}).get("status") != "unavailable" for h in ("MP", "ME")):
        p.append("M8_semantic_heads_readable")
    if digest(rd.get("MS")) != b["reading_sha256"]:          # definition: object hash of the MS ReadingView
        p.append("M8_reading_sha")
    return dict(prefix_id=b["prefix_id"], owner_id=owner, cutoff_rank=cutoff, legal_sessions=len(legal),
                future_rows=len(extra), kinds=dict(kinds),
                dispositions={"|".join(k): n for k, n in sorted(disp.items())}, problems=p)


# ------------------------------------------------------------------ Generator-visible projection
ROLE = {"supporter": "assistant", "seeker": "user"}
META = [(re.compile(r"\b[0-9a-f]{40,64}\b"), "hex_digest"), (re.compile(r"asof-record:|E1-proposal:|renderer-"), "identity"),
        (re.compile(r"\bp(?:1[0-8]|[1-9])_conv_\d+\b|\besc\d{2,4}\b"), "session_id"),
        (re.compile(r"\b(?:owner_id|prefix_id|cutoff_rank|snapshot_sha|disposition|quarantine|NeedCard|J1|J2)\b"), "field_name"),
        (re.compile(r"\b(?:OFF|RET-MS|DP-MS|ESC-RANK)\b"), "condition_name")]


def ngrams(text: str, n: int = 8) -> set[tuple[str, ...]]:
    w = re.findall(r"[a-z0-9']+", html.unescape(text).lower())
    return {tuple(w[i:i + n]) for i in range(len(w) - n + 1)}


def check_projection(row: dict, prefix: dict, reading: dict | None, raw: Raw, g0e: dict, off_messages=None) -> dict:
    p: list[str] = []
    m = row["preview_messages"]
    if not m:
        return dict(request_id=row["request_id"], arm=row["arm"], previewed=False, problems=[])
    if m[0] != dict(role="system", content=g0e["common"]["system_prompt"]):
        p.append("P1_system_prompt_not_G0e")
    conv = [dict(role=ROLE[t["role"]], content=t["text"]) for t in prefix["turns"]]
    inserted = m[1:len(m) - len(conv)]
    if m[len(m) - len(conv):] != conv:
        p.append("P2_conversation_not_verbatim_prefix")
    if row["arm"] in ("OFF", "RS-R0"):
        if inserted:
            p.append("P3_off_has_insert")
    elif len(inserted) != 1 or inserted[0]["role"] != "user":
        p.append("P3_not_exactly_one_inserted_block")
    if off_messages is not None and row["arm"] != "OFF" and [x for x in m if x not in inserted] != off_messages:
        p.append("P3_not_single_factor_vs_OFF")
    escaped = False
    if row["arm"] == "MS-RAW-direct" and inserted:
        blk = inserted[0]["content"]
        mm = re.search(r'<ExternalEvidence type="MS-RAW-direct">\n(.*)\n</ExternalEvidence>', blk, re.S)
        if not mm:
            p.append("P4_evidence_block_missing")
        else:
            payload = mm.group(1)
            if payload != reading["reading_text"]:
                if html.unescape(payload) == reading["reading_text"]:
                    escaped = True
                else:
                    p.append("P4_payload_not_reading")
    # leaks: metadata patterns and n-grams from illegal text
    vis = "\n".join(x["content"] for x in m[1:])
    meta = sorted({tag for rx, tag in META if rx.search(vis)})
    owner, cutoff = prefix["owner_id"], prefix["cutoff_rank"]
    legal_text = set()
    for s in raw.legal_past(owner, cutoff, prefix["timestamp"]):
        for t in s["turns"]:
            legal_text |= ngrams(t["text"])
    for t in prefix["turns"]:
        legal_text |= ngrams(t["text"])
    allowed_extra = ngrams(inserted[0]["content"]) if row["arm"].startswith("RS-") and inserted else set()
    seen = ngrams(vis) - legal_text - allowed_extra
    future, other = set(), set()
    cur = raw.sessions[(owner, prefix["session_id"])]
    for t in cur["turns"][prefix["cut_turn"] + 1:]:
        future |= ngrams(t["text"])
    for s in raw.by_owner[owner]:
        if s["rank"] > cutoff:
            for t in s["turns"]:
                future |= ngrams(t["text"])
    for o, ss in raw.by_owner.items():
        if o != owner:
            for s in ss:
                for t in s["turns"]:
                    other |= ngrams(t["text"])
    fut_hits, oth_hits = len(seen & future), len(seen & other)
    if fut_hits:
        p.append(f"P5_future_text_ngrams:{fut_hits}")
    if oth_hits:
        p.append(f"P5_other_owner_ngrams:{oth_hits}")
    # identity / capacity / decode
    if digest(m) != row["messages_sha256"]:
        p.append("P6_messages_sha")
    if digest(row["input_ids"]) != row["input_ids_sha256"] or len(row["input_ids"]) != row["input_tokens"]:
        p.append("P6_input_ids_sha_or_len")
    if row["input_tokens"] + row["output_reserve"] > row["runtime_context"] or row["output_reserve"] != 320:
        p.append("P7_capacity")
    if row["decode"] != g0e["common"]["decode"] or row["step2_id"] != g0e["common"]["step2_id"]:
        p.append("P7_decode_or_step2_not_G0e")
    if row["runtime_callable"] or row["execution_authorized"] or row["reward"] is not None or \
            row["terminal_result"] is not None:
        p.append("P8_not_inert")
    return dict(request_id=row["request_id"], arm=row["arm"], owner_id=owner, previewed=True,
                input_tokens=row["input_tokens"], html_escaped_payload=escaped, metadata_patterns=meta,
                problems=p)
