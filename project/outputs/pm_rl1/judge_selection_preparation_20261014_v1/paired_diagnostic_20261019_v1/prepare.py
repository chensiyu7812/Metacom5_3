"""Offline materialization only. Never reads credentials or sends requests."""
from pathlib import Path
import csv
import json
import shutil
from decimal import Decimal
import paired as p
from paired import s
from live import table_identity

OUT=p.HERE/'package'
REF=p.BASE/'reference_preparation_20261016_v1'


def write(name,value):
    path=OUT/name;path.parent.mkdir(parents=True,exist_ok=True)
    # These are this new, unapproved preparation's generated files only.
    if (OUT/'APPROVED.json').exists():raise ValueError('approved package immutable')
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def main():
    live_root=p.BASE/'paired_diagnostic_runs'/p.STUDY/'live'
    if live_root.exists() and (list(live_root.rglob('*.started.json')) or (live_root/'STOP.json').exists()):
        raise ValueError('study already entered execution; never regenerate its approved package')
    packet=s.read(REF/'materials/packet.json');mapping=s.read(REF/'coordinator/item_bindings.json')
    source=s.load_plan();items={}
    for x,m in zip(packet['items'],mapping):
        key=m['old_item_key'];e=packet['contexts'][x['context_id']]
        assert key in p.ITEM_KEYS and source['items'][key]['evidence']==e and source['items'][key]['reply']==x['reply']
        assert s.digest(e)==x['evidence_identity'] and s.digest(x['reply'])==x['reply_identity']
        items[key]=dict(reply=x['reply'],evidence=e,context_id=x['context_id'],item_id=x['item_id'],split='development')
    assert tuple(items)==p.ITEM_KEYS
    write('items.json',items)
    (OUT/'sources').mkdir(exist_ok=True)
    for cid in sorted({i['context_id'] for i in items.values()}):
        shutil.copyfile(REF/'materials'/(cid+'_complete.txt'),OUT/'sources'/(cid+'_complete.txt'))
    rows=[]
    for key,item in items.items():
        for comp in ('joint','extract'):
            messages,schema=p.payload(item,comp);screen=p.input_guard(messages)
            write(f'payloads/{key}.{comp}.json',dict(messages=messages,schema=schema,
                messages_identity=s.digest(messages),schema_identity=s.digest(schema),input_screen=screen))
            rows.append(dict(item=key,component=comp,**screen,reservation_usd=s.usd(p.RESERVE)))
        rows.append(dict(item=key,component='score',serialized_messages_utf8_bytes=None,
            input_status='bound template; exact complete first-step final attached at runtime, never truncated',
            output_max_tokens=393216,reservation_usd=s.usd(p.RESERVE)))
    write('prompts.json',dict(joint=p.s.judge.RUBRIC,extract=p.EXTRACT_PROMPT,
        score=p.s.judge.RUBRIC+p.SCORE_ADDITION,second_step_user_template='unchanged legal_evidence/reply/response_units plus validated preliminary_check',
        joint_schema_unchanged=True,score_schema_unchanged=True,final_interface=p.envelope.identity(),
        old_semantic_revision_count=1,new_workflow_is_separate_research_version=True))
    config=source['configs']['deepseek_flash_high'].copy()
    for k in ('identity','implementation_identity','rubric_identity','readiness','label'):config.pop(k,None)
    config.update(published_mapping='DeepSeek-V4.1-Flash-1017',immutable_weights=False,
        transport_code_sha256=s.sha(p.BASE/'adapters.py'))
    cd=s.read(p.BASE/'CD_engineering_20261015/protocol.json')
    ledger=s.REPO/'project/outputs/paper1_api_budget/cumulative_paid_api_budget.jsonl'
    budget=s.Budget(ledger,trial=cd['identity'],trial_cap=s.nanodollars(2),shared_cap=s.nanodollars(20),
        baseline=s.nanodollars('1.50724291'),opening=s.nanodollars('0.03079930'))
    total,trial,reserved,settled=budget._totals(budget.events())
    assert len(list((p.BASE/'live_runs').rglob('*.started.json')))==54
    assert trial==s.nanodollars('.175995') and not set(reserved)-set(settled)
    financial=dict(ledger_path=str(ledger),ledger_sha256=s.sha(ledger),financial_trial_identity=cd['identity'],
        trial_accounted_usd=s.usd(trial),shared_accounted_usd=s.usd(total),
        shared_baseline_usd='1.50724291',opening_usd='0.03079930',unsettled_count=0,
        new_stage_cap_usd='1',unchanged_trial_cap_usd='2',shared_remaining_work_cap_usd='20')
    files=[p.HERE/n for n in ('paired.py','live.py','prepare.py')]
    files += [p.BASE/n for n in ('selection.py','adapters.py')]
    files += [p.BASE/'outer_format_v1_20261015'/n for n in ('outer_format_v1.py','deepseek_access.py')]
    files += [s.REPO/'project/src/metacom_pm/rl1'/n for n in s.PARSER_FILES]
    files += [s.REPO/'project/src/metacom_pm/rl1/judge_explicit.py']
    files += [REF/'materials/packet.json',REF/'coordinator/item_bindings.json',OUT/'items.json',OUT/'prompts.json']
    files += [REF/'coordinator/validation_inventory.json',p.HERE/'tests/test_paired.py',
        next((p.BASE/'researcher_annotation_review_20261019_v1/originals').glob('*.json')),
        p.BASE/'researcher_clarification_20261019_v1/researcher_answers.json']
    files += list((OUT/'payloads').glob('*.json'))
    files += list((OUT/'sources').glob('*.txt'))
    files += list((p.HERE/'public_docs').glob('*.html'))
    protocol=dict(version=p.VERSION,study=p.STUDY,status='PREPARED_NOT_AUTHORIZED',
        config=config,model_version_source='official public mapping; no claim of immutable weights or old-D replication',
        public_price_table_identity=table_identity((p.HERE/'public_docs/pricing.html').read_bytes()),
        immutable_files={str(f):s.sha(f) for f in files},schedule=p.schedule(items),failure_policy=p.POLICY,
        baseline_cumulative=120,max_new_requests=24,cumulative_hard_cap=144,capacity=289,
        original_D_stage_cap=143,original_D_stage_unchanged=True,
        request_class_counts={'joint':8,'extract':8,'score_conditional_on_extract_valid':8},
        planned_flows=16,distinct_replies=8,distinct_contexts=4,
        financial_baseline=financial,per_request_reservation_usd=s.usd(p.RESERVE),
        runtime_entry='paired.py --live --approval APPROVED.json',
        run_root=str(p.BASE/'paired_diagnostic_runs'/p.STUDY/'live'),
        cross_version_dedup_key='study + bound reply/evidence + component; excludes prompt/code version',
        advance_rule=dict(min_distinct_contexts_with_clear_repairs=2,
            no_new_clear_errors_within_reviewed_scope=True,technical_complete_flow_count_not_lower=True,
            comparable_target_check_coverage_not_lower=True,reasonable_abstention_not_failure=True,
            no_sufficient_baseline_errors='ceiling/inconclusive',tradeoff='no winner',formal_qualification=False),
        forbidden_phases=['old_D_resume','other_candidates','sealed_acceptance','PPO','Step2'],
        reward_eligible=False)
    protocol['identity']=s.digest(protocol);write('protocol.json',protocol)
    auth=dict(status='PENDING',protocol_identity=protocol['identity'],study=p.STUDY,
        baseline_cumulative=120,new_request_limit=24,cumulative_cap=144,capacity=289,
        stage_cap_usd='1',trial_cap_usd='2',shared_cap_usd='20',failure_policy=p.POLICY,
        official_research_payload_authorized=False,intermediate_final_authorized=False,
        credential_process_read_authorized=False,management_requests={'models':1,'user/balance':1},
        old_stops_released=False,qualifies_reward=False,
        exact_egress=['original v2 joint prompt and NEW AI contract','versioned extraction or scoring-step instruction',
            'bound English reply and stable unit IDs','complete legal current/past sources and stable turn IDs',
            'score step only: validated final JSON from this item extraction; never thinking'],
        forbidden_egress=['human labels','analyst findings','expected answers','other-arm outputs','private notes','sealed data','credential files'],
        credential_file='/home/tokkio/metacom5_3.env',credential_variable='DEEPSEEK_API_KEY',
        endpoint='https://api.deepseek.com/chat/completions',new_terms_acceptance=False,
        approval_source=None)
    write('APPROVAL_PENDING.json',auth)
    prev=s.read(p.BASE/'D_development_20261015/cost_projection.json')
    write('budget_receipt.json',dict(financial_baseline=financial,request_lengths=rows,
        prices_USD_per_million=dict(peak_input_cache_miss='.30',peak_output='1.20',peak_cache_hit='.006',
            offpeak_input_cache_miss='.15',offpeak_output='.60',offpeak_cache_hit='.003'),
        input_exact_tokens='not available offline; record actual UTF-8 lengths and keep full native input liability bound',
        input_screen='UTF-8 serialized messages +8192 framing margin +393216 output <=1048576; conservative screen, not certified provider token count',
        reservation_formula='1048576*0.30/1e6 +393216*1.20/1e6 =0.786432; unchanged from inherited guard',
        next_call_possible_only_while_stage_settled_plus_unsettled_at_most_usd='.213568',
        empirical_24_call_scenario_usd=[str(Decimal(prev['unit_observed_cache_time_mean_usd'])*24),
            str(Decimal(prev['unit_peak_uncached_mean_usd'])*24)],
        empirical_twofold_usage_scenario_usd=[str(Decimal(prev['unit_observed_cache_time_mean_usd'])*48),
            str(Decimal(prev['unit_peak_uncached_mean_usd'])*48)],
        empirical_scenarios_not_new_pipeline_estimates=True,second_step_exact_input='unknown until first final; checked again before reserve/send',
        reserve_release='only complete prompt/completion usage settles; no usage retains entire reservation',
        settled_method='peak cache-miss conservative upper, thinking included once; not invoice reconciliation',
        native_reservation_not_total_bill=True,serial_only=True,stage_1USD_does_not_guarantee_24=True))
    inventory=s.read(REF/'coordinator/validation_inventory.json')
    write('validation_inventory.json',dict(original_metadata=inventory,original_metadata_sha256=s.sha(REF/'coordinator/validation_inventory.json'),
        new_text_reads=0,new_sealed_label_reads=0,new_independent_materials_certified=0,
        current_8_reply_contexts={k:items[k]['context_id'] for k in items},
        interpretation='same owner/history envelope and adjacent prefixes may share fact families; no independence claim or hidden-source read'))
    # PRIVATE offline reference. The runtime only loads items.json, not this file.
    original_path=next((p.BASE/'researcher_annotation_review_20261019_v1/originals').glob('*.json'))
    original=s.read(original_path);answers={x['item_id']:x for x in original['state']['items']}
    supplement=s.read(p.BASE/'researcher_clarification_20261019_v1/researcher_answers.json')
    extra={x['item_id']:x['verbatim'] for x in supplement['answers']}
    targets={
      'dev04A':('对用户困扰和不容忍不公的归属；开放探询不得无依据升级为已发生行动。', ['C:T001','C:T006','C:T008'], '研究者认可整体回应；具体主张拆解为分析者核查，不是新增原子金标准。'),
      'dev04B':('团队士气／效率影响的事实预设与引导读法均保留；另核查当前职场事实。', ['C:T001','C:T006','C:T007','C:T008'], '研究者明确接受两种读法；所列来源不确证团队后果；不设唯一q/m目标。'),
      'dev06A':('愤怒触发因素的备选探询是否被误罚；未澄清身份的问题独立保留。', ['C:T007','C:T008','C:T009'], '不是整条m=0的干净负例；原q范围和m=.25保留。'),
      'dev06B':('谈话已经发生的预设；区分交友话题、旅行争论和谈话建议；不自动预设实际平息或升级。', ['C:T007','C:T008','C:T009','H002:T010','H002:T021','H002:T022'], '研究者确认行动预设；旧讨论能否支持具体指向仍须按来源核查，严重度不补造。'),
      'dev07A':('简短承接与邀请继续谈的恰当性；不因缺少长建议自动扣分。', ['C:T001','C:T006','C:T008'], '研究者q=4/m=0为单人参照，不推广为所有短问句都满分；少事实不证明核查能力。'),
      'dev15B':('Talking with me的获益归属应对照old college friend，而非AI或历史支持者。', ['C:T005','C:T013'], '研究者明确指出人物与既成帮助关系；原q=2/m=1保留。'),
      'dev16A':('When I said/my mom/my own experience的说话者与经历归属；AI可引述但不能认领。', ['C:T008','C:T009'], '研究者确认会误导为亲历；来源支持旧支持者说过，不支持AI拥有经历；m=.25不自动改1。'),
      'dev35B':('job hunting无来源；旧睡眠和婚姻困难不能自动升级为当前原因。', ['C:T002','H001:T003','H002:T003'], '研究者核查完整合法来源未见找工作；缺乏支持不等于现实已证伪；严重度按具体后果复核。')}
    checklist=[]
    for key,item in items.items():
        description,source_ids,note=targets[key];turns=p.evidence_turns(item['evidence']);a=answers[item['item_id']]
        checklist.append(dict(item_key=key,item_id=item['item_id'],context_id=item['context_id'],
            reply_identity=s.digest(item['reply']),evidence_identity=s.digest(item['evidence']),reply_original=item['reply'],
            analyst_target=description,analyst_note=note,
            source_quotes=[dict(source_id=sid,role=turns[sid]['role'],quote=turns[sid]['text']) for sid in source_ids],
            full_source_path=str(REF/'materials'/(item['context_id']+'_complete.txt')),
            full_source_copy='sources/'+item['context_id']+'_complete.txt',
            original_human_answer=a,supplement_verbatim=extra.get(item['item_id']),
            atomic_gold_labels=False,independent_human_count=1,not_for_model_input=True,
            translation_version=original['ui_metadata']['translation_version']))
    write('target_checklist_PRIVATE.json',dict(items=checklist,scope='8 replies,4 contexts,2 source owners; exposed development only',
        original_submission_sha256=s.sha(original_path),human_and_analyst_separate=True,not_an_exhaustive_claim_gold_set=True))
    lines=['# 八题核对清单（仅离线核对，不进入模型输入）','',
      '研究者原始答案、三项补充和分析者核查分别保存。中文版本 pmrl1-zh-reader-20261016-v1；保留英文原文。8条回复、4个上下文，不是8个独立情境。','',
      '| 题号 | 上下文 | 原人工q／m | 目标与限制 |','|---|---|---|---|']
    for x in checklist:
        a=x['original_human_answer'];q=a['q_value'] if a['q_status']=='single' else a['q_min']+'–'+a['q_max']
        lines.append(f"| {x['item_key']} | {x['context_id']} | {q}／{a['m_status']} | {x['analyst_target']} {x['analyst_note']} |")
    lines+=['','06B和16A同属context_02；若两者改善，只计一个上下文。04B合理保留歧义不算技术失败。',
        '完整英文回复、逐字来源与原人答见 [target_checklist_PRIVATE.json](target_checklist_PRIVATE.json)；完整上下文在 [sources](sources/)；自由文字未被补写成研究者确认的原子标签。']
    (OUT/'CHECKLIST_ZH.md').write_text('\n'.join(lines)+'\n')
    write('technical_and_semantic_review_template.json',dict(protocol_identity=protocol['identity'],analyst_not_independent_human=True,
        per_flow_fields=['technical_complete','target_claim_detected','actor_time_action_relation','citation_entailment',
            'new_unsupported_accusation','appropriate_ambiguity_retention','q_range_relation','severity_reason','source_checks'],
        per_transition_fields=['first_claim_id','final_assessment_indices','retained_corrected_omitted_new_or_uncertain','source_checks','reason'],
        all_semantic_values_pending=True,advance_rule=dict(min_distinct_contexts_with_clear_repairs=2,
            no_new_clear_errors_within_reviewed_scope=True,technical_complete_flow_count_not_lower=True,
            comparable_target_check_coverage_not_lower=True,reasonable_abstention_not_failure=True,
            no_sufficient_baseline_errors='ceiling/inconclusive',tradeoff='no winner',formal_qualification=False)))
    with (OUT/'schedule.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(protocol['schedule'][0]));w.writeheader();w.writerows(protocol['schedule'])
    print(s.canonical(dict(protocol_identity=protocol['identity'],requests=24,trial_accounted=s.usd(trial),new_calls=0)))


if __name__=='__main__':main()
