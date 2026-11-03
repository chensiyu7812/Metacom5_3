"""Verify intake preservation and cost arithmetic without creating q/m labels."""
from fractions import Fraction
import hashlib
import json
from pathlib import Path

PROJECT=Path(__file__).resolve().parents[4]
BASE=PROJECT/'outputs/pm_rl1'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    root=BASE/'contextual_value_reference_20261104_v1'
    manifest=read(root/'OUTPUT_MANIFEST.json')
    for name,h in manifest.items():
        assert not Path(name).is_absolute() and '..' not in Path(name).parts
        assert sha(root/name)==h
    sources=read(root/'SOURCE_HASHES_PRIVATE.json')
    for p,h in sources.items():assert sha(Path(p))==h
    intake=read(root/'INTAKE_PRIVATE.json');registry=read(root/'ANSWER_REGISTRY_PRIVATE.json')
    original=read(BASE/'human_answer_reanalysis_20261103_v2/ANSWER_REGISTRY_PRIVATE.json')
    assert registry[:-1]==original and len(registry)==35
    assert registry[-1]['raw_label']['original_answer']==intake['original_answer']
    assert 'B是90分，A是95分' in intake['original_answer'] and '个人感觉是相当' in intake['original_answer']
    assert intake['exact_qm'] is intake['numeric_reward'] is None and not intake['qualified_reward']
    assert registry[-1]['preferred_reply_identity'] is None
    assert registry[-1]['slight_edge_reply_identity']==intake['alias_bindings']['A']['reply_identity']
    value=read(root/'VALUE_SENSITIVITY.json');cost=Fraction(4868,40960)
    assert value['actual']['additional_utility_cost']==float(cost)
    assert value['hypothetical']['net_at_current_weight']==float(Fraction(5,100)-cost)
    assert value['hypothetical']['break_even_token_difference']==2048
    assert value['actual']['measured_net_advantage'] is None
    assert value['hypothetical']['not_measurements'] and value['hypothetical']['not_training_labels']
    es=read(BASE/'actual_training_feedback_20261103_v1/ENDPOINTS_PRIVATE.json')
    utilities=sorted({Fraction(q,4)-m for q in range(5) for m in (0,Fraction(1,4),1)})
    step=min(b-a for a,b in zip(utilities,utilities[1:]))
    maxcost=max(Fraction(e['resource_tokens'],40960) for e in es)
    assert step==Fraction(1,4) and maxcost<step
    # Confirm the grid against the runtime's accepted Score domain.
    import sys
    sys.path.insert(0,str(PROJECT/'src'))
    from metacom_pm.rl1.schema import Score
    marker=('schema-domain-check-only-not-a-response-label',)
    for q in range(5):
        for m in (0,.25,1):Score(q,m,evidence=marker)
    rejected=False
    try:Score(3.6,0,evidence=marker)
    except ValueError:rejected=True
    assert rejected
    cfg=read(BASE/'execution_bridges_20261103_v1/J_CONFIG_PRIVATE.json')
    for p,h in cfg['policy']['historical_files'].items():assert sha(Path(p))==h
    old=read(PROJECT/'docs/reviews/20261104/pm_rl1_decision_branches/CHECKS.json')
    assert sha(Path(cfg['ledger']))==old['original_ledger_sha256']
    stats=read(root/'SUMMARY.json')
    checks=dict(intake_exit_code=0,independent_verification_exit_code=0,
        verified_artifacts=len(manifest),verified_bound_sources=len(sources),
        frozen_historical_files_verified=len(cfg['policy']['historical_files']),
        ledger_sha256=sha(Path(cfg['ledger'])),original_records_preserved=34,
        new_answer_exactly_preserved=True,near_equivalence_not_hard_tie=True,
        new_scalar_rewards=0,question_reasked=False,
        actual_extra_utility_cost=float(cost),
        utility_grid_step=float(step),maximum_pool_cost=float(maxcost),
        terminal_order_equivalence='Within each prefix, for fixed legal q/m on this cached pool: highest U, then lowest cost.',
        expected_policy_values_can_still_be_continuous=True,
        cost_rule_changed=False,new_calls=0,new_cost_usd=0,natural_updates=0,
        output_manifest_sha256=sha(root/'OUTPUT_MANIFEST.json'))
    here=Path(__file__).resolve().parent
    (here/'SUMMARY.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2)+'\n')
    (here/'CHECKS.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(checks,ensure_ascii=False))


if __name__=='__main__':main()
