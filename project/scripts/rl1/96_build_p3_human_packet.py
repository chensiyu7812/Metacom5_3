#!/usr/bin/env python3
"""Build a frozen blind 40-pair handoff from locked conditions and full sources."""
from collections import Counter
import base64
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / 'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.evidence import evidence_turns
from metacom_pm.rl1.human_calibration import PROTOCOL
from metacom_pm.rl1.judge_completion import ROLE_CONTRACT
from metacom_pm.rl1.schema import digest

ROOT = PROJECT / 'outputs/pm_rl1/completion_20260930_v2/P3'
OUT = ROOT / 'calibration'

# Coordinator-created diagnostic contrasts, never independent human truth.
# Only the indicated assertion is replaced in the four severe contrasts.
CONTROLS = {
    'development': [
        (102, ['C:T008', 'C:T009'],
         "The earlier supporter described a conflict with their mother, but that is not my own experience. Would you like to explore how to talk with your mom about choosing your friends?",
         "When I said my mom did not want me to make friends with some people, I was describing my own experience. Would you like to explore how to talk with your mom about choosing your friends?"),
        (104, ['C:T005', 'C:T013'],
         "Talking with your old college friend helped you see your thesis from a different perspective. What part of that perspective feels most helpful to hold onto?",
         "Talking with me helped you see your thesis from a different perspective. What part of that perspective feels most helpful to hold onto?"),
        (97, ['C:T000', 'C:T008'],
         "Your boss has resigned, and you are worried about who will take over. It makes sense to want respectful leadership after what you have been through.",
         "Your boss has not resigned, and you will have to keep reporting to that same boss. It makes sense to want respectful leadership after what you have been through."),
        (96, ['C:T011', 'C:T012'],
         "You are planning to discuss the new relationship with your therapist. It is good that yoga and reading give you some space to unwind.",
         "You have already discussed the new relationship with your therapist in your session. It is good that yoga and reading give you some space to unwind."),
        (105, ['C:T016'],
         "I'm glad you feel heard. You can take some time before deciding what to do next.",
         "I am glad you feel heard. You can take some time before deciding what to do next."),
        (111, ['C:T006', 'C:T008'],
         "It's understandable that this feels unfair. Would you like to talk through what options you have?",
         "It is understandable that this feels unfair. Would you like to talk through what options you have?"),
        (100, ['C:T004', 'C:T006'],
         "It can feel vulnerable to share something personal. You could start with a topic you feel comfortable discussing and decide how much to share at your own pace.",
         "You do not have to share everything at once. Would it help to think about what you feel comfortable making public?"),
        (109, ['C:T002'],
         "I'm here to listen. What has been weighing on you lately?",
         "You can take your time. Would you like to tell me more about what has been tough?"),
    ],
    'validation': [
        (88, ['C:T004', 'C:T006', 'C:T012'],
         "The earlier supporter described having faced rejection; I cannot claim their experience as mine. Could you tell me what usually happens when you reach out to someone?",
         "When I said I had been there myself, I meant my own experience of romantic rejection. Could you tell me what usually happens when you reach out to someone?"),
        (64, ['C:T002', 'C:T006', 'C:T008'],
         "Your daughter's cold and asthma are making it hard for her to sleep, and the worry is keeping you up too. It sounds exhausting to see your child struggling and wish you could take it away.",
         "Your son's cold and asthma are making it hard for him to sleep, and the worry is keeping you up too. It sounds exhausting to see your child struggling and wish you could take it away."),
        (77, ['C:T002', 'C:T014'],
         "You missed out on that overseas promotion and no longer have that offer to accept. Feeling both relief and worry about your career can be difficult to sit with.",
         "You still have that overseas promotion offer and can choose to accept it. Feeling both relief and worry about your career can be difficult to sit with."),
        (38, ['C:T013', 'C:T015'],
         "You are considering asking your supervisor for workload adjustments. You could think through what changes would help and how you would like to bring them up.",
         "Your supervisor has already approved your workload adjustments. You could think through what changes would help and how you would like to bring them up."),
        (24, ['C:T001', 'C:T002'],
         "I'm sorry you lost your dog. It is okay to take time to grieve.",
         "I am sorry you lost your dog. It is okay to take time to grieve."),
        (40, ['C:T001'],
         "It's painful to feel left out. Do you want to talk more about what happened?",
         "It is painful to feel left out. Do you want to talk more about what happened?"),
        (16, ['C:T001', 'C:T002', 'C:T003'],
         "That sounds difficult. Would you like to tell me what nights have been like for you lately?",
         "I'm here to listen. What feels most difficult about this right now?"),
        (49, ['C:T000'],
         "Of course. Take your time; what would you like to talk about?",
         "Yes, I'm here to listen. You can start wherever you feel comfortable."),
    ],
}


def read(path):
    return json.loads(path.read_text())


def save(path, value):
    with path.open('x') as f:
        f.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def main():
    if (OUT / 'packet_freeze.json').exists():
        raise RuntimeError('packet already frozen')
    lock_path = OUT / 'selection_lock_private.json'
    lock = read(lock_path)
    for name, expected in lock['source_files'].items():
        assert sha256_file(PROJECT / name) == expected, name
    pool = read(ROOT / 'common_evidence/evidence_pool_private.json')
    maps = {r['index']: r for r in read(ROOT / 'common_evidence/source_map_private.json')}
    pairs = []
    for row in lock['natural_pairs']:
        replies = []
        for side in row['sides']:
            path = Path(side['raw_path'])
            assert sha256_file(path) == side['raw_sha256'], 'changed actual generation'
            raw = read(path)
            assert raw['finish_reason'] == 'natural_stop' and raw['text'].strip()
            replies.append(raw['text'])
        pairs.append(dict(row, kind='natural', replies=replies))
    for group, controls in CONTROLS.items():
        assert [r[0] for r in controls] == lock['control_slots'][group]
        for category, (index, ids, left, right) in zip(lock['control_types'], controls):
            m = maps[index]
            assert (m['owner'] in lock['development_owners']) == (group == 'development')
            evidence = pool[m['prefix_identity']]
            turns = evidence_turns(evidence)
            sources = [turns[s] for s in ids]
            pairs.append(dict(pair_id=digest([lock['protocol'], group, category, index])[:20],
                group=group, kind='control', control_type=category, index=index, owner=m['owner'],
                prefix_identity=m['prefix_identity'], replies=[left, right],
                construction='AI coordinator authored source-bound contrast; human validity and severity still pending',
                source_anchors=sources,
                intended_check=('second reply contains targeted material error; first is the contrast, not certified gold'
                    if category in lock['control_types'][:4] else
                    'no severe factual penalty from generic support/meaning-preserving contraction alone; quality remains a human judgment'),
                uses_role_contract=category in ('identity', 'subject')))
    assert len(pairs) == 48
    assert len({p['pair_id'] for p in pairs}) == 48
    active = [p for p in pairs if p['group'] != 'reserve']
    packet_identity = digest(dict(protocol=PROTOCOL, pairs=pairs, evidence=pool,
        role_contract=ROLE_CONTRACT, selection_sha256=sha256_file(lock_path)))
    save(OUT / 'pairs_private.json', dict(packet_identity=packet_identity, pairs=pairs))
    # Fresh local key custody. Never embedded in the forms or human exports.
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    key_path = OUT / 'label_decryption_key_private.pem'
    with key_path.open('xb') as f:
        f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()))
    key_path.chmod(0o600)
    public_key = base64.b64encode(key.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)).decode()
    handoff = OUT / 'human_handoff'
    handoff.mkdir(exist_ok=True)
    template = PROJECT / 'src/metacom_pm/rl1/calibration_form.html'
    template_text = template.read_text()
    manifest = {}
    for number in (1, 2):
        rater = f'rater_{number}'
        items = []
        hidden = {}
        ordered = sorted(active, key=lambda p: digest([packet_identity, rater, 'order', p['pair_id']]))
        for p in ordered:
            swapped = int(digest([packet_identity, rater, 'swap', p['pair_id']]), 16) % 2 == 1
            a, b = p['replies'][::(-1 if swapped else 1)]
            item_id = digest([packet_identity, rater, p['pair_id']])[:20]
            items.append(dict(item_id=item_id, source_key=p['prefix_identity'], A=a, B=b))
            hidden[item_id] = dict(pair_id=p['pair_id'], group=p['group'], kind=p['kind'],
                                   index=p['index'], owner=p['owner'], swapped=swapped)
        form = dict(protocol=PROTOCOL, packet_identity=packet_identity, rater_slot=rater,
            role_contract=ROLE_CONTRACT, public_key_spki=public_key, items=items,
            sources={i['source_key']: pool[i['source_key']] for i in items})
        form['form_identity'] = digest(form)
        save(OUT / f'{rater}_form.json', form)
        save(OUT / f'{rater}_map_private.json', hidden)
        payload = json.dumps(form, ensure_ascii=False).replace('<', '\\u003c').replace('&', '\\u0026')
        with (handoff / f'{rater}.html').open('x') as f:
            f.write(template_text.replace('__FORM_DATA__', payload))
        manifest[rater] = dict(form_identity=form['form_identity'], html_sha256=sha256_file(handoff / f'{rater}.html'))
    save(OUT / 'packet_summary.json', dict(status='BLIND_FORMS_PREPARED_HUMAN_LABELS_PENDING',
        packet_identity=packet_identity, active_pairs=40, reserve_pairs=8, human_reviews_received=0,
        counts=dict(Counter(p['group'] + '_' + p['kind'] for p in pairs)),
        owner_partition=dict(development=lock['development_owners'], validation=lock['validation_owners']),
        natural_executor_contrasts=4, natural_resource_contrasts=20,
        full_sources_in_both_forms=True, source_truncation=False,
        interpretation='Source-family envelope is owner-disjoint. Control expected effects are construction hypotheses, not human labels.',
        limitations=lock['limitations'], reward_qualified=False, forms=manifest))
    files = [p for p in OUT.iterdir() if p.is_file() and p.name != 'packet_freeze.json']
    save(OUT / 'packet_freeze.json', dict(packet_identity=packet_identity,
        files={p.name: sha256_file(p) for p in files},
        human_forms={p.name: sha256_file(p) for p in handoff.glob('*.html')},
        source_files={str(p.relative_to(PROJECT)): sha256_file(p) for p in [Path(__file__), template,
            PROJECT / 'src/metacom_pm/rl1/human_calibration.py',
            ROOT / 'common_evidence/input_freeze.json']}))
    print(json.dumps(read(OUT / 'packet_summary.json'), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
