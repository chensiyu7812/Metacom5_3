"""Offline exact bindings; never infer pair preferences from single scores."""
import hashlib,json
def digest(x):return hashlib.sha256(json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def without_translation(value):
    if isinstance(value,dict):return {k:without_translation(v) for k,v in value.items() if k!='zh'}
    if isinstance(value,list):return [without_translation(v) for v in value]
    return value
def match_pair(pair,endpoints,record):
    if record.get('group')!='development' or record.get('reviewer')!='Chen':return None
    if record.get('provenance',{}).get('observation_origin')!='Chen-saved-browser-record':return None
    left=endpoints[pair['left_endpoint']];right=endpoints[pair['right_endpoint']]
    if left['evidence_identity']!=right['evidence_identity'] or record['evidence_identity']!=left['evidence_identity']:return None
    if set(record['reply_identities'].values())!={left['reply_identity'],right['reply_identity']}:return None
    raw=record['raw_label'].get('preference')
    if raw not in {'A','B','tie','unknown'}:return None
    if raw in {'A','B'}:
        winner=record['reply_identities'][raw]
        mapped='A' if winner==left['reply_identity'] else 'B'
    else:mapped=raw
    return dict(old_item_id=record['item_id'],old_pair_id=record['pair_id'],old_intake_identity=record['identity'],
        old_display_to_current={side:'A' if h==left['reply_identity'] else 'B' for side,h in record['reply_identities'].items()},
        old_raw_preference=raw,current_display_preference=mapped,raw_label=record['raw_label'],
        evidence_identity=record['evidence_identity'],source=record['raw_source'],
        reuse_scope='historical pair preference under original instructions; later explicit clarification requirement separately disclosed',
        fresh_human_observations=0,current_target_reconfirmation=False)
