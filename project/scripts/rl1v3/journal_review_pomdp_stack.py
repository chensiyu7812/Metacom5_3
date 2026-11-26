#!/usr/bin/env python3
"""Finite read-only stack/trajectory review. No model imports, GPU, API or edits.

Outputs contain code provenance, aggregate counts and synthetic counterexamples,
never source dialogue, task questions, model replies, evaluation text or owner IDs.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib,json,os,subprocess
from pathlib import Path
from types import SimpleNamespace

BASE='c40b90c99cb991cf1c2793ffbe9927a0011885ab'
MODULES=('contracts.py','io.py','sources/source_registry.py','compile/asof.py','bank/bank_v0.py','bank/v0_port.py',
 'retrieve/v0.py','retrieve/native_tokens.py','env/finite_head.py','env/c0_binding.py','evaluate/terminal_registry.py','train/real_instances.py','train/ppo.py',
 'generator/g0e.py','generator/limited_run.py','journal/selective_memory_validation_sources.py','journal/memory_port.py','journal/runtime_binding.py',
 'journal/pomdp_memory.py','journal/temporal_retrieval.py','journal/pomdp_controller_protocol.py','journal/renderer.py','journal/joint_task_port.py',
 'journal/pomdp_dynamic_runtime.py','journal/pomdp_dynamic_worker.py','journal/pomdp_dynamic_run.py','journal/pomdp_dynamic_results.py','journal/outcome_adapter.py')

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def obj(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def rows(p):return [json.loads(x) for x in Path(p).read_text().splitlines()]
def write(p,v):
 with Path(p).open('x') as f:json.dump(v,f,ensure_ascii=False,indent=2,sort_keys=True);f.write('\n')
def command(args,cwd=None):return subprocess.check_output(args,cwd=cwd,text=True).strip()


def environment(python,vendor=None):
 code='''import json,platform,importlib.metadata as m
names=['torch','transformers','tokenizers','safetensors','vllm','numpy','pytest','xgrammar']
out={}
for n in names:
 try:out[n]=m.version(n)
 except m.PackageNotFoundError:out[n]=None
installed=sorted([{'name':d.metadata.get('Name','UNKNOWN'),'version':d.version} for d in m.distributions()],key=lambda d:(d['name'].lower(),d['version']))
print(json.dumps({'python':platform.python_version(),'packages':out,'installed_distributions':installed,'installed_is_not_actual_import_dependency':True}))'''
 env=dict(os.environ,CUDA_VISIBLE_DEVICES='',PYTHONDONTWRITEBYTECODE='1')
 if vendor:env['PYTHONPATH']=str(vendor)
 return json.loads(subprocess.check_output([str(python),'-c',code],env=env,text=True))


def mechanisms():
 from metacom_pm.rl1v3.journal.pomdp_memory import SearchExpandEpisode
 from metacom_pm.rl1v3.io import object_sha256
 class T:
  identity='synthetic-review-tokenizer'
  def count(self,text):return len(text.split())
  def make_packet(self,views=()):
   text='\n'.join(v.reading_text for v in views)
   return SimpleNamespace(input_ids=list(text.encode()),payload_sha256=object_sha256(text))
 task=dict(task_id='synthetic',timestamp='2020-01-03',turns=[dict(role='seeker',text='alpha beta')],query='alpha beta',view_protocol='synthetic')
 records=[dict(record_id='r'+str(i),head='MS',view='raw',reading_text='seeker: '+word,source_rank=i,
  reported_at=dict(date='2020-01-01',session_rank=i),source_refs=[dict(turn_index=0,speaker='seeker',exact_quote=word)]) for i,word in enumerate(('alpha','beta'))]
 def build():return SearchExpandEpisode(task=task,records=records,tokenizer=T(),legal=lambda r:True,episode_nonce='same-synthetic-episode')
 a,b=build(),build()
 for q in ('alpha beta','alpha','beta'):a.step(dict(action='SEARCH',query=q))
 for q in ('alpha beta','beta','alpha'):b.step(dict(action='SEARCH',query=q))
 assert a.state_hash()==b.state_hash() and a.observe()['last_hits']!=b.observe()['last_hits'] and object_sha256(a.observe())!=object_sha256(b.observe())
 c=build();c.step(dict(action='SEARCH',query='alpha beta'));h=c.last_hits[0];c.step(dict(action='EXPAND',handle=h));pre=(c.packet().payload_sha256,c.state_hash(),c.charged_tokens)
 c.step(dict(action='EXPAND',handle=h));post=(c.packet().payload_sha256,c.state_hash(),c.charged_tokens)
 assert pre[0]==post[0] and pre[1]!=post[1] and pre[2]<post[2]
 quote=c.records[c.handles[h]['record_id']]['source_refs'][0]['exact_quote']
 return dict(state_hash_collision=dict(same_state_hash=True,different_last_hits=True,different_observation_hash=True,accesses=3,
   classification='code_confirmed_limit',historical_corruption_claim=False),
  repeated_expand=dict(same_payload=True,different_state_hash=True,positive_duplicate_token_charge=post[2]-pre[2],accesses=c.accesses),
  span_parent_overlap=dict(exact_quote_occurrences=c._views()[0].reading_text.count(quote),content_units=len(c.contents)),model_calls=0)


def trajectory_counts(collection):
 events=rows(collection/'ALL_EVENTS_PRIVATE.jsonl');endpoints=rows(collection/'ALL_48_ENDPOINTS_PRIVATE.jsonl');calls=rows(collection/'ALL_MODEL_CALLS_PRIVATE.jsonl')
 searches=expands=repeat_searches=no_novel_parent_searches=overlap_expands=stale_handles=0
 pathstate={};dates_out_of_order=paths_with_both=0;date_paths=0
 for e in events:
  if e['event']!='TOOL_RETURNED':continue
  key=e['task_id'],e['method'];s=pathstate.setdefault(key,dict(queries=set(),seen=set(),spans={},handles={}))
  action=e['action'];delivered=e['private_transition'].get('delivered',[])
  if action['action']=='SEARCH':
   searches+=1;repeat_searches+=action['query'] in s['queries'];s['queries'].add(action['query'])
   new={r['record_id'] for r in delivered};no_novel_parent_searches+=bool(new) and new<=s['seen'];s['seen']|=new
   for row in delivered:
    rid=row['record_id'];quote=row['span']['exact_quote'];s['spans'].setdefault(rid,set()).add(quote)
    if rid in s['handles'] and s['handles'][rid]!=row['text']:stale_handles+=1
    s['handles'].setdefault(rid,row['text'])
  elif action['action']=='EXPAND':
   expands+=1
   overlap_expands+=any(any(q in r['text'] for q in s['spans'].get(r['record_id'],())) for r in delivered)
 for ep in endpoints:
  receipt=ep.get('source_receipt') or {};items={}
  for tr in receipt.get('trace',[]):
   for r in tr.get('delivered',[]):
    key=obj([r['record_id'],'complete_parent']) if r['scope']=='MS-RAW-complete-parent' else obj([r['record_id'],r['span']['turn_index'],r['text']])
    items[key]=r
  if items:
   dates=[r['reported_at']['date'] for _,r in sorted(items.items())];date_paths+=1;dates_out_of_order+=dates!=sorted(dates)
   parents={r['record_id'] for r in items.values() if r['scope']=='MS-RAW-complete-parent'}
   spans={r['record_id'] for r in items.values() if r['scope']=='RAW-SPAN'}
   paths_with_both+=bool(parents & spans)
 duplicate_obs=0;duplicate_chars=0;all_resource_chars=0;control_with_resources=0
 for c in calls:
  if c['role']=='terminal':continue
  o=json.loads(c['request']['payload']['messages'][1]['content']);texts=[]
  for hit in o['hits']:
   texts.extend(hit[k] for k in ('reading_text','expanded_text') if hit.get(k))
  texts.extend(r['reading_text'] for r in o.get('readings',[]))
  if texts:
   control_with_resources+=1;duplicate_obs+=len(texts)!=len(set(texts));all_resource_chars+=sum(map(len,texts));duplicate_chars+=sum(map(len,texts))-sum(map(len,set(texts)))
 return dict(source_scope='all verified DR1-DR4 immutable observed trajectories; no quality labels read',
  collection_manifest_sha256=sha(collection/'COLLECTION_MANIFEST_PRIVATE.json'),physical_calls=len(calls),terminal_slots=len(endpoints),
  successful_searches=searches,successful_expands=expands,repeated_exact_query_searches=repeat_searches,
  searches_with_no_new_parent=no_novel_parent_searches,expand_events_repeating_previously_delivered_span=overlap_expands,
  reselected_parent_new_span_but_retained_first_hit_text=stale_handles,
  observed_terminal_paths_with_span_and_its_parent=paths_with_both,terminal_paths_with_content_for_date_order=date_paths,
  hash_sorted_terminal_paths_with_nonmonotone_report_dates=dates_out_of_order,
  controller_calls_with_resource_text=control_with_resources,controller_observations_with_exact_duplicate_resource_fields=duplicate_obs,
  controller_resource_field_chars=all_resource_chars,exact_duplicate_resource_field_chars=duplicate_chars,
  character_counts_not_native_tokens=True,semantic_effect_of_duplicates='unmeasured')


def run(repo,stack_manifest,plan_path,collection,out):
 repo,stack_manifest,plan_path,collection,out=map(Path,(repo,stack_manifest,plan_path,collection,out))
 if out.exists():raise FileExistsError(out)
 assert command(['git','rev-parse','HEAD'],repo)==BASE
 plan=read(plan_path);baseline=read(plan['baseline_path']);dep=read(stack_manifest);stack=stack_manifest.parent
 provenance={r['path']:r for r in dep['files']};stack_bad=[]
 for r in dep['files']:
  p=stack/r['path']
  if not p.is_file() or sha(p)!=r['sha256']:stack_bad.append(r['path'])
 modules=[]
 for name in MODULES:
  rel='project/src/metacom_pm/rl1v3/'+name;p=stack/rel
  r=provenance.get(rel)
  modules.append(dict(path=rel,resolved_path=str(p.resolve()),sha256=sha(p),origin='journal-'+BASE if r is None else r['stream'],
   source_commit=BASE if r is None else r['revision'],frozen_executor_sha256=plan['executor_files_sha256'].get(rel),
   matches_frozen_executor=sha(p)==plan['executor_files_sha256'].get(rel)))
 executor=Path(plan['executor_root']);bad_executor=[];current_differences=[];missing_current=[]
 for rel,expected in plan['executor_files_sha256'].items():
  p=executor/rel
  if not p.is_file() or sha(p)!=expected:bad_executor.append(rel)
  current=repo/rel if (repo/rel).is_file() else stack/rel
  if not current.is_file():missing_current.append(rel)
  elif sha(current)!=expected:current_differences.append(dict(path=rel,current_sha256=sha(current),frozen_sha256=expected))
 all_current_journal={str(p.relative_to(repo)):sha(p) for p in (repo/'project/src/metacom_pm/rl1v3/journal').glob('*.py')}
 baseline_paths=set(command(['git','ls-tree','-r','--name-only',BASE,'project/src/metacom_pm/rl1v3/journal'],repo).splitlines())
 new_journal={p:s for p,s in all_current_journal.items() if p in baseline_paths and p not in plan['executor_files_sha256']}
 untracked_journal=sorted(p for p in all_current_journal if p not in baseline_paths)
 small_model={}
 for name,expected in baseline['spec']['model']['files'].items():
  p=Path(plan['model_path'])/name
  small_model[name]=dict(expected_sha256=expected['sha256'],bytes=p.stat().st_size,expected_bytes=expected['bytes'],
   actual_sha256=None if name.endswith('.safetensors') else sha(p),
   check_scope='size only here; immutable DR MODEL_BYTES_VERIFIED events attest prior fresh full SHA before each load' if name.endswith('.safetensors') else 'fresh small-file SHA')
 py311=Path('/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python')
 env=dict(generator=environment(plan['python'],plan['vendor_path']),cpu_tests=environment(py311),
  generator_expected=baseline['spec']['runtime'],grammar_vendor_inventory_sha256=obj(plan['vendor_files_sha256']),
  grammar_vendor_files=len(plan['vendor_files_sha256']),grammar_vendor_files_match=all(sha(Path(plan['vendor_path'])/r)==h for r,h in plan['vendor_files_sha256'].items()))
 source_rel='project/src/metacom_pm/rl1v3/sources/source_registry.py'
 equivalent={}
 for name,revision in [('base',dep['base']),('A',dep['dependencies']['A'])]:
  blob=subprocess.check_output(['git','show',revision+':'+source_rel],cwd=repo)
  equivalent[name]=dict(commit=revision,sha256=hashlib.sha256(blob).hexdigest())
 equivalent['same_bytes']=equivalent['base']['sha256']==equivalent['A']['sha256']==sha(stack/source_rel)
 closure=dict(protocol='pmrl1-j-complete-code-dependency-closure-v1',journal_baseline=BASE,
  stack_files=[{k:r[k] for k in ('path','stream','revision','sha256','bytes')} for r in dep['files']],
  frozen_DR_executor_files=[dict(path=p,sha256=h) for p,h in sorted(plan['executor_files_sha256'].items())],
  frozen_grammar_vendor_files=[dict(path=p,sha256=h) for p,h in sorted(plan['vendor_files_sha256'].items())],
  interpretation='Path/identity metadata only; not raw source datasets or file contents. Installed packages are listed separately and do not imply runtime use.')
 proofs=mechanisms();actual=trajectory_counts(collection)
 report=dict(protocol='pmrl1-j-system-stack-review-v1',journal_git_baseline=BASE,journal_tracked_diff=command(['git','diff','--name-status',BASE],repo),
  stack=dict(path=str(stack),manifest_sha256=sha(stack_manifest),base=dep['base'],dependencies=dep['dependencies'],
   files=len(dep['files']),source_stream_counts=dict(Counter(r['stream'] for r in dep['files'])),mismatches=stack_bad,
   journal_symlink=str((stack/'project/src/metacom_pm/rl1v3/journal').readlink()),
   journal_resolved=str((stack/'project/src/metacom_pm/rl1v3/journal').resolve()),automatic_merge=False,
   source_registry_base_A_equivalence=equivalent),
  runtime_modules=modules,executor=dict(root=str(executor),plan_file_sha256=sha(plan_path),inventory_object_sha256=plan['executor_inventory_sha256'],
   files=len(plan['executor_files_sha256']),frozen_inventory_mismatches=bad_executor,current_composite_differences=current_differences,
   current_missing_paths=missing_current,current_journal_additions=new_journal,
   workingtree_new_journal_modules_not_in_baseline_or_DR=untracked_journal),
  model=dict(path=plan['model_path'],model_id=baseline['spec']['model']['model_id'],revision=baseline['spec']['model']['revision'],
   architecture=baseline['spec']['model']['architecture'],files=small_model,no_weight_loading=True,no_new_weight_hash_claim=True),
  environments=env,complete_file_closure=dict(file='COMPLETE_CODE_FILE_CLOSURE_PUBLIC.json',stack_files=531,executor_files=613,vendor_files=81,
    object_sha256=obj(closure)),mechanism_probes=proofs,observed_trajectory_counts=actual,
  actual_model_calls_in_review=0,GPU_calls_in_review=0,source_content_or_gold_exported=False,
  limitations=['This is the dependency closure of the actual dynamic path, not a J00 corpus/asset re-audit.',
   'Dependency integrity and event hashes do not confer scientific label or semantic qualification.',
   'Synthetic mechanism probes demonstrate reachable implementation properties, not historical corruption or measured quality harm.'])
 out.mkdir(parents=True)
 write(out/'DEPENDENCY_MANIFEST_PUBLIC.json',report)
 write(out/'COMPLETE_CODE_FILE_CLOSURE_PUBLIC.json',closure)
 write(out/'MECHANISM_PROBES_PUBLIC.json',proofs)
 write(out/'OBSERVED_TRAJECTORY_COUNTS_PUBLIC.json',actual)
 write(out/'REVIEW_REPLAY_RECEIPT.json',dict(script_sha256=sha(__file__),files_sha256={p.name:sha(p) for p in out.iterdir()},model_calls=0,GPU_calls=0))
 return dict(files=report['stack']['files'],stack_mismatches=len(stack_bad),executor_files=len(plan['executor_files_sha256']),executor_mismatches=len(bad_executor),
  current_composite_differences=len(current_differences),current_missing_paths=len(missing_current),current_journal_additions=len(new_journal),
  manifest_sha256=sha(out/'DEPENDENCY_MANIFEST_PUBLIC.json'),actual=actual,mechanisms=proofs)

if __name__=='__main__':
 parser=argparse.ArgumentParser()
 for flag in ('repo','stack-manifest','plan-path','collection','out'):parser.add_argument('--'+flag,required=True)
 print(json.dumps(run(**vars(parser.parse_args())),indent=2))
