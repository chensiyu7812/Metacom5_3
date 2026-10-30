#!/usr/bin/env python3
"""Prepare source views, fixed development contrasts and exact J1 primary wire.

Only prior hash-allowlisted isolated train/dev files and a local tokenizer are
read. No weights, embedding, G/J, human assignment, credentials, test or gold.
"""
import argparse
from collections import Counter, defaultdict
from dataclasses import replace
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import sys
import time

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT/'src'))
from metacom_pm.rl1.schema import HEADS, EpisodeSpec, Resource, digest
from metacom_pm.rl1.evidence import prefix_from_dict
from metacom_pm.rl1.resource_evidence_views import EvidenceViews, VERSION
from metacom_pm.rl1.resource_organization import OrganizedItem, OrganizationCatalog, OrganizedRenderer
from metacom_pm.rl1.representation_direct import DirectReplyRenderer
from metacom_pm.rl1.development_feedback import DevelopmentAdapter


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open('x') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False); f.write('\n')
    path.chmod(0o600)


def run(args):
    start = time.monotonic(); out = args.output
    audit, org = args.audit, args.organization
    used = {}
    def manifest(base):
        p = base/'OUTPUT_MANIFEST.json'; used[str(p)] = sha(p)
        return json.loads(p.read_text())
    am, om = manifest(audit), manifest(org)
    def checked(base, name, allow):
        if Path(name).is_absolute() or '..' in Path(name).parts or name not in allow:
            raise ValueError('input outside explicit frozen allowlist')
        p = base/name
        if sha(p) != allow[name]: raise ValueError('input changed: ' + name)
        used[str(p)] = allow[name]
        return json.loads(p.read_text()) if p.suffix == '.json' else p.read_text()
    def ar(name): return checked(audit, name, am)
    def old(name): return checked(PROJECT, name, old_inputs)
    def organization(name): return checked(org, name, om)
    old_inputs = ar('INPUT_HASHES_PRIVATE.json')
    protected = ar('PROTECTED_HASHES.json')
    for p, h in protected.items():
        if sha(Path(p)) != h: raise ValueError('protected input changed')
    rows = organization('CATALOG_MANIFEST.json')
    rs = organization('RS_LIBRARY_PRIVATE.json')
    library = {x['key']: OrganizedItem(**x) for x in rs['items']}
    if digest([x.identity for x in library.values()]) != rs['identity']:
        raise ValueError('shared RS identity mismatch')
    if len(rows) != 114 or Counter(r['split'] for r in rows) != {'train': 96, 'dev': 18}:
        raise ValueError('isolated train/dev coverage changed')
    # Freeze selection using prefix/owner metadata only; before source-view or
    # response analysis. Two prefixes per existing dev owner, not six users.
    by_owner = defaultdict(list)
    for r in rows:
        if r['split'] == 'dev': by_owner[r['owner']].append(r)
    selected = [r for owner in sorted(by_owner) for r in sorted(by_owner[owner],
        key=lambda r: digest(['pmrl1-source-views-v1-20261030', 'fixed-development', r['prefix_identity']]))[:2]]
    save(out/'SELECTION_BEFORE_VIEWS.json', dict(rows=selected, selection_uses_quality=False,
        independent_validation=False, purpose='fixed development only', owners=len(by_owner)))
    from transformers import AutoTokenizer
    from metacom_pm.paper1.llama_tokenizer import LLAMA_TOKENIZER_JSON_SHA256
    if sha(args.tokenizer_dir/'tokenizer.json') != LLAMA_TOKENIZER_JSON_SHA256:
        raise ValueError('local tokenizer changed')
    tok = AutoTokenizer.from_pretrained(args.tokenizer_dir, local_files_only=True, trust_remote_code=False)
    @lru_cache(maxsize=32768)
    def count(text): return len(tok.encode(text, add_special_tokens=False))
    def chat(messages): return len(tok.apply_chat_template(messages, tokenize=True, add_generation_prompt=True))
    native = json.loads((args.tokenizer_dir/'config.json').read_text())['max_position_embeddings']
    renderer = OrganizedRenderer(count_text=count, count_chat=chat,
        tokenizer_identity=digest(dict(tokenizer=LLAMA_TOKENIZER_JSON_SHA256, template=tok.chat_template)), context_limit=native)
    view_renderer = OrganizedRenderer(count_text=count, count_chat=chat,
        tokenizer_identity=digest(dict(tokenizer=LLAMA_TOKENIZER_JSON_SHA256, template=tok.chat_template)), context_limit=native)
    view_renderer.identity = digest(dict(base_renderer=renderer.identity, source_view=VERSION,
        policy='all ordered source turns; no summaries or clipping'))
    off_renderer = DirectReplyRenderer(count_text=count, count_chat=chat,
        tokenizer_identity=digest(dict(tokenizer=LLAMA_TOKENIZER_JSON_SHA256, template=tok.chat_template)), context_limit=native)
    frozen_specs = old('outputs/pm_rl1/completion_20260930_v2/P1/episode_specs_private.json')
    specs = {}
    for s in frozen_specs:
        spec = EpisodeSpec(**dict(s, prefix=prefix_from_dict(s['prefix']), inventory=tuple(
            tuple(Resource(**dict(r, source_ids=tuple(r['source_ids']))) for r in h) for h in s['inventory'])))
        if spec.prefix.split not in ('train', 'dev'): raise ValueError('unexpected split in frozen specs')
        specs[spec.prefix.identity] = spec
    freeze = old('outputs/pm_rl1/completion_20260930_v2/P1/interface_repair_v3/renderer_freeze.json')
    if off_renderer.identity != freeze['new_renderer_identity']: raise ValueError('original OFF renderer changed')
    response_rows = ar('RESPONSE_LEDGER_PRIVATE.json'); pairs = ar('EXECUTOR_PAIRS_PRIVATE.json')
    old_requests = {}
    for row in response_rows:
        request = old(row['request_path'])
        if request['request_id'] != row['request_id'] or digest({k:v for k,v in request.items() if k != 'request_id'}) != row['request_id']:
            raise ValueError('old generation request identity mismatch')
        old_requests[row['request_id']] = request
    executors = {r['executor_identity'] for r in response_rows}
    if len(executors) != 1: raise ValueError('fixed primary G identity ambiguous')
    executor = next(iter(executors))
    prepared = {}; contrasts = []; totals = Counter(); view_receipts = []; issues = []
    def generation(cat, r, keys, purpose):
        usage = r.usage(cat, keys)
        if not usage['within_native_context']: raise ValueError('fixed input exceeds native G context')
        messages = r.messages(cat, keys); renderer_identity = r.identity
        route = 'new_organization_renderer'
        if not keys:
            # OFF explicitly uses the original renderer and original request
            # provenance. Do not relabel old outputs as new-renderer results.
            original = off_renderer.messages(specs[cat.prefix.identity], (0,0,0,0))
            if messages != original: raise ValueError('new OFF is not the identical original input')
            messages = original; renderer_identity = off_renderer.identity; route = 'unchanged_original_OFF'
        body = dict(prefix_identity=cat.prefix.identity, executor_identity=executor,
            renderer_identity=renderer_identity, renderer_route=route, messages=messages, selected_keys=list(keys),
            selected_resource_identities=[x.identity for x in cat.canonical(keys)],
            catalog_identity=cat.identity, usage=usage)
        identity = digest(body)
        if identity not in prepared:
            exact = [rid for rid, q in old_requests.items() if q['messages'] == body['messages'] and
                     q['renderer_identity'] == body['renderer_identity'] and q['executor_identity'] == executor
                     and q['provenance']['prefix_identity'] == cat.prefix.identity
                     and (bool(keys) or q['provenance']['canonical_counts'] == [0,0,0,0])]
            body.update(identity=identity, purposes=[], reusable_old_requests=exact,
                same_messages_old_requests=[rid for rid,q in old_requests.items() if q['messages'] == body['messages']],
                permission='PREPARED_NOT_AUTHORIZED', generated_reply=None, score=None)
            prepared[identity] = body
        prepared[identity]['purposes'].append(purpose)
        return identity
    selected_ids = {r['prefix_identity'] for r in selected}
    for row in rows:
        pid = row['prefix_identity']; catalog = organization('catalogs_private/'+pid+'.json')
        p = prefix_from_dict(catalog['prefix'])
        if p.identity != pid or p.split != row['split']: raise ValueError('prefix identity drift')
        memory = [OrganizedItem(**x) for x in catalog['memory']]
        views = EvidenceViews(p, ar('ledgers_private/'+pid+'.json'))
        # Missing isolated sources stay missing. Semantic truths are not inferred.
        organized = views.organize(memory)
        save(out/'source_views_private'/(pid+'.json'), organized)
        totals.update((x['head'] + ':' + x['status']) for x in organized['bindings'])
        totals['shared_source_groups'] += len(organized['shared_source_locations'])
        for item in memory:
            if item.head != 'MS': continue
            binding = views.binding(item)
            if binding['status'] != 'located': continue
            changed, receipt = views.ms_turn_view(item)
            receipt.update(prefix_identity=pid, key=item.key,
                original_content_tokens=count(item.content), view_content_tokens=count(changed.content))
            view_receipts.append(receipt)
        if pid not in selected_ids: continue
        # Ranking A holds old candidate membership AND exact delivered bodies
        # constant. Expanded-library/system effects are deliberately separate.
        frozen_rs = [replace(library[k], original_rank=v[0], bge_similarity=v[1]) for k,v in catalog['frozen_RS_metadata'].items()]
        common = frozen_rs + [x for x in memory if x.original_rank is not None]
        cat = OrganizationCatalog(p, common, provenance_identity=catalog['catalog_identity'])
        generation(cat, renderer, (), dict(comparison='OFF', prefix_identity=pid))
        for head in HEADS:
            eligible = sorted((x for x in common if x.head == head), key=lambda x:x.original_rank)
            if not eligible:
                issues.append(dict(prefix_identity=pid, comparison='A', head=head, status='no_inventory')); continue
            old_top = eligible[0].key; new_top = cat.rank(head)[0]['key']
            a = generation(cat, renderer, (old_top,), dict(comparison='A', arm='BGE', head=head))
            b = generation(cat, renderer, (new_top,), dict(comparison='A', arm='literal_index', head=head))
            contrasts.append(dict(comparison='A', prefix_identity=pid, owner=p.owner_id, head=head,
                input_identities=[a,b], changed_candidate=old_top != new_top, source_domain='same original candidate pool',
                causal_quality_effect='not_measured', semantic_relevance='unverified'))
        ms = sorted((x for x in common if x.head == 'MS'), key=lambda x:x.original_rank)
        if ms and views.binding(ms[0])['status'] == 'located':
            changed, _ = views.ms_turn_view(ms[0])
            newcat = OrganizationCatalog(p, [changed if x.key == changed.key else x for x in common],
                                         provenance_identity=digest([catalog['catalog_identity'], views.identity]))
            a = generation(cat, renderer, (ms[0].key,), dict(comparison='B', arm='full_transcript'))
            b = generation(newcat, view_renderer, (ms[0].key,), dict(comparison='B', arm='all_turn_evidence_view'))
            contrasts.append(dict(comparison='B', prefix_identity=pid, owner=p.owner_id, head='MS',
                input_identities=[a,b], source_ids=list(ms[0].source_ids), omitted_turns=0,
                same_selected_sources=True, summary_generated=False, quality_effect='not_measured'))
        else:
            issues.append(dict(prefix_identity=pid, comparison='B', status='complete isolated source unavailable'))
    save(out/'MS_VIEW_RECEIPTS_PRIVATE.json', view_receipts)
    save(out/'COMPARISONS_PRIVATE.json', contrasts)
    save(out/'GENERATION_INPUTS_PRIVATE.json', list(prepared.values()))
    save(out/'INPUT_GAPS.json', issues)
    # Rebuild all 22 exact S requests with the NEW reusable adapter. No future
    # audit/repair result is invented for these real materials.
    prep = 'outputs/pm_rl1/completion_preparation_20261022/'
    base = 'outputs/pm_rl1/judge_selection_preparation_20261014_v1/feedback_source_evidence_preparation_20261022_v2/'
    materials = old(prep+'stage_materials_private.json')
    protocol = old(base+'protocol.json'); prompt = old(base+'JOINT_PROMPT_EN.txt')
    prior = {x['identity']:x for x in old(prep+'primary_requests_private.json')}
    adapter = DevelopmentAdapter(prompt=prompt, config=protocol['config'])
    primary = []
    for m in materials:
        request = adapter.prepare({k:m[k] for k in ('reply','evidence')}, 'S')
        previous = prior[request['primary_preparation_identity']]
        if request['wire_body'] != previous['wire_body'] or request['local_schema'] != previous['local_schema']:
            raise ValueError('complete J1 primary wire changed')
        primary.append(dict(material=m['key'], purpose=m['purpose'], request=request))
    save(out/'J1_PRIMARY_REQUESTS_PRIVATE.json', primary)
    save(out/'J1_HANDOFF.json', dict(adapter_identity=adapter.identity,
        primary_requests=len(primary), audit_slots_upper=len(primary), repair_slots_upper=len(primary),
        stage_recovery_shared=16, maximum_development_attempts=3*len(primary)+16,
        primary_wire_equal_to_prior=True, repair_interface='new source-evidence + score-links; full final schema',
        production_launch='not connected to approved live financial broker',
        development_does_not_require_qualification=True, real_requests=0, qualification_granted=False,
        validation='selected-route phase still requires exposure adjudication; no sealed material opened',
        human_packet='existing 8 pairs + 6 regressions only; no new assignment or expansion',
        launch_proposal='historical 141 S / 259 A including validation; not approved; no counter or money revision'))
    fresh = [x for x in prepared.values() if not x['reusable_old_requests']]
    b_rows = [x for x in contrasts if x['comparison']=='B']
    profile = dict(version=VERSION, prefixes=len(rows), split=dict(Counter(r['split'] for r in rows)),
        bindings=dict(totals), ms_complete_turn_views=len(view_receipts),
        ms_turns_omitted=0, ms_new_summaries=0, semantic_updates_created=0, semantic_relations_created=0,
        selected_dev_prefixes=len(selected), selected_dev_owners=len(by_owner),
        A_pairs=sum(x['comparison']=='A' for x in contrasts),
        A_changed_choices=sum(x.get('changed_candidate',False) for x in contrasts), B_pairs=len(b_rows),
        B_input_token_deltas=[prepared[x['input_identities'][1]]['usage']['input_tokens']-
                              prepared[x['input_identities'][0]]['usage']['input_tokens'] for x in b_rows],
        C_status='not prepared: no verified applicability-condition annotations; no invented labels',
        prepared_unique_G_inputs=len(prepared), reusable_old_G_inputs=len(prepared)-len(fresh),
        future_G_upper_if_all_approved=len(fresh), total_G_input_tokens=sum(x['usage']['input_tokens'] for x in fresh),
        old_primary_inputs_checked=len(old_requests), old_base_lora_pairs_preserved=len(pairs),
        old_input_identical_but_identity_changed=sum(bool(x['same_messages_old_requests']) and not x['reusable_old_requests'] for x in prepared.values()),
        actual_model_calls=0, actual_API_usd=0, new_human_reviews=0, BC_checkpoints=0, natural_PPO_updates=0,
        J1_primary_wire_verified=len(primary), new_reward_qualified=False,
        elapsed_cpu_preparation_seconds=round(time.monotonic()-start,3))
    save(out/'PROFILE.json', profile)
    for p,h in protected.items():
        if sha(Path(p)) != h: raise ValueError('protected file modified')
    save(out/'PROTECTED_HASHES.json', protected)
    save(out/'INPUT_HASHES_PRIVATE.json', used)
    sources = ['scripts/rl1/132_prepare_evidence_views_and_development.py',
        'src/metacom_pm/rl1/resource_evidence_views.py','src/metacom_pm/rl1/resource_organization.py',
        'src/metacom_pm/rl1/temporal_evidence_ledger.py','src/metacom_pm/rl1/development_feedback.py',
        'src/metacom_pm/rl1/feedback_score_audit.py','src/metacom_pm/rl1/strict_audit_delivery.py',
        'src/metacom_pm/rl1/diagnostic_engine.py','src/metacom_pm/rl1/recovery_schedule.py']
    save(out/'SOURCE_CODE_HASHES.json', {s:sha(PROJECT/s) for s in sources})
    save(out/'OUTPUT_MANIFEST.json', {str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file()})
    print(json.dumps(profile, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--audit', type=Path, default=PROJECT/'outputs/pm_rl1/reorganization_20261029_v4')
    parser.add_argument('--organization', type=Path, default=PROJECT/'outputs/pm_rl1/resource_organization_20261029_v1')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--tokenizer-dir', type=Path, required=True)
    args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=False, mode=0o700)
    try: run(args)
    except BaseException as exc:
        save(args.output/'FAILURE.json', dict(type=type(exc).__name__, error=str(exc), no_real_calls=True))
        raise
