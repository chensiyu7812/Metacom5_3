#!/usr/bin/env python3
"""Read-only research replay and completion preparation. No execution switch.

Reads opened train/dev artifacts and exposure metadata, never sealed labels or
test contents. No provider credentials, inference, optimizer or account query.
Writes only a new output directory. Historical requests and failures stay intact.
"""
import argparse
import csv
from collections import Counter, defaultdict
from dataclasses import asdict, replace
from decimal import Decimal
from functools import lru_cache
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import sys
from types import SimpleNamespace
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / 'src'))
from metacom_pm.rl1.schema import EpisodeSpec, Resource, HEADS, PLANS, digest
from metacom_pm.rl1.evidence import prefix_from_dict
from metacom_pm.rl1.bound_generation import BoundResourceEnv
from metacom_pm.rl1.representation_direct import DirectReplyRenderer
from metacom_pm.rl1.learning_preparation import (TerminalCandidate, compile_demonstration,
    select_bc_target, initialization_manifest)
from metacom_pm.rl1 import strict_audit_delivery as strict

BASE = PROJECT / 'outputs/pm_rl1/judge_selection_preparation_20261014_v1'
Q = PROJECT / 'outputs/pm_rl1/completion_20260930_v2'
SOURCES = {}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    path = Path(path)
    SOURCES[str(path)] = sha(path)
    return json.loads(path.read_text())


def save(root, name, value):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')
    path.chmod(0o600)


def historical_guard():
    pr = read(BASE / 'score_audit_strict_preparation_20261022_v1/protocol.json')
    files = dict(pr['immutable_files']) | pr['historical_started_hashes'] | pr['old_stop_hashes']
    for p in Path(pr['run_dir']).glob('*'):
        if p.is_file() and p.suffix in ('.json', '.sse'):
            files[str(p)] = sha(p)
    ledger = pr['financial_baseline']['ledger_path']
    files[ledger] = sha(ledger)
    for p, expected in files.items():
        if sha(p) != expected:
            raise ValueError('historical artifact changed: ' + p)
    return files


def wire_review(out):
    """Historical sealed requests plus actual Transport.send byte capture offline."""
    original = BASE / 'score_audit_validation_preparation_20261022_v1'
    items = read(original / 'inputs_private.json')
    scores = read(original / 'historical_scores_private.json')
    rubric_path = original / 'FROZEN_RUBRIC_EN.txt'
    SOURCES[str(rubric_path)] = sha(rubric_path)
    rubric = rubric_path.read_text()
    entry_spec = importlib.util.spec_from_file_location('completion_previous_entry', PROJECT/'scripts/rl1/119_run_feedback_validation.py')
    entry = importlib.util.module_from_spec(entry_spec)
    entry_spec.loader.exec_module(entry)
    engine = entry.engine()
    rows = []
    for dirname in ('score_audit_validation_preparation_20261022_v1', 'score_audit_strict_preparation_20261022_v1'):
        pr = read(BASE / dirname / 'protocol.json')
        root = Path(pr['run_dir'])
        is_strict = 'strict' in dirname
        for started_path in sorted(root.glob('*.started.json')):
            start = read(started_path); slot = start['slot']; sid = slot['slot_id']
            request = read(root/(sid+'.request.json'))
            result = read(root/(sid+'.result.json'))
            seal = read(root/(sid+'.seal.json'))
            for name, expected in seal.items():
                if Path(name).name != name or sha(root/name) != expected:
                    raise ValueError('historical request/result seal differs')
            data = json.loads(request['wire_body']['messages'][1]['content'])
            expected = items[slot['item_key']]
            checks = dict(messages_in_wire=request['messages'] == request['wire_body']['messages'],
                complete_reply=data['reply'] == expected['reply'],
                complete_sources=data['legal_evidence'] == expected['evidence'],
                complete_rubric=data['rubric_reference'] == dict(identity=digest(rubric), text=rubric),
                preliminary_score=data['preliminary_score'] == scores[slot['item_key']]['evaluation']['value'],
                request_identity=digest(dict(protocol=pr['identity'], slot=sid,
                    messages=request['messages'], schema=request['schema'])) == start['request_identity'],
                no_client_truncation=request['input_screen']['client_truncation'] is False)
            capture = None
            if is_strict:
                messages, schema = strict.payload(slot, expected, scores, engine, rubric)
                body = strict.wire_body(pr['config'], messages, schema, engine)
                checks['current_builder_equals_archived_wire'] = body == request['wire_body']
                checks['server_schema_projection'] = body['tools'][0]['function']['parameters'] == strict.server_schema(schema)[0]
                checks['strict_flag'] = body['tools'][0]['function']['strict'] is True
                captured = []
                stream = (root/(sid+'.sse')).read_bytes()
                class RecordedResponse(io.BytesIO):
                    headers = {}
                class NoNetworkOpener:
                    def open(self, req, timeout):
                        captured.append((req.full_url, req.data))
                        return RecordedResponse(stream)
                proxy = SimpleNamespace(api_body=lambda *_: body)
                # Only a dummy string is visible to this transport; no real key
                # is read. Its urllib sender is replaced before send is invoked.
                with patch('os.environ', {'DEEPSEEK_API_KEY': 'OFFLINE_DUMMY_NOT_A_CREDENTIAL'}), \
                     patch('urllib.request.build_opener', return_value=NoNetworkOpener()):
                    strict.Transport(pr['config'], proxy).send(messages, schema,
                        request={'request_id': start['request_identity']}, raw_path=out/(sid+'.offline_replay.sse'))
                checks['transport_serialized_bytes'] = len(captured) == 1 and json.loads(captured[0][1]) == body
                checks['endpoint'] = captured[0][0] == strict.ENDPOINT
                capture = hashlib.sha256(captured[0][1]).hexdigest()
            if not all(checks.values()):
                raise ValueError('outbound mismatch: ' + repr(checks))
            rows.append(dict(slot_id=sid, item=slot['item_key'], protocol_identity=pr['identity'],
                historical_technical_valid=result['technical_valid'], checks=checks,
                archived_wire_identity=digest(request['wire_body']), offline_serialized_bytes_sha256=capture))
    old_audits=[]
    for dirname in ('feedback_validation_preparation_20261022_v2','feedback_source_evidence_preparation_20261022_v2'):
        pr=read(BASE/dirname/'protocol.json')
        for started_path in sorted(Path(pr['run_dir']).glob('*.started.json')):
            started=read(started_path)
            if started['slot']['component']!='audit':continue
            req=read(started_path.with_name(started_path.name.replace('.started.json','.request.json')))
            text=json.dumps(req['wire_body']['messages'],ensure_ascii=False)
            old_audits.append(dict(slot=started['slot']['slot_id'],
                full_rubric_delivered=any(rubric in m['content'] for m in req['wire_body']['messages']),
                complete_local_schema_embedded=json.dumps(req['schema'],ensure_ascii=False) in req['wire_body']['messages'][0]['content']))
    return dict(historical_started_requests=len(rows), strict_transport_captures=sum(r['offline_serialized_bytes_sha256'] is not None for r in rows),
        earlier_audit_gap_census=old_audits,
        rows=rows, new_network_requests=0, real_credential_reads=0,
        limit='Offline transport capture verifies serialized bytes; no historical packet capture or future provider reliability claim.')


def ngrams(text, n=4):
    tokens = re.findall(r"[a-z0-9]+(?:'[a-z]+)?", text.lower())
    return {tuple(tokens[i:i+n]) for i in range(len(tokens)-n+1)}


def primary_payload(item, engine, prompt):
    """Deliver the unchanged local contract, not only a client-side schema.

    Forward-only engineering input revision. The q/m/task text stays exact;
    old scores and old request identities never inherit this delivery version.
    """
    messages,schema=engine.payload(item,'joint')
    messages[0]['content']=prompt+'\nOUTPUT CONTRACT pmrl1-primary-full-schema-v1:\n'+json.dumps(schema,ensure_ascii=False)
    data=json.loads(messages[1]['content'])
    if data['reply']!=item['reply'] or data['legal_evidence']!=item['evidence']:
        raise ValueError('primary source/reply delivery differs')
    return messages,schema


def prepare_pool(out):
    slots = read(Q/'P2/common_pool/slots_private.json')
    generation = Path(read(Q/'P2/common_pool/primary_generation_pointer.json')['run_dir'])
    summary = read(generation/'summary.json')
    freeze = read(Q/'P2/executor_freeze.json')
    raw_specs = read(Q/'P1/episode_specs_private.json')
    specs = [EpisodeSpec(**dict(s, prefix=prefix_from_dict(s['prefix']), inventory=tuple(
        tuple(Resource(**dict(r, source_ids=tuple(r['source_ids']))) for r in head) for head in s['inventory']))) for s in raw_specs]
    assert all(s.prefix.split in ('train', 'dev') for s in specs)
    evidence = read(Q/'P3/common_evidence/evidence_pool_private.json')
    capacities = read(Q/'P1/capacity_prefix_private.json')
    # These are metadata-only roster and already exposed developer materials.
    inventory = read(BASE/'reference_preparation_20261016_v1/coordinator/validation_inventory.json')
    historical_dev = read(BASE/'plan.json')['items']
    locked_prefix = {x['prefix_index'] for x in historical_dev.values()}
    by_slot = {r['slot_id']: r for r in slots['rows']}
    meta_by_index = defaultdict(list)
    for r in summary['rows']:
        meta_by_index[r['index']].append(r)
    new_meta = sorted((m for m in inventory['remaining_development_metadata'] if m['index'] not in locked_prefix),
                      key=lambda m: digest(['completion-dev-selection-v1', m['index']]))
    # Round-robin owners, then fixed hash: no scores, replies or effect selection.
    buckets = defaultdict(list)
    for m in new_meta:
        buckets[m['owner']].append(m)
    ordered = [bucket[i] for i in range(3) for _, bucket in sorted(buckets.items()) if i < len(bucket)]
    selected = []
    for m in ordered[:8]:
        rows = meta_by_index[m['index']]
        off = next(r for r in rows if sum(r['counts']) == 0)
        on = min((r for r in rows if sum(r['counts'])), key=lambda r: digest(['completion-pair-v1', r['slot_id']]))
        selected.append(dict(index=m['index'], owner=m['owner'], prefix_identity=off['prefix_identity'],
            request_ids=[off['request_id'], on['request_id']], counts=[off['counts'], on['counts']],
            purpose='new development relative to recorded judge tuning, not untouched validation'))
    save(out, 'DEVELOPMENT_SELECTION_BEFORE_REPLY_ANALYSIS.json', dict(pairs=selected,
        all_nine_candidates=[m['index'] for m in ordered], selection_uses_scores_or_reply_text=False,
        owner_disjoint=False, historical_source_overlap=True, independent_validation_certified=False))
    replies = {}; requests = {}
    for row in summary['rows']:
        rid = row['request_id']; req = read(generation/(rid+'.request.json')); raw = read(generation/(rid+'.raw.json'))
        if sha(generation/(rid+'.raw.json')) != row['raw_sha256'] or raw['request_id'] != rid or raw['finish_reason'] != 'natural_stop':
            raise ValueError('generation provenance failed')
        if digest({k:v for k,v in req.items() if k != 'request_id'}) != rid or req['messages'] != by_slot[row['slot_id']]['messages']:
            raise ValueError('generation input identity failed')
        if raw['runtime_identity'] != freeze['primary_runtime']['identity']:
            raise ValueError('executor identity changed')
        replies[rid] = raw['text']; requests[rid] = req
    off_by_prefix = {r['prefix_identity']: replies[r['request_id']] for r in summary['rows'] if not sum(r['counts'])}
    analysis = []; candidates = defaultdict(list)
    for row in summary['rows']:
        spec = specs[row['index']]; pid = row['prefix_identity']; rid = row['request_id']
        assert pid == spec.prefix.identity
        reply = replies[rid]; current = ngrams(spec.prefix.query)
        resource = set().union(*(ngrams(r.content) for head,n in zip(spec.inventory, row['counts']) for r in head[:n]))
        new_resource = resource-current
        overlap = ngrams(reply) & new_resource
        delta_overlap = overlap-ngrams(off_by_prefix[pid])
        row_analysis = dict(index=row['index'], split=row['split'], owner=row['owner'], prefix_identity=pid,
            counts=row['counts'], request_id=rid, response_identity=digest(reply), resource_tokens=row['resource_tokens'],
            same_text_as_own_OFF=reply == off_by_prefix[pid],
            novel_resource_4grams=len(new_resource), reply_matching_novel_4grams=len(overlap),
            reply_matching_novel_4grams_absent_in_OFF=len(delta_overlap),
            matched_phrases=[' '.join(x) for x in sorted(delta_overlap)[:8]],
            evidence_of_correct_or_useful_use=False)
        analysis.append(row_analysis)
        if row['split'] == 'train':
            c = TerminalCandidate(pid, 'train', tuple(row['counts']), row['resource_tokens'], rid,
                digest(reply), digest(evidence[pid]), requests[rid]['executor_identity'], requests[rid]['renderer_identity'])
            candidates[pid].append(c)
    private_pairs = []
    for pair in selected:
        private_pairs.append(dict(pair, replies=[replies[rid] for rid in pair['request_ids']], evidence=evidence[pair['prefix_identity']],
            human_reference=None, reviewer_assignment='researcher to confirm; not dispatched'))
    save(out, 'development_pairs_private.json', private_pairs)
    save(out, 'resource_rows_private.json', analysis)
    save(out, 'bc_terminal_candidates_private.json', [asdict(c) for cs in candidates.values() for c in cs])
    aggregates = []
    groups = [('all_non_OFF', [r for r in analysis if sum(r['counts'])])]
    groups += [(h+'_only', [r for r in analysis if r['counts'][i] and sum(bool(n) for n in r['counts']) == 1]) for i,h in enumerate(HEADS)]
    groups += [('mixed', [r for r in analysis if sum(bool(n) for n in r['counts']) > 1])]
    for name, rows in groups:
        aggregates.append(dict(group=name, responses=len(rows), same_as_OFF=sum(r['same_text_as_own_OFF'] for r in rows),
            with_novel_resource_4grams=sum(r['novel_resource_4grams'] > 0 for r in rows),
            with_added_resource_phrase_overlap=sum(r['reply_matching_novel_4grams_absent_in_OFF'] > 0 for r in rows)))
    identities = {(digest(evidence[r['prefix_identity']]), digest(replies[r['request_id']])) for r in summary['rows']}
    public = dict(responses=len(analysis), by_split=dict(Counter(r['split'] for r in analysis)),
        prefixes=len(off_by_prefix), legal_slots=len(slots['rows']), unavailable_slots=len(slots['unavailable']),
        unique_evidence_reply_inputs=len(identities), by_condition=aggregates,
        interpretation='English lexical overlap only: no entailment, attribution, usefulness, causal uptake, or quality labels.',
        selection_bias='All legal frozen menu slots retained, including OFF ties. No task was removed for low benefit.')
    # Reconstruct exact local rendering using only a tokenizer, no G/BGE weights.
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(freeze['primary_runtime']['model_dir'], local_files_only=True)
    @lru_cache(maxsize=32768)
    def count(text): return len(tok.encode(text, add_special_tokens=False))
    class CachedRenderer(DirectReplyRenderer):
        def __init__(self, **kw):
            super().__init__(**kw); self.costs={}; self.fit_cache={}
        def cost(self,s,c):
            key=(id(s),tuple(c))
            if key not in self.costs:self.costs[key]=super().cost(s,c)
            return self.costs[key]
        def fits(self,s,c):
            key=(id(s),tuple(c))
            if key not in self.fit_cache:self.fit_cache[key]=super().fits(s,c)
            return self.fit_cache[key]
    rf = read(Q/'P1/renderer_freeze.json')
    renderer = CachedRenderer(count_text=count,
        count_chat=lambda ms: len(tok.apply_chat_template(ms, tokenize=True, add_generation_prompt=True)),
        tokenizer_identity=rf['tokenizer_identity'], context_limit=freeze['primary_runtime']['policy']['context_limit'])
    assert renderer.identity == freeze['renderer_identity']
    runtime_specs = {i: replace(specs[i], executor_identity=freeze['primary_runtime']['identity'],
        draw_identity=freeze['terminal_draw_identity']) for i in meta_by_index}
    paths = []; branches = []
    for index, spec in runtime_specs.items():
        env = BoundResourceEnv(spec, renderer)
        assert list(env.observe().initial_plan_mask) == capacities[index]['initial_plan_mask']
        for head in range(4):
            env = BoundResourceEnv(spec, renderer)
            if not env.observe().action_mask[head+1]: continue
            before = env.observe(); env.step(head+1, expected_state_hash=env.state_hash); after=env.observe()
            branches.append(dict(index=index, head=HEADS[head], acquired_texts_before=len(before.acquired),
                acquired_texts_after=len(after.acquired), next_legal_GETs=sum(after.action_mask[1:]),
                can_STOP=after.action_mask[0], acquired_content_visible=after.acquired[0].content==spec.inventory[head][0].content,
                unacquired_content_in_observation=False))
        for row in meta_by_index[index]:
            path = compile_demonstration(lambda: BoundResourceEnv(spec,renderer), tuple(row['counts']))
            replay = BoundResourceEnv(spec,renderer)
            for observation, action in path:
                assert replay.observe() == observation
                assert len(observation.acquired) == sum(observation.counts)
                replay.step(action, expected_state_hash=replay.state_hash)
            req = replay.generation_request()
            assert req == requests[row['request_id']]
            paths.append(dict(prefix_identity=spec.prefix.identity, request_id=req['request_id'],
                counts=row['counts'], actions=[action for _,action in path],
                target=None, status='LEGAL_PATH_SKELETON_NOT_BC_DEMONSTRATION'))
    save(out, 'legal_path_skeletons_private.json', paths)
    save(out, 'sequential_opportunity_metadata.json', branches)
    init = [initialization_manifest(method=m,seed=s,feature_identity='requires-final-BGE-and-view-binding')
            for m in ('BC-init','BC-union','OneShot','PPO-NoText') for s in (17,29,43)]
    learning = dict(cache_requests_replayed=len(paths), tokenizer_only=True, model_inference=0,
        natural_policy_updates=0, actual_BC_checkpoints=0, train_prefix_groups=len(candidates),
        target_states=dict(Counter(select_bc_target(cs,{},qualification=None)['status'] for cs in candidates.values())),
        first_GET_states=len(branches), first_GET_states_with_further_choice=sum(r['next_legal_GETs']>0 for r in branches),
        sequential_quality_advantage_established=False, initializations=init,
        remaining='Formal PendingBatch mode and actual model loading require separately scoped integration; no diagnostic bypass.')
    return public, learning, selected


def stage_materials(out):
    """Exact primary input manifest; audit/repair bind to future score identities."""
    entry_spec=importlib.util.spec_from_file_location('completion_feedback_entry',PROJECT/'scripts/rl1/119_run_feedback_validation.py')
    entry=importlib.util.module_from_spec(entry_spec);entry_spec.loader.exec_module(entry);engine=entry.engine()
    pr=read(BASE/'feedback_source_evidence_preparation_20261022_v2/protocol.json')
    prompt_path=BASE/'feedback_source_evidence_preparation_20261022_v2/JOINT_PROMPT_EN.txt'
    prompt=prompt_path.read_text();SOURCES[str(prompt_path)]=sha(prompt_path)
    regression=read(BASE/'score_audit_validation_preparation_20261022_v1/inputs_private.json')
    pairs=read(out/'development_pairs_private.json')
    materials=[dict(key=key,purpose='known_regression',**item) for key,item in sorted(regression.items())]
    for i,pair in enumerate(pairs):
        for side,reply in enumerate(pair['replies']):
            materials.append(dict(key=f'newdev_{i+1:02d}_{side}',purpose='new_development_not_independent_validation',
                reply=reply,evidence=pair['evidence']))
    requests={};mapping=[]
    for item in materials:
        messages,schema=primary_payload(item,engine,prompt)
        body=engine.api_body(pr['config'],messages)
        identity=digest(dict(config=pr['config'],messages=messages,schema=schema))
        requests[identity]=dict(identity=identity,wire_body=body,local_schema=schema,
            evidence_identity=digest(item['evidence']),response_identity=digest(item['reply']))
        mapping.append(dict(material_key=item['key'],purpose=item['purpose'],request_identity=identity))
    save(out,'primary_requests_private.json',list(requests.values()))
    save(out,'stage_materials_private.json',materials)
    manifest=dict(material_slots=len(materials),unique_primary_requests=len(requests),mapping=mapping,
        single_prompt_sha256=sha(prompt_path),single_config_identity=digest(pr['config']),
        primary_input_version='pmrl1-primary-full-schema-v1',
        full_local_schema_delivered=True,engineering_delivery_revision_not_qm_change=True,
        scorer_input_dedup='full config/messages/schema identity; planned independent repeats never deduplicated',
        audit_builder='score_audit_validation.payload + strict_audit_delivery.wire_body',
        resolution_builder='feedback_prototype.repair_payload; exact current initial-score/audit identities',
        dynamic_requests_fully_known=False,final_rubric_changed=False,requests_sent=0,
        newdev_label_status='not collected',validation='old 24 pairs/47 inputs/12 repeats are count-only and conditional on exposure adjudication')
    save(out,'STAGE_MATERIALS.json',manifest)
    with (out/'human_review_template_private.csv').open('x') as f:
        writer=csv.DictWriter(f,fieldnames=['task','material','reference_path','reviewer','preference_or_risk',
            'source_quote_ids','score_error_or_reply_error','uncertainty','minutes','independence_disclosure'])
        writer.writeheader()
        for i in range(len(pairs)):
            writer.writerow(dict(task='blind_reply_preference_before_model_scores',material=f'newdev_{i+1:02d}',reference_path='development_pairs_private.json'))
        for key in sorted(regression):
            writer.writerow(dict(task='known_failure_source_check_not_new_identity_question',material=key,reference_path='stage_materials_private.json'))
        for row in mapping:
            writer.writerow(dict(task='after_scores_check_basis_and_audit_effect',material=row['material_key'],reference_path='stage_materials_private.json'))
    # Enumerate exact fixed-pool primary scorer identities. Their eligibility
    # still depends on the chosen pipeline and final measurement freeze.
    generation=Path(read(Q/'P2/common_pool/primary_generation_pointer.json')['run_dir'])
    evidence=read(Q/'P3/common_evidence/evidence_pool_private.json')
    fixed={}
    for row in read(generation/'summary.json')['rows']:
        raw=read(generation/(row['request_id']+'.raw.json'))
        item=dict(reply=raw['text'],evidence=evidence[row['prefix_identity']])
        messages,schema=primary_payload(item,engine,prompt)
        identity=digest(dict(config=pr['config'],messages=messages,schema=schema))
        fixed.setdefault(identity,[]).append(row['request_id'])
    save(out,'FIXED_REQUEST_IDENTITIES.json',dict(unique_primary_inputs=len(fixed),
        requests=fixed,stage_primary_overlap=sorted(set(fixed)&set(requests)),
        independent_repeats_excluded=True,qualified_cache_exists=False,
        eligibility='Exact construction under proposed S; A has dynamic dependencies. Reuse after qualification must bind same complete identity.'))
    return len(requests)


def cost_model(pool, selection, primary_count):
    slots = read(Q/'P2/common_pool/slots_private.json')['rows']
    capacity = read(Q/'P1/capacity_prefix_private.json')
    cached = {(s['prefix_identity'],tuple(s['counts'])) for s in slots}
    train_missing = sum(c['reachable']-sum((c['prefix_identity'],p) in cached for p in PLANS) for c in capacity if c['split']=='train')
    dev_missing = sum(c['reachable']-sum((c['prefix_identity'],p) in cached for p in PLANS) for c in capacity if c['split']=='dev')
    results=[]
    for dirname in ('feedback_validation_preparation_20261022_v2','feedback_source_evidence_preparation_20261022_v2'):
        pr=read(BASE/dirname/'protocol.json')
        for p in Path(pr['run_dir']).glob('*.result.json'):
            r=read(p)
            if r.get('financial',{}).get('settlement_confirmed'):
                results.append(r)
    by=defaultdict(list)
    for r in results: by[r['component']].append(r)
    means={k:sum(Decimal(r['financial']['accounted_upper_usd']) for r in rs)/len(rs) for k,rs in by.items()}
    n=primary_count
    dev_max=3*n
    technical_reserve=16
    stage=dict(known_regression_reply_slots=6,new_development_pairs=len(selection),
        primary_and_audit_first_attempts=2*n,conditional_resolution_max=n,
        selected_only_validation_single_calls=59,selected_only_validation_audit_upper=177,
        technical_extra_stage_max=technical_reserve,per_identity_extra_max=2,
        validation_nonrepeat_recoveries_max=1,validation_independent_repeat_recoveries=0,
        total_call_ceiling_single=dev_max+59+technical_reserve,
        total_call_ceiling_audit=dev_max+177+technical_reserve,
        capacity_if_all_planned_audit=307+dev_max+177+technical_reserve,
        cumulative_capacity_now=374,capacity_revision_required=True,
        cash_ceiling_proposal_usd='6',cash_ceiling_authorized=False,
        full_worst_case_call_liability_usd='.786432',completion_guaranteed_by_cash_ceiling=False,
        projected_single_route_usd=str(n*(means['joint']+means['audit']+means['repair'])+59*means['joint']+technical_reserve*max(means.values())),
        projected_audit_route_usd=str((n+59)*(means['joint']+means['audit']+means['repair'])+technical_reserve*max(means.values())))
    scenarios=[]
    for episodes in (128,384):
        # Upper bound before adaptive cache overlap. No duplicate counting claim
        # across learned dev/test policies; final plan identities are unknown.
        rows=[dict(phase='unscored_existing_common_pool',new_G_upper=0,new_J_upper=pool['unique_evidence_reply_inputs']),
            dict(phase='remaining_train_OFF',new_G_upper=72,new_J_upper=72),
            dict(phase='PPO_and_NoText',new_G_upper=min(6*episodes,train_missing),new_J_upper=min(6*episodes,train_missing)),
            dict(phase='policy_dev_and_supervised_dev',new_G_upper=min(378,dev_missing),new_J_upper=min(378,dev_missing)),
            dict(phase='core_test_20_instances_x48',new_G_upper=960,new_J_upper=960),
            dict(phase='semantic_recheck_reserve',new_G_upper=0,new_J_upper=96),
            dict(phase='remaining_technical_recovery_reserve',new_G_upper=96,new_J_upper=192-technical_reserve)]
        js=sum(r['new_J_upper'] for r in rows); gs=sum(r['new_G_upper'] for r in rows)
        scenarios.append(dict(episodes_per_seed=episodes,policy_episodes=6*episodes,rows=rows,
            additional_G_upper=gs,additional_J_upper_single=js,
            conservative_single_cost_scenario_usd=str(js*means['joint']+Decimal(stage['projected_single_route_usd'])),
            pervasive_audit_cost_scenario_usd=str(js*(means['joint']+means['audit'])+Decimal(stage['projected_audit_route_usd'])),
            optional_executor_matrix_additional_G_J_each=288,
            lower_bound_note='Adaptive incremental train/dev G/J may be zero after exact qualified-cache reuse; core test has at least 48 OFF endpoints; no zero-cost assumption for the whole study.',
            overlap='Upper rows can overlap. Never sum this as exact unique requests; stage-common overlap also remains conservative.',
            shared_technical_J_reserve='16 in selection stage plus176 later =192, not208'))
    return dict(historical_sample_counts={k:len(v) for k,v in by.items()},
        historical_means_usd={k:str(v) for k,v in means.items()},
        not_current_provider_quote=True,fixed_existing_G_requests=586,
        exact_unique_existing_evidence_reply_inputs=pool['unique_evidence_reply_inputs'],
        qualified_reward_cache_entries=0,train_plan_capacity_missing=train_missing,dev_plan_capacity_missing=dev_missing,
        stage=stage,scenarios=scenarios,shared_remaining_usd='18.0941768',
        training_scale_rule='unchanged: low contrast128; otherwise full engine projection<=96h384, else128; freeze before rollout',
        local_G_and_BGE_engine_hours='not certified by cached replay; profile at authorized actual integration',
        human_hours_assumptions=dict(new_dev_pairs=8,known_regression_replies=6,validation_pairs=24,
            final_pairs=48,optional_validation_reserve_pairs=8,train_unknown_replies_max=12,
            minutes_per_pair_range=[8,20],minutes_per_single_range=[5,15],
            score_basis_review_items=22,minutes_per_score_basis_review_range=[3,10],
            development_rater_hours=[2.6667,7.8334],final48_rater_hours=[6.4,16],
            development_plus_final_single_rater_hours=[9.0667,23.8334],
            old24_labels='reuse if unchanged meaning and exposure adjudication permits; do not ask same researcher to refill',
            optional_new24_validation_rater_hours=[3.2,8],train12_unknown_rater_hours=[1,3],
            optional8_reserve_rater_hours=[1.0667,2.6667],
            excludes='adjudication and scheduling; multiply only newly assigned work for additional real raters; record actual source-reading time',
            rater_hourly_rate=None,assigned_rater=None))


def main(out):
    os.umask(0o077)
    out.mkdir(parents=True,exist_ok=False)
    for p in (Path(__file__),PROJECT/'src/metacom_pm/rl1/learning_preparation.py'):
        SOURCES[str(p)]=sha(p)
    guard=historical_guard()
    wire=wire_review(out); save(out,'WIRE_REVIEW.json',wire)
    print('historical request chain verified; no network',flush=True)
    pool,learning,selection=prepare_pool(out)
    save(out,'RESOURCE_ANALYSIS.json',pool);save(out,'LEARNING_PREPARATION.json',learning)
    primary_count=stage_materials(out)
    save(out,'BUDGET_SCENARIOS.json',cost_model(pool,selection,primary_count))
    for path, expected in guard.items():
        if sha(path)!=expected:raise ValueError('historical artifact modified: '+path)
    save(out,'SOURCE_HASHES_PRIVATE.json',SOURCES)
    save(out,'RECEIPT.json',dict(status='OFFLINE_PREPARATION_COMPLETE',source_files=len(SOURCES),
        protected_files_unchanged=len(guard),research_attempts=307,natural_updates=0,
        new_model_calls=0,new_human_tasks=0,new_cost_usd='0',sealed_labels_read=False,test_contents_read=False,
        source_manifest_sha256=sha(out/'SOURCE_HASHES_PRIVATE.json'),
        outputs={p.name:sha(p) for p in out.iterdir() if p.is_file()}))
    print(json.dumps(dict(output=str(out),pool=pool,learning={k:v for k,v in learning.items() if k!='initializations'}),ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    main(p.parse_args().out.resolve())
