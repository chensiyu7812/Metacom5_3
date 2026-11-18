"""Independent B review: real RAW frontier oracle plus adversarial sidecar checks.

No extraction/model calls. Human-approved flags below are synthetic mechanism
fixtures, never human approval of the real source semantics.
"""
from __future__ import annotations

from dataclasses import fields, replace
import html
import json
from pathlib import Path

import pytest

from metacom_pm.rl1v3 import contracts as K
from metacom_pm.rl1v3.compile import asof as A
from metacom_pm.rl1v3.io import canonical_json, object_sha256
from metacom_pm.rl1v3.sources import source_registry as S

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / 'project/outputs/pm_rl1/v3/asof_cpu_20261118/b_review'
ORACLE = json.loads((OUTPUT / 'RAW_FRONTIER_ORACLE.json').read_text())
WRITER = 'ws-b-synthetic-mechanism-fixture-not-human-review-v1'


@pytest.fixture(scope='module')
def registry():
    return S.load(ROOT / 'project/outputs/pm_rl1/v3/A1_preparation/final/registry')


@pytest.fixture(scope='module')
def raw_ledger(registry):
    ledger = A.Ledger()
    for entry in sorted(registry.entries, key=lambda e: (e.source.owner_id, e.source.chronological_rank)):
        if entry.source.owner_id in ORACLE['owners']:
            ledger.append(A.record_from_source(entry, kind='MS_RAW', writer=WRITER), registry)
    return ledger


def prefix_at(registry, owner='p1', rank=5):
    source = next(e.source for e in registry.entries
                  if e.source.owner_id == owner and e.source.chronological_rank == rank)
    cut = next(i for i, turn in enumerate(source.turns[:-1])
               if turn.role == 'seeker' and source.turns[i+1].role == 'supporter')
    return registry.prefix(owner, source.session_id, cut)


def reidentify(row, **changes):
    changed = replace(row, record_id='pending', **changes)
    return replace(changed, record_id=changed.content_id)


def fixture_claim(registry, *, rank=0, subject='user', slot='test_slot', text=None,
                  review_status='human_approved', **kwargs):
    entry = next(e for e in registry.entries
                 if e.source.owner_id == 'p1' and e.source.chronological_rank == rank)
    ordinal = next(i for i, t in enumerate(entry.source.turns) if t.role == 'seeker' and t.text)
    ref = S.span(entry.source, ordinal)
    return A.record_from_source(entry, kind='MP', refs=(ref,), text=text or ref.exact_quote,
        writer=WRITER, subject=subject, slot=slot, review_status=review_status,
        approval_ref='SYNTHETIC_TEST_FLAG_ONLY_NOT_REAL_HUMAN_APPROVAL', **kwargs)


@pytest.mark.parametrize('case', ORACLE['cuts'], ids=lambda c: f"{c['owner_id']}-r{c['cutoff_rank']}")
def test_b_real_frontier_matches_independent_raw_json_oracle(registry, raw_ledger, case):
    prefix = registry.prefix(case['owner_id'], case['session_id'], case['cut_turn'])
    snapshot = A.materialize(registry, prefix, raw_ledger, writer=WRITER)
    actual = snapshot['source_frontier'].sources
    expected = case['expected_sources']
    assert [(r['session_id'], r['chronological_rank'], r['family_id'], r['transcript_sha256'])
            for r in actual] == [(r['session_id'], r['rank'], r['family_id'], r['transcript_sha256'])
                                for r in expected]
    assert all(r['owner_id'] == case['owner_id'] for r in actual)
    assert all(r['known_at'].session_rank == r['chronological_rank'] + 1 for r in actual)
    assert len(A.candidate_ids(snapshot, 'MS')) == len(expected)
    assert all(r.session_id != case['session_id'] for r in snapshot['ledger_prefix'])
    A.verify_snapshot(snapshot)


def subset_registry(registry, entries):
    return S.Registry(entries, inputs=registry.inputs, folds=registry.folds,
                      excluded_families=registry.excluded_families)


@pytest.mark.parametrize('owner', ORACLE['owners'])
def test_b_future_extension_including_global_corpus_hash_preserves_old_snapshot(registry, raw_ledger, owner):
    prefix = prefix_at(registry, owner, 5)
    early = subset_registry(registry, [e for e in registry.entries
        if e.source.owner_id == owner and e.source.chronological_rank <= 5])
    short = A.Ledger()
    for row in raw_ledger.rows:
        if row.owner_id == owner and row.reported_at.session_rank < 5:
            short.append(row, early)
    before = A.materialize(early, prefix, short, writer=WRITER)
    after = A.materialize(registry, prefix, raw_ledger, writer=WRITER)
    assert canonical_json(before) == canonical_json(after)
    # A full corpus file SHA changes on append; per-session content must not.
    changed_entries = []
    for entry in registry.entries:
        source = replace(entry.source, raw_sha256='f' * 64)
        changed_entries.append(replace(entry, source=source, source_id=S._source_id(source)))
    changed = subset_registry(registry, changed_entries)
    rebound = A.materialize(changed, prefix, raw_ledger, writer=WRITER)
    assert rebound['snapshot_sha'] == before['snapshot_sha']


def test_b_stream_batch_and_persistent_idempotence(registry, raw_ledger, tmp_path):
    prefix = prefix_at(registry, 'p1', 8)
    streamed = A.Ledger(tmp_path / 'ledger')
    count = 0
    for row in raw_ledger.rows:
        if row.owner_id == 'p1' and row.reported_at.session_rank < 8:
            assert streamed.append(row, registry)
            assert not streamed.append(row, registry)
            count += 1
    restored = A.Ledger(tmp_path / 'ledger')
    assert len(restored.rows) == count
    assert A.materialize(registry, prefix, restored, writer=WRITER)['snapshot_sha'] == \
        A.materialize(registry, prefix, raw_ledger, writer=WRITER)['snapshot_sha']


def test_b_delayed_writer_is_invisible_until_ready(registry):
    row = fixture_claim(registry, ready_at=K.TimePoint(session_rank=5))
    ledger = A.Ledger()
    ledger.append(row, registry)
    assert not A.candidate_ids(A.materialize(registry, prefix_at(registry, rank=4), ledger, writer=WRITER), 'MP')
    assert A.candidate_ids(A.materialize(registry, prefix_at(registry, rank=5), ledger, writer=WRITER), 'MP') == (row.record_id,)


def test_b_late_report_of_earlier_event_never_backfills_old_snapshot(registry):
    row = fixture_claim(registry, rank=5, event_time=K.TimePoint(session_rank=1),
                        valid_from=K.TimePoint(session_rank=1))
    ledger = A.Ledger()
    ledger.append(row, registry)
    assert not A.candidate_ids(A.materialize(registry, prefix_at(registry, rank=5), ledger, writer=WRITER), 'MP')
    assert A.candidate_ids(A.materialize(registry, prefix_at(registry, rank=6), ledger, writer=WRITER), 'MP') == (row.record_id,)


def test_b_date_only_fact_validity_is_supported_without_invented_rank(registry):
    source = registry.entry('p1', 'esc1024').source
    row = fixture_claim(registry, valid_from=K.TimePoint(date=source.date),
                        valid_to=K.TimePoint(date=source.date))
    ledger = A.Ledger()
    ledger.append(row, registry)
    snapshot = A.materialize(registry, prefix_at(registry), ledger, writer=WRITER)
    assert snapshot['views'][0]['current_validity'] == 'expired_as_reported'
    assert snapshot['views'][0]['record'].valid_from.session_rank is None


def test_b_pending_content_id_cannot_be_published(registry):
    row = replace(fixture_claim(registry), record_id='pending')
    with pytest.raises(ValueError):
        A.Ledger().append(row, registry)


def test_b_forged_family_rejected(registry):
    row = reidentify(fixture_claim(registry), family_id='evoemo_owner:p18')
    with pytest.raises(ValueError, match='family|mismatch'):
        A.Ledger().append(row, registry)


def test_b_same_family_and_text_never_erase_owner_boundary(registry, raw_ledger):
    p13 = registry.entry('p13', 'esc1198')
    p18 = registry.entry('p18', 'esc1198')
    assert p13.source.family_id == p18.source.family_id
    assert p13.source.transcript_sha256 == p18.source.transcript_sha256
    assert A.source_sha(p13.source) != A.source_sha(p18.source)
    ledger = A.Ledger()
    ledger.append(A.record_from_source(p13, kind='MS_RAW', writer=WRITER), registry)
    prefix = prefix_at(registry, 'p18', 8)
    snapshot = A.materialize(registry, prefix, ledger, writer=WRITER)
    assert not A.candidate_ids(snapshot, 'MS')
    full = A.materialize(registry, prefix, raw_ledger, writer=WRITER)
    assert all(r.owner_id == 'p18' for r in full['ledger_prefix'])


def test_b_supporter_suggestion_cannot_be_promoted_to_execution(registry):
    entry = registry.entry('p1', 'esc1024')
    ref = S.span(entry.source, 3)
    with pytest.raises(ValueError, match='supporter suggestion'):
        A.record_from_source(entry, kind='ME', refs=(ref,), text=ref.exact_quote,
            stage='completed', subject='user', writer=WRITER)


def test_b_unknown_subject_stays_quarantined_even_with_fixture_approval(registry):
    row = fixture_claim(registry, subject='unknown')
    ledger = A.Ledger()
    ledger.append(row, registry)
    snapshot = A.materialize(registry, prefix_at(registry), ledger, writer=WRITER)
    assert snapshot['views'][0]['disposition'] == 'quarantine'
    assert not A.candidate_ids(snapshot, 'MP')


def test_b_unreviewed_correction_does_not_rewrite_prior_fact(registry):
    claim = fixture_claim(registry)
    entry = registry.entry('p1', 'esc1172')
    ref = S.span(entry.source, 1)
    correction = A.record_from_source(entry, kind='RELATION', refs=(ref,), text=ref.exact_quote,
        writer=WRITER, subject='user', slot='test_slot', operation='INVALIDATE', target_id=claim.record_id)
    ledger = A.Ledger()
    ledger.append(claim, registry)
    ledger.append(correction, registry)
    snapshot = A.materialize(registry, prefix_at(registry), ledger, writer=WRITER)
    assert not snapshot['invalidations']
    assert A.candidate_ids(snapshot, 'MP') == (claim.record_id,)


def test_b_get_does_not_expose_private_binding_or_evaluation_fields(registry, raw_ledger):
    snapshot = A.materialize(registry, prefix_at(registry), raw_ledger, writer=WRITER)
    class Counter:
        identity = 'fixture-codepoint-counter-not-native'
        def count(self, text):
            return len(text)
    view = A.read(snapshot, 'MS', ordinal=1, token_counter=Counter(), context_remaining=100000)
    assert isinstance(view, K.ReadingView)
    assert {f.name for f in fields(view)} == {'schema_version','head','view','expandable',
        'expanded_from_ordinal','ordinal','reading_text','reported_at','tokens','stage'}
    serialized = canonical_json(view)
    assert snapshot['snapshot_sha'] not in serialized
    assert WRITER not in serialized
    for row in snapshot['ledger_prefix']:
        assert row.record_id not in serialized
        assert row.source_sha256 not in serialized
    assert 'NeedCard' not in serialized
    assert A.read(snapshot, 'MS', ordinal=1, token_counter=Counter(), context_remaining=1)['status'] == 'capacity'


def test_b_tampered_snapshot_cannot_be_read(registry, raw_ledger):
    snapshot = A.materialize(registry, prefix_at(registry), raw_ledger, writer=WRITER)
    snapshot['writer_identity'] = 'changed'
    with pytest.raises(ValueError, match='integrity'):
        A.candidate_ids(snapshot, 'MS')


def test_b_writer_identity_is_part_of_snapshot(registry, raw_ledger):
    prefix = prefix_at(registry)
    original = A.materialize(registry, prefix, raw_ledger, writer=WRITER)
    changed = A.materialize(registry, prefix, raw_ledger, writer='different-writer')
    assert original['snapshot_sha'] != changed['snapshot_sha']
    assert not changed['ledger_prefix']


def test_b_conflict_get_fails_closed_instead_of_presenting_latest_only(registry):
    first = fixture_claim(registry, text='Synthetic slot value A; mechanism fixture only')
    second = fixture_claim(registry, text='Synthetic slot value B; mechanism fixture only')
    ledger = A.Ledger()
    ledger.append(first, registry)
    ledger.append(second, registry)
    snapshot = A.materialize(registry, prefix_at(registry), ledger, writer=WRITER)
    assert all(v['disposition'] == 'conflict' for v in snapshot['views'])
    class Counter:
        identity = 'fixture-not-native'
        def count(self, text): return len(text)
    result = A.read(snapshot, 'MP', ordinal=1, token_counter=Counter(), context_remaining=100000)
    assert result['status'] == 'conflict_requires_review'


def test_b_current_session_never_written_as_long_term_memory(registry):
    prefix = prefix_at(registry)
    entry = registry.entry(prefix.owner_id, prefix.session_id)
    ledger = A.Ledger()
    ledger.append(A.record_from_source(entry, kind='MS_RAW', writer=WRITER), registry)
    snapshot = A.materialize(registry, prefix, ledger, writer=WRITER)
    assert not snapshot['ledger_prefix']
    assert not A.candidate_ids(snapshot, 'MS')


def test_b_rejected_stage_preserved_without_changing_c0_enum(registry):
    entry = registry.entry('p1', 'esc1024')
    ref = S.span(entry.source, 0)
    row = A.record_from_source(entry, kind='ME', refs=(ref,), text=ref.exact_quote,
        stage='rejected', subject='user', writer=WRITER, review_status='human_approved',
        approval_ref='SYNTHETIC_MECHANISM_ONLY_NOT_REAL_SEMANTIC_APPROVAL')
    ledger = A.Ledger()
    ledger.append(row, registry)
    snapshot = A.materialize(registry, prefix_at(registry), ledger, writer=WRITER)
    class Counter:
        identity = 'fixture-not-native'
        def count(self, text): return len(text)
    view = A.read(snapshot, 'ME', ordinal=1, token_counter=Counter(), context_remaining=100000)
    assert view.stage == 'unknown'
    assert 'stage: rejected' in view.reading_text
    assert 'supported_report' not in view.reading_text


@pytest.fixture(scope='module')
def real_legacy_bank(registry):
    from metacom_pm.rl1v3.bank.bank_v0 import load
    return load(ROOT / 'project/outputs/pm_rl1/v3/A1b_preparation/measured_v1/bank', registry)


@pytest.fixture
def renderer_inputs(registry, raw_ledger, real_legacy_bank):
    from metacom_pm.rl1v3.retrieve.v0 import Reader
    from metacom_pm.rl1v3.render.v0 import messages
    class Counter:
        identity = 'ws-b-renderer-fixture-not-native'
        native_context_tokens = 100000
        def count(self, text): return len(text)
        def prompt_tokens(self, prefix, readings): return len(canonical_json(messages(prefix, readings)))
    prefix = prefix_at(registry)
    reader = Reader(real_legacy_bank, prefix, Counter(), g_id='fixture-g', decode_id='fixture-decode')
    result = reader.read('MS')
    assert isinstance(result, K.ReadSuccess)
    return dict(prefix=prefix, readings=(result.reading,), legacy_key=reader.terminal_key((result,)),
        system='Fixture basic system; no resource or evaluation labels.',
        snapshot=A.materialize(registry, prefix, raw_ledger, writer=WRITER), bank=real_legacy_bank)


def test_b_new_renderer_preserves_exact_evidence_and_current_prefix(renderer_inputs):
    from metacom_pm.rl1v3.render.asof_candidate import prepare
    data = renderer_inputs
    result = prepare(**data)
    assert '<evidence>' + html.escape(data['readings'][0].reading_text) + '</evidence>' in result['messages'][1]['content']
    assert result['messages'][-len(data['prefix'].turns):] == [
        dict(role='user' if t.role == 'seeker' else 'assistant', content=t.text)
        for t in data['prefix'].turns]
    assert result['input_ids'] is None
    assert result['terminal_result'] is None
    assert result['executable'] is False
    assert result['legacy_result_reuse'] is False
    assert result['new_request_identity'] != data['legacy_key'].sha256
    visible = canonical_json(result['messages'])
    assert result['snapshot_sha'] not in visible
    assert result['writer_identity'] not in visible
    assert result['legacy_terminal_key_sha256'] not in visible


def test_b_new_renderer_off_remains_true_off(renderer_inputs):
    from metacom_pm.rl1v3.render.asof_candidate import prepare
    data = renderer_inputs
    key = K.TerminalKey.for_prefix(data['prefix'], domain_id='finite_head_v1',
        ordered_path=('STOP',), acquired=(), bank_version=data['bank'].version,
        index_version=data['bank'].index_version, renderer_id='fixture-legacy-renderer',
        step2_id='none', g_id='fixture-g', decode_id='fixture-decode')
    result = prepare(**dict(data, readings=(), legacy_key=key))
    assert len(result['messages']) == len(data['prefix'].turns) + 1
    assert 'TypedNotes' not in canonical_json(result['messages'])


@pytest.mark.parametrize('change', ['text', 'head_missing', 'prefix', 'key_prefix'])
def test_b_new_renderer_rejects_unvalidated_evidence(renderer_inputs, registry, change):
    from metacom_pm.rl1v3.render.asof_candidate import prepare
    data = dict(renderer_inputs)
    if change == 'text':
        data['readings'] = (replace(data['readings'][0], reading_text='FORGED FUTURE CLAIM'),)
    elif change == 'head_missing':
        data['readings'] = ()
    elif change == 'prefix':
        data['prefix'] = prefix_at(registry, rank=6)
    else:
        data['legacy_key'] = replace(data['legacy_key'], prefix_context_sha256='f' * 64)
    with pytest.raises(ValueError):
        prepare(**data)


@pytest.mark.parametrize('field', ['g_id', 'decode_id', 'step2_id'])
def test_b_request_identity_changes_with_generator_stack(renderer_inputs, field):
    from metacom_pm.rl1v3.render.asof_candidate import prepare
    original = prepare(**renderer_inputs)
    key = replace(renderer_inputs['legacy_key'], **{field: 'different-fixture-version'})
    changed = prepare(**dict(renderer_inputs, legacy_key=key))
    assert original['new_request_identity'] != changed['new_request_identity']
    assert changed['legacy_result_reuse'] is False


def test_b_raw_sum_dependency_survives_same_ready_batch_and_restart(registry, tmp_path):
    entry = registry.entry('p1', 'esc1024')
    raw = A.record_from_source(entry, kind='MS_RAW', writer=WRITER)
    ref = S.span(entry.source, 0)
    summary = A.record_from_source(entry, kind='MS_SUM', writer=WRITER,
        refs=(ref,), text=ref.exact_quote, subject='session', raw_parent_id=raw.record_id,
        review_status='unusable')
    assert raw.ready_at == summary.ready_at
    streamed = A.Ledger(tmp_path / 'ledger')
    streamed.append(raw, registry)
    streamed.append(summary, registry)
    resumed = A.Ledger(tmp_path / 'ledger')
    assert [r.kind for r in resumed.rows] == ['MS_RAW', 'MS_SUM']
    batch = A.Ledger()
    for row in resumed.rows:
        batch.append(row, registry)
    prefix = prefix_at(registry)
    snapshots = [A.materialize(registry, prefix, ledger, writer=WRITER)
                 for ledger in (streamed, resumed, batch)]
    assert len({s['snapshot_sha'] for s in snapshots}) == 1
    fallback = A.summary_or_raw(snapshots[0], summary.record_id)
    assert fallback['condition'] == 'SUM_TO_RAW_FALLBACK'
    assert fallback['selected_id'] == raw.record_id


@pytest.mark.parametrize('subject', ['p1', 'evoemo_owner:p1', 'private-person-123', 'SYSTEM_OVERRIDE'])
def test_b_private_subject_identifiers_cannot_enter_public_role_field(registry, subject):
    with pytest.raises(ValueError, match='subject|role'):
        fixture_claim(registry, subject=subject)


def test_b_pinned_snapshot_loader_roundtrip(registry, raw_ledger, tmp_path):
    snapshot = A.materialize(registry, prefix_at(registry), raw_ledger, writer=WRITER)
    path = tmp_path / 'snapshot.json'
    path.write_text(canonical_json(snapshot) + '\n')
    restored = A.load_snapshot(path, expected_sha=snapshot['snapshot_sha'])
    assert canonical_json(restored) == canonical_json(snapshot)
    assert A.candidate_ids(restored, 'MS') == A.candidate_ids(snapshot, 'MS')
    with pytest.raises(ValueError, match='pinned'):
        A.load_snapshot(path, expected_sha='e' * 64)


def test_b_rehashed_changed_snapshot_still_rejected_by_pinned_sha(registry, raw_ledger, tmp_path):
    snapshot = A.materialize(registry, prefix_at(registry), raw_ledger, writer=WRITER)
    original_sha = snapshot['snapshot_sha']
    snapshot['writer_identity'] = 'modified-writer'
    snapshot['snapshot_sha'] = object_sha256({k: v for k, v in snapshot.items() if k != 'snapshot_sha'})
    path = tmp_path / 'snapshot.json'
    path.write_text(canonical_json(snapshot) + '\n')
    with pytest.raises(ValueError, match='pinned'):
        A.load_snapshot(path, expected_sha=original_sha)
