#!/usr/bin/env python3
"""Freeze actual populations and rules BEFORE new model predictions."""
import argparse,json,math,shutil
from pathlib import Path
from metacom_pm.need_aware.data.v11 import jsonl,ordered,AUTHORITY
from metacom_pm.need_aware.data.contracts import digest
from metacom_pm.need_aware.data.personamem import write_json,write_jsonl,sha_file
from metacom_pm.need_aware.data.training_v11 import runtime_projection
from metacom_pm.need_aware.evaluation.short_mcq import PROTOCOL,SHORT_SUFFIX

def freeze(wp3,wp4,old,out):
    wp3,wp4,old,out=map(Path,(wp3,wp4,old,out))
    if out.exists():raise FileExistsError('evaluation rules already frozen')
    r3=json.loads((wp3/'RECEIPT.json').read_text());r4=json.loads((wp4/'RECEIPT.json').read_text())
    power=[dict(n=n,discordance=d,normal_approx_mde_80=(1.959964+.841621)*math.sqrt(d/n),
                n_for_five_pp_80=math.ceil(d*((1.959964+.841621)/.05)**2)) for n in (60,140) for d in (.1,.2,.3,.5)]
    common=dict(authority_commit=AUTHORITY,paired_inference=dict(bootstrap_seed=20261128,bootstrap_replicates=10000),
                minimum_meaningful_difference=.05,noninferiority_margin=.05,confidence=.95,
                technical_failures='Unknown; completed-case, predefined eligible denominator with failures zero, and unknown bounds all reported.',
                structural='Not model errors. Comparisons first intersect predefined evaluable sets, then complete pairs.',
                multiplicity='Holm within each fixed family; confidence intervals unadjusted; exploratory strata clearly separate.',
                evidence_sufficiency='Source-certified sufficient / insufficient / ambiguous / unknown; Direct location never a semantic label.',
                power_grid=power,power_note='Paired Bernoulli normal approximation using discordance; underpowered for 5pp at n=140/60. No equivalence from nonsignificance, no new data-driven sample expansion.',
                model_outputs_seen=False,new_gpu_authorized=False)
    policy=dict(common,protocol='naa-wp3-evaluation-v1',scoring_protocol=PROTOCOL,short_suffix=SHORT_SUFFIX,
        max_new_tokens=64,material_freeze_sha256=sha_file(wp3/'FREEZE.json'),
        populations=dict(confirmation=140,gemma_subset=60,bridge=60),
        primary_paired_family=[['Qwen35|'+l,'Qwen35|'+r] for l,r in [('B0','B1'),('B1','B1s'),('B1','E0'),('E0','E0s'),('E0s','C'),('C','C+noise')]],
        noninferiority_contrasts=[['Qwen35|E0','Qwen35|E0s']],
        cross_model_family=['B0','E0s','C'],cross_model_rule='Preselected same 60 task IDs, joint eligible, then both completed. No separate marginal denominators.',
        bridge_family=[dict(model=m,arm=a,old='official',new=PROTOCOL) for m in ('G0e','Qwen35') for a in ('B0','C')],
        bridge_rule='Reuse exact old B/C outputs and scoring; 60 preselected same tasks. New short protocol scored separately. Not protocol equivalence.',
        expected_logical=r3['logical_slots'],expected_executable_before_capacity=r3['expected_executable_before_capacity'],
        capacity_rule='Full C over native cap -> structural with explicit token receipt; never truncate C or silently substitute task.')
    write_json(out/'WP3_POLICY.json',policy)
    dev=jsonl(wp4/'targets/development.jsonl');gids=set(ordered(sorted({r['group_id'] for r in dev}),'open-development-60-groups')[:60]);selected=[r for r in dev if r['group_id'] in gids]
    write_jsonl(out/'open/targets.private.jsonl',selected)
    write_jsonl(out/'open/runtime.jsonl',[runtime_projection(r) for r in selected])
    write_json(out/'open/selection.json',dict(groups=sorted(gids),task_ids=[r['variant_id'] for r in selected],selection='hash only; no model output'))
    # Independent natural 60 remain exactly the existing material, referenced by
    # immutable hashes. They need separate semantic ratings, not MCQ gold scores.
    write_json(out/'open/natural60.json',dict(runtime=str(old/'runtime/tasks.generation.jsonl'),
                runtime_sha256=sha_file(old/'runtime/tasks.generation.jsonl'),
                evaluation_sha256=sha_file(old/'evaluation/tasks.generation.jsonl'),
                count=60,independent_owners=60,protocol='open generation, no options; remove compulsory recall suffix for all U arms equally',
                evidence='B frozen same-evidence delivery for U0/U1/U2/U3; unlocated Direct six structural if Direct diagnostic is used'))
    write_json(out/'WP4_POLICY.json',dict(common,protocol='naa-wp4-open-evaluation-v1',rubric='naa-open-rubric-v1',
        training_freeze_sha256=sha_file(wp4/'FREEZE.json'),open_groups=60,open_variants=len(selected),natural_open=60,
        constructed_and_natural='Always separate; never pool synthetic group counts as independent people.',
        primary_contrast='U2->U3 same complete matched groups, family cluster bootstrap; all variants must meet task and applicability criteria.',
        secondary_contrasts=['U0->U1','U1->U2'],success_rule='paired success point gain >=5pp and CI lower>0, appropriate-use and completion lower>-5pp, no misuse/over-refusal tradeoff.',
        dimensions=['paired_success','task_complete','appropriate_use','misuse','unnecessary_clarification','over_refusal','natural_quality'],
        rater_rule='Two independent blinded raters; disagreement/insufficient evidence remains unknown until separately recorded adjudication. Candidate calibration is not independent scoring.',
        no_proxy='Action JSON accuracy is mechanical only, never semantic task success.',
        actual_model_baseline_requests=2*(len(selected)+60),post_training_requests=2*(len(selected)+60)))
    config=dict(protocol='naa-wp4-training-candidate-v1',authority_commit=AUTHORITY,authorization='not_granted',
        base_model='Qwen/Qwen3.5-9B',revision='c202236235762e1c871ad0ccb60c8ee5ba337b9a',
        train_file=str(wp4/'targets/fit.jsonl'),tune_file=str(wp4/'targets/tune.jsonl'),
        train_sha256=sha_file(wp4/'targets/fit.jsonl'),tune_sha256=sha_file(wp4/'targets/tune.jsonl'),
        rows=r4['by_split']['fit']['rows'],groups=r4['by_split']['fit']['groups'],
        methods=['U2','U3'],same_chosen_examples=True,same_prompt=True,same_model_initialization=True,
        seed=20261128,group_order='fixed hash; preserve all variants; same order for both methods',
        max_seq_length=2048,epochs=1,max_optimizer_steps=500,microbatch=1,gradient_accumulation=8,
        planned_optimizer_steps_per_method=math.ceil(r4['by_split']['fit']['rows']/8),
        optimizer='adamw',learning_rate=2e-4,weight_decay=.01,warmup_steps=25,
        lora=dict(rank=8,alpha=16,dropout=0.,target_modules=['q_proj','v_proj']),
        u2_objective='mean chosen response SFT',u3_objective='same SFT + .1 * masked softplus(.5 - chosen_action_logp + incompatible_action_logp)',
        pair_weight=.1,pair_margin=.5,negative_scope='Explicitly incompatible action tokens only, no alternative natural reply negatives.',
        max_input_target_tokens_per_method=r4['by_split']['fit']['rows']*2048,
        fairness='U2/U3 same chosen examples/steps/token cap/seed/base and same three forward passes. U2 auxiliary action branches have zero coefficient and zero gradient; ordinary SFT objective unchanged. B must retain auxiliary forward/backward work for matched tokens/compute, with compile disabled; record actual wall/FLOPs. No output-based checkpoint choice.',
        auxiliary_forwards_per_example=2,u2_auxiliary_coefficient=0.,torch_compile=False,
        checkpoint_selection='last completed fixed epoch/step, no dev-score selection',
        requires=['explicit new training authorization','B backend/module/memory/time audit','independent calibration of source targets; no fabricated reviewer completion'])
    write_json(out/'TRAINING_CANDIDATE.json',config)
    write_json(out/'FREEZE.json',dict(artifacts={str(p.relative_to(out)):sha_file(p) for p in sorted(out.rglob('*')) if p.is_file()}))
    return dict(wp3_logical=r3['logical_slots'],open_groups=60,open_variants=len(selected),natural60=60,baseline_requests=2*(len(selected)+60),train_rows=config['rows'])

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('wp3','wp4','old','out'):p.add_argument('--'+n,required=True)
    a=p.parse_args();print(json.dumps(freeze(a.wp3,a.wp4,a.old,a.out),indent=2))
