"""Bounded full-Agent evaluation checks; lexical checks are not helpfulness scores."""
from ..data.contracts import digest,text_hash

REQUIRED_EVENTS=('need_understood','reply_emitted','history_appended','followup_ready')


def check_trace(task,events,reply):
    """Mechanical provenance/state checks; no forced MP/MS/ME/RS call labels."""
    if any(e.get('task_id')!=task['task_id'] for e in events):raise ValueError('foreign task event')
    kinds=[e['event'] for e in events]
    missing=[x for x in REQUIRED_EVENTS if x not in kinds]
    violations=[]
    if not missing:
        positions=[kinds.index(x) for x in REQUIRED_EVENTS]
        if positions!=sorted(positions):violations.append('lifecycle_order')
    for e in events:
        if e['event']=='history_read':
            if e.get('owner')!=task['owner']:violations.append('foreign_owner')
            if e.get('cutoff')!=task['cutoff']:violations.append('wrong_cutoff')
            if not e.get('source_ids') or not e.get('source_hashes'):violations.append('unbound_history')
        if e['event']=='skill_read':
            if e.get('skill_id') not in task.get('available_skill_ids',[]):violations.append('unavailable_skill')
            if not e.get('applicability_basis'):violations.append('missing_skill_applicability_basis')
        if e['event'] in ('reply_emitted','history_appended') and e.get('reply_sha256')!=text_hash(reply):
            violations.append('response_persistence_mismatch')
    return dict(task_id=task['task_id'],missing_events=missing,provenance_violations=violations,
        lifecycle_complete=not missing and not violations,semantic_help_quality='requires_reply_review',
        missing_role_evidence=[x for x in ('MP','MS','ME','RS','PM1','PM2','Generator')
            if x not in {e.get('component') for e in events}],
        note='A role may legitimately abstain; missing component telemetry is not a mandatory-call failure')


def check_reply(reply,spec):
    """Reproducible literal fact/constraint checks plus explicit semantic unknowns.

    Exact phrase present != complete meaning; phrase absent != factual error.
    Do not promote this to a scalar judge, action reward or automatic helpfulness.
    """
    normalized=' '.join(reply.lower().split())
    facts=[]
    for atom in spec.get('personal_fact_references',[]):
        hits=[s for s in atom.get('acceptable',[]) if ' '.join(s.lower().split()) in normalized]
        facts.append(dict(id=atom['id'],literal_supported_phrase=hits,
            semantic_completion='needs_review_even_if_literal_present'))
    return dict(task_id=spec['task_id'],reply_sha256=text_hash(reply),empty=not reply.strip(),
        facts=facts,requirements=[dict(id=x['id'],status='needs_reply_review') for x in spec.get('requirements',[])],
        prohibitions=[dict(id=x['id'],status='needs_reply_review') for x in spec.get('prohibitions',[])],
        helpfulness=None,misuse=None,independent_human_rating=False)
