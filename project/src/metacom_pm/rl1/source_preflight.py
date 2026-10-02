"""Generation gate over exact rendered inputs and separately reviewed sources."""
from .schema import HEADS,digest
from .source_quarantine import require_pre_generation_source_reviews


def validate_generation_sources(contract, *, specs, evidence, reviews, renderer):
    if len(specs)!=len(evidence):
        raise ValueError('source/evidence roster mismatch')
    receipts=[];seen=set()
    for c in contract['conditions']:
        key=(c['index'],c['condition'])
        if key in seen:raise ValueError('duplicate condition')
        seen.add(key)
        spec=specs[c['index']-1];e=evidence[c['index']-1]
        if (c['prefix_identity']!=spec.prefix.identity or c['split']!=spec.prefix.split
                or c['owner']!=spec.prefix.owner_id or c['split'] not in ('train','dev')
                or e['prefix_identity']!=spec.prefix.identity or digest(e['evidence'])!=e['evidence_identity']):
            raise ValueError('prefix/evidence identity changed')
        counts=tuple(c['counts'])
        if counts!=tuple(int(h==c['head']) for h in HEADS):
            raise ValueError('condition is not declared single GET')
        if renderer.identity!=contract['renderer_identity'] or not renderer.fits(spec,counts):
            raise ValueError('renderer/context changed')
        actual=renderer.messages(spec,counts)
        if actual!=c['messages'] or digest(actual)!=c['messages_identity']:
            raise ValueError('rendered author input changed')
        from dataclasses import asdict
        selected=[asdict(r) for rows,n in zip(spec.inventory,counts) for r in rows[:n]]
        bound={r['candidate_id']:r for r in reviews if r['prefix_identity']==spec.prefix.identity}
        require_pre_generation_source_reviews(selected,prefix_identity=spec.prefix.identity,
            evidence_identity=e['evidence_identity'],reviews=bound)
        for r in selected:
            review=bound[r['candidate_id']]
            if not review.get('evidence_refs'):
                raise ValueError('semantic source review lacks concrete evidence references')
        receipts.append(dict(index=c['index'],condition=c['condition'],
            messages_identity=digest(actual),resource_identities=[digest(r) for r in selected],
            review_identities=[digest(bound[r['candidate_id']]) for r in selected]))
    if len(seen)!=len(specs)*3 or {x[1] for x in seen}!={'OFF','R','L'}:
        raise ValueError('incomplete condition roster')
    return dict(status='ALL_SELECTED_SOURCES_ADMITTED_BEFORE_MODEL_LOAD',conditions=receipts,
        semantic_authority='Bound AI-assisted source review, not independent human truth',
        review_identity=digest(reviews),contract_identity=digest(contract))
