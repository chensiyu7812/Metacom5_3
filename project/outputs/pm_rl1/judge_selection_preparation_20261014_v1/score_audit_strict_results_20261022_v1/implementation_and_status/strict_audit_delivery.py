"""Proposed strict tool-argument delivery; no model calls on import.

Reuse the exact local score/source validator and paired dispatch loop. The tool
is only an output record: no function execution or tool-result conversation.
"""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import json
import os
import time

from . import score_audit_validation as prior, feedback_score_audit as audit
from . import relation_reference as r

VERSION = 'pmrl1-score-audit-strict-delivery-v1-20261022'
DELIVERY = 'deepseek-beta-strict-audit-arguments-v1-20261022'
ENDPOINT = 'https://api.deepseek.com/beta/chat/completions'
TOOL = 'submit_audit'
INSTRUCTION = '''
DELIVERY OVERRIDE (serialization only; all preceding audit criteria unchanged):
Submit the one complete audit object through the submit_audit function arguments,
instead of message content. The function only records this audit: it performs no
external action. Use exactly one call and no answer in content. Do not call any
other function. Do not send a second message or produce a tool-result round.
All fields, source_evidence, score links and the full local schema above remain
required. Do not return replacement numeric scores. The local validator still
enforces nonempty strings/arrays and exact quotes even where the server schema
cannot express those constraints. Do not repair or reuse an earlier failed answer.
'''


def server_schema(schema):
    """Documented Beta subset; full original constraints stay in local validation."""
    changes = []
    def convert(node, path):
        if not isinstance(node, dict): raise ValueError('schema node must be object')
        out = deepcopy(node)
        for key in ('minLength', 'maxLength', 'minItems', 'maxItems'):
            if key in out:
                changes.append(dict(path=path, keyword=key, value=out.pop(key), enforcement='unchanged local schema'))
        if 'const' in out and isinstance(out['const'], str):
            out['enum'] = [out.pop('const')]; out['type'] = 'string'
            changes.append(dict(path=path,keyword='string const',enforcement='equivalent singleton enum plus local const'))
        if 'enum' in out and 'type' not in out:
            if not all(isinstance(x,str) for x in out['enum']):raise ValueError('unsupported enum type')
            out['type']='string'
        if out.get('type') == 'object':
            if set(out.get('required',[]))!=set(out.get('properties',{})) or out.get('additionalProperties') is not False:
                raise ValueError('strict object must require all fields and forbid extras')
            out['properties']={k:convert(v,path+'/properties/'+k) for k,v in out['properties'].items()}
        if 'items' in out:out['items']=convert(out['items'],path+'/items')
        allowed={'type','properties','required','additionalProperties','items','enum','pattern','minimum','maximum','const'}
        if set(out)-allowed:raise ValueError('unreviewed server schema keyword')
        return out
    return convert(schema,''), changes


def payload(slot,item,scores,p,rubric):
    messages,schema=prior.payload(slot,item,scores,p,rubric)
    messages[0]['content']+=INSTRUCTION
    return messages,schema


def wire_body(config,messages,schema,p):
    # Preserve exact model/thinking/output boundary; change delivery only.
    body=p.api_body(config,messages)
    if body['thinking']!={'type':'enabled'} or body['reasoning_effort']!='high':raise ValueError('frozen high required')
    body.pop('response_format')
    projected,_=server_schema(schema)
    body.update(tools=[dict(type='function',function=dict(name=TOOL,strict=True,
        description='Record the complete audit only; no external action or tool-result round.',parameters=projected))],tool_choice='auto')
    return body


def engine_proxy(p,pr,items,scores,rubric):
    catalog={r.digest(payload(s,items[s['item_key']],scores,p,rubric)[0]):s for s in pr['schedule']}
    def body(config,messages):
        slot=catalog.get(r.digest(messages))
        if slot is None:raise ValueError('unbound outbound messages')
        expected,schema=payload(slot,items[slot['item_key']],scores,p,rubric)
        if messages!=expected or config!=pr['config']:raise ValueError('changed delivery config/input')
        return wire_body(config,messages,schema,p)
    def guard(messages):
        base=p.input_guard(messages)
        # Include tools/schema in the native byte screen, not just messages.
        n=len(p.s.canonical(body(pr['config'],messages)).encode())
        if n+8192+393216>1048576:raise ValueError('complete tool schema and input exceed context')
        return dict(base,serialized_wire_utf8_bytes=n,client_truncation=False)
    proxy=SimpleNamespace(**{k:getattr(p,k) for k in dir(p) if not k.startswith('__')})
    proxy.api_body=body;proxy.input_guard=guard
    return proxy


class Collector:
    """Lossless SSE accumulation; no interpretation of arguments or reasoning."""
    def __init__(self,request_identity):
        self.raw=dict(transport='deepseek',request_identity=request_identity,native_thinking='enabled',delivery=DELIVERY)
        self.content='';self.reasoning='';self.calls={};self.finish=None;self.done=False

    def feed(self,line):
        if not line.startswith(b'data:'):return
        data=line[5:].strip()
        if data==b'[DONE]':self.done=True;return
        if self.done:raise ValueError('data after DONE')
        x=json.loads(data)
        for k in ('id','model','created','system_fingerprint'):
            if k in x:
                if k in self.raw and self.raw[k]!=x[k]:raise ValueError('service identity drift')
                self.raw[k]=x[k]
        if x.get('usage'):
            if 'usage' in self.raw and self.raw['usage']!=x['usage']:raise ValueError('usage changed')
            self.raw['usage']=x['usage']
        for c in x.get('choices',[]):
            if c.get('index',0)!=0:raise ValueError('multiple completion')
            delta=c.get('delta',{})
            self.content+=delta.get('content') or '';self.reasoning+=delta.get('reasoning_content') or ''
            for part in delta.get('tool_calls') or []:
                ix=part.get('index')
                if type(ix) is not int or ix<0:raise ValueError('invalid tool stream index')
                tool=self.calls.setdefault(ix,dict(function=dict(arguments='')))
                for key in ('id','type'):
                    if part.get(key):
                        if key in tool and tool[key]!=part[key]:raise ValueError('tool identity drift')
                        tool[key]=part[key]
                fn=part.get('function') or {}
                if fn.get('name'):
                    if 'name' in tool['function'] and tool['function']['name']!=fn['name']:raise ValueError('tool name drift')
                    tool['function']['name']=fn['name']
                tool['function']['arguments']+=fn.get('arguments') or ''
            if c.get('finish_reason'):
                if self.finish is not None and self.finish!=c['finish_reason']:raise ValueError('finish changed')
                self.finish=c['finish_reason']

    def complete(self):
        if not self.done or self.finish is None:raise ValueError('incomplete stream')
        msg=dict(content=self.content,reasoning_content=self.reasoning,
                 tool_calls=[self.calls[k] for k in sorted(self.calls)])
        return self.raw|dict(choices=[dict(index=0,message=msg,finish_reason=self.finish)])


class Transport:
    def __init__(self,config,proxy):self.config=config;self.proxy=proxy

    def send(self,messages,schema,*,request,raw_path):
        import urllib.request
        key=os.environ.get('DEEPSEEK_API_KEY')
        if not key:raise RuntimeError('authorized process credential absent')
        body=self.proxy.api_body(self.config,messages)
        req=urllib.request.Request(ENDPOINT,data=json.dumps(body,ensure_ascii=False).encode(),
            headers={'Content-Type':'application/json','Authorization':'Bearer '+key})
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*args,**kwargs):return None
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect)
        c=Collector(request['request_id']);start=time.monotonic();c.raw['request_started_unix']=time.time()
        with Path(raw_path).open('xb') as archive:
            with opener.open(req,timeout=30) as response:
                c.raw['response_headers']={k:v for k,v in response.headers.items() if k.lower() in ('date','x-request-id','request-id')}
                for line in response:
                    archive.write(line);archive.flush()
                    if time.monotonic()-start>self.config['timeout_seconds']:raise TimeoutError('total watchdog')
                    c.feed(line)
                    if c.done:break
        raw=c.complete();raw['total_seconds']=time.monotonic()-start
        return raw


def evaluate(raw,item,score,p):
    try:
        if raw.get('delivery')!=DELIVERY:raise ValueError('wrong delivery version')
        if len(raw['choices'])!=1:raise ValueError('exactly one completion required')
        choice=raw['choices'][0];msg=choice['message']
        if choice['finish_reason']!='tool_calls':raise ValueError('no natural complete tool output')
        if msg.get('content') not in (None,''):raise ValueError('extra content forbidden')
        calls=msg.get('tool_calls') or []
        if len(calls)!=1:raise ValueError('exactly one audit tool required')
        call=calls[0]
        if call.get('type')!='function' or call.get('function',{}).get('name')!=TOOL or not call.get('id'):
            raise ValueError('wrong or unidentified tool')
        arguments=call['function']['arguments']
        if not isinstance(arguments,str) or not arguments.lstrip().startswith('{'):raise ValueError('whole bare object required')
        _,value,adaptation=p.envelope.unwrap(arguments)
        if adaptation['transformation']!='bare_json_unchanged':raise ValueError('no argument repair')
        audit.validate_audit(value,item,score,p)
        return dict(technical_valid=True,value=value,interface_version=audit.INTERFACE,
            delivery_version=DELIVERY,argument_adaptation=adaptation,reward_eligible=False,semantic_gold=False)
    except Exception as exc:
        return dict(technical_valid=False,value=None,error_type=type(exc).__name__,error=str(exc),
            interface_version=audit.INTERFACE,delivery_version=DELIVERY,reward_eligible=False)


def remaining_schedule(original,started):
    if not set(started)<=set(x['slot_id'] for x in original):raise ValueError('unknown old slot')
    # Keep the ORIGINAL slot/repetition identity even under a different run version.
    return [deepcopy(x) for x in original if x['slot_id'] not in started]


def budget_class(p):
    class SameStudyBudget(p.DiagnosticBudget):
        def stage_total(self,reserved,settled):
            return sum(p.s.nanodollars(settled[k]['actual_cost_usd'] if k in settled else v['maximum_cost_usd'])
                for k,v in reserved.items() if v.get('binding',{}).get('study') in (prior.VERSION,VERSION))
    return SameStudyBudget


def require_approval(pr,auth):
    if auth.get('status')!='APPROVED' or auth.get('protocol_identity')!=pr['identity']:raise ValueError('Beta delivery continuation needs scoped approval')
    if any(auth.get(k)!=v for k,v in pr['approval_required'].items()):raise ValueError('continuation scope differs')
    if r.sha(auth['researcher_authorization_record'])!=auth['researcher_record_sha256']:raise ValueError('researcher record changed')
    act=r.read(pr['activation_file'])
    if act.get('protocol_identity')!=pr['identity'] or act.get('approval_identity')!=r.digest(auth) or act.get('applied') is not True:
        raise ValueError('continuation not activated')


def runtime(pr,items,scores,p,rubric,proxy):
    def validate(slot,item,messages,schema,results):
        if (messages,schema)!=payload(slot,item,scores,p,rubric):raise ValueError('outbound changed')
        proxy.input_guard(messages)
    return dict(approve=require_approval,dependency=lambda *_:dict(action='dispatch',dependencies=[]),
        stop=prior.old.stop,summarize=lambda pr,root,p:prior.summary(pr,root,p,scores),
        payload=lambda slot,item,results:payload(slot,item,scores,p,rubric),validate_outbound=validate,
        evaluate=lambda slot,item,raw:evaluate(raw,item,scores[slot['item_key']]['evaluation']['value'],p))
