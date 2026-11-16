"""Private, evidence-bound quarantine for confirmed MP provenance failures.

This is an exclusion gate, NOT an entailment checker or an automatic repair.
Do not silently re-rank existing experiments after excluding candidates: a new
inventory/retrieval identity and source audit are required for a new run.
"""
from .schema import digest


def profile_family(unit):
    return (unit['owner_id'],unit['profile_field_type'],unit['profile_slot_key'])


def quarantine_decision(unit, records):
    """Block all ancestors in an unresolved slot, preventing stale fallback."""
    if 'profile_slot_key' not in unit:
        return dict(blocked=False,meaning='not an MP slot; no semantic endorsement')
    for record in records:
        if not record.get('rationale') or not record.get('bad_unit_identity') or not record.get('evidence'):
            raise ValueError('quarantine record lacks evidence')
        if tuple(record['family'])==profile_family(unit):
            return dict(blocked=True,reason='unresolved_source_refresh_or_stale_profile',
                        record_identity=digest(record),scope='entire MP slot including earlier fallback')
    return dict(blocked=False,meaning='no known quarantine match; unreviewed is not approved')


def validate_quarantine_binding(record, unit):
    if record['bad_unit_identity']!=digest(unit) or record['bad_unit_id']!=unit['memory_id']:
        raise ValueError('quarantine source changed')
    if tuple(record['family'])!=profile_family(unit):
        raise ValueError('wrong quarantine owner/slot')


def require_pre_generation_source_reviews(resources, *, prefix_identity, evidence_identity, reviews):
    """New-batch gate: all selected resources need a separate bound source review.

    This does not rewrite input or feed evaluator-only evidence to the author.
    A developer's semantic review remains weak evidence, not an automatic proof.
    Empty/OFF is valid. Missing, changed, quarantined or uncertain sources fail.
    """
    for resource in resources:
        key=resource['candidate_id']
        review=reviews.get(key)
        if not review:
            raise ValueError('source review missing before generation: '+key)
        if (review.get('resource_identity')!=digest(resource)
                or review.get('prefix_identity')!=prefix_identity
                or review.get('evidence_identity')!=evidence_identity):
            raise ValueError('source review is stale or bound to another context: '+key)
        if (review.get('status')!='source_supported'
                or review.get('temporal_status_checked') is not True
                or not review.get('reviewer') or not review.get('rationale')):
            raise ValueError('source not admitted before generation: '+key)
    return True
