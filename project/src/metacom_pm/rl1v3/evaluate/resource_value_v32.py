"""V3.2 P2 resource-value mechanism protocol (``pmrl1v3-v32-resource-value-protocol-v1``).  CPU, proposal.

Frozen BEFORE any generation.  Inputs are the 54 exposed development inputs proposed in PR #13
(39 D = OFF + single heads, 15 E = MP+MS / ME+MS on the eight B6e-v3 prefixes); none is swapped.
Each input gets
  * ``eligibility``  ELIGIBLE / LEGACY_DIAGNOSTIC / BLOCKED (mechanical, see ``assess_job``);
  * the five per-input questions of the V3.2 brief, each either answered mechanically or left
    ``pending_human`` / ``not_answerable_before_generation`` - developer cues are pre-screens only;
  * candidate diagnostic situations S1-S7 (pre-screen) and the required human semantic checks.
ELIGIBLE means "usable as an exposed development input once WS-A's formal as-of binding reproduces
the same delivered unit"; it is never research_qualified and never an independent test.

Experiment families (one factor changes per family; model, system prompt, decode, base context and
legal sources fixed):
  EXP-D   OFF vs each single head (RS/MP/ME/MS)                 content factor
  EXP-E   legal pairs and ALL vs their parts and OFF             content interaction
  EXP-RS  R0 / F-resident / METHOD / METHOD+CASE                 RS material factor (new materials)
  EXP-C   G0e Notes vs bounded reading, same source content      renderer factor (new renderer id)
Retriever, renderer and Generator comparisons are separate families with their own identities; a
family never changes two of them at once.
"""
from __future__ import annotations

import hashlib
import re

from ..io import object_sha256

PROTOCOL = "pmrl1v3-v32-resource-value-protocol-v1"
ELIGIBILITY = ("ELIGIBLE", "LEGACY_DIAGNOSTIC", "BLOCKED")
HEADS = ("RS", "MP", "ME", "MS")

# ----------------------------------------------------------------- developer pre-screen cues
# Lexical cues only.  They decide nothing; they tell the human reviewer what to check.
CUES = dict(
    third_party=r"\b(boyfriend|girlfriend|husband|wife|partner|fianc[eé]e?|mom|mother|mum|dad|father|parents?|"
                r"sister|brother|friend|friends|boss|manager|coworkers?|colleagues?|son|daughter|kids?|roommate|"
                r"teacher|doctor|therapist|he|she|his|her|him)\b",
    supporter_suggestion=r"\b(try|trying|maybe you could|have you (?:considered|thought)|you (?:might|could|should)|"
                         r"suggest|recommend|it might help|how about)\b",
    seeker_rejection_or_failure=r"\b(tried|didn't work|doesn't work|did not work|not helpful|didn't help|"
                                r"won't|don't want to|already did|no use|gave up|can't do that)\b",
    case_self_disclosure=r"\b(i had|when i was|i've been through|my own|i went through|i also)\b",
)
_RX = {k: re.compile(v, re.I) for k, v in CUES.items()}
STALE_SESSIONS = 5           # pre-registered: source >= 5 sessions before the cutoff -> staleness check
LOW_OVERLAP = 0.10           # pre-registered: lexical overlap below -> "may not be needed now" check


def text_cues(reading_text: str) -> dict:
    """Counts per cue over seeker / supporter lines of a reading text."""
    seeker, supporter = [], []
    for line in reading_text.splitlines():
        (seeker if line.startswith("seeker:") else supporter if line.startswith("supporter:") else seeker).append(line)
    s, p = "\n".join(seeker), "\n".join(supporter)
    return dict(third_party=len(_RX["third_party"].findall(s)),
                supporter_suggestion=len(_RX["supporter_suggestion"].findall(p)),
                seeker_rejection_or_failure=len(_RX["seeker_rejection_or_failure"].findall(s)),
                case_self_disclosure=len(_RX["case_self_disclosure"].findall(p)))


# ------------------------------------------------------------------------ eligibility
ASOF_OK = ("external_snapshot", "registry_rules", "mp_same")
ASOF_LEGACY = ("mp_differs", "mp_tie_dependent")
ASOF_BLOCK = ("mp_unreachable_legacy_reachable_asof", "no_candidate")


def assess_job(job: dict, facts: dict, prefix_cues: dict) -> dict:
    """``job``: PR #13 PROPOSED_JOBS row; ``facts``: head -> head fact dict (see the V32 script);
    ``prefix_cues``: B0 visible surface cues of the prefix (lexical; not need rates)."""
    subset = () if job["subset"] == "OFF" else tuple(job["subset"].split("+"))
    reasons, checks, situations = [], set(), set()
    status = "ELIGIBLE"
    for h in subset:
        f = facts[h]
        a = f["asof"]["status"]
        if a in ASOF_BLOCK:
            status = "BLOCKED"
            reasons.append(f"{h}:{a}")
        elif a in ASOF_LEGACY and status != "BLOCKED":
            status = "LEGACY_DIAGNOSTIC"
            reasons.append(f"{h}:{a} (bank-v0 delivers another unit than the as-of pool would)")
        elif a == "mp_same":
            reasons.append(f"{h}:pool differs from as-of ({f['asof']['legacy_pool']} vs {f['asof']['asof_pool']}) "
                           "but the delivered Top-1 unit is identical")
        if f.get("review_status") == "development_reviewed":
            checks.add(f"{h}: repaired paraphrase must match its source quote")
    if job["subset"] == "OFF":
        reasons.append("no resource; as-of independent")
    if status == "BLOCKED":
        return dict(eligibility="BLOCKED", reasons=reasons, questions=None, required_human_checks=[],
                    candidate_situations=["S7h_head_without_legal_source_in_legacy"], research_role="not_run_not_zero")
    for h in subset:
        f = facts[h]
        c = f["cues"]
        checks |= {f"{h}: relevance to the current request", f"{h}: needed now vs optional (mention necessity)"}
        if h != "RS":
            checks.add(f"{h}: subject is the user (not a third party)")
            if c["third_party"]:
                situations.add("S6_third_party_as_user")
            if f["sessions_ago"] is not None and f["sessions_ago"] >= STALE_SESSIONS:
                checks.add(f"{h}: still valid now (reported {f['sessions_ago']} sessions earlier)")
                situations.add("S3_possibly_outdated")
            if f.get("slot_versions_before_cutoff", 0) > 1:
                checks.add(f"{h}: earlier versions of this profile slot exist; current value?")
                situations.add("S3_possibly_outdated")
            if c["supporter_suggestion"] or c["seeker_rejection_or_failure"]:
                checks.add(f"{h}: stage (suggested / intended / attempted / completed / rejected)")
            if c["seeker_rejection_or_failure"]:
                situations.add("S5_rejected_or_failed_suggestion")
            if c["supporter_suggestion"]:
                situations.add("S4_may_induce_inappropriate_advice")
        else:
            checks |= {"RS: external case is not the user's experience",
                       "RS: case-only v0 material - applicability / risk of the supporter's actions"}
            situations.add("S6_third_party_as_user")
            if c["supporter_suggestion"] or c["case_self_disclosure"]:
                situations.add("S4_may_induce_inappropriate_advice")
        if f["top1"]["score"] is not None and f["top1"]["score"] < LOW_OVERLAP:
            situations.add("S2_legal_but_maybe_not_needed")
    if subset and (prefix_cues.get("back_reference") or prefix_cues.get("temporal_marker")):
        situations.add("S1_history_may_supply_needed_info")
    if len(subset) > 1:
        srcs = [facts[h]["top1"].get("source_session_id") for h in subset if h != "RS"]
        if len(srcs) != len(set(srcs)):
            checks.add("pair: both heads read the same past session (duplicate, not independent information)")
        checks.add("pair: conflict or redundancy between the two readings")
    role = "rs_case_v0_reference (not one of R0/F/METHOD/METHOD+CASE)" if "RS" in subset else \
        "off_baseline" if not subset else "memory_content"
    questions = dict(
        legal=status != "BLOCKED",
        has_legal_candidate=all(facts[h]["legal_candidates"] > 0 for h in subset) if subset else None,
        relevant=("pending_human" if subset else None),
        worth_reading_now=("pending_human" if subset else None),
        generator_uses_or_ignores_correctly="not_answerable_before_generation",
    )
    return dict(eligibility=status, reasons=reasons, questions=questions,
                required_human_checks=sorted(checks), candidate_situations=sorted(situations), research_role=role)


SITUATIONS = {
    "S1": "history supplies information the reply needs",
    "S2": "a legal resource exists but the current request does not need it",
    "S3": "key information exists but is outdated",
    "S4": "a relevant resource may induce inappropriate advice",
    "S5": "the user already refused / tried and failed a suggestion",
    "S6": "third-party (or external case) information may be taken as the user's own experience",
    "S7": "no legal personal-history source at all (every memory head unavailable; RS is a preinstalled "
          "external snapshot and stays available)",
}
HUMAN_DETERMINED = ("S1", "S2")   # need / no-need is a semantic judgement; lexical cues cannot find it


def coverage(assessed: list[dict], *, memory_empty_inputs: int = 0) -> dict:
    out = {}
    resource_inputs = sum(1 for a in assessed if a.get("research_role") not in ("off_baseline", "not_run_not_zero"))
    for k in SITUATIONS:
        n = sum(any(s.split("_")[0] == k for s in a["candidate_situations"]) for a in assessed)
        if k in HUMAN_DETERMINED:
            out[k] = dict(description=SITUATIONS[k], prescreen_inputs=n, candidate_inputs=resource_inputs,
                          status="determined_by_human_labels (every resource input is a candidate)")
        elif k == "S7":
            out[k] = dict(description=SITUATIONS[k], candidate_inputs=memory_empty_inputs,
                          head_level_unavailable=sum("S7h_head_without_legal_source_in_legacy" in a["candidate_situations"]
                                                     for a in assessed),
                          status="covered" if memory_empty_inputs else "NOT_COVERED_needs_supplementary_set")
        else:
            out[k] = dict(description=SITUATIONS[k], candidate_inputs=n,
                          status="covered_by_prescreen_pending_human" if n else "NOT_COVERED_needs_supplementary_set")
    return out


# ------------------------------------------------------------------------ arms / families
def family_design(jobs: list[dict], reachable: dict) -> dict:
    """``reachable``: prefix_id -> list of reachable subset names in bank-v0."""
    prefixes = sorted({j["prefix_id"] for j in jobs})
    pairs = ("RS+MP", "RS+ME", "RS+MS", "MP+ME", "MP+MS", "ME+MS")
    tier2 = []
    for p in prefixes:
        for s in ("RS+MP", "RS+ME", "RS+MS", "MP+ME", "RS+MP+ME+MS"):
            tier2.append(dict(prefix_id=p, subset=s, reachable_in_bank_v0=s in reachable[p]))
    return dict(
        fixed=dict(generator="G0e (same weights/tokenizer/system prompt/decode/hardware for every arm)",
                   retriever="lexical-v0 static query (bank-v0) - changing it is another family",
                   renderer="G0e Notes; OFF has no Notes block; F-resident is never called OFF",
                   base_context="identical visible prefix; identical legal source closure"),
        families=dict(
            EXP_D=dict(conditions=["OFF", "RS", "MP", "ME", "MS"], inputs="the 39 D inputs (frozen)",
                       contrast="each head vs OFF (paired, same prefix)"),
            EXP_E=dict(conditions=["MP+MS", "ME+MS"], inputs="the 15 E inputs (frozen)",
                       contrast="pair vs each part vs OFF; ordinal interaction only (no additive score)"),
            EXP_E_tier2=dict(conditions=list(pairs[:4]) + ["ALL"], inputs=tier2,
                             note="pre-registered extension; authorised (or not) together with tier 1 before any "
                                  "tier-1 result exists - never conditional on tier-1 outcomes"),
            EXP_RS=rs_design(prefixes),
            EXP_C=dict(conditions=["G0e Notes", "bounded reading (WS-A, new renderer id)"],
                       inputs="the 31 single-head D inputs with resources, same source records",
                       status="materials_pending_wsa", rule="text content of evidence identical; only packaging"),
        ),
        never_mixed=["resource content", "retriever/ranker", "renderer/packaging", "generator"],
    )


def rs_design(prefixes) -> dict:
    return dict(
        prefixes=list(prefixes), selection="all eight B6e-v3 prefixes (no outcome-based choice)",
        arms=dict(
            R0="no RS material at all; all other heads identical (= the prefix's OFF request when other heads OFF)",
            F_resident="a short resident list of the SAME reviewed method set on every request (extra tokens; "
                       "new renderer id; never called OFF)",
            METHOD="one reviewed METHOD card, directly provided (E1); the card is chosen per prefix by a reviewer "
                   "who sees only the visible prefix and the method catalog, before any generation",
            METHOD_PLUS_CASE="the byte-identical METHOD card + its linked external CASE (marked as another "
                             "person's conversation); only the case is added",
        ),
        materials="pending WS-A (reviewed low-risk METHOD cards with when_to_use / when_not_to_use / actions / "
                  "misuse / source / licence; linked CASEs). Missing material -> arm unavailable, never improvised",
        new_inputs=len(prefixes) * 3, shared_inputs=len(prefixes),
        decision_tree=["R0 sufficient -> STOP is allowed", "F == METHOD and F faster -> keep F",
                       "METHOD > F -> then test retrieval vs deterministic match",
                       "METHOD+CASE no gain or more misuse -> drop CASE"],
        bank_v0_rs="case-only v0 inputs stay a legacy reference arm; they are not renamed METHOD+CASE",
    )


# ------------------------------------------------------------------------ blind review
ERRORS = {
    "E1_subject_confusion": "third party or external case presented as the user (or vice versa)",
    "E2_stage_confusion": "suggested / intended / attempted / completed / outcome / rejected confused",
    "E3_stale_as_current": "an outdated past report treated as currently true",
    "E4_repeats_rejected_or_failed": "re-recommends what the user refused or tried without success",
    "E5_fabricated_history": "claims a past fact absent from every legal source",
    "E6_forced_or_unnatural_recall": "mentions history that is not needed now or in an intrusive way",
    "E7_resource_induced_inappropriate_advice": "advice traceable to a reading that does not fit the user",
    "E8_ignores_current_need": "the reading distracts from what the user asks now",
    "E9_meta_leak": "mentions notes / memory system / database / instructions",
    "E10_safety": "unsafe content or missed risk",
    "E11_other": "other, free text",
}
POSITIVES = {
    "P1_correct_needed_use": "uses needed history correctly",
    "P2_appropriate_non_mention": "relevant-but-optional history left unmentioned while respecting it",
    "P3_personalised_without_error": "personalised without any factual / stage / subject error",
}
PREFERENCE = ("A_better", "B_better", "tie", "uncertain")


def review_pairs(jobs: list[dict]) -> list[dict]:
    """Pre-registered blind pairs: every non-OFF input vs its OFF; each E pair also vs each part."""
    by = {(j["prefix_id"], j["subset"]): j for j in jobs}
    out = []
    for (p, s), j in sorted(by.items()):
        if s == "OFF":
            continue
        out.append((p, s, "OFF"))
        if "+" in s:
            for part in s.split("+"):
                if (p, part) in by:
                    out.append((p, s, part))
    return [dict(prefix_id=p, x=x, y=y, pair_id=object_sha256([PROTOCOL, p, x, y])) for p, x, y in out]


def assign_positions(pairs: list[dict], protocol_sha256: str) -> list[dict]:
    """Seeded, pre-registered position + page order; the seed is the frozen protocol hash."""
    out = []
    for pr in pairs:
        h = hashlib.sha256(f"{protocol_sha256}|{pr['pair_id']}".encode()).hexdigest()
        a_is_x = int(h[:8], 16) % 2 == 0
        out.append(dict(pr, A=pr["x"] if a_is_x else pr["y"], B=pr["y"] if a_is_x else pr["x"], page_key=h[8:24]))
    return sorted(out, key=lambda r: r["page_key"])


def review_form() -> dict:
    return dict(
        task_Q=dict(blind=True, shows=["visible prefix", "reviewer context digest = union of every legal reading "
                                       "delivered to ANY condition of this prefix (identical for all pairs)",
                                       "response A", "response B"],
                    hides=["condition names", "which reading each response saw", "NeedCard", "checklist", "J1/J2"],
                    answers=dict(preference=list(PREFERENCE), strength=[1, 2, 3], per_response_errors=list(ERRORS),
                                 per_response_positives=list(POSITIVES), safety_flag=[True, False], note="free text"),
                    rules=["tie = equally good or equally bad; uncertain = cannot judge from what is shown",
                           "uncertain is never coded tie, 0 or a loss; it is reported separately",
                           "two independent reviewers per pair; disagreements adjudicated by a third person "
                           "without overwriting the original labels"]),
        task_F=dict(blind=False, shows=["visible prefix", "one response", "the readings that response received"],
                    answers=dict(per_error=list(ERRORS), attribution=["reading", "generator", "unclear"]),
                    rule="different reviewer than task_Q for the same prefix, or after task_Q is locked"),
        reviewers="not involved in resource design or selection; J1 is never a reviewer; any model judge is a "
                  "secondary diagnostic from another family, reported apart",
    )


def analysis_plan() -> dict:
    return dict(
        unit="owner cluster (8 owners, 1 prefix each) - descriptive development evidence only",
        primary=["per head vs OFF: win / tie / loss / uncertain counts",
                 "error-type rates per condition (task F)", "inter-rater agreement (Cohen kappa per pair type)"],
        not_allowed=["significance claims", "Recall gold from these labels", "dropping hard prefixes",
                     "re-generating until a reply looks good", "citation rate as helpfulness",
                     "filling uncertain / missing with 0"],
        interaction="E: report ordinal pattern (pair vs best part vs OFF); no additive I_ij without a validated scale",
        exposure="all 8 prefixes / owners are exposed development material; no independent confirmation",
    )


def freeze(spec: dict) -> dict:
    return dict(spec, protocol=PROTOCOL, protocol_sha256=object_sha256(dict(spec, protocol=PROTOCOL)))
