"""Experimental source views, not a replacement memory compiler or PM backend.

The short view retains every cited source span and adjacent complete turns.
It omits other turns explicitly and does not promote old compiler statements,
infer present facts, join events semantically, or assign resource utility.
"""
import json

from .resource_value_probe import match_session
from .schema import digest

VERSION = 'pmrl1-typed-evidence-and-conditional-strategies-20261111-v1'
BASIC_GUIDANCE = (
    'Respond to the present concern with care. Do not assume that the user wants '
    'advice or a follow-up question. A relevant concise response is acceptable. '
    'Use historical information only when it helps the present response; citing '
    'a memory is not itself a goal.'
)

# Author-designed hypotheses, using the existing eight family names. Conditions
# are not ESConv annotations, established clinical rules, or user preferences.
STRATEGIES = (
    ('question', 'When an unresolved information gap matters for responding, ask a manageable '
     'clarifying question. Avoid asking for information already supplied or making the user '
     'solve an unclear question. Do not end every reply with a question.'),
    ('restatement_or_paraphrasing', 'When checking understanding would help, briefly restate '
     'the concern in your own words. Preserve uncertainty and do not introduce new premises.'),
    ('reflection_of_feelings', 'When the user expresses distress, acknowledge the expressed '
     'feelings. Treat interpretations as tentative; do not diagnose or claim hidden motives.'),
    ('affirmation_and_reassurance', 'When there is evidence of effort or a difficult situation, '
     'acknowledge it without exaggerated praise, guaranteed outcomes, or minimizing distress.'),
    ('providing_suggestions', 'When the user asks for options or welcomes problem solving, '
     'offer an optional feasible next step that respects known constraints. Do not turn a '
     'request to be heard into unsolicited advice or repeat a reported unsuccessful step as new.'),
    ('information', 'When a factual explanation addresses the present question, provide '
     'reliable relevant information. Do not import facts about another person from an example.'),
    ('self_disclosure', 'If a comparison would clarify the present concern, a clearly '
     'hypothetical example or general observation is possible. Do not invent personal experiences.'),
    ('others', 'Follow explicit requests to continue, pause, or end the conversation. Do not '
     'copy dataset survey instructions or impose a closing when the user wants to continue.'),
)


def strategy_text():
    return ('Optional conversational strategies. Choose none, one, or a compatible combination '
            'based on the visible dialogue; these are not facts about this user.\n' +
            '\n'.join(f'{name}: {text}' for name, text in STRATEGIES))


def source_view(prefix, items, all_items, evidence):
    """Bind existing MP/ME evidence to whole legal MS; no query/gold selection."""
    if prefix.split != 'train' or not items:
        raise ValueError('nonempty train diagnostic selection required')
    if len({x.key for x in items}) != len(items):
        raise ValueError('duplicate selected record')
    sessions = {}
    bindings = []
    for item in items:
        if (item.head not in ('MP', 'ME') or item.owner_id != prefix.owner_id
                or item.source_rank >= prefix.cutoff_rank or item.reported_at > prefix.timestamp):
            raise ValueError('foreign or non-past memory')
        body = json.loads(item.content)
        parents = [x for x in all_items if x.head == 'MS'
                   and set(x.source_ids) & set(item.source_ids)]
        if len(parents) != 1:
            raise ValueError('one complete source session required')
        parent = parents[0]
        if (parent.owner_id != prefix.owner_id or parent.source_rank != item.source_rank
                or parent.reported_at != item.reported_at):
            raise ValueError('source owner/time mismatch')
        session = match_session(parent, evidence)
        turns = session['turns']
        row = sessions.setdefault(parent.key, dict(item=parent, session=session, selected=set()))
        if not body.get('evidence'):
            raise ValueError('no evidence spans')
        indices = []
        for span in body['evidence']:
            # The historical compiler's raw turn IDs and blinded evidence
            # ordinals are different namespaces (audit 130 already records it).
            # Bind by a unique exact role/offset/quote in this exact session;
            # preserve the original ID without pretending it is an ordinal.
            if type(span['turn_index']) is not int or span['turn_index'] < 0:
                raise ValueError('invalid declared turn ID')
            a, b = span['start_char'], span['end_char']
            if type(a) is not int or type(b) is not int or not 0 <= a < b:
                raise ValueError('invalid quote offsets')
            matches = [j for j,t in enumerate(turns) if b <= len(t['text'])
                       and t['role'] == span['speaker'] and t['text'][a:b] == span['quote']]
            if len(matches) != 1:
                raise ValueError('quote/role/offset mismatch')
            i = matches[0]
            indices.append(i)
            row['selected'].update(range(max(0, i-1), min(len(turns), i+2)))
        bindings.append(dict(key=item.key, head=item.head, source_key=parent.key,
            item_identity=item.identity, evidence_turns=sorted(set(indices)),
            original_declared_turn_ids=[s['turn_index'] for s in body['evidence']],
            index_binding='unique exact source/role/offset/quote; raw-ID-to-ordinal mapping not assumed',
            original_compiler_statement=body['past_report'],
            profile_slot_hint=body.get('profile_slot'),
            original_action_stage=body.get('action_stage'),
            original_observed_outcome=body.get('observed_outcome'),
            original_claim_semantics='not_revalidated_or_delivered_as_fact'))
    compact = []
    full = []
    for key, row in sorted(sessions.items(), key=lambda kv: (kv[1]['item'].source_rank, kv[0])):
        s = row['session']
        selected = sorted(row['selected'])
        compact.append(dict(recorded_at=s['date'],
            evidence_for=sorted({b['head'] for b in bindings if b['source_key'] == key}),
            turn_fields=['index', 'speaker', 'verbatim_text'],
            turns=[[i, s['turns'][i]['role'], s['turns'][i]['text']] for i in selected],
            omitted_turns=len(s['turns'])-len(selected)))
        full.append(dict(recorded_at=s['date'],
            turn_fields=['index', 'speaker', 'verbatim_text'],
            turns=[[i,t['role'],t['text']] for i,t in enumerate(s['turns'])], omitted_turns=0))
    common = dict(schema=VERSION,
        scope='Past reports, not established current state. Speaker roles are distinct. '
              'No action completion, effect, preference or event link is inferred by this view.')
    return dict(compact=dict(**common, view='evidence_with_adjacent_turns', sessions=compact),
        full=dict(**common, view='complete_parent_sessions', sessions=full), bindings=bindings,
        parent_keys=list(sessions), selected_keys=[x.key for x in items],
        shared_source_count=len(items)-len(sessions),
        semantic_relations_created=0, current_facts_created=0, reward=None,
        identity=digest(dict(version=VERSION, prefix=prefix.identity,
            items=[x.identity for x in items], compact=compact, full=full)))
