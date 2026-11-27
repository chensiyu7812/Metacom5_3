"""NAA B-line Memory Writer/Reader regression (CPU fixtures; not research results)."""
import inspect
from pathlib import Path

import pytest

from metacom_pm.need_aware.data.contracts import EvidenceRecord, text_hash
from metacom_pm.need_aware.memory import reader as R
from metacom_pm.need_aware.memory import writer as W
from metacom_pm.rl1v3.semcap import identity as I

OWNER, FAM = 'pm2:1', 'pm2-fam'


def rec(i, speaker, text, owner=OWNER, fam=FAM):
    return EvidenceRecord(source_id=f'{fam}:m{i}', owner_id=owner, source_family=fam, session=fam, order=i,
                          speaker=speaker, situation='synthetic_history_message', reported_at=None,
                          original_text=text, original_text_sha256=text_hash(text),
                          coordinates={'message_index': i, 'char_start': 0, 'char_end': len(text)})


HISTORY = [rec(0, 'system', 'You are an AI assistant helping a user with the following persona: {"name": "X"}'),
           rec(1, 'user', 'I really like jazz records on quiet weekends.'),
           rec(2, 'assistant', 'Jazz on weekends sounds relaxing; I used to recommend Coltrane.'),
           rec(3, 'user', 'I always forget my keys and I want to delete that paragraph from my essay.'),
           rec(4, 'assistant', 'Sure.'),
           rec(5, 'user', 'Please forget that I like jazz records on weekends.'),
           rec(6, 'user', 'I no longer drink coffee in the morning.')]


def store():
    return W.MemoryWriter().write(HISTORY, owner_id=OWNER, source_family=FAM, cutoff=7)


def test_system_profile_excluded_and_identity_projection():
    s = store()
    assert [x['reason'] for x in s.excluded] == ['system_profile_not_deployable']
    assert all(u.speaker != 'system' for u in s.units)
    assert s.situation == I.UNKNOWN_SOURCE and s.situation_basis == 'not_established'
    u1, a2 = s.by_id()[f'{FAM}:m1'], s.by_id()[f'{FAM}:m2']
    assert u1.is_current_user and u1.subject == 'current_user_self_report' and u1.speaker_label == 'current user'
    assert not a2.is_current_user and 'not established' in a2.speaker_label
    assert all(u.reported_at is None and u.time_basis == 'message_order_only_no_wall_clock' and u.status == 'reported'
               for u in s.units)


def test_constraint_candidates_are_explicit_and_linked_not_deleted():
    s = store()
    by = s.by_id()
    assert by[f'{FAM}:m5'].constraint_candidates == ('forget_request',)
    assert by[f'{FAM}:m3'].constraint_candidates == ()          # "I always forget my keys" / "delete that paragraph"
    assert 'possible_update' in by[f'{FAM}:m6'].constraint_candidates
    assert 'possible_update' not in by[f'{FAM}:m2'].constraint_candidates  # assistant text is never a user constraint
    link = s.constraints[0]
    assert link['unit_id'] == f'{FAM}:m5' and link['target_unit_id'] == f'{FAM}:m1'
    assert f'{FAM}:m1' in by                                     # forgotten statement retained, only annotated


@pytest.mark.parametrize('bad', ['future', 'owner', 'dup', 'type'])
def test_writer_rejects_future_foreign_duplicate_and_untyped(bad):
    rows = list(HISTORY[:3])
    kw = dict(owner_id=OWNER, source_family=FAM, cutoff=3)
    if bad == 'future':
        kw['cutoff'] = 2
    elif bad == 'owner':
        rows.append(rec(3, 'user', 'other person', owner='pm2:2'))
        kw['cutoff'] = 4
    elif bad == 'dup':
        rows.append(rows[1])
    else:
        rows = [dict(source_id='x')]
    with pytest.raises((ValueError, TypeError)):
        W.MemoryWriter().write(rows, **kw)


def test_writer_cannot_receive_query_options_or_evaluation():
    params = set(inspect.signature(W.MemoryWriter.write).parameters)
    assert params == {'self', 'records', 'owner_id', 'source_family', 'cutoff'}
    import ast
    writer_class = next(n for n in ast.parse(Path(W.__file__).read_text()).body
                        if isinstance(n, ast.ClassDef) and n.name == 'MemoryWriter')
    for module, tree in ((W, writer_class), (R, ast.parse(Path(R.__file__).read_text()))):
        imported = [n.module or '' for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        imported += [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
        assert not any('evaluation' in m or 'direct' in m for m in imported), module.__name__
        names = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        names |= {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {
            a.arg for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) for a in n.args.args}
        assert not names & {'options', 'user_query', 'gold_choice_id', 'reference_answer', 'gold_preference',
                            'related_snippet', 'spans', 'task'}, module.__name__


def test_store_identity_and_tamper_detection(tmp_path):
    s = store()
    cache = W.StoreCache(tmp_path)
    p = cache.put(s)
    assert cache.get(s.store_id).store_id == s.store_id
    data = p.read_text().replace('quiet weekends', 'loud weekends')
    p.write_text(data)
    with pytest.raises(ValueError):
        cache.get(s.store_id)


def test_reader_raw_and_state_share_exact_records():
    s = store()
    units = [s.by_id()[f'{FAM}:m{i}'] for i in (1, 2, 5)]
    packed = R.pack(units, lambda t: len(t.split()), 10_000)
    raw, state = R.render(list(packed.units), 'raw'), R.render(list(packed.units), 'state')
    assert state.startswith(raw)
    for u in units:
        assert ' '.join(u.original_text.split()) in raw
    assert 'forget' in state.split(raw)[1].lower() and R.APPLICABILITY in state
    assert R.trace(packed, 'raw')['delivered_ids'] == R.trace(packed, 'state')['delivered_ids']


def test_pack_budget_contiguous_vs_greedy():
    s = store()
    newest_first = sorted(s.units, key=lambda u: -u.order)
    cost = lambda t: 1000 if 'drink coffee' in t else 10
    contiguous = R.pack(newest_first, cost, 500, contiguous=True)
    greedy = R.pack(newest_first, cost, 500)
    assert contiguous.units == ()                     # newest unit does not fit -> window stops
    assert len(greedy.units) == len(s.units) - 1      # ranked packing skips and continues
    assert greedy.skipped_over_budget == (f'{FAM}:m6',)
