# Paper-1 Semantic Compiler v6 — offline implementation review

Status: offline implementation review complete; zero API calls and zero
outcome access during this review. This note does not amend Paper-1 authority
and is not a live-run authorization.

## Resolved offline gates

- The provider contract has three class-specific arrays: `mp_facts`,
  `ms_memories`, and `me_experiences`. Qwen does not emit global subtype,
  utility, retrieval, or ON/OFF fields.
- Runtime validation is item-level. One malformed atom is rejected without
  discarding other valid atoms from the session.
- Accepted units preserve normalized semantics separately from deterministic
  rendered candidate content. Exact subtype mappings, content hashes,
  renderer identity, source spans, typed prior relations, and request/response
  hashes are contract-validated.
- `uncertain` MS state is retained only in the compact state table and cannot
  become a formal candidate.
- The outcome-blind version resolver and candidate adapter are implemented.
  MP field type and ME historical outcome type are materialized directly from
  typed slots, never parsed from prose. Semantic relation edges do not alter
  primary exact-mechanical fold grouping.
- Legacy regex/string construction remains reproducible as a diagnostic API,
  while the formal census and feature-readiness scripts require accepted v6
  units.
- A smoke prefix cannot masquerade as a formal artifact. Formal loaders require
  the complete sanitized owner/session set in exact order and recompute every
  source/prior-table identity.
- Semantic census/readiness rows identify their candidate source. Their
  summaries bind the compiler artifact and compiler, grounding, renderer,
  adapter, and resolver identities. Only `mp_profile_field_type` and
  `me_historical_outcome_type` are upgraded to implemented; BGE-M3 and the
  remaining target-state features stay pending.

## Evidence boundary

Offline fixtures prove schema, grounding, acceptance orchestration, version
resolution, deterministic rendering, adapter behavior, input isolation,
cache/budget behavior, and fail-closed artifact loading. A fake verifier
rejection does not prove Qwen semantic accuracy on third-party action, future
plan, purpose-as-outcome, or unresolved-lineage cases.

The next live step therefore remains a separately authorized 20-session v6
smoke under the existing aggregate USD 2 hard cap. It is not a model or
hyperparameter bakeoff and has no invented empirical PASS threshold. Review
must distinguish isolated atom rejection from systematic schema, grounding,
prompt, or adapter failure. No paid call is authorized by this document.

After a satisfactory smoke, the successful content-addressed cache is resumed
for the remaining sessions under a new explicit authorization. Only the full
identity-checked artifact may rebuild the formal census/readiness and enter a
pre-outcome freeze draft.

## Still pending after semantic compilation

- freeze and materialize exact BGE-M3 revision, pooling, normalization, query
  construction, and artifact identity;
- bind the complete semantic candidate/compiler artifact to the exact K=5,
  seed=0 fold manifest without using semantic links for primary grouping;
- freeze remaining candidate bundle, token cap, and exact feature-schema items;
- obtain explicit authorization before any further paid compiler call;
- keep the formal outcome lock closed until every pre-outcome freeze item is
  complete.
