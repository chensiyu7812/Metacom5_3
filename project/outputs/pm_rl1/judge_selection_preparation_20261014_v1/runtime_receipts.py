"""Future readiness receipts. No weight download/install/inference commands.

local: hashes pre-existing files and tokenizes complete development inputs.
api: explicit approved account READ only; never sends project conversations.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import selection as s


def local(model_dir,out,candidate='gemma4_12b_bf16'):
    plan=s.load_plan();c=s.config_for(plan,candidate)
    public=s.read(s.HERE/'gemma_public_file_metadata.json')
    hashes={}
    for x in public['files']:
        p=model_dir/x['rfilename']
        if p.stat().st_size!=x['size']:raise ValueError('file size mismatch: '+p.name)
        h=s.sha(p)
        if 'lfs' in x:
            if h!=x['lfs']['sha256']:raise ValueError('official LFS hash mismatch')
        else:
            data=p.read_bytes()
            if hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()!=x['blobId']:
                raise ValueError('official metadata git hash mismatch')
        hashes[x['rfilename']]=h
    os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
    from transformers import AutoProcessor
    processor=AutoProcessor.from_pretrained(model_dir,local_files_only=True,trust_remote_code=False)
    lengths={}
    for r in plan['requests']:
        if r['candidate']!=candidate:continue
        messages,_=s.payload(plan,r)
        encoded=processor.apply_chat_template(messages,tokenize=True,return_dict=True,
            add_generation_prompt=True,enable_thinking=c['enable_thinking'])
        ids=encoded['input_ids']
        if ids and isinstance(ids[0],list):ids=ids[0]
        lengths[r['request_id']]=len(ids)
    result=dict(revision=c['revision'],configuration_identity=c['identity'],files=hashes,
        request_input_tokens=lengths,output_reserve_tokens=32768,
        all_full_inputs_fit=all(n+32768<=262144 for n in lengths.values()),
        real_weight_load_tested=False,real_inference=False)
    s.save(out,result);print(json.dumps({'saved':str(out),'maximum_input_tokens':max(lengths.values()),'inference':False}))


def api(approval_path,out,candidate='deepseek_flash_high'):
    plan=s.load_plan();approval=s.read(approval_path)
    s.verify_approval(plan,candidate,'engineering',approval)
    if approval.get('account_read_approved') is not True:raise ValueError('account read not explicitly approved')
    key=os.environ.get('DEEPSEEK_API_KEY')
    if not key:raise ValueError('credential missing; configure locally, never paste in chat')
    import urllib.request
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*a,**k):return None
    opener=urllib.request.build_opener(NoRedirect)
    out.mkdir(parents=True,exist_ok=False)
    for endpoint,name in [('models','models.json'),('user/balance','balance_private.json')]:
        req=urllib.request.Request('https://api.deepseek.com/'+endpoint,
            headers={'Authorization':'Bearer '+key})
        with opener.open(req,timeout=30) as r:value=json.load(r)
        s.save(out/name,value)
    print(json.dumps({'saved':str(out),'J_calls':0,'administrative_reads':2,'project_payload_sent':False}))


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);sub=ap.add_subparsers(dest='command',required=True)
    l=sub.add_parser('local',help='validate already downloaded exact revision and complete-input tokens; no inference')
    l.add_argument('--model-dir',type=Path,required=True);l.add_argument('--out',type=Path,required=True)
    l.add_argument('--candidate',choices=s.CANDIDATES[:2],default=s.CANDIDATES[0])
    a=sub.add_parser('api',help='future approved GET /models and GET /user/balance; no J call')
    a.add_argument('--approval',type=Path,required=True);a.add_argument('--out',type=Path,required=True)
    a.add_argument('--candidate',choices=s.CANDIDATES[2:],default=s.CANDIDATES[3])
    v=ap.parse_args()
    if v.command=='local':local(v.model_dir,v.out,v.candidate)
    else:api(v.approval,v.out,v.candidate)
