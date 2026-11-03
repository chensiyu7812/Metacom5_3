#!/usr/bin/env python3
"""Use original human answers locally and prepare the EXISTING audit requests.

Read-only toward the paid stage. No dispatch, credentials, new labels, revised
prompts, automatic score replacement, or optimizer. A new output path is required.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT/'src'))
from metacom_pm.rl1.development_feedback import thaw_inputs
from metacom_pm.rl1.feedback_reference_review import prepare_bound_review
from metacom_pm.rl1.schema import digest

BASE = PROJECT/'outputs/pm_rl1'


def build(package, snapshot, references, output):
    if output.exists():
        raise ValueError('new immutable output directory required')
    sources = {}
    def sha(path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    def read(path):
        path = Path(path).resolve(); sources[str(path)] = sha(path)
        return json.loads(path.read_text())
    def verify_folder(folder):
        for name, expected in read(folder/'OUTPUT_MANIFEST.json').items():
            if Path(name).is_absolute() or '..' in Path(name).parts:
                raise ValueError('unsafe manifest path')
            if sha(folder/name) != expected:
                raise ValueError('snapshot artifact changed: '+name)
    verify_folder(snapshot); verify_folder(references)
    for path, expected in read(references/'SOURCE_HASHES.json').items():
        if sha(path) != expected:
            raise ValueError('original human answer/source changed: '+path)
    registry = read(references/'ANSWER_REGISTRY_PRIVATE.json')
    # Validate every complete source/reply join, including records not in this stage.
    for ref in registry:
        if digest(ref['evidence']) != ref['evidence_identity'] or any(
                digest(text) != rid for rid, text in ref['replies'].items()):
            raise ValueError('reference registry content identity changed')
    config = read(package/'J_CONFIG_PRIVATE.json')
    material_list, adapter = thaw_inputs(config['inputs'])
    material = {x['key']:{k:x[k] for k in ('reply', 'evidence')} for x in material_list}
    root = Path(config['policy']['run_directory'])
    protocol = read(root/'PROTOCOL.json')
    summary = read(snapshot/'SUMMARY.json'); provenance = read(snapshot/'SOURCE_HASHES.json')
    if (digest(protocol) != config['protocol_identity'] or protocol['adapter'] != adapter.identity
            or summary['protocol_identity'] != config['protocol_identity']
            or sha(package/'J_CONFIG_PRIVATE.json') != provenance['config_sha256']):
        raise ValueError('original protocol/adapter/snapshot changed')
    ledger = Path(config['ledger']); ledger_bytes = ledger.read_bytes()
    if (len(ledger_bytes) != provenance['ledger_snapshot_bytes']
            or sha(ledger) != provenance['ledger_snapshot_sha256']):
        raise ValueError('stage has advanced; create a fresh progress snapshot first')
    sources[str(ledger.resolve())] = sha(ledger)
    for path, expected in config['policy']['historical_files'].items():
        if sha(path) != expected:
            raise ValueError('frozen historical source changed: '+path)
    details = read(snapshot/'DETAILS_PRIVATE.json')
    requests = read(root/'S/REQUESTS.json')
    if set(material) != {m['key'] for m in details['materials']}:
        raise ValueError('material coverage changed')
    prepared, cards, missing, finals = {}, [], [], {}
    for row in details['materials']:
        key, slot = row['key'], row['logical_identity']; item = material[key]
        if (row['reply_identity'] != digest(item['reply'])
                or row['evidence_identity'] != digest(item['evidence'])):
            raise ValueError('material identity changed')
        attempts = [a for a in details['attempts'] if a['logical_identity'] == slot and a['component'] == 'S']
        valid = [a for a in attempts if a['settled'] and a['technical_valid']]
        if not valid:
            missing.append(dict(key=key, status='unsettled' if any(not a['settled'] for a in attempts)
                                else 'failed' if attempts else 'not_attempted',
                audit_request=None, q=None, m=None, automatic_retry=False))
            continue
        # The stage uses the first valid predecessor, including model uncertainty.
        attempt = min(valid, key=lambda a:a['ordinal'])
        rawpath = root/'S'/(attempt['attempt_id']+'.raw.json')
        raw = read(rawpath)
        record = read(root/'S'/(attempt['attempt_id']+'.result.json'))
        if (sha(rawpath) != attempt['raw_sha256'] or digest(raw) != record['raw_identity']
                or raw['attempt_id'] != attempt['attempt_id']):
            raise ValueError('original raw result changed')
        refs = [r for r in registry if r['task_family'] in ('singles', 'supplements')
                and r['evidence_identity'] == row['evidence_identity']
                and r['reply_identity'] == row['reply_identity']]
        built = prepare_bound_review(adapter, item, requests[slot], raw, refs)
        if built['primary_evaluation'] != record['evaluation']:
            raise ValueError('reparsed primary differs from stored evaluation')
        if built['local_review']['candidate'] != row['candidates']['S']:
            raise ValueError('snapshot numeric candidate changed')
        prepared[key] = built['request']; finals[key] = built['primary_evaluation']['value']
        cards.append(dict(key=key, logical_identity=slot, primary_attempt_id=attempt['attempt_id'],
                          **built['local_review']))
    # Compare historical scores ONLY after establishing identical complete inputs.
    oldroot = BASE/'judge_selection_preparation_20261014_v1/feedback_source_evidence_results_20261022_v2'
    olditems = read(oldroot/'ORIGINAL_INPUTS.json'); old = read(oldroot/'ALL_SLOTS.json')
    endpoints = {x['material_id']:x for x in old['endpoints']}
    comparison = []
    for key in ('V3_OFF', 'V3_ON', 'V4_OFF'):
        if olditems[key] != material[key]:
            raise ValueError('cross-version comparison has changed evidence or reply')
        current = next(c['candidate'] for c in cards if c['key'] == key)
        previous = endpoints[key]['initial']
        comparison.append(dict(key=key, evidence_identity=digest(material[key]['evidence']),
            reply_identity=digest(material[key]['reply']), old=previous, current=current,
            delta_q=current['q']-previous['q'], delta_m=current['m']-previous['m'],
            delta_U=current['U']-previous['U'],
            interpretation='Different scoring protocols; not a same-protocol repeat or accuracy estimate.'))
    ms = next(x for x in old['paired'] if x['context_id'] == 'V3')
    now = {x['key']:x['current'] for x in comparison}
    effect = dict(resource_tokens=ms['resource_tokens'], cost=ms['cost'],
        old_protocol_identity=old['protocol_identity'], current_protocol_identity=config['protocol_identity'],
        old_ON_minus_OFF=ms['initial_net']+ms['cost'],
        current_ON_minus_OFF=now['V3_ON']['U']-now['V3_OFF']['U'],
        old_net=ms['initial_net'], current_net=now['V3_ON']['U']-now['V3_OFF']['U']-ms['cost'],
        actual_policy_updates=0, correct_effect_direction_established=False)
    comparisons = [x for c in cards for x in c['comparisons']]
    result = dict(protocol_identity=config['protocol_identity'], adapter_identity=adapter.identity,
        scheduled_inputs=len(material), available_primary_scores=len(prepared),
        audit_requests_prepared=len(prepared), audit_requests_sent=0,
        missing_predecessors=dict(Counter(x['status'] for x in missing)),
        exact_single_references=len(comparisons),
        exact_existing_clarifications=sum(r['task_family']=='supplements' for c in cards for r in c['original_references']),
        comparison_dispositions=dict(Counter(x['disposition'] for x in comparisons)),
        utility_hides_component_disagreement=sum(x['utility_hides_component_disagreement'] is True for x in comparisons),
        human_labels_in_outbound_requests=0, changed_prompts=0, changed_original_scores=0,
        new_human_questions=0, paid_calls=0, new_cost_usd=0, natural_training_updates=0,
        qualification_granted=False, dispatch_order_changed=False,
        status='OFFLINE_REVIEW_READY_PAID_STAGE_REMAINS_STOPPED')
    sources[str(Path(__file__).resolve())] = sha(Path(__file__))
    sources[str(PROJECT/'src/metacom_pm/rl1/feedback_reference_review.py')] = sha(PROJECT/'src/metacom_pm/rl1/feedback_reference_review.py')
    if any(sha(path) != h for path,h in sources.items()):
        raise ValueError('source changed while preparing review')
    output.mkdir(parents=True, mode=0o700)
    def save(name, value):
        path = output/name; path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n'); path.chmod(0o600)
    save('AUDIT_REQUESTS_PRIVATE.json', prepared); save('LOCAL_REVIEW_CARDS_PRIVATE.json', cards)
    save('PRIMARY_FINALS_PRIVATE.json', finals); save('MISSING_PREDECESSORS.json', missing)
    save('CROSS_VERSION_COMPONENTS.json', comparison); save('MS_EFFECT_DIAGNOSTIC.json', effect)
    save('SUMMARY.json', result); save('SOURCE_HASHES_PRIVATE.json', sources)
    save('OUTPUT_MANIFEST.json', {p.name:sha(p) for p in output.iterdir()})
    print(json.dumps(result,ensure_ascii=False),flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, default=BASE/'execution_bridges_20261103_v1')
    parser.add_argument('--snapshot', type=Path, default=BASE/'paid_development_snapshot_20261103_refresh_final')
    parser.add_argument('--references', type=Path, default=BASE/'human_answer_reanalysis_20261103_v2')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); build(args.package,args.snapshot,args.references,args.output)
