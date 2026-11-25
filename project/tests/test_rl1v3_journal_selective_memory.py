"""Observable-only policy boundary and correlated-unknown regression checks."""
import importlib.util
from pathlib import Path
import pytest
from metacom_pm.rl1v3.journal.selective_memory import choose,visible_features


def test_explicit_current_report_overrides_historical_mention():
    q='Here is my earlier statement, supplied in full: “I prefer quiet mornings.” Please briefly reflect that reported fact.'
    assert choose(q)=='STOP'


def test_unresolved_history_and_missing_current_text_fall_back_to_memory():
    assert choose('What did I say in our earlier conversation?')=='MS'
    assert choose('Please briefly reflect that reported fact.')=='MS'


def test_additional_history_question_is_not_covered_by_current_quote():
    q='Here is my earlier statement: “I prefer quiet mornings.” Please briefly reflect that reported fact. Also, what did I say in other conversations?'
    assert choose(q)=='MS'


def test_history_words_inside_quoted_evidence_are_not_missing_information():
    q='Here is my earlier statement: “Before that I was unsure.” Please briefly acknowledge what I reported.'
    assert choose(q)=='STOP'
    assert not visible_features(q)['separate_history_request']


def test_policy_rejects_metadata_envelopes():
    with pytest.raises(TypeError):choose(dict(query='hello',owner_id='x',gold='secret',needs_stratum='none'))


def test_unscoped_quoted_material_does_not_establish_sufficiency():
    assert choose('Here is my earlier statement: “I prefer quiet mornings.” What should I remember from last time?')=='MS'


def test_shared_unknown_is_not_two_independent_outcomes():
    path=Path(__file__).parents[1]/'scripts/rl1v3/journal_selective_diagnostic.py'
    spec=importlib.util.spec_from_file_location('selection_diagnostic',path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    assert m.interval_difference([0,1],[0,1],shared=True)==[0,0]
    assert m.interval_difference([0,1],[0,1])==[-1,1]
    assert m.interval_difference(None,[1,1]) is None
