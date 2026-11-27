#!/usr/bin/env python3
"""G6 online INSPECT_CLAIM close-out (approved 2026-11-27: A6000, <=128 LLM calls, 1 Gemma load, 2400 s).

  prepare (CPU)  frozen states -> STATES (runtime input only), CHECKS (never read by run).
  run     (GPU)  one Gemma load; phase 1 screening A on 32 states; then the process keeps the
                 model loaded and waits for GATE_DECISION.json (written by the reviewer after
                 GATE_REVIEW.private.json; the decision must carry that file's SHA-256);
                 'stop' -> exit; 'continue' -> phase 2 hold-out (16 states): A, N (notes ->
                 reply), risk-claim formation -> B_prime (INSPECT on T1i, CPU) and P (same claims
                 and evidence IDs, no T1i result). If claim formation returns NONE (or nothing
                 parsable), the P and B_prime prompts equal A's and A's reply is reused (no call).
One watchdog covers load, both phases and the gate wait. 0 warmup, 0 retry.
"""
import argparse, hashlib, json, os, sys, threading, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'src'))
from metacom_pm.rl1v3.semcap import g4_context as X  # noqa: E402
from metacom_pm.rl1v3.semcap import g6_context as G6  # noqa: E402

CODE = ['scripts/rl1v3/semcap/g6_run.py', 'src/metacom_pm/rl1v3/semcap/g6_context.py',
        'src/metacom_pm/rl1v3/semcap/g4_context.py', 'src/metacom_pm/rl1v3/semcap/evidence_state.py',
        'src/metacom_pm/rl1v3/semcap/agent_skill.py', 'src/metacom_pm/rl1v3/semcap/identity.py']


def fsha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 24), b''): h.update(b)
    return h.hexdigest()


def code_shas():
    return {c: fsha(ROOT / c) for c in CODE}


def prepare(a):
    from transformers import AutoTokenizer
    fr = json.loads(Path(a.frozen).read_text())
    cands = {json.loads(s)['key']: json.loads(s) for s in Path(a.candidates).read_text().splitlines() if s.strip()}
    base = json.loads(Path(a.baseline).read_text())['spec']
    tok = AutoTokenizer.from_pretrained(a.model, local_files_only=True)
    states, checks, tokens = [], [], {}
    for f in fr['states']:
        c = cands[f['candidate_key']]
        ev = [{k: e[k] for k in ('evidence_id', 'speaker', 'text', 'reported_at', 'origin')} for e in c['evidence']]
        st = dict(state_id=f['state_id'], part=f['part'], dataset=c['dataset'], candidate_key=c['key'], owner_id=c['owner_id'],
                  family_id=c['family_id'], situation=c['situation'], current_date=c['current_date'], evidence=ev,
                  user_turn=c['user_turn'])
        states.append(st); checks.append({k: f[k] for k in ('state_id', 'part', 'dataset', 'owner_id', 'family_id', 'must_not', 'should')})
        msgs = {'A': X.generator_messages(base['system_prompt'], st)}
        if st['part'] == 'holdout':
            msgs.update(notes=X.notes_messages(st), risk=G6.risk_messages(st))
        for k, m in msgs.items():
            n = len(tok.apply_chat_template(m, tokenize=True, add_generation_prompt=True, enable_thinking=False, return_dict=False))
            assert n + base['decode']['max_new_tokens'] + 1200 <= 16384; tokens[f"{st['state_id']}/{k}"] = n
    out = Path(a.output); out.mkdir(parents=True, exist_ok=False)
    (out / 'STATES.private.jsonl').write_text(''.join(json.dumps(s, ensure_ascii=False) + '\n' for s in states))
    (out / 'CHECKS.private.json').write_text(json.dumps(dict(checks=checks, failure_taxonomy=fr['failure_taxonomy'], gate=fr['gate'],
                                                             blind_pairs=fr['blind_pairs']), indent=1, ensure_ascii=False))
    rep = dict(protocol='semcap-g6-v1', states=len(states), screen=sum(s['part'] == 'screen' for s in states),
               holdout=sum(s['part'] == 'holdout' for s in states), states_file_sha256=fsha(out / 'STATES.private.jsonl'),
               checks_file_sha256=fsha(out / 'CHECKS.private.json'), frozen_file_sha256=fsha(a.frozen),
               baseline_file_sha256=fsha(a.baseline), code_sha256=code_shas(), t1i_model_sha256=fsha(Path(a.t1i) / 'model.safetensors'),
               input_tokens=tokens, max_input_tokens=max(tokens.values()))
    (out / 'PREPARE_REPORT.json').write_text(json.dumps(rep, indent=1) + '\n')
    print(json.dumps({k: rep[k] for k in ('states', 'screen', 'holdout', 'states_file_sha256', 'max_input_tokens')}))


def run(a):
    if a.dry_run:
        ap = dict(max_llm_calls=128, max_model_loads=1, global_seconds=2400, warmup_calls=0, retry_calls=0, gpu_uuid=None,
                  states_file_sha256=fsha(a.states), code_sha256=code_shas(), t1i_model_sha256=fsha(Path(a.t1i) / 'model.safetensors'),
                  researcher_approval_path=a.states, researcher_approval_sha256=fsha(a.states))
    else:
        ap = json.loads(Path(a.approval).read_text())
    assert fsha(ap['researcher_approval_path']) == ap['researcher_approval_sha256']
    assert fsha(a.states) == ap['states_file_sha256'] and code_shas() == ap['code_sha256']
    assert fsha(Path(a.t1i) / 'model.safetensors') == ap['t1i_model_sha256']
    assert (ap['max_llm_calls'], ap['max_model_loads'], ap['global_seconds'], ap['warmup_calls'], ap['retry_calls']) == (128, 1, 2400, 0, 0)
    states = [json.loads(s) for s in Path(a.states).read_text().splitlines() if s.strip()]
    screen = [s for s in states if s['part'] == 'screen']; hold = [s for s in states if s['part'] == 'holdout']
    if a.dry_run: screen, hold = screen[:a.dry_run], hold[:a.dry_run]
    out = Path(a.run_root); out.mkdir(parents=True, exist_ok=False)
    t0 = time.monotonic(); deadline = t0 + ap['global_seconds']

    def event(**k):
        k['t'] = round(time.monotonic() - t0, 3)
        with (out / 'EVENTS.jsonl').open('a') as f: f.write(json.dumps(k) + '\n')

    def watchdog():
        while time.monotonic() < deadline: time.sleep(0.5)
        event(kind='hard_deadline_kill'); os._exit(9)
    threading.Thread(target=watchdog, daemon=True).start()
    import torch, subprocess
    from transformers import AutoTokenizer, AutoModelForMultimodalLM, GenerationConfig
    from metacom_pm.rl1v3.semcap.evidence_state import InspectClaim
    from metacom_pm.rl1v3.semcap.agent_skill import InspectClaimSkill
    uuid = None if a.dry_run else subprocess.run(['nvidia-smi', '--query-gpu=uuid', '--format=csv,noheader', '-i',
                                                  os.environ['CUDA_VISIBLE_DEVICES']], capture_output=True, text=True).stdout.strip()
    assert a.dry_run or (uuid == ap['gpu_uuid'] and torch.cuda.device_count() == 1), 'wrong device'
    base = json.loads(Path(a.baseline).read_text())['spec']; decode = base['decode']; G0E = base['system_prompt']
    torch.manual_seed(0); torch.use_deterministic_algorithms(True)
    torch.backends.cuda.matmul.allow_tf32 = False; torch.backends.cudnn.allow_tf32 = False; torch.set_num_threads(8)
    event(kind='t1i_load_start'); inspector = InspectClaim(a.t1i, device='cpu'); event(kind='t1i_load_end')
    event(kind='load_start'); ls = time.monotonic()
    tok = AutoTokenizer.from_pretrained(a.model, local_files_only=True)
    if a.dry_run:
        model = None; loads = 0
    else:
        model = AutoModelForMultimodalLM.from_pretrained(a.model, local_files_only=True, dtype=torch.bfloat16,
                                                         attn_implementation='sdpa').to('cuda:0').eval()
        torch.cuda.synchronize(); loads = 1
    event(kind='load_end', seconds=round(time.monotonic() - ls, 3))
    gc = GenerationConfig.from_pretrained(a.model, local_files_only=True)
    for k, v in decode.items():
        if k not in ('seed', 'enable_thinking'): setattr(gc, k, v)
    calls = [0]; callf = (out / 'CALLS.private.jsonl').open('x'); resf = (out / 'RESULTS.private.jsonl').open('x')

    def gen(messages, role, sid, arm):
        assert calls[0] < ap['max_llm_calls'], 'LLM call budget'
        assert time.monotonic() < deadline - 2, 'deadline'
        ids = list(tok.apply_chat_template(messages, tokenize=True, add_generation_prompt=True, enable_thinking=False, return_dict=False))
        assert len(ids) + decode['max_new_tokens'] <= 16384, 'capacity'
        calls[0] += 1; s = time.monotonic(); eos = decode['eos_token_id']
        if a.dry_run:
            last = messages[-1]['content']
            canned = {'risk': 'RISK: The user has already done what was suggested. || EVIDENCE: ' +
                              ', '.join(G6.ID_RE.findall(last.split('Use only these record IDs:')[-1])[-2:]) +
                              ' || SUBJECT: user || TIME: as_of_latest_evidence' if calls[0] % 2 else 'NONE',
                      'notes': '- [C1] something', 'reply': 'That sounds hard.'}[role]
            o = tok.encode(canned, add_special_tokens=False) + [eos[0]]
        else:
            inp = torch.tensor([ids], device='cuda:0'); torch.manual_seed(0)
            with torch.inference_mode():
                g = model.generate(inp, attention_mask=torch.ones_like(inp), generation_config=gc)
            torch.cuda.synchronize(); o = g[0, len(ids):].tolist()
        e = time.monotonic()
        stop = next((i + 1 for i, x in enumerate(o) if x in eos), len(o)); o = o[:stop]
        raw = tok.decode(o, skip_special_tokens=True); clean, leaked = X.clean_output(raw)
        rec = dict(call=calls[0], state_id=sid, arm=arm, role=role, input_tokens=len(ids), output_tokens=len(o),
                   finish='eos' if o and o[-1] in eos else 'length', seconds=round(e - s, 3), raw=raw, text=clean,
                   thinking_leak=leaked, messages=messages)
        callf.write(json.dumps(rec, ensure_ascii=False) + '\n'); callf.flush()
        event(kind='call', call=calls[0], state=sid, arm=arm, role=role, seconds=rec['seconds'], finish=rec['finish'])
        return rec

    def write(rec):
        resf.write(json.dumps(rec, ensure_ascii=False) + '\n'); resf.flush()

    # ---- phase 1: screening A
    for st in screen:
        s0 = time.monotonic(); rec = dict(phase='screen', state_id=st['state_id'], arm='A', llm_calls=[], error=None)
        try:
            r = gen(X.generator_messages(G0E, st), 'reply', st['state_id'], 'A'); rec.update(llm_calls=[r['call']], reply=r['text'],
                                                                                            reply_finish=r['finish'], reply_thinking_leak=r['thinking_leak'])
        except Exception as err:
            rec['error'] = type(err).__name__ + ': ' + str(err)
        rec['agent_seconds'] = round(time.monotonic() - s0, 3); write(rec)
    event(kind='screen_done', calls=calls[0])
    # ---- gate: wait (model stays loaded; the global deadline keeps running)
    gate = out / 'GATE_DECISION.json'
    if a.dry_run and a.dry_gate:
        Path(out / 'GATE_REVIEW.private.json').write_text('{"dry": true}')
        gate.write_text(json.dumps(dict(decision=a.dry_gate, review_sha256=fsha(out / 'GATE_REVIEW.private.json'))))
    while not gate.exists():
        time.sleep(2)
    time.sleep(1); g = json.loads(gate.read_text())
    assert g['review_sha256'] == fsha(out / 'GATE_REVIEW.private.json'), 'gate decision not bound to the review'
    event(kind='gate', decision=g['decision'])
    if g['decision'] == 'continue':
        skill = InspectClaimSkill(inspector, None) if False else None
        for st in hold:
            sid = st['state_id']; sk = InspectClaimSkill(inspector, st['situation']); vis = G6.with_u0(st)
            res = {}
            for arm in ('A', 'N'):
                s0 = time.monotonic(); rec = dict(phase='holdout', state_id=sid, arm=arm, llm_calls=[], error=None)
                try:
                    if arm == 'A':
                        r = gen(X.generator_messages(G0E, st), 'reply', sid, arm)
                    else:
                        n = gen(X.notes_messages(st), 'notes', sid, arm); rec['llm_calls'].append(n['call']); rec['notes'] = n['text']
                        r = gen(X.generator_messages(G0E, st, block=X.notes_block(n['text'])), 'reply', sid, arm)
                    rec['llm_calls'].append(r['call']); rec.update(reply=r['text'], reply_finish=r['finish'], reply_thinking_leak=r['thinking_leak'])
                except Exception as err:
                    rec['error'] = type(err).__name__ + ': ' + str(err)
                rec['agent_seconds'] = round(time.monotonic() - s0, 3); write(rec); res[arm] = rec
            # shared risk-claim formation
            s0 = time.monotonic(); form = dict(phase='holdout', state_id=sid, arm='claims', llm_calls=[], error=None)
            try:
                c = gen(G6.risk_messages(st), 'risk', sid, 'claims'); form['llm_calls'].append(c['call'])
                none = G6.is_none(c['text'])
                claims, rejects = ([], []) if none else G6.parse_risk(c['text'], X.allowed_ids(vis))
                for cl in claims:
                    cl['evidence_ids'], cl['auto_added_ids'] = G6.link_qa(vis, cl['evidence_ids'])
                form.update(raw_text=c['text'], none=none, claims=claims, claim_rejects=rejects, parse_failure=(not none and not claims))
            except Exception as err:
                form['error'] = type(err).__name__ + ': ' + str(err); claims = []
            form['seconds'] = round(time.monotonic() - s0, 3); write(form)
            results = []; traces = []; isec = 0.0
            for cl in claims:
                act = {k: cl[k] for k in ('action', 'claim', 'evidence_ids', 'subject', 'time_scope')}
                s1 = time.perf_counter()
                try:
                    r, _, tr = sk.invoke(vis, act, {})
                    results.append(dict(judgement=r['judgement'], conflict=r.get('conflict')))
                    tr['result'] = {k: r.get(k) for k in ('judgement', 'probabilities', 'per_item', 'chunked_windows', 'unresolved')}
                except Exception as err:
                    results.append(dict(judgement='unprocessed', conflict=None)); tr = dict(action=act, error=str(err))
                tr['seconds'] = round(time.perf_counter() - s1, 4); isec += tr['seconds']; traces.append(tr)
            for arm, block in (('B_prime', G6.claims_block(claims, results)), ('P', G6.claims_block(claims))):
                s0 = time.monotonic(); rec = dict(phase='holdout', state_id=sid, arm=arm, llm_calls=[], error=None, block=block,
                                                  claims_from_call=form['llm_calls'], inspect=traces if arm == 'B_prime' else None,
                                                  inspect_seconds=round(isec, 4) if arm == 'B_prime' else 0.0)
                try:
                    if block is None:
                        rec.update(reply=res['A'].get('reply'), reply_finish=res['A'].get('reply_finish'), reused_A_reply=True,
                                   reply_thinking_leak=res['A'].get('reply_thinking_leak'))
                    else:
                        r = gen(X.generator_messages(G0E, st, block=block), 'reply', sid, arm); rec['llm_calls'].append(r['call'])
                        rec.update(reply=r['text'], reply_finish=r['finish'], reply_thinking_leak=r['thinking_leak'], reused_A_reply=False)
                except Exception as err:
                    rec['error'] = type(err).__name__ + ': ' + str(err)
                rec['agent_seconds'] = round(time.monotonic() - s0, 3); write(rec)
    total = time.monotonic() - t0
    (out / 'RUN_SUMMARY.json').write_text(json.dumps(dict(status='FINISHED', gate=g['decision'], llm_calls=calls[0], model_loads=loads,
        t1i_cpu_loads=1, warmup_calls=0, retry_calls=0, wall_seconds=round(total, 3), gpu_uuid=uuid, dry_run=bool(a.dry_run),
        peak_allocated_bytes=None if a.dry_run else torch.cuda.max_memory_allocated()), indent=1) + '\n')
    event(kind='finished', calls=calls[0]); print('FINISHED', g['decision'], calls[0], round(total, 1))


if __name__ == '__main__':
    p = argparse.ArgumentParser(); sub = p.add_subparsers(dest='cmd', required=True)
    q = sub.add_parser('prepare')
    for n in ('frozen', 'candidates', 'baseline', 'model', 't1i', 'output'): q.add_argument('--' + n, required=True)
    q = sub.add_parser('run')
    for n in ('states', 'baseline', 'model', 't1i', 'run-root'): q.add_argument('--' + n, required=True)
    q.add_argument('--approval'); q.add_argument('--dry-run', type=int, default=0); q.add_argument('--dry-gate', default=None)
    a = p.parse_args()
    prepare(a) if a.cmd == 'prepare' else run(a)
