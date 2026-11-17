"""B0: legal prefix census, owner/family-first folds, no-future-leak checks."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from metacom_pm.paper1.data.memory_source import MemorySourceUser, Session, Turn
from metacom_pm.rl1v3.prefixes import census as C
from metacom_pm.rl1v3.prefixes import exposure as X

PROJECT = Path(__file__).resolve().parents[1]
ARTIFACT = PROJECT / "data/paper1_public_memory/es_memeval_public_sanitized_runtime_artifact_v1.json"


def T(i, role, text):
    return Turn(idx=i, role=role, content=text)


def S(sid, rank, ts, roles_texts):
    return Session(session_id=sid, timestamp=ts, chronological_rank=rank,
                   turns=tuple(T(i + 1, r, x) for i, (r, x) in enumerate(roles_texts)))


def U(owner, sessions):
    return MemorySourceUser(owner_id=owner, sessions=tuple(sessions), question_groups=(),
                            summaries=(), subsequent_topics=())


def toy_user(owner="p1", future_text="FUTURE SECRET"):
    s0 = S("esc0007", 0, "2024-01-01", [("seeker", "I cannot sleep"), ("supporter", "Tell me more")])
    s1 = S(f"{owner}_conv_1", 1, "2024-01-08", [
        ("supporter", "Welcome back"),
        ("seeker", "Last time you said to try a walk"),       # 1 -> supporter: legal
        ("supporter", "How did it go?"),
        ("seeker", "It helped"),                              # 3 -> seeker: illegal
        ("seeker", "What should I do now?"),                  # 4 -> supporter: legal
        ("supporter", "Let us plan"),
        ("seeker", future_text),                              # 6 last turn: illegal
    ])
    s2 = S(f"{owner}_conv_2", 2, "2024-02-01", [("seeker", future_text), ("supporter", "ok")])
    return U(owner, [s0, s1, s2])


# ------------------------------------------------------------------ positives

def test_legal_cuts_are_seeker_followed_by_supporter():
    user = toy_user()
    assert C.legal_cut_positions(user.sessions[1]) == (1, 4)
    assert C.legal_cut_positions(user.sessions[0]) == (0,)


def test_rank0_sessions_have_no_prefixes_and_rows_are_strictly_past():
    user = toy_user()
    folds = {"fold_of_owner": {"p1": 1},
             "g1_partition_candidate": {"g1_train_owners": [], "eval_fold_of_owner": {}},
             "historical_rl1_split": {"p1": "train"}}
    rows = C.build_rows([user], folds)
    assert {r["session_id"] for r in rows} == {"p1_conv_1", "p1_conv_2"}
    for r in rows:
        assert r["visible"]["n_past_sessions"] == r["cutoff_rank"]
    first = next(r for r in rows if r["session_id"] == "p1_conv_1" and r["cut_turn"] == 1)
    assert first["visible"]["n_prefix_turns"] == 2
    assert first["visible"]["surface_cues"]["back_reference"] is True
    assert first["visible"]["days_since_prev_session"] == 7


def test_visible_features_ignore_future_turns_and_future_sessions():
    a, b = toy_user(future_text="AAA"), toy_user(future_text="totally different later text")
    for cut in (1, 4):
        assert C.visible_features(a, a.sessions[1], cut) == C.visible_features(b, b.sessions[1], cut)
        pa = C.digest(C.turn_payload(C.prefix_turns(a.sessions[1], cut)))
        pb = C.digest(C.turn_payload(C.prefix_turns(b.sessions[1], cut)))
        assert pa == pb
    # the eval-only full-session identity does change: it is not a visible field
    assert C.session_sha256(a.sessions[1]) != C.session_sha256(b.sessions[1])


def test_prefix_text_never_contains_post_cut_content():
    user = toy_user(future_text="FUTURE SECRET")
    for cut in C.legal_cut_positions(user.sessions[1]):
        text = " ".join(t.content for t in C.prefix_turns(user.sessions[1], cut))
        assert "FUTURE SECRET" not in text


def test_materialize_prefix_roundtrip_and_identity():
    user = toy_user()
    folds = {"fold_of_owner": {"p1": 1},
             "g1_partition_candidate": {"g1_train_owners": [], "eval_fold_of_owner": {}},
             "historical_rl1_split": {"p1": "train"}}
    rows = C.build_rows([user], folds)
    for r in rows:
        turns = C.materialize_prefix(r, {"p1": user})
        assert turns[-1].role == "seeker"
    assert C.audit_rows(rows, [user])["passed"]


def test_shared_transcript_merges_owners_into_one_family_group():
    shared = S("esc0042", 1, "2024-01-02", [("seeker", "same"), ("supporter", "same reply")])
    a = U("pA", [S("pA_conv_0", 0, "2024-01-01", [("seeker", "x"), ("supporter", "y")]), shared])
    b = U("pB", [S("pB_conv_0", 0, "2024-01-01", [("seeker", "z"), ("supporter", "w")]),
                 replace(shared, chronological_rank=1)])
    c = U("pC", [S("pC_conv_0", 0, "2024-01-01", [("seeker", "q"), ("supporter", "r")])])
    groups = C.owner_family_groups([a, b, c])
    assert ("pA", "pB") in groups and ("pC",) in groups
    assert C.shared_families([a, b, c])[0]["family_id"] == "esconv:esconv_0042"


def test_first_fit_keeps_groups_whole():
    out = C._first_fit([("a",), ("b", "c"), ("d",), ("e",), ("f",)], [1, 2], 3)
    assert out["b"] == out["c"]
    assert sorted(out.values()).count(1) == 3 and sorted(out.values()).count(2) == 3


def test_exposure_classifier_uses_token_boundaries():
    assert X.classify("project/outputs/pm_rl1/feedback_and_opportunity_20261105_v1") \
        == "judge_or_feedback"
    assert X.classify("project/outputs/pm_rl1/history_necessity_human_review_20261105_v1") \
        == "human_review"
    assert X.classify("project/outputs/pm_rl1/organized_initial_training_20261103_v2") == "training"
    assert X.run_dir_of("project/outputs/pm_rl1/v3/B0/prefix_census.jsonl") is None


def test_exposure_registry_counts_shared_session_for_both_owners():
    rows = X.build_registry(
        [("project/outputs/pm_rl1/history_necessity_human_review_20261105_v1", "esc9")],
        {"pA": ["esc9", "pA_conv_1"], "pB": ["esc9"]}, {"pA": "train", "pB": "dev"},
        {"pA": 1, "pB": 2})
    owners = {r["owner_id"]: r for r in rows if r["record"] == "owner"}
    assert owners["pA"]["sessions_in_human_review_artifacts"] == 1
    assert owners["pB"]["sessions_in_human_review_artifacts"] == 1
    assert all(r["unexposed_confirmation_eligible"] is False for r in owners.values())


# ------------------------------------------------------------------ negatives

def test_cut_at_seeker_followed_by_seeker_is_rejected():
    with pytest.raises(ValueError):
        C.prefix_turns(toy_user().sessions[1], 3)


def test_cut_at_last_turn_is_rejected():
    with pytest.raises(ValueError):
        C.prefix_turns(toy_user().sessions[1], 6)


def test_cut_at_supporter_turn_is_rejected():
    with pytest.raises(ValueError):
        C.prefix_turns(toy_user().sessions[1], 2)


def test_tampered_prefix_hash_is_rejected():
    user = toy_user()
    folds = {"fold_of_owner": {"p1": 1},
             "g1_partition_candidate": {"g1_train_owners": [], "eval_fold_of_owner": {}},
             "historical_rl1_split": {"p1": "train"}}
    row = dict(C.build_rows([user], folds)[0])
    row["prefix_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        C.materialize_prefix(row, {"p1": user})


def test_wrong_cutoff_rank_is_rejected():
    user = toy_user()
    folds = {"fold_of_owner": {"p1": 1},
             "g1_partition_candidate": {"g1_train_owners": [], "eval_fold_of_owner": {}},
             "historical_rl1_split": {"p1": "train"}}
    row = dict(C.build_rows([user], folds)[0])
    row["cutoff_rank"] += 1
    with pytest.raises(ValueError):
        C.materialize_prefix(row, {"p1": user})


def test_group_too_large_for_any_fold_fails_closed():
    with pytest.raises(ValueError):
        C._first_fit([("a", "b", "c", "d")], [1, 2], 3)


def test_family_straddling_fixed_heldout_fold_fails_closed():
    with pytest.raises(ValueError):
        C._units([("p4", "p9")], ("p4", "p7", "p14"), C.FOLD_SALT)


def test_nonconsecutive_ranks_fail_closed():
    user = toy_user()
    broken = U("p1", [replace(user.sessions[1], chronological_rank=5)])
    folds = {"fold_of_owner": {"p1": 1},
             "g1_partition_candidate": {"g1_train_owners": [], "eval_fold_of_owner": {}},
             "historical_rl1_split": {"p1": "train"}}
    with pytest.raises(ValueError):
        C.build_rows([broken], folds)


# --------------------------------------------------------------- real source

@pytest.fixture(scope="module")
def real():
    if not ARTIFACT.exists():
        pytest.skip("sanitized public artifact not present")
    users = C.load_users(ARTIFACT)
    return users, C.build_census(users)


def test_real_census_counts_and_audit(real):
    users, res = real
    t = res.summary["totals"]
    assert (t["owners"], t["sessions"], t["sessions_rank_ge1"]) == (18, 401, 383)
    assert t["legal_cuts"] == len(res.rows) == 4119
    assert res.summary["audit"]["passed"]


def test_real_folds_are_owner_disjoint_family_closed_and_fixed(real):
    users, res = real
    folds = res.folds
    assert folds["folds"]["6"] == ["p4", "p7", "p14"]
    all_owners = [o for f in folds["folds"].values() for o in f]
    assert len(all_owners) == len(set(all_owners)) == 18
    assert all(len(v) == 3 for v in folds["folds"].values())
    for group in C.owner_family_groups(users):
        assert len({folds["fold_of_owner"][o] for o in group}) == 1
    assert folds["fold_of_owner"]["p13"] == folds["fold_of_owner"]["p18"]
    g1 = folds["g1_partition_candidate"]
    train, evals = set(g1["g1_train_owners"]), set(g1["eval_fold_of_owner"])
    assert not train & evals and len(train | evals) == 18
    assert {"p1", "p15", "p18"} <= train and not train & {"p4", "p7", "p14"}
    for group in C.owner_family_groups(users):
        assert set(group) <= train or set(group) <= evals


def test_real_rows_inherit_owner_fold_and_ids_unique(real):
    _, res = real
    ids = [r["prefix_id"] for r in res.rows]
    assert len(ids) == len(set(ids))
    for r in res.rows:
        assert r["assignment"]["fold"] == res.folds["fold_of_owner"][r["owner_id"]]
        assert r["sampling"]["natural_weight"] == 1.0


def test_real_census_is_deterministic(real):
    users, res = real
    again = C.build_census(users)
    assert C.digest(list(again.rows)) == C.digest(list(res.rows))
    assert C.digest(again.folds) == C.digest(res.folds)


def test_prefix_exposure_records_only_for_strong_category_hits():
    rows = [dict(prefix_id="n1", owner_id="pA", session_id="s", cut_turn=1),
            dict(prefix_id="n2", owner_id="pA", session_id="s", cut_turn=3)]
    recs = X.prefix_exposure_records(
        rows, {"n1": "a" * 64, "n2": "b" * 64},
        [("project/outputs/pm_rl1/human_acceptance_20261014_v1", "a" * 64)])
    assert [r["prefix_id"] for r in recs] == ["n1"]
    assert recs[0]["categories"] == ["human_review"]


def test_legacy_identity_matches_historical_rl1_prefixspec():
    user = toy_user()
    s = user.sessions[1]
    a = X.legacy_rl1_prefix_identity("p1", s.session_id, 1, 1, s.timestamp, "train",
                                     C.prefix_turns(s, 1))
    b = X.legacy_rl1_prefix_identity("p1", s.session_id, 1, 1, s.timestamp, "dev",
                                     C.prefix_turns(s, 1))
    assert len(a) == 64 and a != b
