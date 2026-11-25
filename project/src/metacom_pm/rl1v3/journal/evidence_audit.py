"""Bind reviewed QA answer atoms to exact legal source spans, without generation.

The review input is private and explicitly authored after source reading. This
module verifies offsets, versions, temporal scopes, and arm delivery; lexical
matches never manufacture entailment. Original tasks, gold, arms and packets
are read-only. Unknown references do not become negative Generator outcomes.
"""
from __future__ import annotations
from collections import Counter
from datetime import date,timedelta
from pathlib import Path
import hashlib,json,re
from ..io import file_sha256,object_sha256,write_json_once,write_jsonl_once,write_bytes_once

PROTOCOL='pmrl1-j-evidence-aware-qa-v2'
MONTHS={m.lower():i for i,m in enumerate(('January','February','March','April','May','June','July','August','September','October','November','December'),1)}
MONTHS['jenuary']=1
SUPPORTED={'supported','calendar_derived'}
SOURCE_SHA='f30698e87fddaeff51270a666c654da604f487a3456ec60d2b6ae08a6fecd420'


def parse_question_time(question):
    """Uniform parsing; no inference of cutoff from private question-group ID."""
    months='|'.join(MONTHS)
    m=re.search(r'\b(as of|on|by)\s+('+months+r')\s+(\d{1,2}),?\s+(20\d{2})\b',question,re.I)
    if m:
        d=date(int(m[4]),MONTHS[m[2].lower()],int(m[3])).isoformat()
        return dict(kind='explicit_day',phrase=m[0],lower=d,upper=d,
            semantics='knowledge_as_of' if m[1].lower()=='as of' else 'historical_event_date_strict_knowledge_sensitivity',
            spelling_alias='Jenuary→January' if m[2].lower()=='jenuary' else None,
            within_day_policy='completed sessions dated the same day admitted only under end-of-day convention; no wall-clock precision')
    m=re.search(r'\bby\s+('+months+r')\s+(20\d{2})\b',question,re.I)
    if m:
        import calendar
        y,mo=int(m[2]),MONTHS[m[1].lower()]
        return dict(kind='explicit_month_interval',phrase=m[0],lower=date(y,mo,1).isoformat(),
            upper=date(y,mo,calendar.monthrange(y,mo)[1]).isoformat(),semantics='date_precision_ambiguous',
            spelling_alias=None,within_day_policy='No arbitrary exact cutoff; earliest/latest bounds both reported')
    return dict(kind='end_history_only',phrase=None,lower=None,upper=None,semantics='no_explicit_cutoff',spelling_alias=None)


def atom_delivery(groups, delivered):
    """Source delivery only, separate from the reviewer's entailment judgment."""
    return bool(groups) and any(all(ref.split(':',1)[0] in delivered for ref in group) for group in groups)


def aggregate_evidence_status(atoms, arm, strict=False):
    atoms=[a for a in atoms if a.get('required',True)]
    validity='status_explicit_date' if strict else 'status_end_history'
    if any(a[validity] not in SUPPORTED|{'absence_supported'} for a in atoms):
        return 'reference_pending_or_scope_conflict'
    if any(a[validity]=='absence_supported' for a in atoms):
        return 'abstention_requires_archive_absence_review_not_empty_DP'
    key=arm+('_delivered_strict' if strict else '_delivered')
    return 'documented_atoms_covered' if all(a[key] for a in atoms) else 'evidence_insufficient'


def build(root,memory,review_path,output):
    root,memory,review_path,output=map(Path,(root,memory,review_path,output))
    output.mkdir(parents=True,exist_ok=True)
    raw_path=root/'project/data/external/evo_emo.json'
    if file_sha256(raw_path)!=SOURCE_SHA:raise ValueError('pinned EvoEmo bytes differ')
    raw=json.loads(raw_path.read_text());users={u['id']:u for u in raw}
    sanitized_path=root/'project/data/paper1_public_memory/es_memeval_public_sanitized_runtime_artifact_v1.json'
    sanitized=json.loads(sanitized_path.read_text())['users']
    clean={(u['owner_id'],s['session_id']):s for u in sanitized for s in u['sessions']}
    source={(u['id'],s['id']):s for u in raw for s in u['dialog_history']}
    evaluations=[json.loads(x) for x in (memory/'evalspec_private.jsonl').read_text().splitlines()]
    tasks={r['task_id']:r for r in map(json.loads,(memory/'tasks_runtime.jsonl').read_text().splitlines())}
    materials={(r['task_id'],r['arm']):r for r in map(json.loads,(memory/'request_material_private.jsonl').read_text().splitlines())}
    original_report=json.loads((memory/'MEMORY_BUILD_REPORT.json').read_text())
    for name,v in original_report['outputs'].items():
        if file_sha256(memory/name)!=v['sha256']:raise ValueError('original artifact changed '+name)
    review=json.loads(review_path.read_text());decisions=review['records']
    if set(decisions)!=set(map(str,range(1,31))):raise ValueError('30 reviewed rows required')
    rows=[];complete=[]
    for idx,ev in enumerate(evaluations,1):
        reviewed=decisions[str(idx)];task=tasks[ev['task_id']]
        owner=ev['owner_id'];question=task['visible_prefix']['turns'][0]['text']
        user=users[owner];original={f"{owner}::{g['id']}::{q['idx']}":q for g in user['questions'] for q in g['questions']}[ev['row_id']]
        if (original['question'],original['answer'])!=(question,ev['gold']):raise ValueError('original QA changed')
        time=parse_question_time(question)
        def span(ref,relation):
            sid,uid=ref.rsplit(':',1);s=source[(owner,sid)];c=clean[(owner,sid)]
            matches=[(i,t) for i,t in enumerate(s['dialogue']) if str(t['idx'])==uid]
            if len(matches)!=1:raise ValueError('ambiguous exact turn '+ref)
            ordinal,t=matches[0];ct=c['turns'][ordinal]
            if (t['content'],t['role'],t['idx'])!=(ct['content'],ct['role'],ct['idx']):raise ValueError('source/sanitized mapping differs')
            quote=t['content'];reported=s['timestamp']
            legal=True if time['upper'] is None else reported<=time['upper']
            lower_legal=True if time['lower'] is None else reported<=time['lower']
            return dict(owner_id=owner,session_id=sid,ordinal_turn=ordinal,original_idx=t['idx'],speaker=t['role'],
                start_char=0,end_char=len(quote),exact_quote=quote,raw_turn_sha256=hashlib.sha256(quote.encode()).hexdigest(),
                reported_at=dict(date=reported,session_rank=c['chronological_rank']),event_time=None,
                known_at=dict(session_rank=c['chronological_rank']+1),ready_at=dict(session_rank=c['chronological_rank']+1),
                relation=relation,temporal_legal_strict=legal,temporal_legal_earliest_bound=lower_legal,
                source_file_sha256=SOURCE_SHA,source_uri='data/evo_emo.json#'+owner+'/'+sid+'/'+str(t['idx']))
        dp=materials[(ev['task_id'],'DP')]['private_source_session_ids'];ret=materials[(ev['task_id'],'RET')]['private_source_session_ids']
        atoms=[]
        for n,item in enumerate(reviewed['atoms'],1):
            groups=item['support_groups'];support_refs=list(dict.fromkeys(ref for g in groups for ref in g))
            evidence=[span(r,'support') for r in support_refs]+[span(r,'context_only') for r in item['context_refs']]+[span(r,'conflict') for r in item['conflict_refs']]
            strict_groups=[g for g in groups if all(span(r,'support')['temporal_legal_strict'] for r in g)]
            early_groups=[g for g in groups if all(span(r,'support')['temporal_legal_earliest_bound'] for r in g)]
            end_status=item['status']
            if end_status=='temporal_misalignment':end_status='supported'
            strict_status=item['status']
            if time['upper'] is None:strict_status=end_status
            elif strict_status in SUPPORTED and groups and not strict_groups:strict_status='future_only_evidence'
            elif time['kind']=='explicit_month_interval' and groups and strict_groups and not early_groups:strict_status='ambiguous_month_cutoff'
            atom=dict(atom_id=f"{ev['task_id']}:a{n}",claim=item['claim'],required=item.get('required',True),
                source_evidence=evidence,sufficient_source_groups=groups,
                dp_delivered=atom_delivery(groups,set(dp)),ret_delivered=atom_delivery(groups,set(ret)),
                dp_delivered_strict=atom_delivery(strict_groups,set(dp)),ret_delivered_strict=atom_delivery(strict_groups,set(ret)),
                status_end_history=end_status,status_explicit_date=strict_status,
                reviewer_status=item['status'],rationale=item['rationale'],
                representation_policy='Only support exact_quote fields are permitted source inputs; claim/gold/status/answer must never compile into a memory.')
            if item['status']=='calendar_derived':
                report_date=date.fromisoformat(next(e['reported_at']['date'] for e in evidence if e['relation']=='support'))
                saturday=report_date+timedelta(days=(5-report_date.weekday())%7)
                atom['derivation']=dict(rule='upcoming Saturday/Sunday after source date',input_date=report_date.isoformat(),result=[saturday.isoformat(),(saturday+timedelta(days=1)).isoformat()],assumption='weekend refers to immediately upcoming weekend; not a literal date utterance')
            atoms.append(atom)
        future=lambda ids:[sid for sid in ids if time['upper'] and source[(owner,sid)]['timestamp']>time['upper']]
        for a in atoms:
            for e in a['source_evidence']:
                if e['relation']=='support' and e['speaker']=='supporter':
                    e['speaker_limit']='Dialogue question/context only; must be combined with user report, not treated as an independent user fact.'
        row=dict(protocol=PROTOCOL,task_id=ev['task_id'],original_row_id=ev['row_id'],owner_id=owner,
            question=question,gold=ev['gold'],capability=ev['capability'],source_sha256=SOURCE_SHA,
            original_evalspec_sha256=object_sha256(ev),explicit_time=time,scope_note=reviewed.get('scope_note'),
            absence_review=reviewed.get('absence_target'),atoms=atoms,original_dp_sessions=dp,original_ret_sessions=ret,
            dp_future_sessions_strict=future(dp),ret_future_sessions_strict=future(ret),
            dp_evidence_end_history=aggregate_evidence_status(atoms,'dp'),ret_evidence_end_history=aggregate_evidence_status(atoms,'ret'),
            dp_evidence_strict_date=aggregate_evidence_status(atoms,'dp',True),ret_evidence_strict_date=aggregate_evidence_status(atoms,'ret',True),
            evaluation_rule=dict(task_success='No score before generated output; all supported necessary atoms plus explicit prohibitions must be checked independently.',
                reference_unknown='pending [0,1]; never automatically mark generator failure',
                resource_absence='Evidence_insufficient means the reviewed sufficient source groups are not all supplied; it is not a proof that no alternate legitimate inference is possible. Separate this from application_error.',
                temporal='Keep official end-history and strict-question-date views separate; do not rewrite original task or remove future arms.',
                abstention='Absence is an archive review conclusion, not proved by an empty DP; vague requested specificity remains pending.'),
            reviewer='assistant_source_review_not_independent_human_qualification',generation_seen=False)
        rows.append(row)
        # A new, evaluation-privileged proposal only. It is not an edit to original DP.
        chosen=set();unresolved=[]
        for atom in atoms:
            if not atom['required']:continue
            if atom['status_explicit_date'] not in SUPPORTED:
                if atom['status_explicit_date']!='absence_supported':unresolved.append(atom['atom_id'])
                continue
            alternatives=[]
            for group in atom['sufficient_source_groups']:
                es=[span(ref,'support') for ref in group]
                if not all(e['temporal_legal_strict'] for e in es):continue
                sessions={e['session_id'] for e in es}
                alternatives.append((len(sessions-chosen),len(sessions),sorted(sessions)))
            if alternatives:chosen.update(min(alternatives)[2])
            else:unresolved.append(atom['atom_id'])
        ordered=sorted(chosen,key=lambda s:clean[(owner,s)]['chronological_rank'])
        text='\n\n'.join('Completed historical session; reported '+source[(owner,s)]['timestamp']+':\n'+
            '\n'.join(t['role']+': '+t['content'] for t in source[(owner,s)]['dialogue']) for s in ordered)
        complete.append(dict(task_id=ev['task_id'],proposal_id='DP-Complete:'+object_sha256(dict(protocol=PROTOCOL,task=ev['task_id'],sessions=ordered,unresolved=unresolved)),
            arm_identity='DP-Complete-candidate-v1-not-original-DP',source_sessions=ordered,reading_text=text,
            selected_support_atoms=[a['atom_id'] for a in atoms if a['required'] and a['status_explicit_date'] in SUPPORTED],
            unresolved_reference_atoms=unresolved,full_gold_evidence_claim=not unresolved and ev['capability']!='abstention',
            status='candidate_only_no_generation',budget_status='needs_native_token_check' if len(ordered)<=4 else 'over_four_session_budget_no_truncation',
            original_question=question,original_task_unchanged=True,source_material_only=True))
    atom_rows=[a for r in rows for a in r['atoms']]
    summary=dict(protocol=PROTOCOL,tasks=len(rows),atoms=len(atom_rows),necessary_atoms=sum(a['required'] for a in atom_rows),source_sessions_reviewed=91,
        sources_scope='all seeker utterances of 4 development owners, plus relevant supporter context; absence is not an objective closed-world proof',
        atom_status_end_history=dict(Counter(a['status_end_history'] for a in atom_rows)),
        atom_status_explicit_date=dict(Counter(a['status_explicit_date'] for a in atom_rows)),
        tasks_with_explicit_day=sum(r['explicit_time']['kind']=='explicit_day' for r in rows),
        tasks_with_month_interval=sum(r['explicit_time']['kind']=='explicit_month_interval' for r in rows),
        jenuary_alias_tasks=sum(r['explicit_time']['spelling_alias'] is not None for r in rows),
        dp_future_delivery_tasks=sum(bool(r['dp_future_sessions_strict']) for r in rows),
        ret_future_delivery_tasks=sum(bool(r['ret_future_sessions_strict']) for r in rows),
        dp_end_history_status=dict(Counter(r['dp_evidence_end_history'] for r in rows)),
        ret_end_history_status=dict(Counter(r['ret_evidence_end_history'] for r in rows)),
        dp_strict_date_status=dict(Counter(r['dp_evidence_strict_date'] for r in rows)),
        ret_strict_date_status=dict(Counter(r['ret_evidence_strict_date'] for r in rows)),
        dp_complete_full_gold_candidates=sum(x['full_gold_evidence_claim'] for x in complete),
        dp_complete_over_four=sum(x['budget_status'].startswith('over_') for x in complete),
        modified_original_artifacts=0,generator_calls=0,model_outputs_seen=False,
        qualification='assistant-source-audit-development-only; no independent gold/judge qualification',
        stopping='Do not replace tasks, change gold, or relabel uncertainty to obtain positive results.')
    write_jsonl_once(output/'ATOMS_PRIVATE.jsonl',rows)
    write_jsonl_once(output/'DP_COMPLETE_CANDIDATE.private.jsonl',complete)
    write_json_once(output/'EVIDENCE_AUDIT_SUMMARY.json',summary)
    md=['# 30 QA 原子证据审查（私有）','原任务、原gold、原DP/RET不变；以下是生成前测量侧审查。未查看模型输出。','',
        '|#|task_id|原题|gold状态/说明|DP全历史|RET全历史|DP日期之后来源|RET日期之后来源|','|---|---|---|---|---|---|---|---|']
    for i,r in enumerate(rows,1):
        bad=sorted({a['status_explicit_date'] for a in r['atoms'] if a['status_explicit_date'] not in SUPPORTED|{'absence_supported'}})
        md.append('|'+ '|'.join(map(lambda s:str(s).replace('|','/'),[i,r['task_id'],r['question'],','.join(bad) or 'documented',r['dp_evidence_end_history'],r['ret_evidence_end_history'],','.join(r['dp_future_sessions_strict']),','.join(r['ret_future_sessions_strict'])]))+'|')
    for i,r in enumerate(rows,1):
        md+=['',f"## {i}. {r['task_id']}",r['question'],'原gold：'+r['gold'],'时间：'+json.dumps(r['explicit_time'],ensure_ascii=False)]
        if r['scope_note']:md.append('范围：'+r['scope_note'])
        for atom in r['atoms']:
            md += ['',f"- {atom['atom_id'].split(':')[-1]}：{atom['claim']}；全历史={atom['status_end_history']}；严格日期={atom['status_explicit_date']}；DP提供={atom['dp_delivered']}；RET提供={atom['ret_delivered']}"]
            if atom['rationale']:md.append('  审查理由：'+atom['rationale'])
            for e in atom['source_evidence']:
                md.append(f"  - [{e['relation']}] {e['session_id']}:{e['original_idx']} / {e['reported_at']['date']} / {e['speaker']} / chars 0:{e['end_char']}：{e['exact_quote']}")
    write_bytes_once(output/'QA30_EVIDENCE_REVIEW_PRIVATE.md',('\n'.join(md)+'\n').encode())
    write_json_once(output/'FREEZE_MANIFEST.json',dict(protocol=PROTOCOL,status='frozen_pre_generation_evidence_sidecar',
        code_sha256=file_sha256(__file__),review_input_sha256=file_sha256(review_path),source_sha256=SOURCE_SHA,
        original_inputs={n:file_sha256(memory/n) for n in ('tasks_runtime.jsonl','evalspec_private.jsonl','request_material_private.jsonl')},
        outputs={n:file_sha256(output/n) for n in ('ATOMS_PRIVATE.jsonl','DP_COMPLETE_CANDIDATE.private.jsonl','EVIDENCE_AUDIT_SUMMARY.json','QA30_EVIDENCE_REVIEW_PRIVATE.md')},
        model_outputs_seen=False,generator_calls=0,changes_original_protocol=False))
    return summary
