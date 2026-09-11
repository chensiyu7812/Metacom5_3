import copy
from dataclasses import replace
import json
from pathlib import Path

import pytest

from metacom_pm.io import canonical_json, sha256_file, sha256_text
from metacom_pm.paper1.contracts import TaskType
from metacom_pm.paper1.data.memory_source import Target, user_from_dict
from metacom_pm.paper1.evaluation.human_reference import (
    build_dg_reference, read_rating_json, reference_from_view, render_rating_html,
    render_session, upgrade_human_sheet, validate_rated_sheet, validate_reference_catalog,
)
from metacom_pm.paper1.evaluation.pairwise_teacher import (
    DG_REFERENCE_INSTRUCTION, build_pairwise_teacher_prompt, pairwise_teacher_identity_payload,
    parse_pairwise_teacher_response,
)

PROJECT = Path(__file__).resolve().parents[1]
AUTH = PROJECT / "data/paper1_authority"


def _user():
    return user_from_dict({
        "owner_id": "test_owner",
        "sessions": [
            {"session_id": f"session_{n}", "timestamp": f"2025-01-0{n+1}", "chronological_rank": n,
             "turns": [{"idx": 0, "role": "seeker", "content": text}]}
            for n, text in enumerate(["The old arrangement.", "The arrangement changed.", "FUTURE_DO_NOT_SHOW"])
        ],
        "question_groups": [], "summaries": [], "subsequent_topics": [{"idx": 1}],
    })


def _target():
    return Target(target_id="test_owner::dg::1", task_type=TaskType.DIALOGUE_GENERATION,
                  owner_id="test_owner", primary_group_key="test_owner::dg::1", cutoff_rank=2, visible_query_text=None)


def _reference():
    u = _user()
    excerpt = render_session(u.sessions[0].timestamp, [{"role": "seeker", "content": u.sessions[0].turns[0].content}])
    return build_dg_reference(user=u, target=_target(), excerpt=excerpt)


def _sheet():
    view, _ = _reference()
    original = {
        "protocol": "paper1-pairwise-teacher-human-sheet-v1", "rater_id": "RATER_A",
        "status": "READY_FOR_INDEPENDENT_RATING", "instrument": {},
        "items": [{"item_number": 1, "presentation_id": "test_presentation", "task": "DG",
                   "task_input": "Visible test input.", "reference_material": view["excerpt"],
                   "response_A": "Anonymous first test response.", "response_B": "Anonymous second test response.",
                   "verdict": None, "rationale": None}],
    }
    instrument = json.loads((AUTH / "paper1_pairwise_teacher_human_instrument_20260908_v2.json").read_text())
    return upgrade_human_sheet(original, instrument=instrument,
                               presentation_targets={"test_presentation": "test_owner::dg::1"},
                               dg_views={"test_owner::dg::1": view})


def test_complete_past_evidence_includes_updates_and_excludes_future_and_identity_fields():
    view, audit = _reference()
    text = reference_from_view(view)
    assert "The arrangement changed." in text
    assert "FUTURE_DO_NOT_SHOW" not in text
    assert audit["source_session_ranks"] == [0, 1]
    assert set(view) == {"excerpt", "sessions"}
    assert all(set(s) == {"timestamp", "turns"} for s in view["sessions"])
    assert "test_owner" not in canonical_json(view)
    assert "session_0" not in canonical_json(view)


def test_reference_rejects_wrong_owner_missing_rank_and_future_in_excerpt():
    view, _ = _reference()
    with pytest.raises(ValueError, match="owner/task"):
        build_dg_reference(user=_user(), target=replace(_target(), owner_id="wrong"), excerpt=view["excerpt"])
    u = _user()
    with pytest.raises(ValueError, match="ranks"):
        build_dg_reference(user=replace(u, sessions=(u.sessions[0], u.sessions[2])), target=_target(), excerpt=view["excerpt"])
    future_excerpt = render_session(u.sessions[2].timestamp, [{"role": "seeker", "content": "FUTURE_DO_NOT_SHOW"}])
    with pytest.raises(ValueError, match="excerpt"):
        build_dg_reference(user=u, target=_target(), excerpt=future_excerpt)


def test_human_display_and_teacher_receive_identical_reference():
    sheet = _sheet()
    item = sheet["items"][0]
    view = sheet["reference_catalog"][item["reference_id"]]
    assert reference_from_view(view) == item["reference_material"]
    prompt = build_pairwise_teacher_prompt(task="DG", task_input=item["task_input"],
        response_a=item["response_A"], response_b=item["response_B"], reference_material=item["reference_material"])
    assert item["reference_material"] in prompt
    assert DG_REFERENCE_INSTRUCTION in prompt
    broken = copy.deepcopy(sheet)
    broken["reference_catalog"][item["reference_id"]]["sessions"].pop()
    with pytest.raises(ValueError, match="differ"):
        validate_reference_catalog(broken)


def test_roundtrip_only_rating_fields_editable_and_partial_is_not_complete():
    original = _sheet()
    with pytest.raises(ValueError, match="every item"):
        validate_rated_sheet(original, original)
    assert validate_rated_sheet(original, original, require_complete=False)["completed"] == 0
    rated = copy.deepcopy(original)
    rated["items"][0].update(verdict="uncertain", rationale="Test fixture only; insufficient evidence.")
    assert validate_rated_sheet(original, rated) == {"presentations": 1, "completed": 1}
    assert original["items"][0]["verdict"] is None
    for location in ("response_A", "reference_material", "task_input", "presentation_id"):
        changed = copy.deepcopy(rated)
        changed["items"][0][location] += " changed"
        with pytest.raises(ValueError, match="changed"):
            validate_rated_sheet(original, changed)
    changed = copy.deepcopy(rated)
    changed["rater_id"] = "RATER_B"
    with pytest.raises(ValueError, match="changed"):
        validate_rated_sheet(original, changed)
    with pytest.raises(ValueError, match="rated original"):
        upgrade_human_sheet(rated, instrument={}, presentation_targets={}, dg_views={})


@pytest.mark.parametrize("verdict,rationale", [("tie", "x"), ([], "x"), ("equivalent", " "), ("A_better", 1)])
def test_invalid_or_blank_human_rating_is_rejected(verdict, rationale):
    original = _sheet()
    rated = copy.deepcopy(original)
    rated["items"][0].update(verdict=verdict, rationale=rationale)
    with pytest.raises(ValueError):
        validate_rated_sheet(original, rated)


def test_duplicate_human_or_teacher_json_keys_fail_closed(tmp_path):
    raw = '{"verdict":"A_better","verdict":"B_better","rationale":"conflict"}'
    with pytest.raises(ValueError, match="duplicate"):
        parse_pairwise_teacher_response(raw)
    with pytest.raises(ValueError, match="duplicate"):
        parse_pairwise_teacher_response('{"verdict":"equivalent","verdict":"equivalent","rationale":"x"}')
    with pytest.raises(ValueError):
        parse_pairwise_teacher_response('{"verdict":[],"rationale":"x"}')
    p = tmp_path / "rating.json"
    p.write_text(raw)
    with pytest.raises(ValueError, match="duplicate"):
        read_rating_json(p)


def test_html_embeds_untrusted_dialogue_as_data_and_has_no_network_dependency():
    sheet = _sheet()
    attack = '</script><script>window.INJECTED=true</script>&\u2028'
    sheet["items"][0]["response_A"] = attack
    html = render_rating_html(sheet, sheet_sha256="test-hash", filename_stem="fixture")
    assert attack not in html
    payload = html.split('<script id="form-data" type="application/json">', 1)[1].split('</script>', 1)[0]
    assert json.loads(payload)["sheet"]["items"][0]["response_A"] == attack
    assert "connect-src 'none'" in html
    assert "fetch(" not in html and "XMLHttpRequest" not in html and '<script src=' not in html


def test_active_v2_contracts_bind_reference_parser_and_raw_primary_adjudication():
    manifest = json.loads((AUTH / "paper1_pairwise_teacher_human_sheet_manifest_20260908_v2.json").read_text())
    identity_path = AUTH / "paper1_gemini_pairwise_teacher_identity_20260908_v2.json"
    identity = json.loads(identity_path.read_text())
    design = json.loads((AUTH / "paper1_pairwise_teacher_human_reference_design_20260908_v2.json").read_text())
    assert manifest["teacher_identity_sha256"] == sha256_file(identity_path)
    for k, v in pairwise_teacher_identity_payload().items():
        assert identity["prompt_identity"][k] == v
    assert identity["parser"]["source_sha256"] == sha256_file(PROJECT / "src/metacom_pm/paper1/evaluation/pairwise_teacher.py")
    assert manifest["validation"]["DG_candidate_instances_checked"] == 63
    assert manifest["validation"]["new_ratings_created"] == 0
    assert len(manifest["teacher_request_identities"]) == 96
    assert len({r["presentation_id"] for r in manifest["teacher_request_identities"]}) == 96
    for row in manifest["DG_reference_lineage"]:
        assert row["source_session_ranks"] == list(range(row["cutoff_rank"]))
    assert design["disagreement"]["adjudication_is_separate_from_inter_rater_agreement"]
    assert design["disagreement"]["before_candidate_teacher_verdicts_seen"]
    assert design["disagreement"]["unresolved_consensus"] == "uncertain"
    assert identity["budget"]["paid_calls_authorized_by_this_identity"] is False
