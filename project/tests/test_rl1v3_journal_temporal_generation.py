"""Safety and interpretation checks for new strict-date task identities."""
import pytest
from metacom_pm.rl1v3.journal.temporal_generation import legal_selection


def inputs(question='As of November 5, 2024, what was reported?'):
    task={'visible_prefix':{'turns':[{'role':'seeker','text':question}]}}
    records=[dict(record_id=str(i),owner_id='example',source_rank=i,reported_at={'date':date},
                  ready_at={'session_rank':i+1}) for i,date in enumerate(['2024-10-10','2024-11-01','2024-11-10'])]
    ranking={'owner_id':'example','method':'RET-v1-end-history','selected_record_ids':['0','2']}
    return task,records,ranking


def test_legacy_filter_preserves_choice_without_refilling():
    scope,selected=legal_selection(*inputs())
    assert scope['lower']=='2024-11-05'
    assert [r['record_id'] for r in selected]==['0']


def test_claimed_strict_ranking_cannot_supply_future_source():
    task,records,rank=inputs();rank['method']='strict-lexical-v1'
    with pytest.raises(ValueError,match='illegal source'):legal_selection(task,records,rank)


def test_month_lower_bound_and_undated_tasks_are_distinct():
    scope,selected=legal_selection(*inputs('By November 2024, what was reported?'))
    assert scope['lower']=='2024-11-01' and scope['upper']=='2024-11-30'
    with pytest.raises(ValueError,match='explicit-date'):legal_selection(*inputs('What was reported?'))
