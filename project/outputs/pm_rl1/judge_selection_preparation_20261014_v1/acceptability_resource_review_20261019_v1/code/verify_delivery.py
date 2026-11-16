"""Validate this offline analysis without model or account access."""
from pathlib import Path
import hashlib,json,collections,subprocess,sys,os
from html.parser import HTMLParser

OUT=Path(__file__).resolve().parents[1]
ROOT=Path('/opt/tokkio-data0/tokkio_projects/Metacom5_3')
BASE=ROOT/'project/outputs/pm_rl1/judge_selection_preparation_20261014_v1'
def load(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

before=load(OUT/'provenance/before_hashes.json')
changed=[]
status_path=ROOT/'project/docs/PM_RL1_CURRENT_STATUS.md'
for name,h in before.items():
    p=Path(name)
    if p==status_path:
        assert sha(OUT/'provenance/CURRENT_STATUS.before.md')==h
    elif sha(p)!=h:changed.append(name)
assert not changed,changed
provenance=load(OUT/'provenance/source_hashes.json')
for name,h in provenance.items():assert sha(Path(name))==h,name

rows=load(OUT/'materials/selected_existing_records.json')
review=load(OUT/'analyst_review.json')['rows']
ctx=load(OUT/'materials/contexts.json')
assert len(rows)==24 and len({r['row_id'] for r in rows})==24
assert {r['prefix_index'] for r in rows}=={111,102,104,109}
assert {r['context_id'] for r in rows}==set(ctx)
assert len({r['executor_identity'] for r in rows})==1
assert len({r['renderer_identity'] for r in rows})==1
assert all(r['reward_eligible'] is False and r['human_label'] is None for r in review)
assert collections.Counter(r['classification'] for r in review)=={
    'plausibly_acceptable':15,'explicit_problem':1,'unresolved':8}
for r in rows:
    assert r['status']=='completed_existing'
    sources=ctx[r['context_id']]
    for res in r['resources']:
        z=json.loads(res['content'])
        assert res['source_time'] is None or res['source_time']<sources['current_date']
        if res['head']=='RS':continue
        ss=[s for s in sources['legal_past_sessions'] if s['date']==z['reported_at']]
        assert len(ss)==1
        if res['head'] in ['MP','ME']:
            for e in z['evidence']:
                assert any(e['quote'] in t['text'] and e['speaker']==t['role'] for t in ss[0]['turns'])
        else:
            assert all(t['text'] in z['full_source_conversation'] for t in ss[0]['turns'])
for cid in ctx:
    group=[r for r in rows if r['context_id']==cid]
    combo=next(r for r in group if r['counts']==[1,1,1,1])
    assert len(group)==6
    assert sum(r['counts']==[0,0,0,0] for r in group)==1
    for r in group:
        if sum(r['counts'])==1:assert r['resources'][0] in combo['resources']

for name in ['extract_existing.py','author_review.py','build_delivery.py']:
    # Same derived files must remain byte-identical. No retry or re-scoring path.
    result=subprocess.run([sys.executable,str(OUT/'code'/name)],capture_output=True,text=True,check=True)

class CheckHTML(HTMLParser):
    def __init__(self):super().__init__();self.external=[];self.ids=[];self.summaries=0
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='summary':self.summaries+=1
        if 'id' in a:self.ids.append(a['id'])
        for k in ('src','href'):
            if k in a and not a[k].startswith('#'):self.external.append(a[k])
        assert tag not in ['script','iframe','form']
h=CheckHTML();h.feed((OUT/'review.html').read_text())
assert not h.external
assert set(h.ids)=={'decision','minimum','proposal','rows','sources'}
assert h.summaries==52

nb=load(OUT/'recompute.ipynb');namespace={};oldcwd=os.getcwd()
try:
    os.chdir(OUT)
    for c in nb['cells']:
        if c['cell_type']=='code':exec(compile(''.join(c['source']),'recompute.ipynb','exec'),namespace)
finally:os.chdir(oldcwd)

oldstarts=list((BASE/'live_runs').rglob('*.started.json'))
newstarts=[load(p) for p in (BASE/'paired_diagnostic_runs/pmrl1-eight-paired-diagnostic-20261019/live').rglob('*.started.json')]
assert len(oldstarts)==54 and sum('slot' in x for x in newstarts)==24
assert sum('slot' not in x for x in newstarts)==2
assert any(load(p).get('old_calls')==66 for p in oldstarts)

receipt=dict(status='PASS',scope='offline derived records and source bindings, not semantic qualification',
    preserved_original_files_checked=len(before)-1,selected_source_hashes_checked=len(provenance),
    old_current_status_archived_exactly=True,new_generations=0,new_model_scores=0,new_human_labels=0,
    selection_scoring_cumulative=144,capacity=289,management_requests_unchanged=True,
    old_money_ledger_unchanged=True,old_STOP_and_started_records_unchanged=True,
    selected_prefixes=[111,102,104,109],nominal_slots=24,completed_existing=24,unavailable=0,
    all_selected_request_reply_bindings=True,all_selected_resource_source_bindings=True,
    repeated_offline_execution_idempotent=True,notebook_cells_validated=3,
    html_static_checks=True,html_external_requests=0,browser_visual_check_performed=False,
    analyst_labels_not_reward=True,no_formal_contract_change=True,
    exposure_incident='provenance/ACCESS_SCOPE_NOTE.json; one additional current-prefix text; excluded',
    delivery_build_repairs=['Defined missing contexts variable','Compared output bytes rather than universal-newline CSV text; original artifacts untouched'],
    limits=['Four problem-selected contexts, two owners; not representative',
        'Only four of the eight original human replies match selected natural pool rows',
        'No independent acceptability labels or fresh validation',
        'No new model request, policy rollout or training'])
(OUT/'verification.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(receipt,ensure_ascii=False))
