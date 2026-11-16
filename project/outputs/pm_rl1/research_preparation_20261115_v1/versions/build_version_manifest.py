"""Offline version inventory. Never loads a model, label body, or response text."""
import hashlib, json, subprocess
from pathlib import Path
ROOT = Path('/home/tokkio/Metacom5_3')
OUT = ROOT / 'project/outputs/pm_rl1/research_preparation_20261115_v1/versions'
def read(rel): return json.loads((ROOT/rel).read_text())
def fingerprint(p):
    p=Path(p); p=p if p.is_absolute() else ROOT/p
    h=hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda:f.read(1048576),b''): h.update(chunk)
    return {'path':str(p),'sha256':h.hexdigest(),'bytes':p.stat().st_size}
def minimal_runtime(d):
    return {k:d[k] for k in ['identity','protocol','model_dir','model_files','adapter','packages','dtype','attention','seed','do_sample','enable_thinking','policy','chat_template_identity','chat_template_sha256','request_protocol','binding_code_sha256','code_sha256'] if k in d}
p2path='project/outputs/pm_rl1/completion_20260930_v2/P2/executor_freeze.json'
qapath='project/outputs/pm_rl1/qa_resource_gain_20261105_v1/alternate_G/PROTOCOL.json'
typedpath='project/outputs/pm_rl1/typed_resource_views_20261111_v1/alternate_G/PROTOCOL.json'
staticpath='project/outputs/paper1_calibration/static_generation_20260917_v1/manifest.json'
p2,qa,typed,static=map(read,[p2path,qapath,typedpath,staticpath])
p2close=read('project/outputs/pm_rl1/completion_20260930_v2/P2/phase_closeout.json')
refpath='project/outputs/pm_rl1/history_necessity_human_review_20261105_v1/REFERENCE_INDEX.json'
refs=read(refpath)
files=[p2path,qapath,typedpath,staticpath,refpath,
'project/outputs/pm_rl1/completion_20260930_v2/P2/phase_closeout.json',
'project/outputs/pm_rl1/completion_20260930_v2/P2/replay_disposition.json',
'project/outputs/pm_rl1/qa_resource_gain_20261105_v1/EXECUTION_CLOSEOUT_20261111.json',
'project/outputs/pm_rl1/typed_resource_views_20261111_v1/CLOSEOUT_20261111.json',
'project/outputs/pm_rl1/typed_resource_views_20261111_v1/SUMMARY.json',
'project/outputs/pm_rl1/typed_resource_views_20261111_v1/POST_EXECUTION_ANALYSIS_FIX.json',
'project/outputs/paper1_calibration/static_generation_20260917_v1/progress.json',
'project/outputs/paper1_calibration/static_official_scoring_20260917_v1/manifest.json',
'project/outputs/paper1_calibration/static_official_scores_20260917_v1/preflight.json',
'project/docs/reviews/20261104/pm_rl1_latency_primary/OBJECTIVE.json',
'project/docs/reviews/20261104/pm_rl1_relative_feedback_trial/RESULTS_ZH.md']
modules=['schema','resource_organization','representation','representation_direct','organized_policy_interface','organized_features','organized_feedback','organized_learning','organized_supervision','organized_oneshot','organized_local_backend','human_reference_reuse','typed_resource_views','relative_diagnostic','client_latency','latency_serving','reusable_latency']
files += ['project/src/metacom_pm/rl1/'+x+'.py' for x in modules]
claude=Path('/opt/tokkio-data0/tokkio_runs/claude_esc_pilot_20261111')
files += [str(claude/x) for x in ['SUMMARY_20261113_ZH.md','gen_loop.py','rs_ladder.py','ceiling.py','score_rank.py','hard/hard.py'] if (claude/x).exists()]
source_files=[fingerprint(x) for x in files if (ROOT/x).exists()]
# Byte-level row counts and file hashes only; no JSONL contents or gold are interpreted.
pools=[]
for name in ['dialogues.jsonl','dialogues_r2.jsonl','tree_dialogues.jsonl','mc_dialogues.jsonl','ceiling_replies.jsonl','ceiling_L8_replies.jsonl','guide_replies.jsonl','rs_ladder_replies.jsonl','sage_replay.jsonl','sage_replay_faithful.jsonl']:
 p=claude/name
 if p.exists():
  x=fingerprint(p)
  with p.open('rb') as f: x['nonempty_lines']=sum(bool(line.strip()) for line in f)
  x.update(count_unit='serialized records, not independent contexts or verified valid outputs',row_identity_match_performed=False)
  pools.append(x)
identity_fields=['source_snapshot_and_allowed_split','prefix_and_cutoff','retriever_version_and_query','ordered_actions_and_actual_selected_resource_ids','resource_body_hashes_and_order','renderer_and_full_messages','G_weights_adapter_template_decode_runtime','draw_identity','actual_reply_bytes_hash','measurement_input_and_rubric_identity','measured_client_path_cache_policy_hardware']
assets=[
 {'asset':'P2 common pool','counts':p2close['common_pool'],'source':p2path,'reuse_class':'CONDITIONAL_EXACT_REUSE','allowed':'Reuse recorded reply only after exact request/runtime/provenance binding; reuse a human label only if its evidence and actual compared replies match.','new_version_rule':'New representation/retrieval-selected text/renderer/G/draw requires a new request; seed alone cannot recreate old reply.','training_label_ready':False},
 {'asset':'1924 Paper1 QA/Summary','counts':{'responses_reported':1924,'targets_reported':148,'QA_reported':1105,'Summary_reported':819},'source':staticpath,'reuse_class':'DIAGNOSTIC_FOR_CURRENT_NATURAL_SUPPORT','allowed':'May reuse identical old QA/Summary responses within their original task/version; inspect parser/scoring infrastructure without fresh generation.','new_version_rule':'Cannot transfer old-task score to current natural support or Gemma. Official scoring remains a distinct unfinished stage.','training_label_ready':False},
 {'asset':'55 human reference records','counts':refs,'source':refpath,'reuse_class':'CONDITIONAL_EXACT_REUSE','allowed':'Original evidence plus exact actual response pair/triple and presentation mapping must match; keep raw ordinal/relative meanings.','new_version_rule':'New reply needs a new judgment; slight/tie/uncertain cannot be converted into an invented precise q/m or zero reward.','independent_raters':False,'training_label_ready':False},
 {'asset':'QA86','counts':read('project/outputs/pm_rl1/qa_resource_gain_20261105_v1/EXECUTION_CLOSEOUT_20261111.json'),'source':qapath,'reuse_class':'DIAGNOSTIC_FOR_CURRENT_NATURAL_SUPPORT','allowed':'Preserve exact QA screen evidence and same-request outputs; useful for evidence retrieval/executor sanity checks.','new_version_rule':'Passing QA screen is not qualified natural-support reward. New structured evidence input needs generation.','training_label_ready':False},
 {'asset':'typed42','counts':read('project/outputs/pm_rl1/typed_resource_views_20261111_v1/SUMMARY.json'),'source':typedpath,'reuse_class':'CONDITIONAL_EXACT_REPLY_REUSE_DIAGNOSTIC_ONLY','allowed':'Preserve existing 42 actual replies for inspection or exact-input human comparison; no helpfulness labels exist.','new_version_rule':'A revised source view fixing missing antecedents changes input and requires generation.','training_label_ready':False},
 {'asset':'Claude branch pools','pools':pools,'source':str(claude/'SUMMARY_20261113_ZH.md'),'reuse_class':'DIAGNOSTIC_UNTIL_BRANCH_IDENTITY_AND_EXPOSURE_AUDIT','allowed':'Preserve original interventions, actual replies and analyses; use failure categories and candidate controls.','new_version_rule':'Same Gemma directory does not establish identical renderer/runtime/evaluation. Interactive ESC-Role outputs cannot be pooled as single-turn RL episodes.','training_label_ready':False},
 {'asset':'All new method cards / complete RS cases / structured memory views','reuse_class':'NEW_INPUT_REQUIRES_GENERATION','allowed':'Reuse source transcripts, verified spans, split map, eligible retrieval indexes and compiler plumbing.','new_version_rule':'New resource bodies need versioned prompts, actual replies and fresh or exact-matched feedback.','training_label_ready':False}]
for x in assets:x['row_level_cache_or_label_join_performed']=False
manifest={
 'version':'pmrl1-offline-version-reuse-manifest-20261115-v1','scope':'Preparation A; source identities and conditional reuse rulings, not a completed cache migration',
 'repository':{'root':str(ROOT),'resolved_root':str(ROOT.resolve()),'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'branch':subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip()},
 'execution':{'new_model_loads':0,'new_G_calls':0,'new_J_calls':0,'paid_calls':0,'training_updates':0,'production_code_edits':0,'test_gold_read':False,'deprecated_11_80_source_read':False,'row_level_reuse_match_performed':False,'new_formal_primary_frozen':False},
 'G_versions':{
  'P2_Llama':{'runtime':minimal_runtime(p2['primary_runtime']),'renderer_identity':p2['renderer_identity'],'draw_identity':p2['terminal_draw_identity'],'status':'Historical frozen common-pool executor; no proven quality improvement'},
  'P2_base_control':{'runtime':minimal_runtime(p2['base_runtime']),'status':'Same P2-era rendering, no LoRA'},
  'Paper1_static_base':{'identity':static['identity_sha256'],'runtime':static['generator_config'],'status':'Historical QA/Summary version; different chat-template identity from P2'},
  'Gemma_QA_and_typed_candidate':{'runtime':minimal_runtime(qa['runtime']),'same_runtime_in_two_protocols':qa['runtime']==typed['runtime'],'QA_protocol_identity':qa['identity'],'typed_protocol_identity':typed['identity'],'status':'Development candidate; not promoted to primary frozen G'},
  'Claude_Gemma_branch':{'model_path_from_source':str(Path('/opt/tokkio-data0/tokkio_models/gemma-4-12B-it-707f0a3')),'source':str(claude/'gen_loop.py'),'status':'Separate code/prompt/evaluation branch; complete runtime equivalence unverified','also_contains':'Llama supplementary ceiling pool and ESC-Role interactive runs'}},
 'resource_action_versions':{
  'legacy':{'domain':'70 count plans, max 4 GET, candidate 2048-token resource budget, frozen rank-prefix ordering','status':'Historical version retained; do not use to describe expanded ordered domain'},
  'current_organized':{'domain':'Ordered STOP/RS/MP/MS/ME programs, no arbitrary top-k or four-read cap; native context capacity','ranking':'literal-overlap-public-prefix-plus-acquired-v1','status':'Development, not formal freeze','code':'project/src/metacom_pm/rl1/resource_organization.py'},
  'QA_probe':{'retrieval':'BGE ordinary top-1/top-2 under the predeclared probe','status':'Does not mean organized live retriever is BGE'},
  'PM_features':{'encoder':'BGE full-text chunk encoding and pooling','dimension_reported':5139,'status':'Feature encoding and candidate retrieval are separate identities'}},
 'measurement':{'natural_support_reward_qualified':False,'human_references':55,'relative_cost_trial':'Real BC/PPO, 3 seeds and 384 trajectories, on exact same ON/OFF actual replies; demonstrates optimization/cost plumbing, not positive support gains','official_ESC_eval':'Keep official parser and task scope; altered single-turn prompt or expected digit score is a separate metric','latency':'Client send before all method-specific online work to actual first/final visible reply; component generation_seconds is not E2E; cached replay is not a new latency observation','unfrozen':['primary G promotion and renderer','resource representation schema and complete-case delivery','formal retriever/query update','ordered action-domain implementation and OneShot search budget','qualified natural-support feedback and tie/uncertain semantics','seconds coefficient and quality-latency operating point','deployment measurement/cache protocol','owner/source-family grouping and independent final evaluation']},
 'required_reuse_join_fields':identity_fields,'assets':assets,'source_file_fingerprints':source_files,
 'minimal_adapter_plan':[
 {'component':'Versioned resource-view compiler + manifest (new preparation module)','reuse':['typed_resource_views.py','source-bound OrganizedItem','OrganizationCatalog validation'],'change':'Compile MP/ME evidence cards and MS parent expansions; complete RS cases retain context/action/observed follow-up/source boundaries. No gold-based query or applicability labels.'},
 {'component':'Retriever adapter (small interface change)','reuse':['OrganizationCatalog.rank','HeadSession'],'change':'Explicitly choose/freeze BGE or existing overlap; preserve public-prefix-plus-acquired query and identical locator for PPO/OneShot/NoText. Every changed selected resource binds a new terminal identity.'},
 {'component':'Resource delivery/renderer adapter','reuse':['OrganizedRenderer','organized_feedback terminal binding','actual request/response cache'],'change':'Deliver versioned evidence bodies with provenance; parent expansion is a new acquired item; no invisible extra evidence. Keep four-head schema initially unless action change is empirically justified.'},
 {'component':'Reuse/feedback join + measurement adapter','reuse':['human_reference_reuse.py','organized_supervision.prepare_targets','comparison_union','OrganizedRun','qualified feedback gates'],'change':'Match exact actual replies and measurement payloads; leave missing outcomes pending. Keep BC/PPO learner and optimizer; add a qualified feedback source and measured latency cost only after evidence is ready.'}]
}
OUT.mkdir(parents=True,exist_ok=True)
(OUT/'VERSION_REUSE_MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'output':str(OUT/'VERSION_REUSE_MANIFEST.json'),'source_files':len(source_files),'Claude_pools':len(pools),'same_Gemma_runtime':qa['runtime']==typed['runtime'],'all_identity_joins_pending':True},ensure_ascii=False))
