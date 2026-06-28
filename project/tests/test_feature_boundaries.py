from metacom_pm.features import FeatureBuilder

def test_ablation_dimensions_are_distinct(tiny_state):
    dims={}
    for mode in ('text_only','metadata_only','text_metadata','catalog_only','full'):
        b=FeatureBuilder(mode=mode).fit([tiny_state])
        dims[mode]=b.transform([(tiny_state,'M0+R0')]).shape[1]
    assert dims['full']>dims['text_only']
    assert dims['full']>dims['metadata_only']
    assert dims['text_metadata']>dims['text_only']
    assert dims['text_metadata']>dims['metadata_only']
    assert dims['full']>dims['text_metadata']
    assert dims['full']>dims['catalog_only']
    assert len(set(dims.values()))==5

def test_ood_is_reported_and_clipped(tiny_state):
    b=FeatureBuilder(mode='metadata_only').fit([tiny_state])
    shifted=tiny_state.model_copy(deep=True);shifted.session_index=1000
    report=b.ood_report([(shifted,'M0+R0')])
    assert report['outside_dimensions']>=1
    x=b.transform([(shifted,'M0+R0')])
    assert x.shape[0]==1
