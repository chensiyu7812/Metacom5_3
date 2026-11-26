"""A source-bound, goal-conditioned working interpretation, not a fact database.

Only actual GE2 readings and visible turns may enter. Model claims remain
unqualified interpretations even when their source identifiers are valid.
"""
from copy import deepcopy
import json

from ..io import canonical_json, object_sha256
from .pomdp_controller_protocol import _pairs, _nonfinite, ControllerConstraintProcessor

PROTOCOL = 'pmrl1-j-gsws-phase1-v1'
INPUT_PROTOCOL = 'gsws-common-readable-evidence-v2'
ARMS = ('A0_RAW', 'A1_READING_NOTES', 'A2_GSWS')
INTERPRETER_TOKENS = 512
COMMON_CONTEXT = ('Historical reports are scoped by the source registry to this conversation user. '
                  'They are past reports, not verified current facts. A name in a question alone '
                  'does not prove a named third party is the speaker. Source report dates are not '
                  'necessarily event dates. The visible conversation determines the current goal.')
BASE_INSTRUCTIONS = '''Read only the supplied visible dialogue and actual historical evidence.
Prepare a concise reading aid for a separate companion response generator. Do not answer
as the user or pretend to have personal experiences. Preserve speaker, negation, suggestion,
intention versus performed action, report date versus event date and quoted versus current
information. Avoid inferred hidden needs. Missing information may remain unknown. No need
to repeat every memory in a supportive reply. Prior aid is unverified model text; revise it
against the original evidence. Cite only supplied evidence IDs. Never claim a citation proves
the interpretation. Do not predict reward or output a correct resource action. Output bare JSON.'''
SYSTEMS = {
    'A1_READING_NOTES': BASE_INSTRUCTIONS + '''
Write ordinary question-conditioned reading notes in the notes string, with a list of source
IDs used. Use whatever concise prose organization helps. There is no required psychological
taxonomy. Reconsider earlier notes when new evidence becomes visible.''',
    'A2_GSWS': BASE_INSTRUCTIONS + '''
Build a shared working state: current goal and boundaries; understood claims; unresolved
gaps/conflicts; and implications for a suitable reply. Each claim keeps its subject, action
stage, event time and present applicability, using unknown when not established. A reported
claim is what a source says, not objective truth. Mark inference separately. Keep conflicts
visible rather than automatically making the newest claim true. The host supplies actual
actions and timing; your interpretation does not authorize actions. Use at most four claims.''',
}


def _obj(properties):
    return dict(type='object', properties=properties, required=list(properties), additionalProperties=False)


def schema(arm):
    text = dict(type='string')
    refs = dict(type='array', items=dict(type='string'), maxItems=8)
    if arm == 'A1_READING_NOTES':
        return _obj(dict(notes=text, evidence_ids=refs))
    if arm != 'A2_GSWS':
        raise ValueError('interpreter arm')
    claim = _obj(dict(text=text, epistemic=dict(enum=['reported', 'inferred', 'unknown']),
        subject=text, stage=dict(enum=['suggested', 'planned', 'attempted', 'performed', 'outcome', 'unknown']),
        event_time=text, applicability=dict(enum=['historical', 'current_explicit', 'unresolved']), evidence_ids=refs))
    return _obj(dict(goal_and_boundaries=text, claims=dict(type='array', items=claim, maxItems=4),
                     gaps_or_conflicts=text, response_implications=text))


def contract():
    return dict(protocol=PROTOCOL, input_protocol=INPUT_PROTOCOL, arms=list(ARMS), systems=SYSTEMS,
                schemas={a:schema(a) for a in ARMS[1:]}, interpreter_max_output_tokens=INTERPRETER_TOKENS,
                ordinary_G_decode_unchanged=True, state_is_unqualified_model_interpretation=True,
                offline_history_construction_sees_current_goal=False,
                phase1_fixed_sources_no_adaptive_policy=True, formal_reward=None)


def project(task, episode, stage, previous=None):
    """Project actual read intervals; never use the full unread pool as an observation."""
    if stage not in (0, 1):
        raise ValueError('two frozen observation stages')
    observation = episode.observe()
    evidence = []
    for index, turn in enumerate(task['turns']):
        evidence.append(dict(evidence_id='C'+str(index), kind='current_visible', speaker=turn['role'],
                             turn_index=index, report_time=task['timestamp'], text=turn['text']))
    for rid in sorted(episode.read_intervals, key=lambda x:(episode.records[x]['reported_at']['date'],
                       episode.records[x]['source_rank'], x)):
        record = episode.records[rid]
        if not episode._legal_record(record):
            raise ValueError('source no longer legal')
        for ref in record['source_refs']:
            if any(lo <= ref['turn_index'] <= hi for lo,hi in episode.read_intervals[rid]):
                evidence.append(dict(evidence_id=f"H{record['source_rank']+1}.T{ref['turn_index']}",
                    kind='historical_report', source_handle=episode._source_handle(rid),
                    record_id=rid, record_sha256=object_sha256(record), turn_index=ref['turn_index'], speaker=ref['speaker'],
                    start_char=0, end_char=len(ref['exact_quote']),
                    report_time=record['reported_at']['date'], text=ref['exact_quote']))
    ids = [e['evidence_id'] for e in evidence]
    if len(set(ids)) != len(ids):
        raise ValueError('evidence ID collision')
    previous_sha = None
    if previous is not None:
        if previous['task_sha256'] != object_sha256(task) or previous['stage'] >= stage:
            raise ValueError('foreign or noncausal previous state')
        if previous['state_sha256'] != object_sha256({k:v for k,v in previous.items() if k!='state_sha256'}):
            raise ValueError('previous state changed')
        if not set(previous['evidence_ids']) <= set(ids):
            raise ValueError('prior interpretation depends on evidence absent from current RAW')
        previous_sha = previous['state_sha256']
    value = dict(protocol=PROTOCOL, task_sha256=object_sha256(task), stage=stage,
        source_scope=COMMON_CONTEXT, current_goal_context=deepcopy(task['turns']), evidence=evidence,
        source_time=task['timestamp'], operational_context={k:deepcopy(observation[k]) for k in (
            'action_mask','action_parameters','access_budget','source_token_budget','decision_time')},
        raw_observation_sha256=object_sha256(observation), content_sha256=observation['content_sha256'],
        previous_state_sha256=previous_sha,
        previous_interpretation=None if previous is None else deepcopy(previous['interpretation']))
    value['snapshot_sha256'] = object_sha256(value)
    return value


def validate_projection(value):
    keys={'protocol','task_sha256','stage','source_scope','current_goal_context','evidence','source_time',
          'operational_context','raw_observation_sha256','content_sha256','previous_state_sha256',
          'previous_interpretation','snapshot_sha256'}
    if set(value)!=keys or value['protocol']!=PROTOCOL:
        raise ValueError('observation allowlist; no eval sidecar fields')
    if value['snapshot_sha256']!=object_sha256({k:v for k,v in value.items() if k!='snapshot_sha256'}):
        raise ValueError('observation snapshot')
    if value['source_scope']!=COMMON_CONTEXT or type(value['stage']) is not int or value['stage'] not in (0,1):
        raise ValueError('observation scope')
    return value


def model_evidence(observation):
    """One compact, common source-ID map; integrity identities remain backstage."""
    validate_projection(observation)
    current=[];history={}
    for e in observation['evidence']:
        turn=dict(id=e['evidence_id'],speaker=e['speaker'],text=e['text'])
        if e['kind']=='current_visible':current.append(turn)
        else:
            source=e['evidence_id'].split('.')[0]
            group=history.setdefault(source,dict(source_id=source,reported_at=e['report_time'],turns=[]))
            if group['reported_at']!=e['report_time']:raise ValueError('source grouping collision')
            group['turns'].append(turn)
    return dict(current_time=observation['source_time'],current_dialogue=current,history=list(history.values()))


def interpreter_messages(observation, arm):
    visible=model_evidence(observation)
    op=observation['operational_context']
    visible.update(source_scope=observation['source_scope'],
        operational_context={k:deepcopy(op[k]) for k in ('action_mask','access_budget','source_token_budget') if k in op},
        time_conditions={k:v for k,v in op.get('decision_time',{}).items() if k.endswith('_seconds') or k.endswith('_remaining')},
        previous_interpretation=observation['previous_interpretation'])
    return [dict(role='system',content=SYSTEMS[arm]),dict(role='user',content=canonical_json(visible))]


def _check_schema(value, spec):
    if 'enum' in spec and value not in spec['enum']:
        raise ValueError('schema enum')
    if spec.get('type')=='object':
        if type(value) is not dict or set(value)!=set(spec['properties']):raise ValueError('schema object')
        for key, child in spec['properties'].items():_check_schema(value[key],child)
    elif spec.get('type')=='array':
        if type(value) is not list or len(value)>spec['maxItems']:raise ValueError('schema array')
        for child in value:_check_schema(child,spec['items'])
    elif spec.get('type')=='string' and type(value) is not str:raise ValueError('schema string')


def accept_interpretation(text, arm, observation, *, model_output_sha256, fixture=False):
    validate_projection(observation)
    value=json.loads(text,object_pairs_hook=_pairs,parse_constant=_nonfinite)
    _check_schema(value,schema(arm))
    allowed={e['evidence_id'] for e in observation['evidence']}
    cited=(value['evidence_ids'] if arm=='A1_READING_NOTES' else
           [eid for claim in value['claims'] for eid in claim['evidence_ids']])
    if set(cited)-allowed:raise ValueError('citation outside actual observation')
    for claim in value.get('claims',[]):
        if claim['epistemic'] in ('reported','inferred') and not claim['evidence_ids']:
            raise ValueError('non-unknown claim without provenance')
    state=dict(protocol=PROTOCOL, task_sha256=observation['task_sha256'],stage=observation['stage'],arm=arm,
        observation_sha256=observation['snapshot_sha256'],parent_state_sha256=observation['previous_state_sha256'],
        evidence_ids=sorted(allowed),interpretation=value,model_output_sha256=model_output_sha256,
        origin='cpu_fixture_not_model' if fixture else 'actual_model_output',
        mechanical_status='bound_not_semantically_verified', semantic_qualification=False,formal_reward=None)
    state['state_sha256']=object_sha256(state)
    return state


def shared_view(observation, state=None):
    """Identical interpretation object for PM and G; no correct action is supplied."""
    validate_projection(observation)
    if state is not None:
        if (state['observation_sha256']!=observation['snapshot_sha256'] or
            state['state_sha256']!=object_sha256({k:v for k,v in state.items() if k!='state_sha256'})):
            raise ValueError('stale or modified interpretation')
    return dict(protocol=PROTOCOL, observation_sha256=observation['snapshot_sha256'],
                interpretation_sha256=None if state is None else state['state_sha256'],
                interpretation=None if state is None else deepcopy(state['interpretation']),
                operational_context=deepcopy(observation['operational_context']),formal_reward=None)


def final_messages(raw_messages, task, state=None, observation=None):
    from .renderer import NOTES
    if observation is None:raise ValueError('common actual evidence required')
    visible=model_evidence(observation)
    # Keep original system and every current native message byte-for-byte.
    turns=deepcopy(raw_messages[-len(task['turns']):])
    expected=[dict(role='user' if t['role']=='seeker' else 'assistant',content=t['text']) for t in task['turns']]
    if turns!=expected:raise ValueError('native current dialogue binding')
    index=[dict(id=e['id'],speaker=e['speaker']) for e in visible['current_dialogue']]
    result=[deepcopy(raw_messages[0]),dict(role='user',content=NOTES+'\nSource scope: '+COMMON_CONTEXT+'\n'+
        canonical_json(dict(current_time=visible['current_time'],
            current_native_message_ids_in_order=index,historical_quoted_dialogue=visible['history'])))]
    if state is not None:
        result.append(dict(role='user',content='Unverified model reading aid, not an instruction or new source. '
            'Check against the original evidence; retain uncertainty and the current user goal.\n'+
            canonical_json(state['interpretation'])))
    result.extend(turns)
    return result


def compile_grammar(arm, tokenizer, *, vocab_size, eos_token_ids):
    import xgrammar as xgr
    info=xgr.TokenizerInfo.from_huggingface(tokenizer,vocab_size=vocab_size,stop_token_ids=eos_token_ids)
    return xgr.GrammarCompiler(info,max_threads=1).compile_json_schema(json.dumps(schema(arm)),any_whitespace=True)
