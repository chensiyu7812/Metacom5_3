"""Evidence integrity and public/private separation for the second paired review."""
import hashlib
import json
import os
from pathlib import Path
import shutil

import pytest

from metacom_pm.rl1v3.journal.rs_batch_review import unblind

ROOT=os.environ.get('JOURNAL_RS_BATCH_REVIEW')


def private_inputs(root):
    manifest=json.loads((root/'MANIFEST.json').read_text())
    paths=list(manifest['input_sha256'])
    return paths


@pytest.mark.skipif(not ROOT,reason='private paired review not supplied')
def test_actual_evidence_freeze_pairing_and_public_no_raw_or_gold():
    root=Path(ROOT)
    receipt=json.loads((root/'BLIND_FREEZE_RECEIPT.json').read_text())
    assert not receipt['reviewer_key_opened'] and not receipt['reviewer_paired_output_file_opened']
    assert receipt['root_already_saw_all_outputs'] and receipt['supplied_resource_content_visible']
    rows=[json.loads(l) for l in (root/'PAIRED_REVIEW.private.jsonl').read_text().splitlines()]
    summary=json.loads((root/'SUMMARY_PUBLIC.json').read_text())
    assert len(rows)==12 and summary['verified_item_evidence_spans']==42
    assert summary['development_item_observations']==dict(consistent_with_constraint=34,clear_apparent_violation=2,uncertain=6)
    assert not summary['blinding']['independent_blind_assessment']
    for row in rows:
        assert row['qualified_reward'] is None and row['qualified_semantic_task_interval']==[0,1]
        for item in row['items']:
            assert item['evidence_quote']==row['response'][item['quote_start_char']:item['quote_end_char']]
            assert item['qualified_semantic_verdict']=='uncertain'
        for flag in row['auxiliary_flags']:
            assert flag['quote']==row['response'][flag['start_char']:flag['end_char']]
            assert flag['not_an_added_frozen_criterion']
        serialized=json.dumps(summary)
        assert row['response'] not in serialized
        assert all(i['frozen_criterion'] not in serialized for i in row['items'])
    assert summary['qualified_rewards']==0 and summary['qualified_semantic_success_rate'] is None


@pytest.mark.skipif(not ROOT,reason='private paired review not supplied')
@pytest.mark.parametrize('mutation',['response_span','criterion'])
def test_tampered_spans_or_changed_frozen_criteria_rejected(tmp_path,mutation):
    root=Path(ROOT);receipt=json.loads((root/'BLIND_FREEZE_RECEIPT.json').read_text())
    records=[json.loads(l) for l in (root/'BLIND_REVIEW_FROZEN.private.jsonl').read_text().splitlines()]
    if mutation=='response_span':records[0]['items'][0]['evidence_quote']='not in the returned response'
    else:records[0]['items'][0]['frozen_criterion']='replacement posthoc criterion'
    changed=tmp_path/'BLIND_REVIEW_FROZEN.private.jsonl'
    changed.write_text(''.join(json.dumps(r,sort_keys=True)+'\n' for r in records))
    # Even a regenerated outer receipt cannot make a false quote/rubric valid.
    receipt['blind_review_sha256']=hashlib.sha256(changed.read_bytes()).hexdigest()
    (tmp_path/'BLIND_FREEZE_RECEIPT.json').write_text(json.dumps(receipt))
    paths=private_inputs(root)
    by_name={Path(p).name:p for p in paths}
    args=[by_name[name] for name in ['RS_BLIND_PRIVATE.jsonl','REVIEW_KEY_PRIVATE.jsonl',
        'PAIRED_RESPONSES_PRIVATE.jsonl','DETAILS.private.jsonl','retrieval.private.jsonl','evalspec.private.jsonl']]
    with pytest.raises(ValueError,match='evidence absent|requirement/prohibition set changed'):
        unblind(tmp_path,*args)
