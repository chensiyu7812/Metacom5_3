"""Prepared research exception; never grants production measurement qualification.

No credentials, providers or data files are accessed on import. The researcher
must approve the complete hashed proposal before a real episode can be built.
"""
from copy import deepcopy

from .calibration_workflow import stamp, verify_identity
from .natural_runner import _EpisodeLoop
from .schema import Score, digest

DIAGNOSTIC = "WEAK_PROXY_DIAGNOSTIC_V1"
VERSION = "pmrl1-four-head-diagnostic-20261020-v1"
AMBIGUITY_TYPES = (
    "interpretation_boundary", "severity_boundary", "quality_adjacent_anchor",
    "identity_clarification_contract_gap",
)
CHECKING_ERROR_TYPES = (
    "missed_checkable_claim", "wrong_subject_or_time", "wrong_source_relation",
    "unfounded_accusation", "severity_criterion_violation", "unsupported_equivalence_difference",
)
DISPOSITIONS = {
    "reviewed_no_confirmed_issue": "allow_flagged_proxy",
    "reviewer_ambiguity": "allow_flagged_proxy",
    "confirmed_checking_error": "stop_before_update",
    "model_unknown": "pending_stop_stage",
    "technical_failure": "stop_stage",
    "not_reviewed": "pending_review",
}


def require_approval(protocol, approval):
    verify_identity(protocol)
    expected = dict(
        status="APPROVED", protocol_identity=protocol["identity"],
        scope=DIAGNOSTIC, natural_updates_authorized=True,
        model_requests_authorized=True, feedback_dispositions=DISPOSITIONS,
        old_stops_released=False, reward_qualified=False,
        max_trajectories=32, max_updates=2, retries=0,
        initialization=protocol["initialization"],
        limits=protocol["limits"],
    )
    if not isinstance(approval, dict) or any(approval.get(k) != v for k, v in expected.items()):
        raise ValueError("complete explicit diagnostic approval required; proposal is inactive")
    if not approval.get("user_authorization_reference"):
        raise ValueError("missing researcher authorization provenance")
    for key, value in protocol.get("approval_scope", {}).items():
        if approval.get(key) != value:
            raise ValueError("credential, data, money or management approval missing")
    if protocol.get("feedback_dispositions") != DISPOSITIONS:
        raise ValueError("feedback exceptions differ from prepared policy")
    if protocol.get("reward") != {"alpha": 1, "lambda": .05, "gamma": 1, "resource_tokens": 2048}:
        raise ValueError("frozen reward changed")
    if protocol.get("initialization") not in ("random_seed17_diagnostic_only", "original_BC"):
        raise ValueError("unknown initialization; never pretend random is BC")
    if protocol["initialization"] == "original_BC":
        raise ValueError("original BC checkpoint is not available in this diagnostic package")
    return digest(approval)


def feedback_disposition(record, review):
    """Keep mechanical, model and analyst states separate; no score repairs."""
    technical = record.get("measurement_status")
    if technical == "technical_failure":
        if record.get("q") is not None or record.get("m") is not None:
            raise ValueError("technical failure cannot carry scores")
        return "stop_stage"
    if technical == "semantic_uncertainty":
        if record.get("q") is not None or record.get("m") is not None:
            raise ValueError("missing/model-unknown feedback cannot carry scores")
        return "pending_stop_stage"
    if technical != "measured_candidate":
        raise ValueError("unknown mechanical status; not a review ambiguity")
    Score(record["q"], record["m"], ("mechanically-validated-record",))
    if review is None:
        return "pending_review"
    if review.get("record_identity") != digest(record):
        raise ValueError("review bound to different raw feedback")
    if review.get("independent_human_reference") is not False:
        raise ValueError("coordinator review is not independent human assessment")
    errors = review.get("confirmed_errors")
    ambiguities = review.get("ambiguities")
    if not isinstance(errors, list) or not isinstance(ambiguities, list):
        raise ValueError("explicit separate error/ambiguity lists required")
    for issue in ambiguities:
        if (not isinstance(issue, dict) or issue.get("type") not in AMBIGUITY_TYPES
                or not issue.get("claim") or not issue.get("reason")
                or not issue.get("original_criterion")):
            raise ValueError("ambiguity needs an approved category, claim, criterion and reason")
    for error in errors:
        if any(not error.get(k) for k in ("claim", "source_ids", "original_criterion", "reason")):
            raise ValueError("confirmed error requires claim, source and original criterion")
        if (error.get("target") != "measurement_decision"
                or error.get("decision_error_type") not in CHECKING_ERROR_TYPES):
            raise ValueError("identify a checking error, not merely a bad generated reply or adjacent q")
    if errors:
        return "stop_before_update"  # Ambiguity never cancels a confirmed error.
    if review.get("status") not in ("reviewed_no_confirmed_issue", "reviewer_ambiguity"):
        return "pending_review"
    if bool(ambiguities) != (review["status"] == "reviewer_ambiguity"):
        raise ValueError("review status/ambiguity mismatch")
    return "allow_flagged_proxy"


class DiagnosticEpisode(_EpisodeLoop):
    """Reuse the natural state machine without forging a qualified freeze."""
    feedback_scope = DIAGNOSTIC

    def __init__(self, spec, renderer, *, evidence, protocol, approval,
                 trajectory_id, review_lookup):
        approval_id = require_approval(protocol, approval)
        item = protocol["trajectory_manifest"].get(trajectory_id)
        if (item is None or item["prefix_identity"] != spec.prefix.identity
                or item["split"] != spec.prefix.split
                or spec.prefix.split not in ("train", "dev")
                or spec.executor_identity != protocol["executor_identity"]
                or spec.judge_identity != protocol["measurement_identity"]
                or renderer.identity != protocol["renderer_identity"]
                or spec.draw_identity != protocol["draw_identity"]
                or spec.resource_budget != 2048 or spec.alpha != 1 or spec.cost_weight != .05
                or digest(evidence) != item["evidence_identity"]):
            raise ValueError("diagnostic episode differs from locked manifest")
        if item.get("spec_identity", spec.identity) != spec.identity:
            raise ValueError("locked inventory or episode changed")
        self.protocol, self.approval = deepcopy(protocol), deepcopy(approval)
        self.review_lookup = review_lookup
        self.feedback_diagnostics = {}
        snapshot = dict(identity=protocol["identity"], runtime_identity=spec.judge_identity,
                        rubric_identity=protocol["rubric_identity"],
                        purpose="PROTOCOL_SNAPSHOT_NOT_MEASUREMENT_FREEZE")
        unqualified = dict(identity=approval_id, status="UNQUALIFIED_PROXY_ONLY",
                           reward_qualified=False)
        super().__init__(spec, renderer, evidence=evidence, freeze=snapshot,
                         qualification=unqualified, trajectory_id=trajectory_id)

    def _score(self, req, response, measure):
        def gated(binding, evidence, reply):
            record = measure(binding, evidence, reply)
            if record is None:
                return None
            if record.get("binding") != binding:
                raise ValueError("feedback bound to wrong input")
            review = self.review_lookup(digest(record))
            if review and review.get("confirmed_errors"):
                from .evidence import evidence_turns
                turns = evidence_turns(evidence)
                for err in review["confirmed_errors"]:
                    for sid in err.get("source_ids", ()):
                        quote = err.get("source_quotes", {}).get(sid)
                        if sid not in turns or not quote or quote not in turns[sid]["text"]:
                            raise ValueError("confirmed error lacks exact legal source quotation")
            disposition = feedback_disposition(record, review)
            self.feedback_diagnostics[digest(record)] = dict(
                record=deepcopy(record), review=deepcopy(review), disposition=disposition,
                original_q=record.get("q"), original_m=record.get("m"),
                qualification_eligible=False)
            if disposition == "allow_flagged_proxy":
                return record
            if disposition == "stop_before_update":
                self.env.fail("confirmed_checking_error")
            if disposition == "stop_stage":
                self.env.fail("technical_measurement_failure")
            return None
        # Re-check the review even after an earlier poll admitted the same score.
        self.scores.clear()
        return super()._score(req, response, gated)

    def snapshot(self):
        base = super().snapshot()
        base.pop("identity")
        base["feedback_diagnostics"] = deepcopy(self.feedback_diagnostics)
        return stamp(base)

    def restore(self, saved):
        verify_identity(saved)
        base = deepcopy(saved)
        self.feedback_diagnostics = base.pop("feedback_diagnostics")
        base.pop("identity")
        # Parent's final identity comparison calls the virtual snapshot().
        original = self.snapshot
        self.snapshot = lambda: _EpisodeLoop.snapshot(self)
        try:
            super().restore(stamp(base))
        finally:
            self.snapshot = original
        if digest(self.snapshot()) != digest(saved):
            raise ValueError("diagnostic feedback history changed during restore")

    def result(self):
        value = super().result()
        value.pop("identity")
        value.update(scope=DIAGNOSTIC, reward_qualified=False,
                     feedback_diagnostics=deepcopy(self.feedback_diagnostics))
        return stamp(value)

    def require_update_feedback(self):
        """Recheck every used record immediately before an optimizer event."""
        if self.env.phase != "terminal" or not self.feedback_diagnostics:
            raise ValueError("complete reviewed feedback required")
        for entry in self.feedback_diagnostics.values():
            rec = entry["record"]
            review = self.review_lookup(digest(rec))
            if review != entry["review"] or feedback_disposition(rec, review) != "allow_flagged_proxy":
                raise ValueError("feedback review changed or is not allowed for update")
