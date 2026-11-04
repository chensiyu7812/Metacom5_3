"""Prepare five reviewable weak-target edits, without replacing or training P2."""
import hashlib
import json
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[4]
ROOT = PROJECT / 'outputs/pm_rl1/executor_use_probe_20261104_v1'
PRIOR = PROJECT / 'outputs/pm_rl1/resource_value_probe_20261104_v1'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def main():
    rows = json.loads((ROOT / 'TARGET_CARDS_PRIVATE.json').read_text())
    inventory = json.loads((PRIOR / 'INVENTORY_PRIVATE.json').read_text())
    changes = [
        ('N04', 'single', 'speaker_attribution_only', None, None),
        ('N18', 'single', 'avoid_unestablished_RS_applicability',
         "It sounds like the warning has really shaken you. Did it explain what prompted it and what needs to change, or is that still unclear? If you'd rather talk through how this feels first, we can start there.", None),
        ('N21', 'four', 'avoid_adding_work_when_support_capacity_is_unclear',
         "You're trying to support Margaret while feeling stretched yourself. Supporting her doesn't have to mean solving the finances or taking on more work right now. You could start by telling her you're struggling too and asking what feels most pressing, while being clear about what you can manage. Would talking through that conversation help, or do you need space to talk about your own feelings first?", None),
        ('N21', 'single', 'build_on_reported_attempt_without_claiming_success',
         "You're trying to support Margaret while needing support yourself. You previously described trying to talk things out and give each other breaks. If that still feels workable, perhaps support could mean agreeing on one small way for each of you to have breathing room, rather than expecting you to carry everything. Would it help to think about what you can realistically offer Margaret and what support you need in return?", 'H005:T011'),
        ('N23', 'same_two', 'connect_past_imbalance_to_current_relationship_choice',
         "You've described feeling left out even when you make an effort to include friends. Being brushed off now may make that imbalance feel sharper. Since some friends were apologetic, would it help to think about which relationships feel worth investing in and what you'd need to see from them? We can also stay with how hurt you feel before deciding what to do.", 'H003:T007'),
    ]
    candidates = []
    for case, condition, purpose, text, turn_id in changes:
        old = next(r for r in rows if r['case'] == case and r['condition'] == condition)
        if case == 'N04':
            before = 'the strategies we discussed earlier'
            assert old['response'].count(before) == 1
            text = old['response'].replace(before, 'the boundary-setting strategies mentioned in this conversation')
        anchors = []
        if turn_id:
            source = next(n['target_source'] for n in inventory if n['case'] == case)
            turn = next(t for t in source['turns'] if t['id'] == turn_id)
            resources = json.loads(old['messages'][0]['content'].split('<resources>\n', 1)[1].split('\n</resources>', 1)[0])
            full_text = '\n'.join(t['role'] + ': ' + t['text'] for t in source['turns'])
            assert any(json.loads(r['content']).get('full_source_conversation') == full_text for r in resources)
            assert turn['role'] == 'seeker'
            anchors.append(dict(source_session=source['id'], date=source['date'], turn=turn,
                full_source_visible_in_original_input=True,
                limit='past user report, not evidence of present continuation or successful outcome'))
        record = dict(case=case, condition=condition, purpose=purpose, original_slot_id=old['slot_id'],
            prefix_identity=old['prefix_identity'], split=old['split'], owner=old['owner'],
            messages=old['messages'], messages_identity=old['messages_identity'],
            original_response=old['response'], original_response_identity=old['response_identity'],
            proposed_response=text, proposed_response_identity=digest(text), source_anchors=anchors,
            author='Codex assistant after exposed diagnostic; AI-authored weak candidate',
            human_quality_label=None, q=None, m=None, reward=None, accepted_for_training=False,
            independent_validation=False, material_helpfulness_improvement=None)
        assert record['split'] == 'train' and digest(record['messages']) == record['messages_identity']
        candidates.append(record)
    package = dict(status='SOURCE_BOUND_WEAK_DRAFTS_NOT_TRAINING_RELEASE', candidates=candidates,
        cases=4, candidates_count=5, original_dataset_replaced=False, training_updates=0,
        missing=['No independent helpfulness judgement for proposed replies.',
                 'No complete matched resource/OFF/irrelevant-input training design yet.',
                 'No post-update source/quality/latency evaluation.'],
        preservation='Keep appropriate ignoring and near-equivalent cases; do not filter all ignore targets or reward historical mentions.',
        proposed_use='Repair visible target problems and test conditional information use, not create PM rewards.')
    path = ROOT / 'REVISION_CANDIDATES_PRIVATE.json'
    if path.exists():
        assert json.loads(path.read_text()) == package
    else:
        path.write_text(json.dumps(package, ensure_ascii=False, indent=2) + '\n'); path.chmod(0o600)
    print(json.dumps(dict(status=package['status'], candidates=5, training_updates=0)))


if __name__ == '__main__':
    main()
