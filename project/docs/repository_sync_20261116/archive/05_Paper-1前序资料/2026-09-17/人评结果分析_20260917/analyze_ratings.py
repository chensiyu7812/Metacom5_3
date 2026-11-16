"""Read-only intake and descriptive audit; no formal labels, no qualification decision."""
from pathlib import Path
from collections import Counter, defaultdict
import json, re, sys, hashlib, csv, shutil

ROOT = Path('/opt/tokkio-data0/tokkio_projects/Metacom5_3')
OUT = Path(__file__).resolve().parent
AUTH = ROOT / 'project/data/paper1_authority'
sys.path.insert(0, str(ROOT / 'project/src'))
from metacom_pm.paper1.evaluation.human_reference import validate_rated_sheet

def unique(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError(f'duplicate JSON key: {key}')
        obj[key] = value
    return obj

def loads(s): return json.loads(s, object_pairs_hook=unique)
def read(p): return loads(p.read_text(encoding='utf-8'))
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def save(name, obj): (OUT/name).write_text(json.dumps(obj, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
def jsonl(name): return [loads(s) for s in (AUTH/name).read_text().splitlines() if s.strip()]

def run():
    a_path = Path('/home/tokkio/paper1_pairwise_teacher_rater_a_sheet_v2_zh_v1_rated.json')
    b_path = Path('/home/tokkio/AI_B_中文评审结果.html')
    A = read(a_path)
    scripts = re.findall(r'<script\b[^>]*\bid="form-data"[^>]*>(.*?)</script>', b_path.read_text(), re.S)
    assert len(scripts) == 1
    payload = loads(scripts[0]); B = payload['sheet']
    snapshots = OUT / 'originals'; snapshots.mkdir(exist_ok=True)
    for p in (a_path, b_path):
        q = snapshots / p.name
        if q.exists(): assert sha(p) == sha(q), 'Do not overwrite earlier intake'
        else: shutil.copy2(p, q)
    originals = {}; checks = {}
    for r, sheet in [('A', A), ('B', B)]:
        p = ROOT / f'project/outputs/paper1_pairwise_teacher/human_sheets_v2/RATER_{r}/paper1_pairwise_teacher_rater_{r.lower()}_sheet_v2.json'
        originals[r] = {'path': str(p), 'sha256': sha(p)}
        try: checks[r] = {'valid': True, **validate_rated_sheet(read(p), sheet)}
        except ValueError as exc: checks[r] = {'valid': False, 'error': str(exc)}
    assert all(x['valid'] for x in checks.values()), checks
    save('exploratory_AI_B_extracted_sheet.json', B)
    plan = {x['presentation_id']:x for x in jsonl('paper1_pairwise_teacher_presentation_plan_20260904_v1.jsonl')}
    blind = {x['presentation_id']:x for x in jsonl('paper1_pairwise_teacher_blind_key_20260904_v1.jsonl')}
    bases = {x['base_pair_id']:x for x in jsonl('paper1_pairwise_teacher_base_pair_preflight_20260904_v1.jsonl')}
    generation = read(AUTH/'paper1_pairwise_teacher_local_generation_result_20260904_v1.json')
    response_map = {x['base_pair_id']:x for x in generation['base_pair_response_map']}
    cache = {p.stem:read(p) for p in (ROOT/'project'/generation['private_success_cache']['path']).glob('*.json')}
    ai = {x['presentation_id']:x for x in B['items']}
    human = {x['presentation_id']:x for x in A['items']}
    assert len(ai)==len(human)==len(A['items'])==len(B['items'])==96
    assert set(human)==set(ai)==set(plan)==set(blind)
    rows=[]
    for item in A['items']:
        pid=item['presentation_id']; other=ai[pid]; key=blind[pid]; base=bases[key['base_pair_id']]
        for field in ('task','task_input','reference_material','response_A','response_B'):
            assert item[field]==other[field], (pid,field)
        row={
            'presentation_id':pid, 'base_pair_id':key['base_pair_id'], 'reverse_duplicate':key['reverse_duplicate'],
            'human_item_number':item['item_number'], 'ai_item_number':other['item_number'],
            'task':item['task'], 'head':base['head'], 'target_id':base['target_id'],
            'owner_or_dialogue_group':base['owner_or_dialogue_group'],
            'human_verdict':item['verdict'], 'ai_verdict':other['verdict'],
            'human_rationale':item['rationale'], 'ai_rationale':other['rationale'],
            'agreement':item['verdict']==other['verdict'],
            'responses_identical':item['response_A']==item['response_B'],
        }
        for display in ('A','B'):
            arm=key[f'{display}_arm']; req=response_map[key['base_pair_id']][arm]['request_id']; result=cache[req]
            assert result['accepted_text']==item[f'response_{display}']
            row[f'{display}_arm']=arm
            row[f'{display}_finish_reason']=result['finish_reason']
            row[f'{display}_completion_tokens']=result['usage']['completion_tokens']
            row[f'{display}_prefix_applied']=result['complete_sentence_prefix_applied']
        row['any_length']=any(row[f'{d}_finish_reason']=='length' for d in ('A','B'))
        row['human_mentions_truncation']=bool(re.search('截断|截取|没写完|未完成|不完整|不全|截尾|结尾|没说完|断了',item['rationale']))
        row['human_mentions_preference']=bool(re.search('偏好|喜欢|风格|具体看|根据用户|因人|啰嗦|太长|简洁|冗长',item['rationale']))
        rows.append(row)
    save('aligned_ratings.json',rows)
    with (OUT/'逐题对照.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    canonical=[x for x in rows if not x['reverse_duplicate']]
    assert len(canonical)==80
    grouped=defaultdict(list)
    for r in rows: grouped[r['base_pair_id']].append(r)
    flips={'A_better':'B_better','B_better':'A_better','equivalent':'equivalent','uncertain':'uncertain'}
    reverse=[]
    for bid,pair in grouped.items():
        if len(pair)==1: continue
        assert len(pair)==2
        orig=next(x for x in pair if not x['reverse_duplicate']);rev=next(x for x in pair if x['reverse_duplicate'])
        assert human[orig['presentation_id']]['response_A']==human[rev['presentation_id']]['response_B']
        assert human[orig['presentation_id']]['response_B']==human[rev['presentation_id']]['response_A']
        reverse.append({'base_pair_id':bid,'task':orig['task'],'original_pid':orig['presentation_id'],'reverse_pid':rev['presentation_id'],
            **{f'{r}_consistent':orig[f'{r}_verdict']==flips[rev[f'{r}_verdict']] for r in ('human','ai')},
            **{f'{r}_{which}':x[f'{r}_verdict'] for r in ('human','ai') for which,x in [('original',orig),('reverse',rev)]},
            'human_items':[orig['human_item_number'],rev['human_item_number']], 'ai_items':[orig['ai_item_number'],rev['ai_item_number']]})
    assert len(reverse)==16
    save('reverse_consistency.json',reverse)
    labels=['A_better','B_better','equivalent','uncertain']
    def aggregate(rr):
        confusion={a:{b:0 for b in labels} for a in labels}
        for r in rr:confusion[r['human_verdict']][r['ai_verdict']]+=1
        return {'n':len(rr), 'agreement':sum(r['agreement'] for r in rr),
                'human_counts':dict(Counter(r['human_verdict'] for r in rr)),
                'ai_counts':dict(Counter(r['ai_verdict'] for r in rr)),
                'confusion_human_rows_ai_columns':confusion,
                'any_length':sum(r['any_length'] for r in rr),
                'human_truncation_keyword_hits':sum(r['human_mentions_truncation'] for r in rr),
                'human_preference_keyword_hits':sum(r['human_mentions_preference'] for r in rr)}
    summary={'intake_date':'2026-09-17','provenance':{'human_A':'one joint human panel record; independence not established',
          'AI_B':'exploratory ChatGPT ratings; model/version/input history not supplied; not human rater B',
          'AI_metadata_from_HTML':payload['ai_review_metadata'],
          'A_source':{'path':str(a_path),'sha256':sha(a_path)},'B_source':{'path':str(b_path),'sha256':sha(b_path)},
          'canonical_blanks':originals},'validation':checks,
          'presentations_96':aggregate(rows),'canonical_base_pairs_80':aggregate(canonical),
          'by_task_80':{t:aggregate([r for r in canonical if r['task']==t]) for t in ['ESC','QA','Summary','DG']},
          'reversal':{'n':16,**{r:sum(x[f'{r}_consistent'] for x in reverse) for r in ('human','ai')}},
          'generation_unique':{'n':len(cache),'length':sum(v['finish_reason']=='length' for v in cache.values()),
           'by_task_arm':{f'{t}_{arm}':{'n':len(vv:= [v for v in cache.values() if v['task']==t and v['arm']==arm]),'length':sum(v['finish_reason']=='length' for v in vv)} for t in ['ESC','QA','Summary','DG'] for arm in ['OFF','ON']}},
          'length_sensitivity_80':{str(v):aggregate([r for r in canonical if r['any_length']==v]) for v in [False,True]},
          'not_created':['formal effect labels','human-human reliability','qualified teacher','research protocol amendment'],
          'scope':'Descriptive diagnostics only; repeated presentations and shared DG scenarios are not independent observations.'}
    save('summary.json',summary)
    rationales=[]
    for r in rows:
        rationales.append(f"A{r['human_item_number']:02d} / AI-B{r['ai_item_number']:02d} {r['task']} {'反序' if r['reverse_duplicate'] else '原序'} [{r['human_verdict']} | {r['ai_verdict']}] length={r['any_length']}\n人：{r['human_rationale']}\nAI：{r['ai_rationale']}\n")
    (OUT/'全部理由对照.txt').write_text('\n'.join(rationales),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    return summary,rows

if __name__=='__main__': run()
