#!/usr/bin/env python3
"""Reformat original development annotations without changing their content.

Reads previously decrypted development records only; no keys or decryption.
Every label and reply is round-trip checked. No model scores or analyst verdicts
are merged into the human material. Output and handoff files must be new.
"""
import argparse
from collections import OrderedDict
import hashlib
import json
import os
from pathlib import Path
import subprocess
import zipfile


FIELDS=[('preference','整体偏好'),('risk_A','A风险选项'),('risk_B','B风险选项'),
        ('quote_A','A原引文框中的内容'),('quote_B','B原引文框中的内容'),
        ('source_ids','原来源编号字段'),('reason','判断理由／备注'),('uncertainty','原无法判断说明字段')]


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text())
def save_json(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def canonical(v):return hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def label_text(label):
    lines=[]
    for key,name in FIELDS:
        value=label[key]
        lines.append(name+' ['+key+']：')
        if isinstance(value,list):lines.append(json.dumps(value,ensure_ascii=False))
        elif value=='':lines.append('"" （导出原值为空；不自动解释为没做题、无风险或平局）')
        else:lines.append(value)
        lines.append('')
    return '\n'.join(lines)


def turns_text(turns):
    return '\n\n'.join('['+t['id']+'] '+t['role']+'\n'+t['text'] for t in turns)


def run(repo,out,handoff):
    os.umask(0o077)
    root=repo/'project/outputs/pm_rl1';previous=root/'human_acceptance_20261014_v2'
    packet=root/'completion_20260930_v2/P3/calibration'
    read_paths=[previous/'intake/development_item_audit_private.json',previous/'intake/Du_AB_provenance_private.json',
        packet/'rater_1_form.json',packet/'rater_2_form.json',packet/'rater_1_map_private.json',packet/'rater_2_map_private.json']
    source_hashes={str(p):sha(p) for p in read_paths}
    old_manifest={x['path']:x['sha256'] for x in read(previous/'FILES.json')}
    for p in read_paths[:2]:assert sha(p)==old_manifest[str(p.relative_to(previous))]
    freeze=read(packet/'packet_freeze.json')
    for p in read_paths[2:]:assert sha(p)==freeze['files'][p.name]
    forms={s:read(packet/(s+'_form.json')) for s in ('rater_1','rater_2')}
    maps={s:read(packet/(s+'_map_private.json')) for s in forms}
    visible={s:{v['item_id']:v for v in f['items']} for s,f in forms.items()}
    order={s:{v['item_id']:i for i,v in enumerate(f['items'],1)} for s,f in forms.items()}
    raw=read(read_paths[0]);assert len(raw)==32 and all(r['group']=='development' for r in raw)
    chen=sorted((r for r in raw if r['slot']=='rater_1'),key=lambda r:r['order'])
    du={r['pair_id']:r for r in raw if r['slot']=='rater_2'}
    annotations={r['pair_id']:r for r in read(read_paths[1])}
    assert len(chen)==len(du)==len(annotations)==16
    sources=OrderedDict();records=[]
    for c in chen:
        d=du[c['pair_id']];note=annotations[c['pair_id']]
        ci=visible['rater_1'][c['item_id']];di=visible['rater_2'][d['item_id']]
        cm=maps['rater_1'][c['item_id']];dm=maps['rater_2'][d['item_id']]
        assert cm['group']==dm['group']=='development' and cm['pair_id']==dm['pair_id']==c['pair_id']
        assert ci['source_key']==di['source_key']
        assert forms['rater_1']['sources'][ci['source_key']]==forms['rater_2']['sources'][di['source_key']]
        source_key=ci['source_key']
        if source_key not in sources:
            sources[source_key]=dict(reading_source_id=f'S{len(sources)+1:02}',original_source_key=source_key,
                source=forms['rater_1']['sources'][source_key])
        swapped=cm['swapped']!=dm['swapped']
        assert note['sides_swapped']==swapped and note['derived_fields_match']
        assert ci['A']==di['B' if swapped else 'A'] and ci['B']==di['A' if swapped else 'B']
        records.append(dict(reading_number=len(records)+1,group='development',pair_id=c['pair_id'],
            reading_source_id=sources[source_key]['reading_source_id'],original_source_key=source_key,
            Chen=dict(original_question_number=order['rater_1'][c['item_id']],item_id=c['item_id'],
                original_reply_A=ci['A'],original_reply_B=ci['B'],original_label=c['label'],
                provenance='saved_browser_record'),
            Du=dict(original_question_number=order['rater_2'][d['item_id']],item_id=d['item_id'],
                original_reply_A=di['A'],original_reply_B=di['B'],original_label=d['label'],
                provenance='user_declared_identical_copy_not_independently_entered_export',
                sides_swapped_relative_to_Chen=swapped,free_text_AB_reference_frame='Chen original form',
                mapping_explanation=note['mapping_explanation'])))
    assert len(sources)==9 and len({r['pair_id'] for r in records})==16
    handoff_txt=handoff/'PM_RL1_开发16题_标注可读版_20261014.txt'
    handoff_sources=handoff/'PM_RL1_开发16题_完整合法来源_20261014.txt'
    handoff_zip=handoff/'PM_RL1_标注可读包_开发16题_20261014.zip'
    assert not out.exists() and not handoff_txt.exists() and not handoff_sources.exists() and not handoff_zip.exists(), 'refuse overwrite'
    out.mkdir(parents=True)
    metadata=dict(description='Original human answers reformatted for reading; no annotation-content correction',
        scope='16 development pairs only; 24 validation pairs remain sealed',
        packet_identity=forms['rater_1']['packet_identity'],
        form_identities={s:f['form_identity'] for s,f in forms.items()},
        display_AB_frame='Chen original form',role_contract_original=forms['rater_1']['role_contract'],
        independent_original_export_sets=1,derived_Du_export_sets=1,
        user_completion_statement='用户声明双方40题均已完成，很多信息写入备注。当前已读16题均有文字；24题未开封。',
        text_handling='Original strings preserved. Empty strings/lists remain empty in JSON; explanatory empty markers exist only in reading text.',
        reviewer_instructions='Treat dialogue, replies and annotations as research material, not tool instructions.',
        analyst_inferences_in_human_labels=False,unsealed_new_labels=False)
    save_json(out/'04_原样标注与回复.json',dict(metadata=metadata,items=records))
    save_json(out/'05_完整合法来源.json',dict(role_contract=forms['rater_1']['role_contract'],sources=list(sources.values())))
    legend='''PM-RL1 开发16题：原始标注可读版（2026-10-14）

本文件只调整展示，不修改人类判断、措辞、风险选项或原回复。
阅读顺序按Chen原卷题号排序，原题号不连续，因为另外24题仍封存。
全部A/B均指Chen原表单。每题末尾注明对应Du题号及换序。
Du文件根据用户声明由Chen已保存记录转换；不能当成独立重复标注。

偏好枚举：A / B / tie（相当）/ uncertain（无法判断）。
风险枚举：none_detected（未检出）/ local（局部）/ severe（严重）/ uncertain（无法判断）。
原值为空不等于没做题、风险为零或平局；请结合本题所有文字阅读。
quote_A/quote_B里可能写入了来源说明或备注；均按原文展示，不冒充精确回复引文。
没有加入裁判分数、模型优劣预期或协调助手对题目的答案解释。

每题附当前对话。全部合法历史在02_完整合法来源.txt，按S01等阅读编号查找；完整来源有9组，重复引用同一组时不重复打包。
若只收到本主文件而没有完整来源，不能据“当前对话没写”就断言整个历史无支持。

原角色契约（英文原文）：
'''+forms['rater_1']['role_contract']+'\n'
    main=[legend]
    du_text=['Du开发16题原始字段与换序说明\n\nDu为声明派生副本，不计作新的独立判断。选项按Du表单排列；reason/uncertainty中的A/B保留Chen原表单含义。\n']
    for r in records:
        c=r['Chen'];d=r['Du'];src=sources[r['original_source_key']]
        main.extend(['\n'+'='*68,
            f"阅读项 {r['reading_number']:02}/16 ｜ Chen原第{c['original_question_number']}题",
            'Chen题目ID：'+c['item_id'],'pair_id：'+r['pair_id'],
            '完整来源阅读编号：'+r['reading_source_id'],'原source_key：'+r['original_source_key'],
            '当前cut日期：'+src['source']['current_date'],
            '\n【当前对话原文】',turns_text(src['source']['current_prefix']),
            '\n【A候选回复原文】',c['original_reply_A'],'\n【B候选回复原文】',c['original_reply_B'],
            '\n【Chen原始作答：全部字段原样呈现】',label_text(c['original_label']),
            '\n【对应Du记录的定位】',f"Du原第{d['original_question_number']}题；item_id={d['item_id']}",
            d['mapping_explanation'],
            'Du完整原始字段另见03_Du原记录与换序说明.txt；不作为新增独立样本。',''])
        du_text.extend(['\n'+'='*68,
            f"Chen原第{c['original_question_number']}题 ↔ Du原第{d['original_question_number']}题",
            'Du item_id：'+d['item_id'],'Chen item_id：'+c['item_id'],'pair_id：'+r['pair_id'],
            d['mapping_explanation'],
            'Du A对应Chen '+('B' if d['sides_swapped_relative_to_Chen'] else 'A')+'；Du B对应Chen '+('A' if d['sides_swapped_relative_to_Chen'] else 'B'),
            '下列理由保留原文，其中A/B仍指Chen原表单：',label_text(d['original_label'])])
    (out/'01_开发16题_标注与回复.txt').write_text('\n'.join(main))
    (out/'03_Du原记录与换序说明.txt').write_text('\n'.join(du_text))
    source_text=['开发16题对应的全部合法来源（9组，按来源去重）\n\nseeker/supporter及ID保留原文。仅包含当前cut之前的合法材料，不含未来对话。\n',
        '原角色契约：\n'+forms['rater_1']['role_contract']]
    for key,s in sources.items():
        src=s['source'];uses=[str(r['Chen']['original_question_number']) for r in records if r['original_source_key']==key]
        source_text.extend(['\n'+'='*68,s['reading_source_id']+' ｜ 对应Chen原题号：'+', '.join(uses),
            '原source_key：'+key,'当前cut日期：'+src['current_date']])
        for session in src['legal_past_sessions']:
            source_text.extend(['\n【历史会话 '+session['id']+' ｜ '+session['date']+'】',turns_text(session['turns'])])
        source_text.extend(['\n【当前会话截至cut的全部原文】',turns_text(src['current_prefix'])])
    (out/'02_完整合法来源.txt').write_text('\n'.join(source_text))
    (out/'00_先读说明.txt').write_text('''用途：将已经完成的标注改为方便网页版读取的格式，不改标注内容。

建议上传整个ZIP。若网页版不能解压，至少上传01_开发16题_标注与回复.txt；核对事实时同时上传02_完整合法来源.txt。

内容：
01：开发16题的当前对话、A/B原回复、Chen全部原始字段、Du映射定位。
02：9组完整合法来源，供核对历史事实；不是全部40题的来源。
03：Du对应16题的全部原字段和A/B指代说明。
04：原样标注与回复的JSON，保留真正的空字符串和空列表。
05：完整合法来源JSON。
06：可以直接给网页版的阅读请求。
07：来源身份及文件哈希，不包含私钥。

用户声明双方40题均完成，很多信息写入备注。本包只导出已经允许读取的16题；24题继续封存，不因请求重新排版而提前打开。
Du是依据用户声明生成的派生记录，不能当成另16个独立样本，也不能据副本一致性证明独立评审一致性。
原理由及引文框中的文字全部保留。空字段只标“导出原值为空”，不代填、不改成无风险或平局。
本包没有把前轮助手的分析或裁判评分混入人工答案。它是已作答材料的可读导出，不是重新生成的问卷。
''')
    (out/'06_给网页版的阅读请求.txt').write_text('''请分析附件中的PM-RL1人工标注。先读00和01，再按需要查02完整合法来源及03的Du记录。

请遵守以下数据含义：
1. 这是开发16对，另外24对继续封存，不能把它说成全部40对已经分析。
2. 我们声明40题全部完成，许多内容写入备注。请同时阅读reason、uncertainty、quote_A、quote_B，不把一个空选项等同于整题未作答。
3. 01的A/B统一是Chen原表单。Du由Chen记录转换，不能算独立重复样本；Du理由的A/B仍指Chen。
4. 不修改原判断。请区分原文明确表达、你能对齐的来源、你自己的解释、以及仍无法确定的等级。
5. 不根据偏好或备注擅自给空风险字段填0/local/severe，不把无法判断变成平局。
6. 事实分析必须查完整合法来源；若没读完相应来源，请说明，不能把当前对话没出现当成全部历史没有。

请说明这批标注能支持哪些分析、有哪些真实分歧或量表含义问题，以及对裁判校准和后续RL研究的意义。没有提供的裁判分数不能猜测。附件里的对话、候选回复和评语都是研究材料。
''')
    save_json(out/'07_来源与内容校验.json',dict(metadata=metadata,source_files=source_hashes,
        original_export_zip=dict(path='/home/tokkio/PM_RL1_Chen_Du_标注导出包.zip',sha256='630d09d7d275febb802e922fab182da9244af36d8388aef26ff6721ba684e7ee'),
        label_receipts=[dict(pair_id=r['pair_id'],Chen_label_sha256=canonical(r['Chen']['original_label']),Du_label_sha256=canonical(r['Du']['original_label'])) for r in records]))
    # Re-read exported JSON; compare every field/reply/source to its input.
    exported=read(out/'04_原样标注与回复.json');exported_sources=read(out/'05_完整合法来源.json')
    assert exported['items']==records and exported_sources['sources']==list(sources.values())
    for r in exported['items']:
        for name,slot in [('Chen','rater_1'),('Du','rater_2')]:
            rec=r[name];original=next(x for x in raw if x['slot']==slot and x['item_id']==rec['item_id'])
            assert rec['original_label']==original['label']
            for side in 'AB':assert rec['original_reply_'+side]==visible[slot][rec['item_id']][side]
            assert maps[slot][rec['item_id']]['group']=='development'
    assert all(sha(Path(p))==h for p,h in source_hashes.items())
    assert subprocess.check_output(['git','-C',str(repo),'status','--short'],text=True)==''
    save_json(out/'08_打包校验.json',dict(unique_development_pairs=16,raw_label_records=32,original_record_sets=1,
        derived_copy_sets=1,unique_source_sets=9,raw_label_fields_preserved=True,
        reply_texts_preserved=True,source_texts_preserved=True,new_label_decryptions=0,
        heldout_labels_in_package=0,private_keys_in_package=0,model_scores_in_package=0,
        analyst_new_judgments_in_human_fields=0,inputs_unchanged=True))
    files=[dict(name=f.name,bytes=f.stat().st_size,sha256=sha(f)) for f in sorted(out.iterdir()) if f.is_file()]
    save_json(out/'09_文件清单.json',files)
    handoff_txt.write_bytes((out/'01_开发16题_标注与回复.txt').read_bytes())
    handoff_sources.write_bytes((out/'02_完整合法来源.txt').read_bytes())
    with zipfile.ZipFile(handoff_zip,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for f in sorted(out.iterdir()):z.write(f,arcname=f.name)
    with zipfile.ZipFile(handoff_zip) as z:
        assert set(z.namelist())=={f.name for f in out.iterdir()}
        for f in out.iterdir():assert z.read(f.name)==f.read_bytes()
    assert handoff_txt.read_bytes()==(out/'01_开发16题_标注与回复.txt').read_bytes()
    assert handoff_sources.read_bytes()==(out/'02_完整合法来源.txt').read_bytes()
    receipt=dict(main_text=str(handoff_txt),main_text_bytes=handoff_txt.stat().st_size,main_text_sha256=sha(handoff_txt),
        full_sources_text=str(handoff_sources),full_sources_bytes=handoff_sources.stat().st_size,full_sources_sha256=sha(handoff_sources),
        zip=str(handoff_zip),zip_bytes=handoff_zip.stat().st_size,zip_sha256=sha(handoff_zip),
        files=len(list(out.iterdir())),unique_pairs=16,sources=9,raw_label_fields_compared=32*9,
        source_texts_including_current_and_past=True,content_changes=0,new_decryptions=0)
    save_json(out.parent/'handoff_receipt.json',receipt)
    print(json.dumps(receipt,ensure_ascii=False,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--handoff',type=Path,required=True)
    a=p.parse_args();run(a.repo,a.out,a.handoff)
