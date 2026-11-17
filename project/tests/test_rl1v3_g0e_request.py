"""CPU contract checks. Fixture tokenizer is explicitly not model evidence."""
from dataclasses import replace
import itertools
import json
from pathlib import Path
import pytest
from metacom_pm.rl1v3 import contracts as K
from metacom_pm.rl1v3.bank.v0_port import load_bank, PrefixPort
from metacom_pm.rl1v3.generator.g0e import Binding, load_binding, SYSTEM
from metacom_pm.rl1v3.generator.g0e_port import G0ePrefixPort, PromptTokenizer
from metacom_pm.rl1v3.generator import output_cache as C
from metacom_pm.rl1v3.io import canonical_json, file_sha256
from metacom_pm.rl1v3.render.request_packet import messages, request_packet

ROOT=Path(__file__).resolve().parents[2]
class FixtureTokenizer:
    identity='fixture-only-g0e-codepoints'
    native_context_tokens=262144
    def count(self,text): return len(text)
    def encode_messages(self,msgs): return tuple(map(ord,canonical_json(msgs)))
    def prompt_tokens(self,prefix,readings):
        # Sizing accepts ReadPlan internally, as the production native adapter does.
        views=tuple(K.ReadingView(head=v.head,view=v.view,ordinal=v.ordinal,
            reading_text=v.reading_text,reported_at=v.reported_at,tokens=v.tokens,stage=v.stage,
            expandable=False) for v in readings)
        return len(self.encode_messages(messages(prefix,views)))

@pytest.fixture(scope='module')
def assets():
    bank,cfg=load_bank(ROOT)
    rows=[json.loads(x) for x in (ROOT/'project/outputs/pm_rl1/v3/B1/coverage_sample_v1.jsonl').read_text().splitlines()]
    row=next(r for r in rows if r['fold']<=5)
    prefix=bank.registry.prefix(row['owner_id'],row['session_id'],row['cut_turn'])
    spec=load_binding(ROOT,verify_local_files=False).spec
    spec['tokenizer_identity']=FixtureTokenizer.identity
    spec['runtime']['max_model_len']=262144
    return bank,prefix,Binding(canonical_json(spec)),cfg

@pytest.fixture
def port(assets): return G0ePrefixPort(*assets[:2],FixtureTokenizer(),assets[2])

def acquire(port,heads):
    views=()
    for head in heads:
        r=port.read(head,acquired=views)
        assert isinstance(r,K.ReadSuccess)
        views+=(r.reading,)
    return views

def test_all_subsets_and_permutations_have_canonical_requests_and_real_traces(port):
    hashes={};traces=set();orders=0
    for n in range(5):
        for subset in itertools.combinations(K.HEAD_ORDER,n):
            for order in itertools.permutations(subset):
                packet=port.request_packet(acquire(port,order));orders+=1
                stamp=(packet.key.sha256,packet.request_sha256,canonical_json(packet.payload()))
                assert hashes.setdefault(subset,stamp)==stamp
                traces.add(packet.trace.sha256)
                packet.trace.verify_key(packet.key)
                assert isinstance(port.replay(packet.key),K.ExecutionTrace)
    assert len(hashes)==16 and len({v[1] for v in hashes.values()})==16
    assert orders==len(traces)==65

def test_model_input_whitelist_and_off(port):
    off=port.request_packet()
    assert off.payload()['messages']==[{'role':'system','content':SYSTEM}]+[
        {'role':'user' if t.role=='seeker' else 'assistant','content':t.text} for t in port.prefix.turns]
    packet=port.request_packet(acquire(port,K.HEAD_ORDER)); payload=packet.payload()
    assert set(payload)=={'messages','input_ids','decode'}
    assert all(set(m)=={'role','content'} for m in payload['messages'])
    assert payload['messages'][1]['content'].startswith('Notes')
    text=canonical_json(payload)
    for private in ('NeedCard','checklist','judge','oracle','record_id','source_id','owner_id','retrieval_score'):
        assert private not in text
    for ids in packet.key.acquired:
        for rid in ids: assert rid not in text
    assert packet.key.prefix_id not in text
    assert packet.private_envelope()['terminal_status']=='pending'

def test_full_tokens_and_capacity_without_truncation_or_failed_ordinal(port,assets):
    packet=port.request_packet(acquire(port,K.HEAD_ORDER))
    ledger=packet.token_ledger
    assert ledger['input_tokens']==len(packet.input_ids)
    assert ledger['input_tokens']==ledger['system_text_tokens']+ledger['current_turn_text_tokens']+ledger['raw_reading_tokens']+ledger['framing_and_token_boundary_delta']
    spec=assets[2].spec;spec['runtime']['max_model_len']=port.base_tokens+321
    blocked=G0ePrefixPort(port.bank,port.prefix,port.tokenizer,Binding(canonical_json(spec)))
    failed=blocked.read('MS');assert isinstance(failed,K.ReadFailure) and failed.reason=='capacity'
    assert failed.input_tokens_unchanged==blocked.base_tokens and not hasattr(failed,'reading')
    assert blocked._validated=={():blocked.base_tokens}
    assert blocked.action_mask()==('STOP',)
    assert blocked.request_packet().token_ledger['total_context_bound']<=blocked.effective_context_tokens
    assert port.read('MS').reading.ordinal==1

def test_forged_future_owner_and_failed_views_never_render(port):
    view=port.read('ME').reading
    for bad in (replace(view,reading_text=view.reading_text+' invented'),replace(view,ordinal=2)):
        with pytest.raises(ValueError):port.request_packet((bad,))
    with pytest.raises(ValueError):port.request_packet((view,view))
    failed=port.read('ME',bank_version='wrong')
    assert failed.reason=='integrity'
    with pytest.raises(ValueError):port.request_packet((failed,))
    with pytest.raises(ValueError):request_packet(replace(port.prefix,owner_id='foreign'),port=port)
    with pytest.raises(ValueError):request_packet(replace(port.prefix,timestamp='2099-01-01T00:00:00Z'),port=port)
    with pytest.raises(TypeError):messages(port.prefix,(port.reader.measure('ME'),))

def test_evaluation_annotations_do_not_enter_request(port):
    # fold/stratum excluded from runtime prefix hash by frozen C0.
    changed=replace(port.prefix,stratum='both')
    assert request_packet(changed,port=port).request_sha256==port.request_packet().request_sha256

def test_versions_and_old_port_remain_isolated(port,assets):
    old=PrefixPort(port.bank,port.prefix,FixtureTokenizer(),**assets[3]['reader_identity'])
    assert old.identity['renderer_id']!=port.identity['renderer_id']
    assert isinstance(port.replay(old.terminal_key([])),K.ReadFailure)
    assert isinstance(old.replay(port.request_packet().key),K.ReadFailure)
    assert len(port.bank.records)==3188
    for k in ('bank_version','index_version'):
        assert port.read('ME',**{k:'wrong'}).reason=='integrity'
    key=port.request_packet().key
    for field in ('g_id','decode_id','renderer_id','step2_id','bank_version','index_version','owner_id'):
        assert isinstance(port.replay(replace(key,**{field:'wrong'})),K.ReadFailure)

def test_binding_distinguishes_backend_and_preserves_decode():
    hf=load_binding(ROOT,verify_local_files=False);vllm=load_binding(ROOT,backend='vllm',verify_local_files=False)
    assert hf.g_id!=vllm.g_id and hf.decode_id==vllm.decode_id
    assert hf.spec['decode']['max_new_tokens']==320 and not hf.spec['decode']['do_sample']
    assert hf.spec['renderer_implementation_sha256']==file_sha256(ROOT/'project/src/metacom_pm/rl1v3/render/request_packet.py')
    for field,value in (('max_new_tokens',321),('seed',1),('enable_thinking',True)):
        s=hf.spec;s['decode'][field]=value
        with pytest.raises(ValueError):Binding(canonical_json(s))

@pytest.mark.parametrize('shape', ['flat','mapping','batch'])
def test_native_mapping_output_is_counted_by_ids(shape):
    class Native:
        identity='fixture';native_context_tokens=262144
        def count(self,text):return len(text)
        @property
        def tokenizer(self):return self
        def apply_chat_template(self,*a,**kw):
            return [2,3,4] if shape=='flat' else {'input_ids':[2,3,4]} if shape=='mapping' else {'input_ids':[[2,3,4]]}
    assert PromptTokenizer(Native()).encode_messages([{'role':'user','content':'hi'}])==(2,3,4)

@pytest.mark.parametrize('finish,ids,response,complete',[
    ('eos',[5,106],'response',True),('eos',[106],'',False),('length',[5]*320,'partial',False),
    ('timeout',[],'',False),('oom',[],'',False),('error',[5],'partial',False),('cancelled',[],'',False)])
def test_output_cache_never_promotes_technical_failures(port,tmp_path,finish,ids,response,complete):
    p=port.request_packet();r=C.record(p,response=response,generated_token_ids=ids,finish_reason=finish,
        elapsed_seconds=1.,execution_identity=p.binding.g_id,model_called=True)
    assert r['evaluation_status']=='pending' and r['reward'] is None
    C.save(tmp_path,p,r);assert (C.load(tmp_path,p) is not None)==complete
    r['reusable_as_complete']=not complete
    with pytest.raises(ValueError):C.save(tmp_path,p,r)

def test_cache_rejects_unrun_corrupt_wrong_runtime_and_nonfinite(port,tmp_path):
    p=port.request_packet();args=dict(response='fixture',generated_token_ids=[106],finish_reason='eos',
        elapsed_seconds=1.,execution_identity=p.binding.g_id,model_called=True)
    for change in ({'model_called':False},{'execution_identity':'other'},{'elapsed_seconds':float('nan')},
                   {'generated_token_ids':[3]},{'generated_token_ids':[3]*321}):
        with pytest.raises(ValueError):C.record(p,**(args|change))
    r=C.record(p,**args);C.save(tmp_path,p,r)
    path=tmp_path/(C.cache_key(p)+'.json');bad=json.loads(path.read_text());bad['response']='tampered';path.write_text(json.dumps(bad))
    with pytest.raises(ValueError):C.load(tmp_path,p)

def test_b_finite_environment_terminal_key_and_token_ledger_match_renderer(port):
    from metacom_pm.rl1v3.env.c0_binding import C0FiniteHeadEnv,TerminalIdentity,TerminalTable
    from metacom_pm.rl1v3.env.finite_head import PendingTerminal
    env=C0FiniteHeadEnv(prefix=port.prefix,history_sessions=port.prefix.cutoff_rank,
        availability=port.availability(),read=port.read,identity=TerminalIdentity(**port.identity),
        table=TerminalTable({},table_id='fixture-empty'),prefix_tokens=port.base_tokens,
        token_capacity=port.effective_context_tokens-320,read_takes_acquired=True,dynamic_mask=port.action_mask)
    seen=set()
    def visit(state):
        packet=port.request_packet(env.readings(state))
        assert env.terminal_key(state)==packet.key
        assert env.execution_trace(state)==packet.trace
        assert state.input_tokens==packet.token_ledger['billed_input_tokens']
        with pytest.raises(PendingTerminal):env.step(state,'STOP')
        seen.add(packet.key.sha256)
        for action in env.legal_actions(state):
            if action!='STOP':visit(env.step(state,action)[0])
    visit(env.reset());assert len(seen)==16

def test_new_payload_schema_is_separate_from_frozen_c0(port):
    from jsonschema import Draft202012Validator,ValidationError
    schema=json.loads((ROOT/'project/schemas/rl1v3_g0e/ModelInput.schema.json').read_text())
    check=Draft202012Validator(schema);payload=port.request_packet().payload();check.validate(payload)
    with pytest.raises(ValidationError):check.validate(payload|{'NeedCard':{}})
    bad=json.loads(canonical_json(payload));bad['messages'][0]['owner_id']='private'
    with pytest.raises(ValidationError):check.validate(bad)
    assert len(list((ROOT/'project/schemas/rl1v3').glob('*.schema.json')))==32
