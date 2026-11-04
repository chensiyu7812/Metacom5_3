import json
from copy import deepcopy
import pytest
from metacom_pm.rl1.executor_revision import validate_dataset
from metacom_pm.rl1.schema import digest


def material():
    def item(content):
        s='context'
        if content: s+='\n<resources>\n'+json.dumps([dict(content=json.dumps(dict(full_source_conversation=content)))])+'\n</resources>'
        return dict(messages=[dict(role='system',content=s),dict(role='user',content='current')],selected_keys=['r'] if content else [])
    inputs={'off':item(None),'on':item('seeker: We are trying to give each other breaks.'),'other':item('seeker: Work has been difficult.')}
    rows=[]
    for key in inputs:
        text='You previously described trying to give each other breaks.' if key=='on' else 'What feels hardest right now?'
        rows.append(dict(id=key,input_identity=key,case='case',split='train',weak_supervision=True,reward=None,
            response=text,response_identity=digest(text),role='other_topic_control' if key=='other' else key,
            historical_claims=[dict(source_quote='We are trying to give each other breaks.',modality='past_report_not_current_success')] if key=='on' else []))
    return rows,inputs


def test_matched_off_source_and_other_topic_targets_are_validated():
    rows,inputs=material()
    assert validate_dataset(rows,inputs)['historical_target_rows']==1


def test_missing_controls_or_hidden_source_claims_are_not_training_ready():
    rows,inputs=material()
    with pytest.raises(ValueError,match='other-topic control'):validate_dataset(rows[:2],inputs)
    bad=deepcopy(rows);bad[0]['historical_claims']=bad[1]['historical_claims']
    with pytest.raises(ValueError,match='absent from acquired input'):validate_dataset(bad,inputs)
    bad=deepcopy(rows);bad[1]['historical_claims'][0]['modality']='known_success'
    with pytest.raises(ValueError,match='status strengthened'):validate_dataset(bad,inputs)
