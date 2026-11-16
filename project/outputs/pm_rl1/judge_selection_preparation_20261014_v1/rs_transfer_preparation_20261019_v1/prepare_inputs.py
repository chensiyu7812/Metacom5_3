"""Offline, input-only extension inventory; no model imports or output reads.

Whole-file byte hashes and a structural JSON scan are allowed. Only explicitly
whitelisted source bodies are decoded; validation bodies and reply files are
never decoded, emitted, copied or used for selection.
"""
import hashlib
import json
import os
from pathlib import Path
import sys
from datetime import datetime, timezone

OUT = Path(__file__).resolve().parent
PROJECT = OUT.parents[3]
sys.path.insert(0, str(PROJECT / 'src'))
from metacom_pm.rl1.schema import digest
from metacom_pm.rl1.rs_development import save_once
from metacom_pm.rl1.bound_generation import validate_and_project
from metacom_pm.rl1.evidence import prefix_from_dict, evidence_turns
from metacom_pm.rl1.representation import RESOURCE_GUIDANCE_V2

B = OUT.parent
C = PROJECT / 'outputs/pm_rl1/completion_20260930_v2'
EXPECTED = [98, 99, 101, 103, 106, 107, 108, 110, 112]
PLANS = [(0, 0, 0, 0), (1, 0, 0, 0), (1, 1, 1, 1)]


def read(p):
    return json.loads(p.read_text())


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def skip_ws(data, i):
    while i < len(data) and data[i] in b' \n\r\t':
        i += 1
    return i


def end_value(data, start):
    """Find a JSON value boundary without decoding its strings/content."""
    start = skip_ws(data, start)
    if data[start] == 34:
        i = start + 1
        while i < len(data):
            if data[i] == 92:
                i += 2
            elif data[i] == 34:
                return i + 1
            else:
                i += 1
        raise ValueError('unterminated JSON string')
    if data[start] in (91, 123):
        stack = [data[start]]
        i = start + 1
        while i < len(data):
            c = data[i]
            if c == 34:
                i = end_value(data, i)
                continue
            if c in (91, 123):
                stack.append(c)
            elif c in (93, 125):
                if not stack or (stack.pop(), c) not in ((91, 93), (123, 125)):
                    raise ValueError('bad nesting')
                if not stack:
                    return i + 1
            i += 1
        raise ValueError('unterminated JSON container')
    i = start
    while i < len(data) and data[i] not in b',]} \r\n\t':
        i += 1
    if i == start:
        raise ValueError('empty value')
    return i


def members(data, start=0):
    """Yield key/index plus byte bounds; never deserialize the whole object."""
    start = skip_ws(data, start)
    opening = data[start]
    assert opening in (91, 123)
    closing = 93 if opening == 91 else 125
    i = skip_ws(data, start + 1)
    index = 0
    while data[i] != closing:
        if opening == 123:
            k_end = end_value(data, i)
            key = json.loads(data[i:k_end])
            i = skip_ws(data, k_end)
            assert data[i] == 58
            i = skip_ws(data, i + 1)
        else:
            key = index
        end = end_value(data, i)
        yield key, i, end
        index += 1
        i = skip_ws(data, end)
        if data[i] == closing:
            return
        assert data[i] == 44
        i = skip_ws(data, i + 1)


def selected_array(path, selected_indexes):
    data = path.read_bytes()
    result = {}
    for _, start, end in members(data):
        fields = {key: (a, b) for key, a, b in members(data, start)}
        a, b = fields['index']
        index = json.loads(data[a:b])
        if index in selected_indexes:
            assert index not in result
            result[index] = json.loads(data[start:end])
    assert set(result) == set(selected_indexes)
    return result


def selected_object(path, selected_keys):
    data = path.read_bytes()
    result = {}
    for key, start, end in members(data):
        if key in selected_keys:
            assert key not in result
            result[key] = json.loads(data[start:end])
    assert set(result) == set(selected_keys)
    return result


def main():
    os.umask(0o077)
    meta_path = B / 'reference_preparation_20261016_v1/coordinator/validation_inventory.json'
    selection_path = C / 'P3/calibration/selection_lock_private.json'
    stats_path = C / 'P3/common_evidence/source_statistics_private.json'
    maps_path = C / 'P3/common_evidence/source_map_private.json'
    evidence_path = C / 'P3/common_evidence/evidence_pool_private.json'
    frozen_path = C / 'P3/common_evidence/input_freeze.json'
    exposure_path = PROJECT / 'outputs/pm_rl1/source_and_capacity_20260928_v1/source_exposure_v2.json'
    freeze = read(frozen_path)
    for p in (stats_path, maps_path, evidence_path):
        assert sha(p) == freeze['files'][p.name]
    old_inventory = read(meta_path)
    selected = sorted(r['index'] for r in old_inventory['remaining_development_metadata'])
    assert selected == EXPECTED
    selection = read(selection_path)
    locked = {r['index'] for r in selection['natural_pairs']}
    locked.update(i for values in selection['control_slots'].values() for i in values)
    assert not set(selected) & locked
    stats_all = read(stats_path)
    stats = {r['index']: r for r in stats_all if r['index'] in selected}
    assert set(stats) == set(selected)
    assert all(r['split'] == 'dev' and r['owner'] in selection['development_owners']
               and r['owner'] not in selection['validation_owners'] for r in stats.values())
    lock = dict(version='rs-transfer-input-selection-v1-20261019',
        created_utc=datetime.now(timezone.utc).isoformat(),
        status='INPUT_SELECTION_LOCKED_BEFORE_NEW_CONTENT_OR_OUTPUT_REVIEW',
        indexes=selected, policy='all nine existing eligible dev prefixes; ascending frozen index',
        plans=[list(p) for p in PLANS], conditional_generation_design='shared OFF; old/new RS-only; old/new all-four',
        old_output_selection=False, metadata_sources={str(p):sha(p) for p in
            (meta_path, selection_path, stats_path)},
        fresh_owner_disjoint_validation=False, generation_authorized=False)
    if (OUT / 'selection_lock.json').exists():
        lock['created_utc'] = read(OUT / 'selection_lock.json')['created_utc']
    save_once(OUT / 'selection_lock.json', lock)
    # No source decoding before the immutable all-nine selection above.
    mappings = selected_array(maps_path, selected)
    sources = selected_object(evidence_path, {stats[i]['prefix_identity'] for i in selected})
    runtime = read(C / 'P2/executor_freeze.json')['primary_runtime']
    generation = Path(read(C / 'P2/common_pool/primary_generation_pointer.json')['run_dir'])
    old_summary = read(generation / 'summary.json')
    meta_by_key = {(r['index'], tuple(r['counts'])): r for r in old_summary['rows']
                   if r['index'] in selected and tuple(r['counts']) in PLANS}
    assert all((i,p) in meta_by_key for i in selected for p in PLANS[:2])
    exposure = {r['prefix']: r for r in read(exposure_path)['rows']}
    old4 = {r['index']: set(r['full_source_turn_hashes']) for r in stats_all
            if r['index'] in (111, 102, 104, 109)}
    old_union = set().union(*old4.values())
    contexts = []
    requests = []
    unavailable = []
    preserved = {str(p): sha(p) for p in [meta_path, selection_path, stats_path,
        maps_path, evidence_path, frozen_path, exposure_path, C / 'P2/executor_freeze.json']}
    for index in selected:
        mapping = mappings[index]
        prefix = prefix_from_dict(mapping['prefix'])
        evidence = sources[prefix.identity]
        assert prefix.identity == stats[index]['prefix_identity'] == mapping['prefix_identity']
        assert digest(evidence) == stats[index]['evidence_identity'] == mapping['evidence_identity']
        assert len(evidence['legal_past_sessions']) == len(mapping['source_map'])
        assert all(r['rank'] < prefix.cutoff_rank for r in mapping['source_map'])
        expected_current = [dict(id=f'C:T{i:03d}', role=t.role, text=t.content) for i,t in enumerate(prefix.turns)]
        assert evidence['current_prefix'] == expected_current
        evidence_turns(evidence)  # duplicate-ID validation
        save_once(OUT / f'sources/dev_{index:03d}.json', evidence)
        save_once(OUT / f'sources/dev_{index:03d}.mapping.json', mapping)
        for counts in PLANS:
            if (index,counts) not in meta_by_key:
                unavailable.append(dict(index=index, counts=list(counts),
                    reason='no such input in the frozen common pool; do not synthesize or substitute',
                    failed_model_request=False))
                continue
            meta = meta_by_key[index, counts]
            path = generation / (meta['request_id'] + '.request.json')
            req = read(path)
            validate_and_project(req, runtime['identity'])
            assert req['request_id'] == meta['request_id']
            assert req['provenance']['prefix_identity'] == prefix.identity
            assert req['provenance']['canonical_counts'] == list(counts)
            requests.append(dict(index=index, counts=list(counts), metadata=meta,
                original_request_path=str(path), original_request_file_sha256=sha(path), request=req))
            preserved[str(path)] = sha(path)
        tokens = set(stats[index]['full_source_turn_hashes'])
        current_hashes = {digest([t['role'],t['text']]) for t in evidence['current_prefix']}
        contexts.append(dict(index=index, owner=prefix.owner_id, split=prefix.split,
            prefix_identity=prefix.identity, evidence_identity=digest(evidence),
            current_session=prefix.session_id, cutoff_rank=prefix.cutoff_rank,
            source_statistics=stats[index],
            overlap_with_prior_four=dict(exact_unique_turns=len(tokens & old_union),
                total_unique_turns=len(tokens), current_turns_in_old_legal_evidence=len(current_hashes & old_union),
                current_unique_turns=len(current_hashes)),
            historical_exposure_metadata=exposure.get(prefix.identity),
            old_judge_locked=False, previous_generator_outputs_exist=True,
            previous_generator_outputs_read_this_preparation=False,
            independence='additional developer-held contexts, shared owners/history; not untouched validation'))
    save_once(OUT / 'input_requests_private.json', requests)
    save_once(OUT / 'inventory.json', dict(status='NINE_INPUTS_PREPARED_NO_MODEL_CALLS',
        contexts=contexts, old_generator_request_count=len(requests), unavailable_plans=unavailable,
        current_scoring_attempts=144, new_scoring_attempts=0, new_generation_attempts=0,
        new_model_labels=0, protected_source_bodies_decoded=0, reply_files_read=0,
        credentials_read=False, gpu_used=False, selection_identity=digest(lock),
        structural_scan='whole-file hash/structural byte scan; only allowlisted nine body records decoded',
        immutable_inputs=preserved))
    lines = []
    marker = '\n\n' + RESOURCE_GUIDANCE_V2 + '<resources>\n'
    for index in selected:
        e = sources[stats[index]['prefix_identity']]
        req = next(r['request'] for r in requests if r['index']==index and r['counts']==[1,0,0,0])
        resource = json.loads(req['messages'][0]['content'].split(marker)[1][:-len('\n</resources>')])
        lines.extend([f'\n## dev_{index:03d}', 'CURRENT'])
        lines.extend(f"{t['id']} {t['role']}: {t['text']}" for t in e['current_prefix'])
        lines.append('RS TOP1: ' + json.dumps(resource,ensure_ascii=False))
    text = '\n'.join(lines)+'\n'
    path = OUT / 'INPUT_REVIEW_EN.md'
    if path.exists():
        assert path.read_text() == text
    else:
        with path.open('x') as f:
            f.write(text)
    print(json.dumps(dict(contexts=len(contexts), prepared_old_inputs=len(requests),
        unavailable_plans=unavailable,
        output_texts_read=0, scoring_calls=0, generator_calls=0,
        selected=selected),ensure_ascii=False))


if __name__ == '__main__':
    main()
