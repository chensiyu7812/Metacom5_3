from __future__ import annotations

import json
from pathlib import Path

import pytest

from metacom_pm.paper1.evaluation.static_official_scoring import (
    OfficialParseError, PINNED_JSON_REPAIR_VERSION, PRIMARY_METRIC, VENDOR_PYTHON,
    load_json_repair, parse_official_qa, parse_official_reply, parse_official_summary,
)

VENDOR_REQUIREMENTS = Path(__file__).resolve().parents[1] / "outputs/vendor_es_memeval/requirements.txt"


def test_vendored_json_repair_matches_the_upstream_pin():
    assert f"json-repair=={PINNED_JSON_REPAIR_VERSION}" in VENDOR_REQUIREMENTS.read_text()
    assert (VENDOR_PYTHON / f"json_repair-{PINNED_JSON_REPAIR_VERSION}.dist-info").is_dir()
    assert load_json_repair().loads('{"score": 1}') == {"score": 1}


def test_qa_parser_takes_the_first_zero_to_two_digit_anywhere_in_the_reply():
    # Upstream searches the whole message, so prose before the score still parses.
    assert parse_official_qa("Score: 2").score == 2
    assert parse_official_qa("The answer is fine.\nScore: 1").score == 1
    assert parse_official_qa("9 8 7 0").score == 0


def test_qa_parser_failure_is_an_error_and_never_a_zero():
    with pytest.raises(OfficialParseError):
        parse_official_qa("Score: unavailable")
    with pytest.raises(OfficialParseError):
        parse_official_qa("")


def test_qa_primary_normalizes_the_official_zero_to_two_scale():
    assert parse_official_reply("qa", "Score: 0")["quality"] == 0.0
    assert parse_official_reply("qa", "Score: 1")["quality"] == 0.5
    assert parse_official_reply("qa", "Score: 2")["quality"] == 1.0
    assert parse_official_reply("qa", "Score: 2")["primary_metric"] == PRIMARY_METRIC["qa"]


def summary_reply(score=4, reference=4, generated=5, recalled=3, **extra):
    return json.dumps({"score": score, "num_events_reference": reference,
                       "num_events_generated": generated, "num_events_recalled": recalled,
                       "hallucination": False, **extra})


def test_summary_parser_reproduces_the_upstream_event_ratios():
    parsed = parse_official_summary(summary_reply())
    assert (parsed.events_precision, parsed.events_recall) == (3 / 5, 3 / 4)
    assert parsed.events_f1 == pytest.approx(2 * (3 / 4) * (3 / 5) / ((3 / 4) + (3 / 5)))
    assert parse_official_reply("summary", summary_reply())["quality"] == parsed.events_f1


def test_summary_zero_denominators_follow_upstream_and_do_not_divide():
    parsed = parse_official_summary(summary_reply(reference=0, generated=0, recalled=0))
    assert (parsed.events_precision, parsed.events_recall, parsed.events_f1) == (0, 0, 0)


def test_summary_parser_uses_json_repair_on_truncated_official_json():
    # json_repair is exactly why upstream tolerates an unterminated object.
    parsed = parse_official_summary(
        '{"score": 5, "num_events_reference": 2, "num_events_generated": 2, "num_events_recalled": 2')
    assert (parsed.score, parsed.events_f1) == (5, 1.0)


def test_summary_parse_failure_is_disclosed_missingness_not_a_zero_score():
    for reply in ["", "I cannot evaluate this.", '{"score": "high"}', '{"num_events_reference": 3}']:
        with pytest.raises(OfficialParseError):
            parse_official_summary(reply)


def test_only_the_two_static_tasks_are_scored_here():
    with pytest.raises(ValueError, match="qa and summary"):
        parse_official_reply("dialogue_generation", "Score: 2")
