"""Reproduce the pinned official QA/Summary judge parsers and primary metrics.

The upstream harness is not imported or executed. These functions mirror the
exact parsing steps of `qa_experiment.llm_as_a_judge` and
`sum_experiment.llm_as_a_judge` at commit 6926242, including upstream's own
failure boundary: a reply the official parser cannot read yields no score at
all. A parse failure is never silently converted into zero, and the caller must
keep it as disclosed missingness.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

# The upstream requirements pin json-repair==0.52.4. It is vendored beside the
# calibration package so the frozen Generator environment stays byte-identical.
VENDOR_PYTHON = Path(__file__).resolve().parents[4] / "outputs/paper1_calibration/vendor_python"
PINNED_JSON_REPAIR_VERSION = "0.52.4"

# QA normalizes the official 0-2 integer; Summary Event F1 is already a ratio.
QA_MAX_SCORE = 2
PRIMARY_METRIC = {"qa": "official_llm_as_a_judge_score_normalized", "summary": "official_event_f1"}


class OfficialParseError(ValueError):
    """The official parser could not read a judge reply. Never a zero score."""


def load_json_repair():
    """Import the upstream-pinned json_repair without mutating any environment."""
    if str(VENDOR_PYTHON) not in sys.path:
        sys.path.insert(0, str(VENDOR_PYTHON))
    import json_repair

    installed = Path(json_repair.__file__).resolve()
    if VENDOR_PYTHON not in installed.parents:
        raise RuntimeError("json_repair resolved outside the pinned vendored copy")
    return json_repair


@dataclass(frozen=True)
class OfficialQaScore:
    score: int

    @property
    def primary(self) -> float:
        return self.score / QA_MAX_SCORE


@dataclass(frozen=True)
class OfficialSummaryScore:
    score: int
    events_reference: int
    events_generated: int
    events_recalled: int
    events_precision: float
    events_recall: float
    events_f1: float

    @property
    def primary(self) -> float:
        return self.events_f1


def parse_official_qa(reply: str) -> OfficialQaScore:
    """Upstream `re.search(r"[0-2]", message.text())` on the whole reply."""
    match = re.search(r"[0-2]", reply)
    if match is None:
        raise OfficialParseError("official QA parser found no [0-2] digit")
    return OfficialQaScore(score=int(match.group()))


def parse_official_summary(reply: str) -> OfficialSummaryScore:
    """Upstream json_repair.loads plus the four integer fields and ratios.

    Upstream writes `except ValueError | json.JSONDecodeError`, which is not a
    catchable expression, so on malformed content its own handler raises
    TypeError rather than returning the empty judgement. We keep the same
    inputs-to-outputs behaviour and record every failure explicitly instead of
    reproducing that crash.
    """
    json_repair = load_json_repair()
    try:
        response = json_repair.loads(reply)
        score = int(response["score"])
        reference = int(response["num_events_reference"])
        generated = int(response["num_events_generated"])
        recalled = int(response["num_events_recalled"])
    except Exception as exc:  # upstream LlmAsAJudgeError boundary
        raise OfficialParseError(f"official Summary parser failed: {type(exc).__name__}: {exc}") from exc
    precision = recalled / generated if generated > 0 else 0
    recall = recalled / reference if reference > 0 else 0
    f1 = 2 * recall * precision / (recall + precision) if recall + precision > 0 else 0
    return OfficialSummaryScore(
        score=score, events_reference=reference, events_generated=generated,
        events_recalled=recalled, events_precision=precision, events_recall=recall, events_f1=f1)


def parse_official_reply(task: str, reply: str) -> dict:
    """Parsed official fields plus the task primary metric used for amount choice."""
    if task == "qa":
        qa = parse_official_qa(reply)
        return {"task": "qa", "official_score": qa.score, "primary_metric": PRIMARY_METRIC["qa"],
                "quality": qa.primary}
    if task == "summary":
        summary = parse_official_summary(reply)
        return {"task": "summary", "official_score": summary.score,
                "events_reference": summary.events_reference,
                "events_generated": summary.events_generated,
                "events_recalled": summary.events_recalled,
                "events_precision": summary.events_precision,
                "events_recall": summary.events_recall,
                "events_f1": summary.events_f1,
                "primary_metric": PRIMARY_METRIC["summary"], "quality": summary.primary}
    raise ValueError("static amount calibration scores only qa and summary")


__all__ = [
    "OfficialParseError", "OfficialQaScore", "OfficialSummaryScore", "PINNED_JSON_REPAIR_VERSION",
    "PRIMARY_METRIC", "QA_MAX_SCORE", "VENDOR_PYTHON", "load_json_repair",
    "parse_official_qa", "parse_official_reply", "parse_official_summary",
]
