"""Prepare exact new batch for the existing P2 runner; tokenizer-only/offline."""
import importlib.metadata
import json
import os
from pathlib import Path
import sys

OUT = Path(__file__).resolve().parent
PROJECT = OUT.parents[3]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.schema import digest
from metacom_pm.rl1.rs_development import read,save_once,validate_package
from metacom_pm.rl1.rs_applicability import RSApplicabilityRenderer,paired_request,INSTRUCTION,VERSION
from metacom_pm.rl1.representation_direct import DirectReplyRenderer
from metacom_pm.rl1.representation import RESOURCE_GUIDANCE_V2
from metacom_pm.rl1.bound_generation import validate_and_project

NEW_VERSION='pm-rl1-rs-additional-contexts-v1-20261019'
INDEXES=[98,99,101,103,106,107,108,110,112]
PLANS=[(0,0,0,0),(1,0,0,0),(1,1,1,1)]


def main():
    os.umask(0o077)
    from transformers import AutoTokenizer
    root=PROJECT/'outputs/pm_rl1/completion_20260930_v2'
    original=read(OUT.parent/'rs_applicability_20261019_v1/protocol.json')
    runtime=read(root/'P2/executor_freeze.json')['primary_runtime']
    assert runtime==original['runtime']
    packages={k:importlib.metadata.version(k) for k in runtime['packages']}
    assert packages==runtime['packages']
    assert importlib.metadata.version('peft')==runtime['adapter']['peft_version']
    tokenizer=AutoTokenizer.from_pretrained(runtime['model_dir'],local_files_only=True)
    assert digest(tokenizer.chat_template)==runtime['chat_template_sha256']
    count=lambda s:len(tokenizer.encode(s,add_special_tokens=False))
    chat=lambda m:len(tokenizer.apply_chat_template(m,tokenize=True,add_generation_prompt=True))
    kwargs=dict(count_text=count,count_chat=chat,
        tokenizer_identity=read(root/'P1/renderer_freeze.json')['tokenizer_identity'],
        context_limit=runtime['policy']['context_limit'])
    old,new=DirectReplyRenderer(**kwargs),RSApplicabilityRenderer(**kwargs)
    assert old.identity==original['renderer_baseline'] and new.identity==original['renderer_intervention']
    inputs=read(OUT/'input_requests_private.json')
    by_key={(r['index'],tuple(r['counts'])):r for r in inputs}
    assert len(by_key)==25
    jobs=[];planned=[];pair_number=0
    for index in INDEXES:
        for counts in PLANS:
            row_id=f'dev_{index:03d}__'+''.join(map(str,counts))
            if counts[0]:
                arms=['baseline','rs_applicability'] if pair_number%2==0 else ['rs_applicability','baseline']
                pair_number+=1
            else:
                arms=['baseline']
            if (index,counts) not in by_key:
                assert counts==(1,1,1,1) and index in (108,110)
                for arm in arms:
                    planned.append(dict(slot_id=row_id+'__'+arm,index=index,counts=list(counts),arm=arm,
                        status='UNAVAILABLE_ORIGINAL_PLAN',reason='frozen common pool: not_reachable',model_attempt=False))
                continue
            oldrow=by_key[index,counts];req0=oldrow['request']
            assert sha256_file(Path(oldrow['original_request_path']))==oldrow['original_request_file_sha256']
            assert chat(req0['messages'])==oldrow['metadata']['input_tokens']
            for arm in arms:
                req=paired_request(req0,arm=arm,
                    renderer_identity=old.identity if arm=='baseline' else new.identity,
                    draw_identity=NEW_VERSION+':paired-greedy-seed0')
                validate_and_project(req,runtime['identity'])
                n=chat(req['messages'])
                cost=oldrow['metadata']['resource_tokens']
                if arm=='rs_applicability':
                    before,block=req0['messages'][0]['content'].split('\n\n'+RESOURCE_GUIDANCE_V2,1)
                    cost=count('\n\n'+INSTRUCTION+RESOURCE_GUIDANCE_V2+block)
                    assert req['messages'][0]['content'].replace(INSTRUCTION,'',1)==req0['messages'][0]['content']
                else:
                    assert req['messages']==req0['messages']
                assert req['messages'][1]==req0['messages'][1]
                assert cost<=2048 and n<runtime['policy']['context_limit']
                job=dict(slot_id=row_id+'__'+arm,row_id=row_id,index=index,context_id=f'dev_{index:03d}',
                    counts=list(counts),arm=arm,old_request_id=req0['request_id'],old_slot_id=oldrow['metadata']['slot_id'],
                    input_tokens=n,resource_tokens=cost,native_output_remainder=runtime['policy']['context_limit']-n,
                    request=req)
                jobs.append(job)
                planned.append({k:job[k] for k in ('slot_id','index','counts','arm') }|
                    dict(status='PREPARED_NOT_STARTED',model_attempt=False))
    assert len(jobs)==41 and len(planned)==45
    assert len({j['request']['request_id'] for j in jobs})==41
    save_once(OUT/'jobs_private.json',jobs)
    save_once(OUT/'slots_45.json',planned)
    save_once(OUT/'tokenization_receipt.json',dict(status='PASSED_FULL_INPUTS_NO_TRUNCATION',
        prepared_requests=41,unavailable_slots=4,packages=packages,model_loaded=False,gpu_used=False,
        prompt_tokens=sum(j['input_tokens'] for j in jobs),
        max_input_tokens=max(j['input_tokens'] for j in jobs),
        max_resource_tokens=max(j['resource_tokens'] for j in jobs),
        min_native_output_remainder=min(j['native_output_remainder'] for j in jobs),
        complete_current_and_acquired_resources_unchanged=True,intervention_text_unchanged=True,
        full_evidence_for_review_only_not_injected_into_generator=True))
    inventory=read(OUT/'inventory.json')
    files=['selection_lock.json','inventory.json','input_requests_private.json',
        'jobs_private.json','slots_45.json','tokenization_receipt.json']
    files.extend(str(p.relative_to(OUT)) for p in sorted((OUT/'sources').glob('*.json')))
    source_files=dict(inventory['immutable_inputs'])
    for p in [Path(__file__),OUT/'prepare_inputs.py',PROJECT/'scripts/rl1/92_run_p2_common_pool.py',
        OUT.parent/'selection.py',OUT.parent/'resume_engineering.py',
        PROJECT/'docs/pm_rl1_completion_20260930_v2/execution_contract.json',
        *[PROJECT/f'src/metacom_pm/rl1/{n}.py' for n in ('rs_development','rs_applicability',
            'representation_direct','representation','bound_generation','generation','cache','render')]]:
        source_files[str(p)]=sha256_file(p)
    protocol=dict(version=NEW_VERSION,status='PREPARED_NOT_EXECUTION_AUTHORIZED',
        stage=OUT.name,intervention_version=VERSION,instruction=INSTRUCTION,
        max_generation_attempts=41,new_judge_requests=0,api_cost_usd=0,
        existing_judge_attempts=144,judge_capacity=289,old_D_stage_boundary=143,
        runtime=runtime,renderer_baseline=old.identity,renderer_intervention=new.identity,
        jobs_identity=digest(jobs),execution_dir=str(OUT/'execution'),
        gpu_uuid=original['gpu_uuid'],gpu_guard_path=original['gpu_guard_path'],guard=original['guard'],
        technical_failure_policy=original['technical_failure_policy'],semantic_policy=original['semantic_policy'],
        environment=original['environment'],original_STOPs_preserved=True,
        files={n:sha256_file(OUT/n) for n in files},source_files=source_files,
        eligible_for_reward=False,independent_validation=False,
        claim_boundary='nine development contexts/three curated source owners; six additional current contexts and three exact-history-overlap regression cases; not independent natural-user validation',
        input_selection_identity=digest(read(OUT/'selection_lock.json')),
        development_counts=dict(contexts=9,new_current_contexts_vs_prior_four=6,history_overlap_regression_contexts=3,
            source_owners=3,planned_slots=45,structurally_unavailable_slots=4,OFF=9,RS_only_pairs=9,all_four_pairs=7),
        no_independent_human_labels_created=True,no_freshness_from_renaming=True)
    save_once(OUT/'protocol.json',protocol)
    save_once(OUT/'launch_request.json',dict(status='PENDING_RESEARCHER_APPROVAL',
        protocol_identity=digest(protocol),max_generation_attempts=41,max_new_judge_requests=0,
        max_api_cost_usd=0,gpu_uuid=protocol['gpu_uuid'],user_instruction=None))
    validate_package(OUT)
    print(json.dumps(dict(status='PREPARED_NOT_LAUNCHED',protocol_identity=digest(protocol),
        jobs=41,unavailable=4,model_calls=0,tokenization=read(OUT/'tokenization_receipt.json')),ensure_ascii=False))


if __name__=='__main__':main()
