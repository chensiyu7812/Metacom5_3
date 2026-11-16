#!/usr/bin/env python3
"""Produce three review-only replacement candidates; never mutate existing catalogs."""
from pathlib import Path
import json,hashlib
P=Path(__file__).resolve().parent;ROOT=P.parents[3]
canon=lambda x:json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
sha=lambda b:hashlib.sha256(b).hexdigest()
read=lambda p:json.loads(p.read_text())
comparisons_path=P/'CURRENT_VIEW_COMPARISONS_PRIVATE.json';comparisons_hash_before=sha(comparisons_path.read_bytes());rows=read(comparisons_path)
config={
'mp::mvu_2a73b2853cdd499d576e2ab5':dict(
 head='ME',past_report='At the time of this conversation, the seeker reported having hung up on a friend who dominated phone conversations, and reported that the friend became easily offended. This records a past attempt and the reported reaction, not a stable tendency to avoid hanging up.',
 action=dict(actor='historical seeker',description='hung up on the friend',stage='attempted',completion_scope='at least one hang-up is self-reported; no resolution of the recurring problem is established',event_time=None),
 self_reported_reaction=dict(reporter='historical seeker',subject='the friend',description='the friend gets extremely offended easily',relation_to_action='reported in the same statement about hanging up; no independent causal verification',valence='reported adverse interpersonal reaction',duration=None),
 limits=['No stable MP avoidance trait is inferred.','Current preference, current relationship state and long-term result remain unknown.'],
 context_observations=[]),
'mp::mvu_785a6f6f9e719c52ef13fc57':dict(
 head='ME',past_report='At the time of this conversation, the seeker reported having joined a writing workshop that helped, while impostor feelings still recurred. The kind, size and duration of the benefit were not specified.',
 action=dict(actor='historical seeker',description='joined a writing workshop',stage='attempted',completion_scope='joining is self-reported; completion of the workshop is not established',event_time=None),
 self_reported_reaction=dict(reporter='historical seeker',subject='historical seeker',description='the workshop helped, but impostor feelings still recurred',relation_to_action='helpfulness is attributed to the workshop by the speaker; not a causal estimate',valence='partial benefit with continuing difficulty',duration=None),
 limits=['Do not rewrite helped as recovery, cured writer block, or lasting improvement.','Current participation and present benefit are unknown.'],
 context_observations=[]),
'me::mvu_c8da36ab41b1d4da5464dd8d':dict(
 head='ME',past_report='At the time of this conversation, the seeker said that knowing they were not alone helped. Separately, they described the online community as supportive. The quote does not establish a particular community intervention or its causal effect.',
 action=dict(actor=None,description=None,stage='unknown',completion_scope=None,event_time=None),
 self_reported_reaction=dict(reporter='historical seeker',subject='historical seeker',description='knowing they are not alone helps',relation_to_action='no specific action is identified in this quote; no causal link to the online community is assigned',valence='self-reported helpful feeling',duration=None),
 limits=['The two sentences are separate observations.','Do not turn community support into a completed intervention with a measured effect.','Current community participation and current helpfulness are unknown.'],
 context_observations=[dict(reporter='historical seeker',description='the online community has been supportive',causal_relation_to_self_reported_reaction='unknown')])
}
results=[];protected={}
for row in rows:
 old=row['item'];c=config[old['key']];old_body=row['body'];bindings=[]
 # Catalog ranks may differ by target. Preserve and validate every actual old identity separately.
 for binding in row['prefix_bindings']:
  path=ROOT/binding['source_path'];before=sha(path.read_bytes());assert before==binding['source_sha256'];protected[str(path)]=before
  cat=read(path);matches=[x for x in cat['memory'] if x['key']==old['key']];assert len(matches)==1
  item=matches[0];assert item['content']==old['content'] and item['source_identity']==old['source_identity'] and item['source_ids']==old['source_ids']
  bindings.append(dict(**binding,old_catalog_item_identity=sha(canon(item)),old_content_sha256=sha(item['content'].encode())))
 quote=row['source_quote_binding'];assert any(e['quote']==quote['text'] for e in old_body['evidence'])
 candidate=dict(candidate_only=True,status='OFFLINE_REVIEW_SIDECAR_NOT_CONNECTED',proposed_head=c['head'],proposed_past_report=c['past_report'],proposed_search_text=c['past_report'],
  historical_action=c['action'],self_reported_reaction=c['self_reported_reaction'],separate_context_observations=c['context_observations'],
  current_status='unknown',current_validity='unknown_not_revalidated',event_time=None,reported_at=old['reported_at'],
  source_evidence_unchanged=old_body['evidence'],source_owner_id=old['owner_id'],source_rank=old['source_rank'],source_ids=old['source_ids'],
  extraction_scope='only the frozen quoted evidence in this old item; no new cross-session relationship',causal_effect_established=False,
  semantic_review='single assistant source review; independent adjudication pending',formal_training_label=False,
  acceptance_limits=c['limits'])
 results.append(dict(repair_id='candidate-memory-repair-'+sha(canon(candidate))[:20],old_key=old['key'],old_head=old['head'],old_snapshot=old,
  old_snapshot_identity=sha(canon(old)),old_content_sha256=sha(old['content'].encode()),old_source_identity=old['source_identity'],
  original_quote_and_binding=quote,old_catalog_bindings=bindings,candidate_identity=sha(canon(candidate)),candidate=candidate,
  application_effect='none; original resource key, body, quote, identity and historical catalogs remain unchanged; candidate requires distinct future resource identity'))
assert len(results)==3
for r in results:
 assert r['old_snapshot_identity']==sha(canon(r['old_snapshot']))
 assert r['candidate_identity']==sha(canon(r['candidate']))
 assert r['candidate']['source_evidence_unchanged']==json.loads(r['old_snapshot']['content'])['evidence']
 assert r['candidate']['current_validity']=='unknown_not_revalidated'
 assert r['candidate']['formal_training_label'] is False
for path,h in protected.items():assert sha(Path(path).read_bytes())==h
assert sha(comparisons_path.read_bytes())==comparisons_hash_before
(P/'CANDIDATE_VIEW_REPAIRS_PRIVATE.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
validation=dict(status='PASS_OFFLINE_CANDIDATE_REPAIR_INVARIANTS',repairs=3,original_catalog_files_checked_unchanged=len(protected),original_quote_arrays_preserved=True,old_identity_and_source_binding_preserved=True,
 repair_sidecar_applied=False,production_changes=False,external_G_J_or_paid_calls=0,unknown_current_validity_preserved=True,
 no_stable_MP_hangup_trait=True,community_reaction_not_assigned_to_intervention=True,
 input_hashes={comparisons_path.name:sha(comparisons_path.read_bytes())},protected_catalog_hashes=protected,
 remaining=['independent source review','new candidate renderer/schema integration','new ranking and cost identities','paired consumption and support benefit evaluation'])
(P/'CANDIDATE_REPAIR_VALIDATION.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in validation.items() if k!='protected_catalog_hashes'},ensure_ascii=False,indent=2))
