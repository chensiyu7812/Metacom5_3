"""Three visibility whitelists and a fail-closed leak scanner (``pmrl1v3-visibility-whitelist-v1``).

  PM_OBSERVATION     what the policy may observe (C0 ``Observation``, finite_head_v1)
  GENERATOR_REQUEST  what may be sent to G (chat messages / input ids / decode parameters)
  EVALUATION_ONLY    NeedCard writer, checklist, judges, researcher; strictly-past legal evidence
                     plus evaluation artefacts.  Future history is visible to the *auditor* role only,
                     for leakage audits, never as a label input.

A field path is written with ``[]`` for list elements, e.g. ``acquired[].reading_text``.  The scanner
rejects (1) any path outside the whitelist, (2) any key in FORBIDDEN_KEYS anywhere, (3) any exact
private identifier supplied by the caller (record/source/prefix/owner ids, hashes) inside any
string, and (4) any future utterance (>= ``min_future_chars``) inside any string, except future
texts that are byte-identical to legal visible/past text (e.g. a fixed supporter greeting), which
are counted separately - same rule as the G0e addendum.
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

from ..io import object_sha256

PROTOCOL = "pmrl1v3-visibility-whitelist-v1"

PM_OBSERVATION = frozenset({
    "schema_version", "domain_id", "history_sessions", "input_tokens", "action_mask[]",
    "prefix.schema_version", "prefix.timestamp", "prefix.turns[].schema_version", "prefix.turns[].turn_index",
    "prefix.turns[].role", "prefix.turns[].text",
    "acquired[].schema_version", "acquired[].head", "acquired[].view", "acquired[].expandable",
    "acquired[].expanded_from_ordinal", "acquired[].ordinal", "acquired[].reading_text", "acquired[].tokens",
    "acquired[].stage", "acquired[].reported_at", "acquired[].reported_at.schema_version", "acquired[].reported_at.date",
    "acquired[].reported_at.session_rank",
    "availability[].schema_version", "availability[].head", "availability[].available", "availability[].count",
})
# NoText ablation: identical except the delivered reading text.
PM_OBSERVATION_NOTEXT = PM_OBSERVATION - {"acquired[].reading_text"}

GENERATOR_REQUEST = frozenset({
    "messages[].role", "messages[].content", "input_ids[]", "decode.max_new_tokens", "decode.temperature",
    "decode.top_p", "decode.top_k", "decode.seed", "decode.stop[]", "decode.stop_token_ids[]",
    "decode.repetition_penalty", "decode.do_sample", "decode.enable_thinking", "decode.eos_token_id[]",
    "decode.num_beams", "decode.pad_token_id", "decode.suppress_tokens[]",
})

EVALUATION_ONLY = dict(
    needcard_writer=("current visible prefix (last turns)", "complete strictly-past legal RAW sessions",
                     "RS-v0 label catalog (unverified tags)"),
    checklist_writer=("span-verified NeedCard",),
    judge=("visible prefix", "candidate reply", "frozen checklist", "readings delivered to that terminal"),
    human_reviewer=("visible prefix", "candidate replies (blinded, randomised)",
                    "union of legal readings for the prefix (identical for every candidate)"),
    auditor=("everything incl. future sessions, ids and traces; leakage audits only, never labels"),
)

FORBIDDEN_KEYS = frozenset({
    "record_id", "record_ids", "source_id", "source_ids", "source_key", "owner_id", "session_id", "prefix_id",
    "family_id", "ancestor_family_ids", "fold", "split", "stratum", "needcard", "needcard_sha256", "checklist",
    "checklist_sha256", "judge", "verdict", "verdicts", "reward", "er", "gsc", "score", "scores", "ranked",
    "rank", "components", "oracle", "optimal", "optimal_subset", "gold", "gold_evidence", "evidence_spans",
    "terminal_key", "key_sha256", "bank_version", "index_version", "query_identity", "retrieval_trace",
    "future", "eval_only", "sampling", "natural_weight", "assignment", "head_needs", "method_need",
    "required", "relevant_optional", "must_not_contradict", "body", "legacy_unit",
})

_PRIVATE_PREFIXES = re.compile(r"\b(resource|source|bank|index|renderer|decode|G0e|sources):[0-9a-f]{16,}")
_HEX64 = re.compile(r"\b[0-9a-f]{64}\b")


def _walk(value: Any, path: str = ""):
    if isinstance(value, Mapping):
        for k, v in value.items():
            yield from _walk(v, f"{path}.{k}" if path else str(k))
            yield ("key", f"{path}.{k}" if path else str(k), k)
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from _walk(v, f"{path}[]")
        if not value:
            yield ("empty", f"{path}[]", None)
    else:
        yield ("leaf", path, value)


def to_plain(obj: Any) -> Any:
    """C0 contracts / dataclasses / mappings -> plain JSON structures (same encoder as the hashes)."""
    import json
    from ..io import canonical_json
    return json.loads(canonical_json(obj))


def scan(obj: Any, whitelist: frozenset, *, private_tokens: Iterable[str] = (),
         future_texts: Iterable[str] = (), legal_texts: Iterable[str] = (), min_future_chars: int = 24) -> dict:
    plain = to_plain(obj)
    private = sorted({t for t in private_tokens if t and len(t) >= 6})
    legal_blob = "\n".join(legal_texts)
    fut = [t for t in {f.strip() for f in future_texts} if len(t) >= min_future_chars]
    fut_same_as_legal = sorted(t for t in fut if t in legal_blob)
    fut_check = [t for t in fut if t not in legal_blob]
    bad_paths, bad_keys, id_hits, hex_hits, fut_hits, leaves = set(), set(), set(), 0, set(), 0
    for kind, path, v in _walk(plain):
        if kind == "key":
            if str(v) in FORBIDDEN_KEYS:
                bad_keys.add(path)
            continue
        if kind == "empty":
            continue
        leaves += 1
        if path not in whitelist:
            bad_paths.add(path)
        if isinstance(v, str):
            for t in private:
                if t in v:
                    id_hits.add(t[:16])
            if _PRIVATE_PREFIXES.search(v) or _HEX64.search(v):
                hex_hits += 1
            for t in fut_check:
                if t in v:
                    fut_hits.add(object_sha256(t)[:16])
    ok = not (bad_paths or bad_keys or id_hits or hex_hits or fut_hits)
    return dict(protocol=PROTOCOL, ok=ok, leaves=leaves, non_whitelisted_paths=sorted(bad_paths),
                forbidden_keys=sorted(bad_keys), private_id_hits=sorted(id_hits), private_hash_like=hex_hits,
                future_text_hits=sorted(fut_hits), future_texts_checked=len(fut_check),
                future_texts_identical_to_legal_text=len(fut_same_as_legal))


def whitelist_manifest() -> dict:
    spec = dict(protocol=PROTOCOL, pm=sorted(PM_OBSERVATION), pm_notext=sorted(PM_OBSERVATION_NOTEXT),
                generator=sorted(GENERATOR_REQUEST), evaluation_only=EVALUATION_ONLY,
                forbidden_keys=sorted(FORBIDDEN_KEYS))
    return dict(spec, sha256=object_sha256(spec))
