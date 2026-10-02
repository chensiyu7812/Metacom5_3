"""Lossless intake of independent pilot reviews. No missing-to-zero conversion."""
import json
from .schema import digest


def read_unique_json(path):
    def unique(pairs):
        result={}
        for k,v in pairs:
            if k in result: raise ValueError('duplicate JSON key: '+k)
            result[k]=v
        return result
    return json.loads(path.read_text(),object_pairs_hook=unique)


def validate_submission(raw, *, exam, source_sha256):
    if raw.get('protocol')!='pm-rl1-independent-review-v1' or raw.get('source_sha256')!=source_sha256:
        raise ValueError('review instrument/source binding mismatch')
    if raw.get('reviewer_kind') not in ('individual_human','human_consensus','model'):
        raise ValueError('reviewer provenance is required; a model is not a second human')
    if not isinstance(raw.get('reviewer_identity'),str) or not raw['reviewer_identity'].strip():
        raise ValueError('missing reviewer identity')
    if raw['reviewer_kind']=='model' and not str(raw.get('reviewer_details','')).strip():
        raise ValueError('model review needs a disclosed model/version description')
    expected={i['item_id'] for i in exam['items']}
    rows=raw.get('items',[])
    if len(rows)!=len(expected) or {r.get('item_id') for r in rows}!=expected:
        raise ValueError('review item IDs missing, duplicated or replaced')
    normalized=[]
    for row in rows:
        if set(row)!={'item_id','q_A','m_A','q_B','m_B','pairwise','evidence','uncertainty'}:
            raise ValueError('review fields differ from the instrument')
        value={'item_id':row['item_id']};missing=[]
        for k in ('q_A','m_A','q_B','m_B'):
            allowed=('0','1','2','3','4') if k.startswith('q') else ('0','0.25','1')
            s=row[k]
            if not isinstance(s,str) or s not in (*allowed,'','uncertain'):
                raise ValueError('rating outside the declared scale')
            if s in ('','uncertain'):
                value[k]=None;missing.append(dict(field=k,reason='unanswered' if s=='' else 'reviewer_uncertainty'))
            else:value[k]=int(s) if k.startswith('q') else float(s)
        if row['pairwise'] not in ('','A','B','equivalent','uncertain'):
            raise ValueError('invalid pairwise verdict')
        for k in ('evidence','uncertainty'):
            if not isinstance(row[k],str):raise ValueError('review reason must be text')
            value[k]=row[k]
        value['pairwise']=row['pairwise'] or None
        value['missing']=missing
        value['completed']=all(row[k]!='' for k in ('q_A','m_A','q_B','m_B','pairwise')) and bool(row['evidence'].strip())
        value['uncertainty_explained']=not (any(row[k]=='uncertain' for k in ('q_A','m_A','q_B','m_B','pairwise')) and not row['uncertainty'].strip())
        normalized.append(value)
    return dict(status='INDEPENDENT_REVIEW_INTAKE_NOT_AUTOMATIC_GOLD',source_sha256=source_sha256,
        raw_submission_identity=digest(raw),reviewer_identity=raw['reviewer_identity'],
        reviewer_kind=raw['reviewer_kind'],reviewer_details=raw.get('reviewer_details',''),
        rows=normalized,complete_items=sum(r['completed'] for r in normalized),
        unresolved_uncertainty_explanations=sum(not r['uncertainty_explained'] for r in normalized),
        training_feedback_allowed=False)
