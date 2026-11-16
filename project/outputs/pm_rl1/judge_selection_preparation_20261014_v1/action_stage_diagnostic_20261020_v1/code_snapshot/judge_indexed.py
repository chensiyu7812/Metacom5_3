"""Prepared next transport contract: model selects IDs, code resolves raw spans.

NOT executed/qualified by the v1 pilot. q/m anchors stay unchanged. Whole source
turns and response sentences are coarser citations; semantic relevance must still
be independently reviewed. No factual conclusion is filled in by this resolver.
"""
from hashlib import sha256
import json
import re

from .evidence import evidence_turns
from .judge import RUBRIC,_pairs,_keys,parse_measurement
from .schema import digest

FORMAT='''Return one JSON object with exactly the following structure. Select existing IDs from the supplied evidence and response units; do not copy or paraphrase quotations into the JSON. The program will resolve each selected ID to its exact original text and character positions. Selecting an ID is not proof that it supports your conclusion: explain the semantic relationship.
Keys:
status: "scored" or "uncertain"; q: integer 0..4 or null; m: 0,0.25,1 or null.
q_rationale: {current_need: text, response_unit_ids: nonempty array of response-unit IDs, source_turn_ids: nonempty array of legal evidence-turn IDs, reason: text}.
claims: array of {response_unit_id: one response-unit ID, relation: "supported","contradicted","unsupported" or "uncertain", severity: 0,0.25 or 1, source_turn_ids: array of legal evidence-turn IDs, reason: text}.
misuse_findings: zero-based indexes of actual errors in claims.
coverage: text explaining which personal claims/boundaries were checked.
uncertainty_reasons: array of strings, empty only when scored.
The earlier q/m definitions apply. A source turn can contain multiple clauses: specify in reason which one is relevant. A tentative question is not automatically an asserted fact. No support/contradiction label may rest on a supporter guess alone. q_rationale always selects current-context evidence even if there are no personal factual claims. A claim marked supported/contradicted must select source evidence. Do not cite unselected future material; only the supplied IDs exist.
'''
INDEXED_RUBRIC=(RUBRIC.split('Return ONE JSON object',1)[0]
    .replace('quote the smallest complete response span and assess','select the smallest complete response unit and assess')
    .replace('Supported/contradicted relations require exact source quotes.',
             'Supported/contradicted relations require legal source-turn IDs, resolved by the program to exact quotes.')
    .replace('quote relevant context if present.','select relevant source turns if present.'))+FORMAT
INDEXED_RUBRIC_ID=digest(dict(protocol='pm-rl1-qm-indexed-evidence-candidate-v2',text=INDEXED_RUBRIC))
VERSION='pm-rl1-qm-indexed-span-v2'


def response_units(reply):
    if not isinstance(reply,str) or not reply.strip():raise ValueError('empty reply')
    units=[];cursor=0
    boundaries=[m.end() for m in re.finditer(r'[.!?](?=\s|$)',reply)]
    if not boundaries or boundaries[-1]!=len(reply):boundaries.append(len(reply))
    for end in boundaries:
        while cursor<end and reply[cursor].isspace():cursor+=1
        stop=end
        while stop>cursor and reply[stop-1].isspace():stop-=1
        if stop>cursor:units.append(dict(id=f'R{len(units)+1:03d}',text=reply[cursor:stop],start=cursor,end=stop))
        cursor=end
    return units


def messages_and_schema(evidence,reply):
    turns=evidence_turns(evidence);units=response_units(reply)
    string={'type':'string','minLength':1}
    source_ids={'type':'array','items':{'type':'string','enum':list(turns)}}
    response_id={'type':'string','enum':[u['id'] for u in units]}
    def obj(properties):return dict(type='object',properties=properties,required=list(properties),additionalProperties=False)
    schema=obj(dict(status={'type':'string','enum':['scored','uncertain']},q={'enum':[0,1,2,3,4,None]},m={'enum':[0,.25,1,None]},
        q_rationale=obj(dict(current_need=string,response_unit_ids={'type':'array','minItems':1,'items':response_id},
            source_turn_ids={**source_ids,'minItems':1},reason=string)),
        claims={'type':'array','items':obj(dict(response_unit_id=response_id,
            relation={'enum':['supported','contradicted','unsupported','uncertain']},severity={'enum':[0,.25,1]},
            source_turn_ids=source_ids,reason=string))},
        misuse_findings={'type':'array','items':{'type':'integer','minimum':0}},coverage=string,
        uncertainty_reasons={'type':'array','items':string}))
    messages=[dict(role='system',content=INDEXED_RUBRIC),dict(role='user',content=json.dumps(dict(
        legal_evidence=evidence,reply=reply,response_units=[{k:u[k] for k in ['id','text']} for u in units]),ensure_ascii=False))]
    return messages,schema


def parse_indexed(raw,**bindings):
    base=dict(response_sha256=sha256(bindings['reply'].encode()).hexdigest(),legal_evidence_identity=digest(bindings['evidence']),
        rubric_identity=INDEXED_RUBRIC_ID,judge_runtime_identity=bindings['runtime_identity'],measurement_draw_id=bindings['draw_id'],
        parser_version=VERSION,raw_output_sha256=sha256(raw.encode()).hexdigest(),reward_eligible=False,q=None,m=None)
    if bindings['finish_reason']!='natural_stop':return base|dict(measurement_status='technical_failure',technical_reason=bindings['finish_reason'])
    final=raw.strip()
    if '</think>' in final:
        if final.count('</think>')!=1:return base|dict(measurement_status='parse_or_evidence_failure',error='multiple thinking closures')
        final=final.split('</think>',1)[1].strip()
    if final.startswith('```json') and final.endswith('```'):final=final[7:-3].strip()
    try:
        obj=json.loads(final,object_pairs_hook=_pairs,parse_constant=lambda x:(_ for _ in ()).throw(ValueError('nonfinite JSON')))
        _keys(obj,'status q m q_rationale claims misuse_findings coverage uncertainty_reasons')
        _keys(obj['q_rationale'],'current_need response_unit_ids source_turn_ids reason')
        if not isinstance(obj['claims'],list):raise ValueError('claims must be a list')
        for claim in obj['claims']:
            _keys(claim,'response_unit_id relation severity source_turn_ids reason')
        turns=evidence_turns(bindings['evidence']);units={u['id']:u for u in response_units(bindings['reply'])}
        def resolve(ids):
            if not isinstance(ids,list) or any(not isinstance(i,str) or i not in turns for i in ids):
                raise ValueError('invalid legal source IDs')
            return [dict(source_id=i,quote=turns[i]['text']) for i in ids]
        qr=obj['q_rationale']
        if not isinstance(qr['response_unit_ids'],list) or not qr['response_unit_ids']:
            raise ValueError('quality rationale requires response units')
        if any(not isinstance(i,str) or i not in units for i in qr['response_unit_ids']):
            raise ValueError('unknown response unit')
        if any(not isinstance(c['response_unit_id'],str) or c['response_unit_id'] not in units for c in obj['claims']):
            raise ValueError('unknown claim response unit')
        selected=[units[i] for i in qr['response_unit_ids']]
        quote=bindings['reply'][min(u['start'] for u in selected):max(u['end'] for u in selected)]
        converted=dict(status=obj['status'],q=obj['q'],m=obj['m'],q_rationale=dict(current_need=qr['current_need'],
            response_quote=quote,evidence=resolve(qr['source_turn_ids']),reason=qr['reason']),
            claims=[dict(response_quote=units[c['response_unit_id']]['text'],relation=c['relation'],severity=c['severity'],
                evidence=resolve(c['source_turn_ids']),reason=c['reason']) for c in obj['claims']],
            misuse_findings=obj['misuse_findings'],coverage=obj['coverage'],uncertainty_reasons=obj['uncertainty_reasons'])
        parsed=parse_measurement(json.dumps(converted,ensure_ascii=False),**bindings)
        return parsed | {k:v for k,v in base.items() if k not in ['q','m']} | dict(indexed_judge_output=obj,
            citation_resolution='model-selected IDs resolved mechanically to complete source turns and response sentences',
            semantic_validation=False,transport_contract_status='MEASUREMENT_CANDIDATE_NOT_REWARD_QUALIFIED')
    except (ValueError,TypeError,KeyError,IndexError) as exc:
        return base | dict(measurement_status='parse_or_evidence_failure',error=str(exc))
