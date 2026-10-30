"""Public version of the historical service, account and visible-writer guards.

Called ONLY by an authorized live launcher. No private engine source dependency,
automatic service substitution, implicit management retry or credential output.
"""
from decimal import Decimal
from html.parser import HTMLParser
import hashlib
import json
import os
from pathlib import Path
import time

from .development_feedback import save_once
from .schema import digest

PRICING = 'https://api-docs.deepseek.com/quick_start/pricing/'


class FirstTable(HTMLParser):
    def __init__(self):
        super().__init__(); self.depth=0; self.done=False; self.cell=None; self.row=[]; self.rows=[]
    def handle_starttag(self,tag,attrs):
        if tag=='table' and not self.done:self.depth+=1
        if self.depth and tag=='tr':self.row=[]
        if self.depth and tag in ('th','td'):self.cell=[]
    def handle_data(self,data):
        if self.depth and self.cell is not None:self.cell.append(data)
    def handle_endtag(self,tag):
        if self.depth and tag in ('th','td') and self.cell is not None:
            self.row.append(' '.join(' '.join(self.cell).split()));self.cell=None
        if self.depth and tag=='tr' and self.row:self.rows.append(self.row)
        if self.depth and tag=='table':self.depth-=1;self.done=True


def visible_paid_writers():
    suspects=[]
    for p in Path('/proc').iterdir():
        if not p.name.isdigit() or int(p.name)==os.getpid():continue
        try:
            parts=(p/'cmdline').read_bytes().split(b'\0');comm=(p/'comm').read_text().strip()
            if not any(x in comm.lower() for x in ('python','curl','wget')):continue
            scripts=[Path(x.decode(errors='replace')).name for x in parts[1:] if x.endswith(b'.py')]
            paid=any(any(k in x.lower() for k in ('api','acceptance_batch','teacher_qualification','continue_v1','selection.py','run_development_stage')) for x in scripts)
            if paid or any(b'api.deepseek.com' in x or b'generativelanguage.googleapis.com' in x for x in parts):
                suspects.append(dict(pid=int(p.name),comm=comm,scripts=scripts))
        except (PermissionError,FileNotFoundError,ProcessLookupError):continue
    return suspects


def validate_preflight(root, identity, policy, approval):
    root=Path(root);r=json.loads((root/'PREFLIGHT.json').read_text())
    if (r['protocol_identity']!=identity or r['approval_identity']!=digest(approval)
            or r['public_price_table_identity']!=policy['public_price_table_identity']):
        raise ValueError('service preflight binding changed')
    for name,h in r['files'].items():
        if Path(name).name!=name or hashlib.sha256((root/name).read_bytes()).hexdigest()!=h:
            raise ValueError('service/account receipt changed')
    return r


def ensure_preflight(stage):
    from .development_dispatch import require_approval
    require_approval(stage.identity,stage.policy,stage.approval)
    if not stage.budget.lease_active:raise ValueError('legacy lease required before management')
    if visible_paid_writers():raise ValueError('visible concurrent paid writer')
    stage.budget._history()
    if (stage.root/'CLOSED.json').exists():raise ValueError('stage already closed; read report without network')
    import urllib.request
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):return None
    op=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect)
    root=stage.root/'management';root.mkdir(exist_ok=True,mode=0o700)
    # Recheck the public table at each explicit launch/resume, like the old
    # launcher. Model-list and balance requests happen at most once per stage.
    raw=op.open(PRICING,timeout=30).read();parser=FirstTable();parser.feed(raw.decode())
    if not parser.rows or digest(parser.rows)!=stage.policy['public_price_table_identity']:
        raise ValueError('published service/capabilities/pricing changed; no automatic substitution')
    save_once(root/('public_'+str(time.time_ns())+'.json'),dict(url=PRICING,table_identity=digest(parser.rows),html_sha256=hashlib.sha256(raw).hexdigest()))
    if (root/'PREFLIGHT.json').exists():
        return validate_preflight(root,stage.identity,stage.policy,stage.approval)
    if list(root.glob('*.started.json')):raise ValueError('incomplete management attempt; no automatic retry')
    key=os.environ.get('DEEPSEEK_API_KEY')
    if not key:raise ValueError('authorized process credential absent')
    fingerprint=hashlib.sha256(key.encode()).hexdigest()
    def get_once(name,endpoint):
        save_once(root/(name+'.started.json'),dict(protocol_identity=stage.identity,endpoint=endpoint))
        req=urllib.request.Request('https://api.deepseek.com/'+endpoint,headers={'Authorization':'Bearer '+key})
        with op.open(req,timeout=30) as response: data=json.loads(response.read())
        save_once(root/(name+'.json'),data);return data
    models=get_once('models','models')
    service=next((x for x in models.get('data',[]) if x.get('id')==stage.policy['request_model']),None)
    if (not service or ('name' in service and service['name'] not in stage.policy['published_model_names'])
            or ('context_window' in service and service['context_window']!=1048576)
            or ('max_output_tokens' in service and service['max_output_tokens']!=393216)):
        raise ValueError('service identity/capability changed')
    balance=get_once('balance','user/balance')
    if balance.get('is_available') is not True:raise ValueError('account unavailable')
    amounts={x['currency']:Decimal(x['total_balance']) for x in balance['balance_infos']}
    # Original fixed tariff-equivalent ratio, not a claim about market FX.
    available=amounts.get('USD',Decimal(0))+amounts.get('CNY',Decimal(0))*Decimal('.15')
    n=int(available*10**9)
    if n<stage.policy['reserve_nanodollars']:raise ValueError('account below one native reserve')
    _,trial,reserved,settled=stage.budget._totals(stage.budget.events())
    if set(reserved)-set(settled):raise ValueError('existing unsettled liabilities')
    record=dict(protocol_identity=stage.identity,approval_identity=digest(stage.approval),
        public_price_table_identity=stage.policy['public_price_table_identity'],service=service,
        credential_fingerprint=fingerprint,available_nanodollars=n,opening_trial_nanodollars=trial,
        management_requests=2,immutable_provider_weights=False,
        files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in root.glob('*.json')})
    save_once(root/'PREFLIGHT.json',record)
    return record
