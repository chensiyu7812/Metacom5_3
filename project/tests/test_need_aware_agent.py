"""NAA B-line retrieval and four-arm contract regression (CPU fixtures)."""
import json

import pytest

from metacom_pm.need_aware.agent import arms as ARMS
from metacom_pm.need_aware.agent.retrieval import OwnerIndex, RetrievalSpec, query_text, recency
from metacom_pm.need_aware.data.contracts import RuntimeTask, digest
from metacom_pm.need_aware.data.history import HistoryResolver
from metacom_pm.need_aware.memory import reader as R
from metacom_pm.need_aware.memory.writer import MemoryWriter, write_for_task

OWNER, FAM = 'pm2:7', 'pm2-famx'
MESSAGES = [{'role': 'system', 'content': 'persona profile: secret hobby zither'},
            {'role': 'user', 'content': 'I love hiking in the Alps every summer.'},
            {'role': 'assistant', 'content': 'The Alps are lovely in summer.'},
            {'role': 'user', 'content': 'My favourite food is ramen with extra garlic.'},
            {'role': 'assistant', 'content': 'Ramen with garlic is a classic.'},
            {'role': 'user', 'content': 'Lately work has been busy.'},
            {'role': 'assistant', 'content': 'That sounds tiring.'}]
OPTIONS = [{'id': 'A', 'text': 'Suggest zither concerts.'}, {'id': 'B', 'text': 'Suggest ramen spots.'},
           {'id': 'C', 'text': 'Suggest beach resorts.'}, {'id': 'D', 'text': 'Suggest museums.'}]


def runtime(tmp_path, **over):
    body = json.dumps(dict(owner_id=OWNER, source_family=FAM, messages=MESSAGES)).encode()
    (tmp_path / 'histories').mkdir(exist_ok=True)
    (tmp_path / 'histories' / f'{FAM}.json').write_bytes(body)
    import hashlib
    fields = dict(task_id='t-1', dataset_revision='rev', split='val', persona_group=OWNER, source_family=FAM,
                  history_ref=f'histories/{FAM}.json', history_sha256=hashlib.sha256(body).hexdigest(), cutoff=7,
                  current_messages=[], user_query='Where should I eat dinner tonight?', task_mode='mcq', options=OPTIONS)
    fields.update(over)
    return RuntimeTask(**fields), HistoryResolver(tmp_path)


def count(text):
    return len(text.split())


def test_query_uses_visible_request_only_not_options(tmp_path):
    task, _ = runtime(tmp_path)
    q = query_text(task)
    assert q == task.user_query and not any(o['text'] in q for o in OPTIONS)
    with_other_options, _ = runtime(tmp_path, options=[dict(o, text='zither ' * 5) for o in OPTIONS])
    assert query_text(with_other_options) == q


def test_wrong_persona_future_and_gold_fields_are_blocked(tmp_path):
    task, resolver = runtime(tmp_path)
    with pytest.raises(ValueError, match='owner'):
        resolver.resolve(RuntimeTask(**{**task.to_dict(), 'persona_group': 'pm2:8'}))
    with pytest.raises(ValueError, match='cutoff'):
        resolver.resolve(RuntimeTask(**{**task.to_dict(), 'cutoff': 99}))
    with pytest.raises(TypeError):
        RuntimeTask(**{**task.to_dict(), 'gold_choice_id': 'B'})
    with pytest.raises(ValueError):
        RuntimeTask(**{**task.to_dict(), 'options': [dict(OPTIONS[0], correct=True)] + OPTIONS[1:]})


def test_bm25_ranks_relevant_unit_and_index_is_owner_bound(tmp_path):
    task, resolver = runtime(tmp_path, user_query='Any ramen with garlic places near me?')
    store = write_for_task(resolver, MemoryWriter(), task)
    ranked = OwnerIndex(store, RetrievalSpec(backend='bm25')).rank(query_text(task))
    assert {u.unit_id for u in ranked[:2]} == {f'{FAM}:m3', f'{FAM}:m4'}
    assert all('zither' not in u.original_text for u in store.units)       # system profile never indexed
    with pytest.raises(ValueError):
        OwnerIndex(store, RetrievalSpec(backend='hybrid'))                   # dense without vectors fails closed


def test_four_arms_share_contract_and_cd_see_identical_evidence(tmp_path):
    task, resolver = runtime(tmp_path)
    store = write_for_task(resolver, MemoryWriter(), task)
    index = OwnerIndex(store, RetrievalSpec(backend='bm25'))
    direct = [f'{FAM}:m3', f'{FAM}:m4']
    built = {}
    for arm in ARMS.ARMS:
        packed = ARMS.select_units(arm, task, store, index=index, direct_ids=direct, count_tokens=count, budget=60)
        built[arm] = ARMS.build(arm, task, store, packed)
    systems = {m[0]['content'] for m, _ in built.values()}
    assert len(systems) == 1 and all(m[0]['role'] == 'system' for m, _ in built.values())
    for msgs, _ in built.values():
        assert msgs[-1]['role'] == 'user' and 'Final Answer: [Letter]' in msgs[-1]['content']
        assert 'zither' not in msgs[-1]['content'].split('Current request from the user:')[0]
    assert built['C'][1]['delivered_ids'] == built['D'][1]['delivered_ids'] == direct
    c_block = built['C'][0][-1]['content'].split('\n\nCurrent request')[0]
    assert built['D'][0][-1]['content'].startswith(c_block) and R.APPLICABILITY in built['D'][0][-1]['content']
    assert built['A'][1]['delivered_ids'][-1] == f'{FAM}:m6'                  # recency window ends at cutoff


def test_cd_not_evaluable_without_direct_or_for_excluded_profile(tmp_path):
    task, resolver = runtime(tmp_path)
    store = write_for_task(resolver, MemoryWriter(), task)
    for direct in (None, [f'{FAM}:m0']):
        for arm in ('C', 'D'):
            with pytest.raises(ARMS.NotEvaluable):
                ARMS.select_units(arm, task, store, direct_ids=direct, count_tokens=count, budget=1000)
    a = ARMS.select_units('A', task, store, count_tokens=count, budget=1000)
    assert a.units                                                           # A/B still produced


def test_generation_mode_never_receives_options(tmp_path):
    task, resolver = runtime(tmp_path, task_mode='generation', options=[])
    store = write_for_task(resolver, MemoryWriter(), task)
    msgs, _ = ARMS.build('A', task, store, ARMS.select_units('A', task, store, count_tokens=count, budget=100))
    assert 'Final Answer' not in msgs[-1]['content']
    with pytest.raises(ValueError):
        runtime(tmp_path, task_mode='generation')                             # A's contract rejects options


def test_recency_is_newest_first_and_contiguous(tmp_path):
    task, resolver = runtime(tmp_path)
    store = write_for_task(resolver, MemoryWriter(), task)
    assert [u.order for u in recency(store)] == sorted((u.order for u in store.units), reverse=True)
    spec = RetrievalSpec(backend='bm25', unit_filter='user_only', expand_next=True)
    ranked = OwnerIndex(store, spec).rank('ramen garlic')
    assert [u.unit_id for u in ranked[:2]] == [f'{FAM}:m3', f'{FAM}:m4']
    assert spec.identity != RetrievalSpec(backend='bm25').identity and digest(spec.identity)
