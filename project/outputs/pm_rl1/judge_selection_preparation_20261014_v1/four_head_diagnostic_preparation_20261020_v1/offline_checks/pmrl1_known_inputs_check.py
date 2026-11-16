from pathlib import Path
import sys,json,socket
R=Path('/opt/tokkio-data0/tokkio_projects/Metacom5_3');B=R/'project/outputs/pm_rl1/judge_selection_preparation_20261014_v1';P=B/'four_head_diagnostic_preparation_20261020_v1'
sys.path[:0]=[str(R/'project/src'),str(B/'paired_diagnostic_20261019_v1')]
def no_network(*a,**k):raise AssertionError('no network in offline input check')
socket.socket.connect=no_network
import paired
p=json.loads((P/'protocol.json').read_text());d=json.loads((P/'inputs_private.json').read_text());prompt=json.loads((P/'joint_system_prompt.json').read_text())['content']
records=[]
for rid,x in d['generation_cache'].items():
 req=json.loads(Path(x['request_path']).read_text());pid=req['provenance']['prefix_identity'];counts=req['provenance']['canonical_counts']
 if pid not in d['specs']:continue
 split=d['specs'][pid]['prefix']['split']
 if counts!=[0,0,0,0] and not(split=='dev' and counts==[1,0,0,0]):continue
 raw=json.loads(Path(x['raw_path']).read_text());item=dict(reply=raw['text'],evidence=d['evidence'][pid]);messages,schema=paired.payload(item,'joint');messages[0]['content']=prompt
 assert set(json.loads(messages[1]['content']))=={'legal_evidence','reply','response_units'}
 records.append(dict(request_id=rid,prefix_identity=pid,counts=counts,screen=paired.input_guard(messages)))
assert len(records)==36
receipt=dict(protocol_identity=p['identity'],known_cached_inputs=36,rows=records,
 max_bytes=max(x['screen']['serialized_messages_utf8_bytes'] for x in records),
 newly_generated_reply_screen='checked at dispatch, no truncation',new_requests=0)
(P/'offline_input_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print('complete known inputs',len(records),'max UTF8 bytes',receipt['max_bytes'])
