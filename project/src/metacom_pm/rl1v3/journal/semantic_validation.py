"""One frozen CPU NLI diagnostic, with independent source strata and abstention.

No fitting, threshold search, generation output selection, or reward promotion.
Private references and source quotations never appear in the public aggregate.
"""
import argparse,csv,hashlib,json,math,os,time
from collections import Counter,defaultdict
from pathlib import Path
from urllib.parse import urlsplit,parse_qs

PROTOCOL='pmrl1-j-fixed-semantic64-cpu-v1'
THRESHOLD=.8
OPPOSITE_MAX=.1


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def obj(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def jl(path):return [json.loads(x) for x in Path(path).read_text().splitlines()]
def write(path,value,lines=False):
    with Path(path).open('x') as f:
        if lines:
            for row in value:f.write(json.dumps(row,sort_keys=True,ensure_ascii=False)+'\n')
        else:json.dump(value,f,sort_keys=True,ensure_ascii=False,indent=2);f.write('\n')


def wilson(k,n):
    if n==0:return None
    z=1.959963984540054;p=k/n;d=1+z*z/n
    center=(p+z*z/(2*n))/d;radius=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return [max(0,center-radius),min(1,center+radius)]


def decision(probabilities):
    contradiction,entailment,neutral=probabilities
    if entailment>=THRESHOLD and contradiction<=OPPOSITE_MAX:return 'pass'
    if contradiction>=THRESHOLD and entailment<=OPPOSITE_MAX:return 'fail'
    return 'unknown'


def metrics(rows):
    n=len(rows);negative=sum(r['reference']=='fail' for r in rows);positive=sum(r['reference']=='pass' for r in rows)
    ambiguous=sum(r['reference']=='unknown' for r in rows)
    fp=sum(r['reference']=='fail' and r['prediction']=='pass' for r in rows)
    fn=sum(r['reference']=='pass' and r['prediction']=='fail' for r in rows)
    abstain=sum(r['prediction']=='unknown' for r in rows)
    def rate(k,d):return dict(count=k,denominator=d,rate=k/d if d else None,wilson95=wilson(k,d))
    return dict(items=n,false_pass=rate(fp,negative),false_fail=rate(fn,positive),abstention=rate(abstain,n),
        ambiguous_reference=ambiguous,pass_on_ambiguous=rate(sum(r['reference']=='unknown' and r['prediction']=='pass' for r in rows),ambiguous),
        fail_on_ambiguous=rate(sum(r['reference']=='unknown' and r['prediction']=='fail' for r in rows),ambiguous),
        capacity_abstentions=sum(r.get('technical_status')=='capacity_not_scored' for r in rows))


def video(url):
    p=urlsplit(url);key=parse_qs(p.query).get('v',[None])[0]
    if key:return 'youtube.com/watch?v='+key
    return p.netloc.removeprefix('www.')+p.path.rstrip('/')


def owner_group(owner):return 'evoemo-owner-family:'+('p13+p18' if owner in ('p13','p18') else owner)


def freeze(*,annomi,raw_memory,bank,historical,reference_design,nli_config,snapshot,out):
    annomi,raw_memory,bank,historical,reference_design,nli_config,snapshot,out=map(Path,
        (annomi,raw_memory,bank,historical,reference_design,nli_config,snapshot,out))
    out.mkdir(parents=True,exist_ok=False)
    design=json.loads(reference_design.read_text());sources={str(p):sha(p) for p in (annomi,raw_memory,bank,reference_design,nli_config)}
    items=[];refs=[]
    def add(stratum,key,premise,hypothesis,reference,group,provenance,evidence,factor):
        iid=obj([PROTOCOL,stratum,key])[:24]
        items.append(dict(item_id=iid,stratum=stratum,factor=factor,premise=premise,hypothesis=hypothesis,source_group=group))
        refs.append(dict(item_id=iid,reference=reference,provenance=provenance,evidence=evidence))
    records=list(csv.DictReader(annomi.open()));units=defaultdict(list)
    for row in records:units[(video(row['video_url']),row['transcript_id'],row['utterance_id'])].append(row)
    eligible=defaultdict(lambda:defaultdict(list))
    for key,rows in units.items():
        labels={r['main_therapist_behaviour'] for r in rows};texts={r['utterance_text'] for r in rows}
        if len(labels)!=1 or len(texts)!=1:continue
        label=next(iter(labels));row=rows[0]
        if row['mi_quality']=='high' and row['interlocutor']=='therapist' and label in ('reflection','question'):
            eligible[key[0]][label].append((key,row,rows))
    chosen=sorted((v for v,labels in eligible.items() if labels['reflection'] and labels['question']),key=lambda v:obj([PROTOCOL,v]))[:12]
    assert len(chosen)==12
    for v in chosen:
        for label in ('reflection','question'):
            key,row,rows=min(eligible[v][label],key=lambda x:obj([PROTOCOL,x[0]]))
            prior=[(k,rr[0]) for k,rr in units.items() if k[0]==v and k[1]==key[1] and int(k[2])<int(key[2]) and rr[0]['interlocutor']=='client']
            context=max(prior,key=lambda x:int(x[0][2]))[1]['utterance_text'] if prior else '[No earlier client utterance in this transcript.]'
            premise='Latest available client utterance: '+context+'\nTherapist utterance: '+row['utterance_text']
            add('official_behavior',key,premise,'The therapist primarily reflects what the client has said.',
                'pass' if label=='reflection' else 'fail','annomi-video:'+v,'official_AnnoMI_human_main_behavior_annotation',
                dict(source_file_sha256=sha(annomi),transcript_id=key[1],utterance_id=key[2],label=label,
                    annotator_ids=sorted({r['annotator_id'] for r in rows}),
                    qualification='Behavior recognition only; no applicability or support-quality reference.'),'behavior')
    raw=json.loads(raw_memory.read_text());sessions={(u['id'],s['id']):s for u in raw for s in u['dialog_history']}
    for control in design['controls']:
        source=sessions[(control['owner'],control['session'])]
        turn=next(t for t in source['dialogue'] if t['idx']==control['original_idx'])
        assert turn['role']==control['speaker'] and sha(raw_memory)==design['raw_memory_sha256']
        premise=f"Report date (not event date): {source['timestamp']}.\nQuoted speaker: {turn['role']}.\nExact statement: {turn['content']}"
        for variant in control['variants']:
            add('mechanical_minimal',[control['case_id'],variant['name']],premise,variant['hypothesis'],variant['reference'],
                owner_group(control['owner']),'source_exact_minimal_contrast_not_independent_human_reference',
                dict(source_file_sha256=sha(raw_memory),owner=control['owner'],session=control['session'],
                    original_idx=control['original_idx'],quote=turn['content'],reported_date=source['timestamp'],
                    proof=variant['proof'],authorship='Explicit source clause/role/date and declared logical minimal transformation; authored development diagnostic.'),control['factor'])
    historical_bank=json.loads(bank.read_text());singles={r['record_id']:r for r in historical_bank['singles']}
    for recipe in design['historical_atoms']:
        record=singles[recipe['record_id']];path=historical/'sources'/(record['old_item_key']+'.json')
        sources[str(path)]=sha(path);source=json.loads(path.read_text())
        lookup={t['id']:t for t in source['current_prefix']}
        for past in source['legal_past_sessions']:lookup.update({t['id']:t for t in past['turns']})
        selected=[lookup[x] for x in recipe['source_turn_ids']]
        premise='Local historical source excerpt; omitted context is not asserted.\n'+'\n'.join(t['id']+' '+t['role']+': '+t['text'] for t in selected)
        if recipe['record_id']=='P01':assert record['raw_label']['claims'][0]['relation']=='supported'
        if recipe['record_id']=='P04':assert any(r['record_id']=='P04' and '默认已经发生' in r['raw_label']['verbatim'] for r in historical_bank['supplements'])
        add('historical_human_atom',recipe['record_id'],premise,recipe['hypothesis'],recipe['reference'],
            owner_group(recipe['owner']),'historical_single_human_atomic_or_explicit_unknown_not_overall_quality',
            dict(bank_sha256=sha(bank),record_id=recipe['record_id'],evidence_identity=record['evidence_identity'],
                original_human_label=record['raw_label'],source_path=str(path),source_turn_ids=recipe['source_turn_ids'],
                reference_basis=recipe['reference_basis'],overall_quality_score_not_used=True),recipe['factor'])
    assert len(items)==len({x['item_id'] for x in items})==64
    assert dict(Counter(x['stratum'] for x in items))=={'official_behavior':24,'mechanical_minimal':32,'historical_human_atom':8}
    assert dict(Counter(r['reference'] for r in refs))=={'pass':21,'fail':29,'unknown':14}
    spec=json.loads(nli_config.read_text())['nli_candidate'];assert spec['revision']==snapshot.name and spec['max_length']==512
    from transformers import AutoTokenizer
    tok=AutoTokenizer.from_pretrained(snapshot,local_files_only=True,trust_remote_code=False)
    lengths=[]
    for row in items:
        p,h=(' '.join(row[k].split()) for k in ('premise','hypothesis'))
        ids=tok(p,h,truncation=False)['input_ids']
        lengths.append(dict(item_id=row['item_id'],native_pair_tokens=len(ids),input_ids_sha256=obj(ids),eligible_no_truncation=len(ids)<=512))
    write(out/'INPUTS_PRIVATE.jsonl',items,True);write(out/'REFERENCES_PRIVATE.jsonl',refs,True);write(out/'TOKEN_LENGTHS_PRIVATE.jsonl',lengths,True)
    protocol=dict(protocol=PROTOCOL,nli_spec=spec,snapshot_path=str(snapshot.resolve()),
        inference=dict(device='cpu',dtype='float32',batch_size=4,cpu_threads=4,one_load=True,one_candidate=True,
            entailment_threshold=THRESHOLD,contradiction_threshold=THRESHOLD,opposite_max=OPPOSITE_MAX,
            neutral='unknown',capacity='unknown_without_forward; never truncate',prediction_attempts=1,no_threshold_retuning=True),
        inputs_sha256=sources,source_files_unchanged=True,
        files_sha256={n:sha(out/n) for n in ('INPUTS_PRIVATE.jsonl','REFERENCES_PRIVATE.jsonl','TOKEN_LENGTHS_PRIVATE.jsonl')},
        counts=dict(items=64,by_stratum=dict(Counter(x['stratum'] for x in items)),reference_counts=dict(Counter(r['reference'] for r in refs)),
            eligible=sum(x['eligible_no_truncation'] for x in lengths),capacity=sum(not x['eligible_no_truncation'] for x in lengths)),
        selection='Fixed source metadata/hash order and declared reference design before model probabilities; no current M1/R1/W1 outputs read.',
        intervals='Wilson95 descriptive binomial intervals per stratum and source group; correlated repeated-source items are not independent samples.',
        exclusions='No reward qualification, behavior applicability or natural support-quality claim.',code_sha256=sha(__file__))
    write(out/'PROTOCOL_FROZEN.json',protocol)
    return dict(protocol_sha256=sha(out/'PROTOCOL_FROZEN.json'),**protocol['counts'],model_forward_calls=0)


def predict(frozen,out):
    frozen,out=Path(frozen),Path(out);out.mkdir(parents=True,exist_ok=False)
    protocol=json.loads((frozen/'PROTOCOL_FROZEN.json').read_text())
    assert protocol['protocol']==PROTOCOL and protocol['code_sha256']==sha(__file__)
    for name,h in protocol['files_sha256'].items():assert sha(frozen/name)==h
    for name,h in protocol['inputs_sha256'].items():assert sha(name)==h
    assert os.environ.get('CUDA_VISIBLE_DEVICES')=='' and os.environ.get('HF_HUB_OFFLINE')=='1'
    items=jl(frozen/'INPUTS_PRIVATE.jsonl');lengths={x['item_id']:x for x in jl(frozen/'TOKEN_LENGTHS_PRIVATE.jsonl')}
    write(out/'RUN_ONCE.json',dict(protocol_sha256=sha(frozen/'PROTOCOL_FROZEN.json'),device='cpu',candidate_count=1,thresholds=[THRESHOLD,OPPOSITE_MAX]))
    import torch
    from metacom_pm.v1_5_support_need_bakeoff import FrozenSupportNeedNLIScorer,FrozenSupportNeedNLISpec
    import metacom_pm.v1_5_support_need_bakeoff as legacy
    torch.set_num_threads(4);torch.set_num_interop_threads(1)
    started=time.perf_counter()
    scorer=FrozenSupportNeedNLIScorer.load(FrozenSupportNeedNLISpec.model_validate(protocol['nli_spec']),device='cpu',batch_size=4)
    assert str(next(scorer.model.parameters()).device)=='cpu'
    load_seconds=time.perf_counter()-started;forward=0;prediction=[]
    eligible=[x for x in items if lengths[x['item_id']]['eligible_no_truncation']]
    with (out/'PREDICTIONS_BEFORE_REFERENCE_JOIN_PRIVATE.jsonl').open('x') as f:
        for start in range(0,len(eligible),4):
            batch=eligible[start:start+4];matrix=scorer.score([x['premise'] for x in batch],[x['hypothesis'] for x in batch]);forward+=len(batch)
            for row,probs in zip(batch,matrix):
                pred=dict(item_id=row['item_id'],prediction=decision(probs),probabilities=probs.tolist(),technical_status='CPU_scored')
                f.write(json.dumps(pred,sort_keys=True)+'\n');f.flush();prediction.append(pred)
        for row in items:
            if not lengths[row['item_id']]['eligible_no_truncation']:
                pred=dict(item_id=row['item_id'],prediction='unknown',probabilities=None,technical_status='capacity_not_scored')
                f.write(json.dumps(pred,sort_keys=True)+'\n');prediction.append(pred)
    # Only after immutable prediction output exists, load reference verdicts.
    reference={x['item_id']:x for x in jl(frozen/'REFERENCES_PRIVATE.jsonl')};inputs={x['item_id']:x for x in items}
    joined=[dict(**p,reference=reference[p['item_id']]['reference'],stratum=inputs[p['item_id']]['stratum'],
        factor=inputs[p['item_id']]['factor'],source_group=inputs[p['item_id']]['source_group']) for p in prediction]
    write(out/'JOINED_RESULTS_PRIVATE.jsonl',joined,True)
    grouped=defaultdict(list)
    for r in joined:grouped[(r['stratum'],r['source_group'])].append(r)
    private_groups=[dict(stratum=s,source_group=g,**metrics(rows)) for (s,g),rows in sorted(grouped.items())]
    write(out/'SOURCE_GROUP_RESULTS_PRIVATE.json',private_groups)
    report=dict(protocol=PROTOCOL,items=len(joined),CPU_scored=forward,capacity_abstentions=len(items)-forward,
        model_loads=1,new_Generative_calls=0,new_training=0,GPU_used=False,load_seconds=load_seconds,
        total_wall_seconds=time.perf_counter()-started,thresholds=dict(entailment=THRESHOLD,contradiction=THRESHOLD,opposite_max=OPPOSITE_MAX),
        stratum_metrics=[dict(stratum=s,**metrics([r for r in joined if r['stratum']==s])) for s in sorted({r['stratum'] for r in joined})],
        source_group_metrics=[dict(stratum=g['stratum'],source_group_hash=obj(g['source_group'])[:16],
            **{k:v for k,v in g.items() if k not in ('stratum','source_group')}) for g in private_groups],
        factor_metrics=[dict(factor=k,**metrics([r for r in joined if r['stratum']=='mechanical_minimal' and r['factor']==k])) for k in sorted({r['factor'] for r in joined if r['stratum']=='mechanical_minimal'})],
        provenance=['24 original AnnoMI human main-behavior annotations, no applicability or quality labels.',
            '32 source-grounded authored minimal contrasts: explicit clause/role/report-date transformations, not independent human judgments.',
            '8 historical single-human atomic/uncertain references, not overall quality converted into NLI; local windows disclosed.'],
        limitations=['Fixed exposed development diagnostic; no reward qualification or autonomous semantic evaluator approval.',
            'NLI contradiction is narrower than unsupportedness; unknown/neutral and known-negative abstentions remain explicit.',
            'Wilson intervals are descriptive within correlated source groups; no 64-independent-observations claim.',
            'No threshold/window/candidate retuning or outcome-based replacement after prediction.'],
        bindings=dict(protocol_sha256=sha(frozen/'PROTOCOL_FROZEN.json'),prediction_sha256=sha(out/'PREDICTIONS_BEFORE_REFERENCE_JOIN_PRIVATE.jsonl'),
            scorer_binding=scorer.binding.model_dump(mode='json'),legacy_scorer_code_sha256=sha(legacy.__file__),implementation_sha256=sha(__file__)),
        reward_qualified=False)
    write(out/'PUBLIC_AGGREGATE.json',report)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
    f=sub.add_parser('freeze')
    for name in ('annomi','raw-memory','bank','historical','reference-design','nli-config','snapshot','out'):f.add_argument('--'+name,required=True)
    s=sub.add_parser('predict');s.add_argument('--frozen',required=True);s.add_argument('--out',required=True)
    args=vars(p.parse_args());command=args.pop('command')
    print(json.dumps((freeze if command=='freeze' else predict)(**args),indent=2,ensure_ascii=False))
