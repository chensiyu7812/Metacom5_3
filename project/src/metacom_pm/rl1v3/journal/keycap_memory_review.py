"""CPU evidence checks for fixed Memory/Writer outputs, never a semantic reward.

All observed task content and hand-authored semantic decisions are private inputs.
These functions verify identities, exact quotations and source metadata; they do
not infer that an exact quotation is a sufficient or correct interpretation.
"""
from collections import Counter, defaultdict
from datetime import date, timedelta
import html
import json
from pathlib import Path
import re

from ..io import file_sha256, object_sha256, sha256_text

INCOMPLETE = 'Incomplete extractive digest; consult the full conversation.'


def jsonl(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line]


def load_completed_job(requests_path, job_path):
    """Require one returned and validated event per original frozen request."""
    requests = jsonl(requests_path)
    by_id = {r['request_id']: r for r in requests}
    if len(by_id) != len(requests):
        raise ValueError('duplicate frozen request')
    for row in requests:
        if object_sha256(row['model_input']) != row['payload_sha256']:
            raise ValueError('request payload changed')
    returned, validated = {}, {}
    for event_name, target in [('REQUEST_RETURNED', returned), ('REQUEST_VALIDATED', validated)]:
        for path in sorted(Path(job_path).glob('*-' + event_name + '.json')):
            event = json.loads(path.read_text())
            key = event['request_id']
            if key not in by_id or key in target or event['event'] != event_name:
                raise ValueError('unexpected or duplicate job event')
            target[key] = dict(event=event, event_file_sha256=file_sha256(path))
    if set(returned) != set(by_id) or set(validated) != set(by_id):
        raise ValueError('incomplete job; preserve technical failure separately')
    rows = []
    for request in requests:
        rid = request['request_id']
        output = returned[rid]['event']['output']
        if output['input_tokens'] != len(request['model_input']['input_ids']):
            raise ValueError('input token count differs from frozen payload')
        rows.append(dict(request_id=rid, request=request, output=output,
            returned_event_sha256=returned[rid]['event_file_sha256'],
            validated_event_sha256=validated[rid]['event_file_sha256'],
            output_sha256=object_sha256(output)))
    return rows


def delivered_text(request):
    """Decode renderer escaping for inspection; preserve original payload bytes."""
    return html.unescape('\n'.join(m['content'] for m in request['model_input']['messages'][:-1]))


def validate_m1_manual(review, joined, audit):
    """Validate private review completeness and quote bindings, not semantics."""
    if review['request_id'] != joined['request_id'] or review['task_id'] != audit['task_id']:
        raise ValueError('review identity mismatch')
    expected = {a['atom_id'] for a in audit['atoms'] if a['required']}
    atoms = review['atoms']
    if len(atoms) != len(expected) or {a['atom_id'] for a in atoms} != expected:
        raise ValueError('review must include every required atom exactly once')
    supplied, output = delivered_text(joined['request']), joined['output']['text']
    for atom in atoms:
        if atom['observed'] not in {'complete', 'partial', 'omitted', 'contradicted', 'uncertain'}:
            raise ValueError('invalid development observation')
        if atom['delivery'] not in {'full', 'partial', 'absent', 'uncertain'}:
            raise ValueError('invalid delivery observation')
        if atom['observed'] in {'complete', 'partial', 'contradicted'} and not atom['output_quotes']:
            raise ValueError('observed answer claim needs output evidence')
        if any(not q or q not in output for q in atom['output_quotes']):
            raise ValueError('output quotation is not exact')
        for evidence in atom['delivered_source_quotes']:
            if not evidence['quote'] or evidence['quote'] not in supplied:
                raise ValueError('source quotation was not delivered')
        if atom['delivery'] == 'full' and not atom['delivered_source_quotes']:
            raise ValueError('full delivery needs actual supplied source evidence')
    for finding in review.get('additional_findings', []):
        if any(not q or q not in output for q in finding.get('output_quotes', [])):
            raise ValueError('additional claim quote is not exact')
        if any(not q or q not in supplied for q in finding.get('delivered_source_quotes', [])):
            raise ValueError('additional claim source is not supplied')
    if review['formal_semantic_status'] != 'uncertain' or review['reward'] is not None:
        raise ValueError('unqualified development review cannot produce formal reward')
    return True


def writer_quote_screen(text, source):
    """Replay the frozen strict line/role/substr screen, with exact offsets."""
    errors, quotes = [], []
    for line_number, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line == INCOMPLETE:
            continue
        match = re.fullmatch(r'(?:- )?(seeker|supporter):\s*(.+)', line)
        if not match:
            errors.append('unparsed_line')
            continue
        speaker, quote = match.groups()
        locations, wrong_role = [], False
        for turn in source['turns']:
            offset = turn['text'].find(quote)
            if offset < 0:
                continue
            if turn['speaker'] != speaker:
                wrong_role = True
                continue
            locations.append(dict(turn=turn['turn'], speaker=speaker,
                start_char=offset, end_char=offset + len(quote),
                source_turn_sha256=sha256_text(turn['text'])))
        if not locations:
            errors.append('speaker_mismatch' if wrong_role else 'non_exact_or_unsupported_quote')
        quotes.append(dict(line_number=line_number, speaker=speaker, text=quote,
            exact_role_match=bool(locations), locations=locations))
    if not quotes:
        errors.append('no_source_quotes')
    return dict(mechanical_status='fail' if errors else 'pass', errors=errors,
        quotes=quotes, incomplete_marker_present=INCOMPLETE in text.splitlines(),
        semantic_approved=False, formal_semantic_status='uncertain', reward=None)


def source_sentence_units(source):
    """Transparent punctuation units, only a retention proxy, not fact atoms."""
    units = []
    for turn in source['turns']:
        for match in re.finditer(r'\S(?:.*?\S)?(?:[.!?](?=\s|$)|$)', turn['text']):
            units.append(dict(turn=turn['turn'], speaker=turn['speaker'],
                start_char=match.start(), end_char=match.end(), text=match.group()))
    return units


def validate_writer_manual(review, inventory, output):
    expected = {p['proposition_id'] for p in inventory['propositions']}
    rows = review['propositions']
    if len(rows) != len(expected) or {r['proposition_id'] for r in rows} != expected:
        raise ValueError('every frozen source proposition needs one review')
    for row in rows:
        if row['observed'] not in {'retained', 'partial', 'omitted', 'contradicted', 'uncertain'}:
            raise ValueError('invalid source proposition observation')
        if row['observed'] in {'retained', 'partial', 'contradicted'} and not row['output_quotes']:
            raise ValueError('observed proposition needs output evidence')
        if any(not q or q not in output for q in row['output_quotes']):
            raise ValueError('writer review quote is not exact')
    if review['formal_semantic_status'] != 'uncertain' or review['reward'] is not None:
        raise ValueError('writer source review is not a qualified reward')
    return True


REFERENCE_FIELDS = {'owner_id', 'session_id', 'turn', 'speaker', 'reported_date',
                    'start_char', 'end_char', 'exact_quote', 'event_stage'}


def check_reference(answer, source):
    """Check actual source fields and offsets, without interpreting event stage."""
    errors = []
    if not isinstance(answer, dict) or set(answer) != REFERENCE_FIELDS:
        return dict(structural_status='fail', errors=['schema'], semantic_quality_evaluated=False)
    for key in ('owner_id', 'session_id'):
        if answer[key] != source['source'][key]:
            errors.append(key)
    if answer['reported_date'] != source['reported_date']:
        errors.append('reported_date')
    if answer['event_stage'] != 'unknown':
        errors.append('event_stage_not_structurally_defined')
    turn_index = answer['turn']
    turn = next((t for t in source['turns'] if t['turn'] == turn_index), None) if type(turn_index) is int else None
    if turn is None:
        errors.append('turn')
    else:
        if answer['speaker'] != turn['speaker']:
            errors.append('speaker')
        start, end = answer['start_char'], answer['end_char']
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(turn['text']):
            errors.append('quote_offsets')
        elif turn['text'][start:end] != answer['exact_quote']:
            errors.append('quote_offset_text_mismatch')
    return dict(structural_status='fail' if errors else 'pass', errors=errors,
        semantic_quality_evaluated=False, natural_QA_success_evaluated=False, reward=None)


def reference_mutations(source, turn_index):
    turn = next(t for t in source['turns'] if t['turn'] == turn_index)
    answer = dict(owner_id=source['source']['owner_id'], session_id=source['source']['session_id'],
        turn=turn_index, speaker=turn['speaker'], reported_date=source['reported_date'],
        start_char=0, end_char=len(turn['text']), exact_quote=turn['text'], event_stage='unknown')
    return [dict(variant='correct', answer=answer, expected='pass'),
        dict(variant='speaker_changed', answer={**answer, 'speaker': 'supporter' if turn['speaker'] == 'seeker' else 'seeker'}, expected='fail'),
        dict(variant='report_date_changed', answer={**answer, 'reported_date': (date.fromisoformat(source['reported_date']) + timedelta(days=1)).isoformat()}, expected='fail'),
        dict(variant='quote_offset_changed', answer={**answer, 'start_char': 1}, expected='fail')]


def raw_fallbacks(registry, tokenizer, ledger, source_inventory):
    """Execute existing As-of RAW reads at real later prefixes, no Ledger writes.

    Whole Writer digests remain outside the atomic MS-SUM admission contract.
    This verifies the readable RAW route; it does not fabricate an approved SUM
    or claim that summary_or_raw admitted a new summary record.
    """
    from ..compile import asof as A
    from .. import contracts as K
    from .memory_packages import next_real_prefix
    rows = []
    for inventory in source_inventory:
        ref = inventory['source']
        source = registry.entry(ref['owner_id'], ref['session_id']).source
        if A.source_sha(source) != ref['source_sha256']:
            raise ValueError('fallback source identity changed')
        try:
            prefix = next_real_prefix(registry, source)
        except ValueError as error:
            if str(error) != 'no real later prefix; do not fabricate a conversation cutoff':
                raise
            rows.append(dict(request_id=inventory['request_id'], status='unavailable_no_later_real_prefix'))
            continue
        snapshot = A.materialize(registry, prefix, ledger, writer=ledger.rows[0].writer_identity)
        A.verify_snapshot(snapshot)
        candidates = A.candidate_ids(snapshot, 'MS')
        selected = next(v['record'] for v in snapshot['views'] if v['record'].record_id == candidates[-1])
        reading = A.read(snapshot, 'MS', ordinal=1, token_counter=tokenizer, context_remaining=16064)
        if not isinstance(reading, K.ReadingView):
            raise ValueError('expected actual RAW ReadingView')
        if selected.session_id != source.session_id or selected.owner_id != source.owner_id:
            raise ValueError('existing chronological read selected a different source')
        if any(t.text not in reading.reading_text for t in source.turns):
            raise ValueError('RAW reading omitted source turn')
        A.verify_record(selected, registry)
        rows.append(dict(request_id=inventory['request_id'], status='actual_full_raw_read_available',
            prefix=prefix, snapshot_sha256=snapshot['snapshot_sha'], selected_record_id=selected.record_id,
            source_sha256=A.source_sha(source), source_ref=ref, reading=reading,
            reading_text_sha256=sha256_text(reading.reading_text),
            raw_record_text_sha256=sha256_text(selected.text), record_content_identity_verified=True,
            all_source_turns_retained=True, source_turn_count=len(source.turns),
            summary_admitted=False, reason='new Writer summary remains unqualified',
            old_summary_or_raw_called=False, condition='unapproved_external_digest_to_existing_RAW'))
    return rows


def m1_aggregate(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[row['arm']].append(row)
    result = {}
    for arm, items in groups.items():
        atom_counts = Counter(a['observed'] for r in items for a in r['atoms'])
        result[arm] = dict(tasks=len(items), required_atom_presentations=sum(atom_counts.values()),
            atom_observations=dict(atom_counts), fully_complete_tasks=sum(all(a['observed']=='complete' for a in r['atoms']) for r in items),
            input_tokens=sum(r['technical']['input_tokens'] for r in items),
            output_tokens=sum(r['technical']['output_tokens'] for r in items),
            local_seconds=sum(r['technical']['seconds'] for r in items))
    return dict(protocol='pmrl1-j-keycap-memory-development-v1', by_arm=result,
        semantic_approved=0, rewards=0, independent_human_review=False,
        scope='same-source Direct diagnostic on exposed development tasks; not production Writer or retrieval')
