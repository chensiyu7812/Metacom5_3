"""ME semantic extraction pilot: can a real LLM call recover more valid
action+outcome candidates than the strict regex compiler (0.40% pass rate,
3/747 real chunks -- PM_V1_5_V5_3_ME_VERIFICATION_FINDINGS_20260806_ZH.md)?

Status: dry-run by default, real --live calls only on explicit request.

This is deliberately a small, cheap PILOT, not the full "semantic ME
compiler" a second Codex session proposed. It tests only the empirical
question that proposal's cost/benefit depends on: does a real extractor
find meaningfully more candidates than 0.4%, on real chunks the current
regex compiler already rejects? It does NOT implement the full compiler
contract (owner_id/session_id/turn_id plumbing, the full hard-validator
suite) -- that is real, separate engineering work, not justified until
this pilot's answer is known.

Backend hard check (the one thing this pilot does implement for real,
because it is cheap and load-bearing): both extracted spans must be exact
substrings of the original chunk text. An extractor claiming a span that
is not verbatim in the source is rejected outright, regardless of how
plausible it looks -- same fail-closed principle already used throughout
this project (describe_memory_candidate's causal-boundary assertion,
compile_atomic_reusable_outcome's literal-span requirement).

What this pilot does NOT verify (a known, disclosed limitation, not an
oversight): whether an extracted "completed action" / "observed outcome"
pair is genuinely completed/observed rather than hypothetical or future --
that is a semantic question the independent review correctly flagged as
not mechanically checkable the same way substring-existence is. Spans here
are only checked for verbatim existence in the source; a human read of the
results is still required before treating any of them as usable evidence.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.contracts import MemorySource  # noqa: E402
from metacom_pm.evoemo import build_evo_memory  # noqa: E402
from metacom_pm.v1_5_v5_2_atomic_memory import compile_atomic_reusable_outcome  # noqa: E402

EVOEMO = ROOT / "data/external/evo_emo.json"
PANEL_DIR = ROOT / "outputs/pm_v1_5b_corrected_external_split_v1"
OUT_DIR = ROOT / "outputs/pm_v1_5_v5_3_me_extraction_pilot_v1"

# 2026-08-06 v2: the first version of this prompt (no examples) got 0/15 on
# a real pilot. An independent review manually re-read the raw "abstained"
# chunks and found at least 2 genuine misses (confirmed directly against the
# saved chunk text, not taken on trust): a p18 chunk containing "i decided
# to to yoga for better sleep its nice and going good" (messy grammar, but
# a clear action+outcome), and a p9 chunk containing "I used this chat...
# It helps... Yes it helps" (outcome mentioned before the action is named,
# i.e. not in linear order). The recall failure looks like it came from (a)
# no worked examples at all, and (b) messy/informal or non-linear phrasing
# probably reading as "not confident enough" under a bare "abstain if
# unsure" instruction. v2 adds real few-shot examples, including messy ones,
# and says explicitly that bad grammar or informal phrasing is not by
# itself a reason to abstain.
EXTRACTION_SYSTEM_PROMPT = (
    "You will be given one chunk of a user's own past chat turns (their own words, in "
    "order, sometimes informal or with typos). Look for a specific, local instance of: the "
    "user did something (a concrete past action they actually took, not a plan or hope), and "
    "they observed a specific result from it (not a general feeling, not advice they "
    "received, not something a third party did). Both the action and the result must be "
    "about the SAME local event. They do not have to appear in that order in the text, and "
    "messy grammar, typos, or informal phrasing are NOT by themselves a reason to abstain -- "
    "judge the content, not the writing quality.\n\n"
    "Examples of chunks that DO contain one (has_reusable_outcome=true):\n"
    "- \"I tried to focus on engaging one-on-one, which helped a bit, but it was hard to "
    "shake the feeling of being judged.\" -> action_span=\"I tried to focus on engaging "
    "one-on-one\", outcome_span=\"which helped a bit, but it was hard to shake the feeling "
    "of being judged or not doing enough.\"\n"
    "- \"...i decided to to yoga for better sleep its nice and going good ok.thank you\" "
    "(messy grammar, still valid) -> action_span=\"i decided to to yoga for better sleep\", "
    "outcome_span=\"its nice and going good\"\n"
    "- \"It helps to have a person to talk to. I used this chat ... Yes it helps.\" (outcome "
    "mentioned before the action is named -- still valid, look at the whole chunk) -> "
    "action_span=\"I used this chat\", outcome_span=\"Yes it helps\"\n\n"
    "If you find one: return has_reusable_outcome=true, and action_span/outcome_span as "
    "EXACT, VERBATIM substrings copied from the chunk (do not paraphrase, do not fix grammar "
    "or punctuation -- copy the exact characters, including typos).\n\n"
    "If there really is no local action+outcome pair (e.g. only a feeling, a plan, advice "
    "received, or something someone else did), return has_reusable_outcome=false and leave "
    "both spans empty."
)


def load_jsonl(path: Path) -> list[dict]:
    with path.open() as f:
        return [json.loads(line) for line in f if line.strip()]


def panel_user_ids() -> list[str]:
    uids: list[str] = []
    seen = set()
    for fname in ("evoemo_qualification_panel_private.jsonl", "evoemo_lockbox_panel_private.jsonl"):
        for row in load_jsonl(PANEL_DIR / fname):
            uid = row["user_id_private_analysis_only"]
            if uid not in seen:
                seen.add(uid)
                uids.append(uid)
    return uids


def collect_uncompilable_chunks(
    users: dict, uids: list[str], n: int, exclude_memory_ids: frozenset[str] = frozenset()
) -> list[dict]:
    """Real ME chunks (via the real build_evo_memory() compiler) that FAIL
    the current strict regex -- these are the only chunks worth piloting an
    alternative extractor on; chunks that already pass need no pilot.

    Spreads across distinct users round-robin (one chunk per user per pass)
    rather than draining one user's pool first, so a small pilot sample
    isn't accidentally all one person's writing style.

    exclude_memory_ids lets a re-test draw genuinely fresh material -- in
    particular, two chunks from the first pilot round are now baked into
    EXTRACTION_SYSTEM_PROMPT as few-shot examples (v2), so re-testing on
    them would not be a fair read of whether the prompt improvement
    generalizes, only whether the model can recognize its own example.
    """

    per_user: dict[str, list] = {}
    for uid in uids:
        user = users[uid]
        items, _extra = build_evo_memory(user)
        me_items = [it for it in items if it.source is MemorySource.ME]
        per_user[uid] = [
            it for it in me_items
            if compile_atomic_reusable_outcome(it.text) is None
            and it.memory_id not in exclude_memory_ids
        ]

    chunks: list[dict] = []
    max_pool_len = max((len(pool) for pool in per_user.values()), default=0)
    for index in range(max_pool_len):
        for uid in uids:
            if len(chunks) >= n:
                return chunks
            pool = per_user[uid]
            if index < len(pool):
                it = pool[index]
                chunks.append({"user_id": uid, "memory_id": it.memory_id, "text": it.text})
    return chunks


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Make real, billable API calls.")
    parser.add_argument("--n", type=int, default=15, help="Number of uncompilable chunks to pilot.")
    args = parser.parse_args()

    exclude_memory_ids: frozenset[str] = frozenset()
    out_path = OUT_DIR / "me_extraction_pilot_results.jsonl"
    if args.live and out_path.exists():
        previous = [json.loads(line) for line in out_path.read_text().splitlines() if line.strip()]
        exclude_memory_ids = frozenset(r["memory_id"] for r in previous if "memory_id" in r)
        archive_path = OUT_DIR / "me_extraction_pilot_results_v1_prompt_20260806.jsonl"
        if not archive_path.exists():
            out_path.rename(archive_path)
            print(f"archived v1-prompt run ({len(exclude_memory_ids)} chunks) to {archive_path}")

    users = {str(u["id"]): u for u in json.loads(EVOEMO.read_text(encoding="utf-8"))}
    uids = panel_user_ids()
    chunks = collect_uncompilable_chunks(users, uids, args.n, exclude_memory_ids=exclude_memory_ids)
    print(f"selected {len(chunks)} real ME chunks that fail the current strict compiler, "
          f"across {len({c['user_id'] for c in chunks})} distinct users "
          f"(excluded {len(exclude_memory_ids)} previously-piloted chunks)")

    if not args.live:
        for c in chunks:
            print(f"\n[{c['user_id']}] {c['text'][:150]}")
        print("\n(dry-run: no extraction calls made)")
        return

    from metacom_pm.api import OpenAICompatibleClient  # noqa: PLC0415
    from metacom_pm.config import endpoint_from_config, load_config  # noqa: PLC0415
    from metacom_pm.contracts import StrictModel  # noqa: PLC0415

    class _ExtractionSchema(StrictModel):
        has_reusable_outcome: bool
        action_span: str
        outcome_span: str

    config = load_config(ROOT / "configs/experiment.yaml")
    endpoint = endpoint_from_config(config, "generator")
    client = OpenAICompatibleClient(endpoint)

    results = []
    n_claimed = n_verbatim_valid = 0
    try:
        for i, c in enumerate(chunks, 1):
            messages = [
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": c["text"]},
            ]
            result, parsed = client.chat(messages, response_schema=_ExtractionSchema)
            row = {"user_id": c["user_id"], "memory_id": c["memory_id"], "chunk_text": c["text"]}
            if parsed is None:
                row["error"] = str(result)
                print(f"\n[{i}/{len(chunks)}] {c['user_id']}: no structured output")
                results.append(row)
                continue
            extracted = parsed.model_dump()
            row.update(extracted)
            if extracted["has_reusable_outcome"]:
                n_claimed += 1
                action_ok = extracted["action_span"] and extracted["action_span"] in c["text"]
                outcome_ok = extracted["outcome_span"] and extracted["outcome_span"] in c["text"]
                row["action_span_verbatim_in_source"] = bool(action_ok)
                row["outcome_span_verbatim_in_source"] = bool(outcome_ok)
                valid = bool(action_ok and outcome_ok)
                row["verbatim_validated"] = valid
                if valid:
                    n_verbatim_valid += 1
                print(f"\n[{i}/{len(chunks)}] {c['user_id']}: claimed=yes, "
                      f"verbatim_validated={valid}")
                print(f"  action: {extracted['action_span']!r}")
                print(f"  outcome: {extracted['outcome_span']!r}")
            else:
                row["verbatim_validated"] = False
                print(f"\n[{i}/{len(chunks)}] {c['user_id']}: claimed=no (abstained)")
            results.append(row)
    finally:
        client.close()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        for row in results:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"\n=== summary ===")
    print(f"chunks piloted: {len(chunks)}")
    print(f"extractor claimed a reusable outcome: {n_claimed}")
    print(f"claims that passed the verbatim-substring hard check: {n_verbatim_valid}")
    print(f"pilot verbatim-validated rate: {n_verbatim_valid}/{len(chunks)} "
          f"({n_verbatim_valid/len(chunks):.1%})" if chunks else "n/a")
    print(f"(for comparison: strict regex compiler's real rate on the full 747-chunk "
          f"panel was 0.40%, 3/747 -- this pilot only sampled chunks that regex already "
          f"rejects, so these two rates are not directly comparable as stated; see the "
          f"analysis doc for the correct framing)")
    print(f"\nwrote {out_path}")


if __name__ == "__main__":
    main()
