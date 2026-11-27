#!/usr/bin/env python3
"""G4 semantic-skill system contrast (approved 2026-11-27: A6000, <=112 LLM calls, 1 load, 1800 s).

  prepare (CPU)  frozen states -> STATES (runtime input; no check items, no references),
                 static prompts tokenized, capacity checked, code/data hashes recorded.
  run     (GPU)  admit -> load T1i (CPU) -> one Gemma load -> per state, arms in fixed order
                 A, N, B, C -> stop. 0 warmup, 0 retry; watchdog kills at the hard limit.

Arms (same records, identity contract, Generator weights, greedy decode, max_new_tokens 320):
  A  RAW -> G                                             1 LLM call
  N  notes call -> G with notes                           2 LLM calls
  B  claim-formation call (1-3 claims) -> INSPECT_CLAIM (T1i, CPU) on every claim -> G with note
                                                          2 LLM calls
  C  G first pass with the CHECK option: direct reply (1 LLM call) or CHECK lines ->
     INSPECT_CLAIM -> G with note (2 LLM calls). A real fast path: skipping avoids an LLM call.
No human-written claims, gold evidence, hidden answers or future turns are runtime inputs.
"""
import argparse, hashlib, json, os, sys, threading, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'src'))
from metacom_pm.rl1v3.semcap import g4_context as X  # noqa: E402

CODE = ['scripts/rl1v3/semcap/g4_run.py', 'src/metacom_pm/rl1v3/semcap/g4_context.py',
        'src/metacom_pm/rl1v3/semcap/evidence_state.py', 'src/metacom_pm/rl1v3/semcap/agent_skill.py',
        'src/metacom_pm/rl1v3/semcap/identity.py']
ARM_ORDER = ('A', 'N', 'B', 'C')


def fsha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 24), b''): h.update(b)
    return h.hexdigest()


def code_shas():
    return {c: fsha(ROOT / c) for c in CODE}


def prepare(a):
    from transformers import AutoTokenizer
    frozen = json.loads(Path(a.frozen).read_text())
    cands = [json.loads(s) for s in Path(a.candidates).read_text().splitlines() if s.strip()]
    by = {d: [c for c in cands if c['dataset'] == d] for d in ('ESConv', 'EvoEmo')}
    base = json.loads(Path(a.baseline).read_text())['spec']
    tok = AutoTokenizer.from_pretrained(a.model, local_files_only=True)
    states, checks, tokens = [], [], {}
    for f in frozen['states']:
        c = by[f['dataset']][f['index']]
        ev = [{k: e[k] for k in ('evidence_id', 'speaker', 'text', 'reported_at', 'origin')} for e in c['evidence']]
        st = dict(state_id=f['state_id'], dataset=f['dataset'], candidate_key=c['key'], owner_id=c['owner_id'],
                  family_id=c['family_id'], history_family_ids=c['history_family_ids'], situation=c['situation'],
                  current_date=c['current_date'], evidence=ev, user_turn=c['user_turn'], cutoff_turn=c['cutoff_turn'])
        states.append(st); checks.append(dict(state_id=f['state_id'], group=f['group'], must_not=f['must_not'], should=f['should']))
        for name, msgs in (('A_G', X.generator_messages(base['system_prompt'], st)),
                           ('C_first', X.generator_messages(base['system_prompt'], st, tool=True)),
                           ('N_notes', X.notes_messages(st)), ('B_claims', X.controller_messages(st))):
            n = len(tok.apply_chat_template(msgs, tokenize=True, add_generation_prompt=True, enable_thinking=False, return_dict=False))
            assert n + base['decode']['max_new_tokens'] + 1200 <= 16384, (st['state_id'], name, n)  # 1200 reserved for notes/checks
            tokens[f"{st['state_id']}/{name}"] = n
    out = Path(a.output); out.mkdir(parents=True, exist_ok=False)
    (out / 'STATES.private.jsonl').write_text(''.join(json.dumps(s, ensure_ascii=False) + '\n' for s in states))
    (out / 'CHECKS.private.json').write_text(json.dumps(dict(checks=checks, blind_pairs=frozen['blind_pairs_frozen'],
                                                             evaluation_rules=frozen['evaluation_rules']), indent=1, ensure_ascii=False))
    rep = dict(protocol='semcap-g4-v1', states=len(states), states_file_sha256=fsha(out / 'STATES.private.jsonl'),
               checks_file_sha256=fsha(out / 'CHECKS.private.json'), frozen_file_sha256=fsha(a.frozen),
               candidates_file_sha256=fsha(a.candidates), baseline_file_sha256=fsha(a.baseline), code_sha256=code_shas(),
               t1i_checkpoint=a.t1i, t1i_model_sha256=fsha(Path(a.t1i) / 'model.safetensors'), input_tokens=tokens,
               groups={g: [c['state_id'] for c in checks if c['group'] == g] for g in 'SUHO'},
               datasets={d: sum(s['dataset'] == d for s in states) for d in ('ESConv', 'EvoEmo')})
    (out / 'PREPARE_REPORT.json').write_text(json.dumps(rep, indent=1) + '\n')
    print(json.dumps({k: rep[k] for k in ('states', 'states_file_sha256', 'groups', 'datasets')}, indent=1))
    print('max input tokens', max(tokens.values()))


def run(a):
    if a.dry_run:   # CPU bookkeeping check with canned LLM text; no GPU, no Gemma load, no approval used
        ap = dict(max_llm_calls=112, max_model_loads=1, global_seconds=1800, warmup_calls=0, retry_calls=0,
                  gpu_uuid=None, researcher_approval_path=a.states, researcher_approval_sha256=fsha(a.states),
                  states_file_sha256=fsha(a.states), code_sha256=code_shas(), t1i_model_sha256=fsha(Path(a.t1i) / 'model.safetensors'))
        prep = dict(states_file_sha256=fsha(a.states))
    else:
        ap = json.loads(Path(a.approval).read_text()); prep = json.loads(Path(a.prepare_report).read_text())
    assert fsha(ap['researcher_approval_path']) == ap['researcher_approval_sha256'], 'approval evidence'
    assert fsha(a.states) == ap['states_file_sha256'] == prep['states_file_sha256'], 'states not approved'
    assert code_shas() == ap['code_sha256'], 'code changed after approval'
    assert fsha(Path(a.t1i) / 'model.safetensors') == ap['t1i_model_sha256']
    assert (ap['max_llm_calls'], ap['max_model_loads'], ap['global_seconds'], ap['warmup_calls'], ap['retry_calls']) == (112, 1, 1800, 0, 0)
    states = [json.loads(s) for s in Path(a.states).read_text().splitlines() if s.strip()]
    if a.dry_run: states = states[:a.dry_run]
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
    from metacom_pm.rl1v3.semcap.agent_skill import InspectClaimSkill, generator_note
    uuid = None if a.dry_run else subprocess.run(['nvidia-smi', '--query-gpu=uuid', '--format=csv,noheader', '-i',
                          os.environ['CUDA_VISIBLE_DEVICES']], capture_output=True, text=True).stdout.strip()
    assert a.dry_run or (uuid == ap['gpu_uuid'] and torch.cuda.device_count() == 1), 'wrong device'
    base = json.loads(Path(a.baseline).read_text())['spec']; decode = base['decode']; G0E = base['system_prompt']
    torch.manual_seed(0); torch.use_deterministic_algorithms(True)
    torch.backends.cuda.matmul.allow_tf32 = False; torch.backends.cudnn.allow_tf32 = False
    torch.set_num_threads(8)
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
            canned = {'claims': 'thought\nCLAIM: The user has talked about it with someone. || EVIDENCE: ' + ', '.join(X.ID_RE.findall(messages[-1]['content'])[-3:]) + ', Z9 || SUBJECT: user || TIME: as_of_latest_evidence',
                      'first': 'CHECK: The user did it. || EVIDENCE: ' + ', '.join(X.ID_RE.findall(messages[1]['content'])[-2:]) + ' || SUBJECT: user || TIME: as_of_latest_evidence' if calls[0] % 4 != 2 else 'That sounds hard.',
                      'notes': '- [C1] the user said something', 'reply': 'That sounds really hard.'}[role]
            o = tok.encode(canned, add_special_tokens=False) + [eos[0]]
        else:
            inp = torch.tensor([ids], device='cuda:0'); torch.manual_seed(0)
            with torch.inference_mode():
                g = model.generate(inp, attention_mask=torch.ones_like(inp), generation_config=gc)
            torch.cuda.synchronize()
            o = g[0, len(ids):].tolist()
        e = time.monotonic()
        stop = next((i + 1 for i, x in enumerate(o) if x in eos), len(o)); o = o[:stop]
        raw = tok.decode(o, skip_special_tokens=True); clean, leaked = X.clean_output(raw)
        rec = dict(call=calls[0], state_id=sid, arm=arm, role=role, input_tokens=len(ids), output_tokens=len(o),
                   finish='eos' if o and o[-1] in eos else 'length', seconds=round(e - s, 3), raw=raw, text=clean,
                   thinking_leak=leaked, messages=messages)
        callf.write(json.dumps(rec, ensure_ascii=False) + '\n'); callf.flush()
        event(kind='call', call=calls[0], state=sid, arm=arm, role=role, seconds=rec['seconds'], finish=rec['finish'])
        return rec

    def inspect_all(st, claims, sid, arm):
        skill = InspectClaimSkill(inspector, st['situation']); wm = {}; traces = []; secs = 0.0
        for c in claims:
            act = {k: c[k] for k in ('action', 'claim', 'evidence_ids', 'subject', 'time_scope')}
            s = time.perf_counter()
            try:
                res, wm, tr = skill.invoke(st['evidence'], act, wm)
                tr['result'] = {k: res.get(k) for k in ('judgement', 'probabilities', 'per_item', 'chunked_windows',
                                                        'unresolved', 'excluded_external_ids')}
            except Exception as err:   # runtime/validation failure is technical, never not_established
                tr = dict(action=act, error=type(err).__name__ + ': ' + str(err), result_judgement='unprocessed')
            tr['seconds'] = round(time.perf_counter() - s, 4); secs += tr['seconds']; traces.append(tr)
        return wm, traces, secs

    for st in states:
        sid = st['state_id']
        for arm in ARM_ORDER:
            s0 = time.monotonic(); rec = dict(state_id=sid, arm=arm, llm_calls=[], inspect=None, error=None)
            try:
                if arm == 'A':
                    r = gen(X.generator_messages(G0E, st), 'reply', sid, arm); rec['llm_calls'].append(r['call']); final = r
                elif arm == 'N':
                    n = gen(X.notes_messages(st), 'notes', sid, arm); rec['llm_calls'].append(n['call'])
                    rec['notes'] = n['text']
                    r = gen(X.generator_messages(G0E, st, block=X.notes_block(n['text'])), 'reply', sid, arm)
                    rec['llm_calls'].append(r['call']); final = r
                elif arm == 'B':
                    c = gen(X.controller_messages(st), 'claims', sid, arm); rec['llm_calls'].append(c['call'])
                    claims, rejects = X.parse_claims(c['text'], 'CLAIM', X.allowed_ids(st['evidence']), 3)
                    wm, traces, secs = inspect_all(st, claims, sid, arm)
                    note = generator_note(wm)
                    rec.update(claims=claims, claim_rejects=rejects, inspect=traces, inspect_seconds=round(secs, 4),
                               wm=wm, note=note, decision='fixed_check', parse_failure=not claims)
                    r = gen(X.generator_messages(G0E, st, block=note or None), 'reply', sid, arm)
                    rec['llm_calls'].append(r['call']); final = r
                else:
                    f = gen(X.generator_messages(G0E, st, tool=True), 'first', sid, arm); rec['llm_calls'].append(f['call'])
                    if X.wants_check(f['text']):
                        claims, rejects = X.parse_claims(f['text'], 'CHECK', X.allowed_ids(st['evidence']), 2)
                        wm, traces, secs = inspect_all(st, claims, sid, arm)
                        note = generator_note(wm)
                        rec.update(decision='check', claims=claims, claim_rejects=rejects, inspect=traces,
                                   inspect_seconds=round(secs, 4), wm=wm, note=note, parse_failure=not claims)
                        r = gen(X.generator_messages(G0E, st, block=note or None), 'reply', sid, arm)
                        rec['llm_calls'].append(r['call']); final = r
                    else:
                        rec.update(decision='direct_reply', claims=[], inspect=[], inspect_seconds=0.0)
                        final = f
                rec['reply'] = final['text']; rec['reply_finish'] = final['finish']; rec['reply_thinking_leak'] = final['thinking_leak']
            except Exception as err:
                rec['error'] = type(err).__name__ + ': ' + str(err); event(kind='arm_error', state=sid, arm=arm, error=rec['error'])
            rec['agent_seconds'] = round(time.monotonic() - s0, 3)
            resf.write(json.dumps(rec, ensure_ascii=False) + '\n'); resf.flush()
    total = time.monotonic() - t0
    (out / 'RUN_SUMMARY.json').write_text(json.dumps(dict(status='FINISHED', llm_calls=calls[0], model_loads=loads,
        t1i_cpu_loads=1, warmup_calls=0, retry_calls=0, wall_seconds=round(total, 3), gpu_uuid=uuid,
        peak_allocated_bytes=None if a.dry_run else torch.cuda.max_memory_allocated(), dry_run=bool(a.dry_run)), indent=1) + '\n')
    event(kind='finished', calls=calls[0]); print('FINISHED', calls[0], round(total, 1))


if __name__ == '__main__':
    p = argparse.ArgumentParser(); sub = p.add_subparsers(dest='cmd', required=True)
    q = sub.add_parser('prepare')
    for n in ('frozen', 'candidates', 'baseline', 'model', 't1i', 'output'): q.add_argument('--' + n, required=True)
    q = sub.add_parser('run')
    for n in ('states', 'baseline', 'model', 't1i', 'run-root'): q.add_argument('--' + n, required=True)
    q.add_argument('--prepare-report'); q.add_argument('--approval'); q.add_argument('--dry-run', type=int, default=0)
    a = p.parse_args()
    prepare(a) if a.cmd == 'prepare' else run(a)
