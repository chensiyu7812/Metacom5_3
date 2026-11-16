from pathlib import Path
import json,os,time,sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import action_stage as a
from action_stage import s,p

def record(position,notes):
 protocol,items=a.load();slot=protocol['schedule'][position-1];sid=slot['slot_id']
 r=s.read(a.ROOT/(sid+'.result.json'));item=items[slot['item_key']]
 turns=p.evidence_turns(item['evidence'])
 checks=[]
 for check in notes.pop('checks',[]):
  checks.append(check|{'sources':[dict(id=k,**{z:turns[k][z] for z in ('role','text')}) for k in check['ids']]})
 value=dict(slot_id=sid,request_identity=r['request_identity'],response_sha256=s.sha(a.ROOT/(sid+'.response.json')),
  reply_identity=s.digest(item['reply']),evidence_identity=s.digest(item['evidence']),
  reviewer='Codex source review; analyst-derived, not an independent human rating',timestamp=time.time(),
  complete_final_read=True,thinking_used_as_answer=False,source_checks=checks,
  source_proved_substantial_errors=[],unresolved_ambiguities=[],reward_eligible=False,
  original_scores_unchanged=True,disposition='continue')|notes
 path=a.ROOT/(sid+'.review.json');temp=path.with_name(path.name+'.pending')
 s.save(temp,value);os.chmod(temp,0o600);os.link(temp,path);temp.unlink()
 print(s.canonical({'reviewed':position,'item':slot['item_key'],'disposition':value['disposition']}))
