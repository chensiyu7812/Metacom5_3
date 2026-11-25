#!/usr/bin/env python3
"""Export allowlisted counts and identities, never source/gold/response text."""
import argparse
import hashlib
import json
from pathlib import Path

p=argparse.ArgumentParser()
p.add_argument('--root',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
a=p.parse_args()
a.output.mkdir(parents=True,exist_ok=False)
sources={}


def read(name,lines=False):
    path=a.root/name
    sources[name]=hashlib.sha256(path.read_bytes()).hexdigest()
    return [json.loads(x) for x in path.read_text().splitlines()] if lines else json.loads(path.read_text())


def write(name,value):
    (a.output/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,sort_keys=True)+'\n')


def pick(row,keys):return {k:row[k] for k in keys.split()}


audit=read('memory_audit/v2/ATOMS_PRIVATE.jsonl',True)
coverage=[]
for row in audit:
    item=pick(row,'task_id capability dp_evidence_end_history ret_evidence_end_history dp_evidence_strict_date ret_evidence_strict_date')
    item.update(necessary_atoms=sum(x['required'] for x in row['atoms']),
                descriptive_atoms=len(row['atoms']),
                dp_future_session_count=len(row['dp_future_sessions_strict']),
                ret_future_session_count=len(row['ret_future_sessions_strict']),
                date_scope=row['explicit_time']['kind'])
    coverage.append(item)
write('MEMORY_QA30_COVERAGE.json',coverage)
labels={'documented_atoms_covered':'已覆盖','evidence_insufficient':'供证不足',
    'reference_pending_or_scope_conflict':'参考待核/范围冲突',
    'abstention_requires_archive_absence_review_not_empty_DP':'档案缺失审查'}
table=['# 30题生成前证据覆盖逐题表\n',
    '覆盖表示已审查的必要原子来源组得到供应，不代表答案正确或评价器已合格。严格时点与完整历史单列；没有明确日期的题保留完整历史口径。此表仅含不透明任务 ID 与计数，原题、答案及证据留在私有 sidecar。\n',
    '| Task ID | 必要原子 | DP 完整历史 | RET 完整历史 | DP 严格时点 | RET 严格时点 | 未来来源数 DP/RET |',
    '|---|---:|---|---|---|---|---:|']
for row in coverage:
    values=[row['task_id'],str(row['necessary_atoms'])]
    values += [labels[row[k]] for k in ['dp_evidence_end_history','ret_evidence_end_history','dp_evidence_strict_date','ret_evidence_strict_date']]
    values += [f"{row['dp_future_session_count']}/{row['ret_future_session_count']}"]
    table.append('| '+' | '.join(values)+' |')
(a.output/'MEMORY_QA30_COVERAGE_ZH.md').write_text('\n'.join(table)+'\n')
summary=read('memory_audit/v2/EVIDENCE_AUDIT_SUMMARY.json')
write('MEMORY_AUDIT_COUNTS.json',pick(summary,'tasks atoms necessary_atoms source_sessions_reviewed dp_end_history_status ret_end_history_status dp_strict_date_status ret_strict_date_status dp_future_delivery_tasks ret_future_delivery_tasks dp_complete_full_gold_candidates qualification'))

calls=read('smoke_results/PAIRED_RESPONSES_PRIVATE.jsonl',True)
write('SMOKE_CALL_MEASUREMENTS.json',[pick(row,'domain task_id arm request_id payload_sha256 response_sha256 technical_status finish_reason input_tokens output_tokens generation_seconds reward') for row in calls])
measurement=read('smoke_results/MEASUREMENTS.json')
write('SMOKE_MEASUREMENTS.json',pick(measurement,'protocol job_status requests physical_calls returned technical_counts model_load total_wall_seconds total_input_tokens total_output_tokens total_generation_seconds pairs reward_qualified latency_scope'))
a0=read('A0_RESULT_AND_SMOKE_FEASIBILITY.json')
write('A0_MEASUREMENTS.json',pick(a0,'A0_summary_sha256 status calls model_load_seconds total_wall_seconds deterministic_pairs_equal model_loading_errors'))

representations=read('representations/build-v4/REPORT.json')
write('REPRESENTATION_COUNTS.json',pick(representations,'protocol tasks representations ms_sum_candidate_sentence_count ms_sum_parent_session_groups logical_representation_rows ready_requests ledger_rows semantic_approved_new source_quote_identity_errors source_session_sets_identical_across_arms reading_tokens_by_arm model_calls gpu_loads limits'))
inspection=read('representations/FINAL_INSPECTION_V1.json')
write('REPRESENTATION_INSPECTION.json',pick(inspection,'arms interpretation old_gate sample_inspection'))

behavior=read('rs/behavior-compare-v1/RESULTS.json')
methods={}
for method in behavior['old_split']['results']:
    methods[method]={}
    for name,result in [('old_split',behavior['old_split']['results'][method]),('group_out',behavior['group_out_combined'][method])]:
        methods[method][name]=dict(expected_accuracy=result['expected_accuracy'],
            macro_f1=result['classification']['macro avg']['f1-score'],
            unique_utterances=result['unique_utterances'],annotation_rows=result['annotation_rows'],
            disagreement_strata=result['disagreement_strata'],
            therapist_input_recall=result['classification']['therapist_input']['recall'])
write('BEHAVIOR_COMPARISON.json',dict(methods=methods,encoding=behavior['encoding'],
    model_selected=behavior['model_selected'],reward_qualified=behavior['reward_qualified'],
    elapsed_seconds=behavior['elapsed_seconds'],seven_folds=len(behavior['seven_video_folds']),
    family_overlap=[x['family_overlap'] for x in behavior['seven_video_folds']]))
write('BEHAVIOR_UNCERTAINTY.json',read('rs/behavior-uncertainty-v1/PAIRED_UNCERTAINTY.json'))
delivery=read('rs/delivery-audit-v1/RESULTS.json')
write('RS_DELIVERY_COUNTS.json',pick(delivery,'protocol by_arm actual_selected_skills direct_versus_retrieval interpretation preserved_methods preserved_tasks preserved_requests exact_native_token_checks exact_reading_content_checks raw_method_same_paragraph_checks F_resident_full_library_checks truncation_or_missing_content'))
write('RS_SMOKE_REVIEW.json',read('rs/smoke_review-v1/SUMMARY_PUBLIC.json'))
write('MEMORY_SMOKE_REVIEW.json',read('memory_outcomes-v1/PUBLIC_AGGREGATE.json'))
write('SOURCE_HASHES.json',sources)
