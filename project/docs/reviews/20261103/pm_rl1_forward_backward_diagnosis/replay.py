"""Offline structural diagnosis on already-generated train inputs, not rewards."""
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import statistics
import sys

PROJECT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT/'src'))
from metacom_pm.rl1.schema import digest

BASE = PROJECT/'outputs/pm_rl1'
sources = {}


def read(path):
    data = path.read_bytes()
    sources[str(path)] = hashlib.sha256(data).hexdigest()
    return json.loads(data)


def verified(folder, name='OUTPUT_MANIFEST.json'):
    for path, expected in read(folder/name).items():
        if Path(path).is_absolute() or '..' in Path(path).parts:
            raise ValueError('unsafe manifest path')
        if hashlib.sha256((folder/path).read_bytes()).hexdigest() != expected:
            raise ValueError('changed input: '+path)


def main():
    train = BASE/'organized_initial_training_20261103_v2'
    encoding = BASE/'organized_initial_encoding_20261103_v2'
    feedback = BASE/'actual_training_feedback_20261103_v1'
    verified(train, 'PACKAGE_MANIFEST.json'); verified(encoding); verified(feedback)
    menu = read(train/'MENU_PRIVATE.json')['endpoints']
    endpoints = read(feedback/'ENDPOINTS_PRIVATE.json')
    texts = read(feedback/'INPUTS_PRIVATE.json')
    observations = read(train/'OBSERVATIONS_PRIVATE.json')
    features = read(encoding/'FEATURES_PRIVATE.json')
    assert set(observations) == set(features)
    index = {m['identity']:m for m in menu}
    assert set(index) == {e['endpoint_identity'] for e in endpoints}
    by_prefix = defaultdict(list); by_counts = defaultdict(list); by_content = defaultdict(list)
    for e in endpoints:
        m = index[e['endpoint_identity']]
        assert all(m[k] == e[k] for k in ('prefix_identity','actions','resource_tokens'))
        assert e['ON'] in texts and e['OFF'] in texts
        by_prefix[e['prefix_identity']].append(e)
        by_counts[e['prefix_identity'],tuple(e['actions'].count(i) for i in range(1,5))].append(e)
        by_content[e['prefix_identity'],e['ON']].append(e)
    varying_order = [es for es in by_counts.values() if len(es)>1]
    order_resources = []; order_replies = []; private_rows = []
    for es in varying_order:
        resources = {tuple(index[e['endpoint_identity']]['requests']['ON']['provenance']['selected_resource_identities']) for e in es}
        outputs = {e['ON'] for e in es}
        order_resources.append(len(resources)>1); order_replies.append(len(outputs)>1)
        private_rows.append(dict(prefix_identity=es[0]['prefix_identity'],
            actions=[e['actions'] for e in es], resources_changed=len(resources)>1,
            reply_changed=len(outputs)>1, quality_change=None))
    dominated = [e for es in by_content.values() for e in es
                 if e['resource_tokens'] > min(z['resource_tokens'] for z in es)]
    nonoff = [e for e in endpoints if e['actions'] != [0]]
    costs = [e['resource_tokens']/40960 for e in nonoff]
    full_groups = defaultdict(list); initial_texts = []; max_chunks = 0
    for oid,row in observations.items():
        o = row['observation']; f = features[oid]
        assert len(f['features']) == len(f['NoText_features']) == 5139
        assert f['mask'] == o['action_mask']
        full_groups[digest(f['features'])].append(oid)
        if not any(o['counts']):
            initial_texts.append(digest(o['current_prefix']))
        max_chunks = max(max_chunks,max(len(d['chunks']) for d in row['plan']['documents']))
    profile = dict(train_prefixes=len(by_prefix), candidate_programs=len(endpoints),
        non_OFF_programs=len(nonoff), non_OFF_reply_equals_OFF=sum(e['ON']==e['OFF'] for e in nonoff),
        non_OFF_reply_differs_from_OFF=sum(e['ON']!=e['OFF'] for e in nonoff),
        unique_complete_scoring_inputs=len(texts),
        programs_with_cheaper_identical_terminal_reply=len(dominated),
        prefixes_with_cheaper_identical_terminal_reply=len({e['prefix_identity'] for e in dominated}),
        same_counts_multiple_order_groups=len(varying_order),
        order_groups_with_different_resources=sum(order_resources),
        order_groups_with_different_replies=sum(order_replies),
        distinct_prefixes_with_order_resource_change=len({es[0]['prefix_identity'] for es,changed in zip(varying_order,order_resources) if changed}),
        non_OFF_cost=dict(min=min(costs),median=statistics.median(costs),max=max(costs),
                          below_one_q_category=sum(c<.25 for c in costs)),
        GET_count_distribution=dict(Counter(len(e['actions'])-1 for e in endpoints)),
        initial_observations=len(initial_texts), distinct_initial_prefix_texts=len(set(initial_texts)),
        encoded_observations=len(features), exact_full_feature_vectors=len(full_groups),
        largest_document_chunk_count=max_chunks,
        missing_q=sum(t['q'] is None for t in texts.values()), missing_m=sum(t['m'] is None for t in texts.values()),
        oracle_best_returns=None, optimal_action_heterogeneity=None, value_of_reading_before_deciding=None,
        new_human_labels=0,new_G=0,new_J=0,natural_updates=0,
        interpretation='Structural reachability/output differences, not semantic gains, labels or proof of sequential-policy advantage.')
    output = BASE/'forward_backward_diagnosis_20261103_v1'
    output.mkdir(mode=0o700,exist_ok=False)
    def save(path,value):
        path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');path.chmod(0o600)
    save(output/'PROFILE.json',profile);save(output/'ORDER_GROUPS_PRIVATE.json',private_rows)
    save(output/'DOMINATED_TERMINALS_PRIVATE.json',dominated)
    sources[str(Path(__file__).resolve())]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    save(output/'SOURCE_HASHES_PRIVATE.json',sources)
    save(output/'OUTPUT_MANIFEST.json',{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir()})
    Path(__file__).with_name('PROFILE.json').write_text(json.dumps(profile,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(profile,ensure_ascii=False))


if __name__=='__main__':main()
