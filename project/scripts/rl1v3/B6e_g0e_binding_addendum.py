"""B6e plan v3 -> G0e terminal identity binding ADDENDUM (``pmrl1v3-b6e-g0e-binding-addendum-v1``). CPU only.

PLAN_V3_FROZEN.json / REAL_KEYS_CHECK.json and the formal B5 replay bind the 120 terminals of the 8
selected prefixes to the old tokenizer-only replay identity.  WS-A's G0e (PR #10) changes renderer,
Step-2, g_id and decode_id.  This addendum, written once next to (never over) those files:
* uses WS-A's formal ``generator.g0e_port.make_port_factory`` and ``render.request_packet``;
* re-runs the full B5 v2 replay checks (provenance, owner/time/family, spans, native tokens, capacity,
  order invariance, A replay(key), independent reload, pending) on the G0e port for the 8 prefixes;
* rebuilds every reachable TerminalKey / ExecutionTrace and the request packet; checks key/trace/billing
  equality, the runtime context bound, and that the model payload holds no future text, private ids,
  NeedCard / checklist / judge content;
* compares with the old identity: version fields may differ, record groups / reading bodies must not;
* proves old-identity rewards cannot be reused (old-key table -> PendingTerminal for every new key).
If any prefix's reachable count differs from the preregistered selection, it STOPS (exit 2) and reports;
the sampling plan is never rewritten.  No generation, no reward, every STOP pending.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
REPO = PROJECT.parent
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.rl1v3 import contracts as K  # noqa: E402
from metacom_pm.rl1v3.env import finite_head as E  # noqa: E402
from metacom_pm.rl1v3.env.bank_replay_v2 import replay_prefix  # noqa: E402
from metacom_pm.rl1v3.env.c0_binding import DOMAIN, C0FiniteHeadEnv, TerminalIdentity, TerminalTable  # noqa: E402
from metacom_pm.rl1v3.evaluate import terminal_registry as TR  # noqa: E402
from metacom_pm.rl1v3.io import build_manifest, file_sha256, object_sha256, sha256_text, write_json_once, write_jsonl_once  # noqa: E402
from metacom_pm.rl1v3.train.real_instances import _replay  # noqa: E402

PROTOCOL = "pmrl1v3-b6e-g0e-binding-addendum-v1"
V3 = PROJECT / "outputs/pm_rl1/v3"
PLAN_DIR = V3 / "B6e_plan/v3"
FORMAL_REPLAY = V3 / "WSB_S3/integration_acceptance_320a33d1/B5/replay_reports.jsonl"
VERSION_FIELDS = ("bank_version", "index_version", "renderer_id", "step2_id", "g_id", "decode_id")


def git(*a):
    return subprocess.run(["git", *a], cwd=REPO, capture_output=True, text=True).stdout.strip()


def jl(p):
    return [json.loads(x) for x in Path(p).read_text().splitlines()]


def forbidden_markers():
    """Strings that only exist on the evaluation side; none may reach a G0e payload."""
    from metacom_pm.rl1v3.checklist import writer_v3 as CW3
    from metacom_pm.rl1v3.judge import protocol_v3 as JP3
    from metacom_pm.rl1v3.needs import protocol_v2 as W
    out = ["NeedCard", "needcard", "checklist", "RESOURCES_GIVEN_TO_REPLY", "METHOD_LABELS", "evaluation_only",
           "must_not_contradict", "relevant_optional", "history_conflict", "\"verdict\"", "PAST_SESSIONS"]
    out += [JP3.SYSTEM_PROMPT[:80], W.SYSTEM_PROMPT[:80], CW3.R_TEXT[:60]] + [t[:60] for _, t in CW3.FIXED_I]
    return out


def payload_leaks(payload: dict, *, prefix, private_ids, future_texts, markers) -> list[str]:
    if set(payload) != {"messages", "input_ids", "decode"}:
        return [f"payload_keys:{sorted(payload)}"]
    text = "\n".join(m["content"] for m in payload["messages"])
    bad = [f"private_id:{i[:16]}" for i in private_ids if i and i in text]
    bad += [f"future_text:{sha256_text(t)[:12]}" for t in future_texts if t in text]
    bad += [f"evaluation_marker:{m[:24]}" for m in markers if m in text]
    return bad


def private_ids_of(port, prefix, records):
    """Prefix/owner/session ids, every source id of the owner, delivered record ids and their source ids."""
    reg = port.bank.registry
    ids = {prefix.prefix_id, prefix.owner_id, prefix.session_id, prefix.runtime_sha256, prefix.family_id}
    ids |= {e.source_id for e in reg.entries if e.source.owner_id == prefix.owner_id}
    ids |= {e.source.session_id for e in reg.entries if e.source.owner_id == prefix.owner_id}
    ids |= set(records)
    return {i for i in ids if isinstance(i, str) and len(i) >= 6}


def future_texts_of(port, prefix, *, min_len=24):
    """Current-session turns after the cut and every later session of the owner (never visible).

    A future utterance that is verbatim identical to a legally visible one (the visible prefix or a
    strictly-past session, e.g. a supporter's fixed greeting) cannot identify future information and
    is reported separately, not checked.  -> (texts to check, count shared with legal text)."""
    reg = port.bank.registry
    cur = reg.entry(prefix.owner_id, prefix.session_id).source
    out = [t.text for t in cur.turns if t.turn_index > prefix.cut_turn]
    legal = {t.text for t in prefix.turns}
    for e in reg.entries:
        if e.source.owner_id != prefix.owner_id:
            continue
        if e.source.chronological_rank > prefix.cutoff_rank:
            out += [t.text for t in e.source.turns]
        elif e.source.chronological_rank < prefix.cutoff_rank:
            legal |= {t.text for t in e.source.turns}
    fut = {t for t in out if len(t) >= min_len}
    return sorted(fut - legal), len(fut & legal)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(V3 / "B6e_plan/v3_g0e_addendum"))
    args = ap.parse_args()
    out = Path(args.out)
    from metacom_pm.rl1v3.bank import v0_port as AP
    from metacom_pm.rl1v3.generator import g0e_port as GP
    sel = json.loads((PLAN_DIR / "SELECTION.json").read_text())
    plan = json.loads((PLAN_DIR / "PLAN_V3_FROZEN.json").read_text())
    old_rep = {r["prefix_id"]: r for r in jl(FORMAL_REPLAY)}
    cov = {r["prefix_id"]: r for r in jl(V3 / "B1/coverage_sample_v1.jsonl")}
    f, f2 = GP.make_port_factory(root=REPO), GP.make_port_factory(root=REPO)    # second: independent reload
    old_f = AP.make_port_factory(root=REPO)
    binding = f.binding
    new_ident = TerminalIdentity(**{k: v for k, v in f.for_prefix(f.prefix(cov[sel["selected_ids"][0]])).identity.items()
                                    if k in VERSION_FIELDS})
    markers = forbidden_markers()
    reports, terms, summary_rows, stop = [], [], [], None
    for pid in sel["selected_ids"]:
        row, old = cov[pid], old_rep[pid]
        p, p2, po = f.prefix(row), f2.prefix(row), old_f.prefix(row)
        rep = replay_prefix(lambda: f.for_prefix(p), fresh_factory=lambda: f2.for_prefix(p2),
                            meta=dict(rank_bucket=row["rank_bucket"], selection="B6e-v3"))
        reports.append(rep)
        want = next(c["terminals"] for c in sel["selected"] if c["prefix_id"] == pid)
        port, oport = f.for_prefix(p), old_f.for_prefix(po)
        env = C0FiniteHeadEnv(prefix=p, history_sessions=p.cutoff_rank, availability=dict(port.availability()),
                              read=lambda h, acquired, q=port: q.read(h, acquired=acquired), identity=new_ident,
                              table=TerminalTable({}, table_id="g0e-addendum-pending"), prefix_tokens=port.base_tokens,
                              read_takes_acquired=True, dynamic_mask=port.action_mask)
        oenv = C0FiniteHeadEnv(prefix=po, history_sessions=po.cutoff_rank, availability=dict(oport.availability()),
                               read=lambda h, acquired, q=oport: q.read(h, acquired=acquired),
                               identity=TerminalIdentity(**{k: old["identity"][k] for k in VERSION_FIELDS}),
                               table=TerminalTable({}, table_id="old-replay"), prefix_tokens=oport.base_tokens,
                               read_takes_acquired=True, dynamic_mask=oport.action_mask)
        old_table = TerminalTable({k: E.TerminalOutcome(reward=0.5, key_sha256=k) for k in old["key_by_subset"].values()},
                                  table_id="old-identity-rewards-must-not-transfer")
        fut, fut_shared = future_texts_of(port, p)
        checks = dict(reachable_new=rep["n_reachable"], reachable_preregistered=want, replay_passed=rep["passed"],
                      replay_failures=rep["failures"], future_texts_checked=len(fut),
                      future_texts_identical_to_legal_text=fut_shared, failures=[])
        reach_masks = sorted(E.mask_of(() if s == "OFF" else s.split("+")) for s in rep["key_by_subset"])
        if rep["n_reachable"] != want or sorted(rep["key_by_subset"]) != sorted(old["key_by_subset"]):
            stop = stop or f"reachable_changed:{pid[:12]}:{want}->{rep['n_reachable']}"
        for m in reach_masks:
            name = TR.subset_name(m)
            s, so = _replay(env, m), _replay(oenv, m)
            key, trace = env.terminal_key(s), env.execution_trace(s)
            okey = oenv.terminal_key(so)
            pk = port.request_packet(env.readings(s))
            led = pk.token_ledger
            fail = []
            if pk.key != key or pk.trace != trace:
                fail.append("packet_key_or_trace_differs_from_env")
            if led["billed_input_tokens"] != s.input_tokens:
                fail.append("billing_differs")
            if led["total_context_bound"] > led["runtime_context_tokens"]:
                fail.append("runtime_context_exceeded")
            if tuple(pk.input_ids) != tuple(port.tokenizer.encode_messages([dict(role=r, content=c) for r, c in pk.message_pairs])):
                fail.append("input_ids_not_the_rendered_messages")
            if pk.payload()["decode"] != binding.spec["decode"]:
                fail.append("decode_differs_from_binding")
            rids = [rid for g in key.acquired for rid in g]
            fail += payload_leaks(pk.payload(), prefix=p, private_ids=private_ids_of(port, p, rids), future_texts=fut,
                                  markers=markers)
            if key.acquired != okey.acquired:
                fail.append("record_groups_differ_from_old_replay")
            if [sha256_text(r.reading_text) for r in trace.readings] != [sha256_text(r.public_view.reading_text) for r in so.readings]:
                fail.append("reading_bodies_differ_from_old_replay")
            if [r.tokens for r in trace.readings] != [r.public_view.tokens for r in so.readings]:
                fail.append("reading_tokens_differ_from_old_replay")
            if okey.sha256 != old["key_by_subset"][name]:
                fail.append("old_key_not_reproduced")
            if key.sha256 in old["key_by_subset"].values():
                fail.append("new_key_equals_an_old_key")
            try:
                old_table.lookup(key)
                fail.append("old_reward_reusable")
            except E.PendingTerminal:
                pass
            try:
                env.step(s, E.STOP)
                fail.append("stop_not_pending")
            except E.PendingTerminal:
                pass
            bodies = port.records(rids)
            terms.append(dict(prefix_id=pid, subset=name, key_sha256=key.sha256, trace_sha256=trace.sha256,
                              request_sha256=pk.request_sha256, old_key_sha256=okey.sha256,
                              record_groups=[list(g) for g in key.acquired],
                              record_body_sha256={rid: sha256_text(r.body) for rid, r in sorted(bodies.items())},
                              reading_sha256=[sha256_text(r.reading_text) for r in trace.readings],
                              reading_tokens=[r.tokens for r in trace.readings], input_tokens_new=s.input_tokens,
                              input_tokens_old=so.input_tokens, token_ledger=led, failures=fail))
            checks["failures"] += [f"{name}:{x}" for x in fail]
        summary_rows.append(dict(prefix_id=pid, **checks, terminals=len(reach_masks),
                                 passed=rep["passed"] and not checks["failures"] and rep["n_reachable"] == want))
    old_id = {k: next(iter(old_rep.values()))["identity"][k] for k in VERSION_FIELDS}
    new_id = {k: getattr(new_ident, k) for k in VERSION_FIELDS}
    rec = dict(
        protocol=PROTOCOL, amends=dict(plan_v3_sha256=plan["plan_sha256"], selection_sha256=sel["selection_sha256"],
                                       plan_file_sha256=file_sha256(PLAN_DIR / "PLAN_V3_FROZEN.json"),
                                       real_keys_check_sha256=file_sha256(PLAN_DIR / "REAL_KEYS_CHECK.json"),
                                       overwritten=False),
        g0e=dict(protocol=binding.spec["protocol"], binding_sha256=binding.sha256, identity=binding.identity,
                 decode=binding.spec["decode"], runtime_max_model_len=binding.spec["runtime"]["max_model_len"],
                 request_packet_protocol="pmrl1v3-g0e-request-packet-1", read_port="pmrl1v3-g0e-read-port-1"),
        identity_old=old_id, identity_new=new_id,
        identity_fields_changed=sorted(k for k in VERSION_FIELDS if old_id[k] != new_id[k]),
        prefixes=summary_rows, terminals=len(terms), terminals_preregistered=sel["terminals"],
        status=("stopped:" + stop) if stop else ("passed" if all(r["passed"] for r in summary_rows) else "failed"),
        old_rewards_reusable=False, terminal_outcomes="all pending (no generation)",
        code_head=git("rev-parse", "HEAD"), model_calls=0, gpu_used=False, evidence_tier="engineering_only")
    rec["addendum_sha256"] = object_sha256({k: v for k, v in rec.items() if k != "code_head"})
    write_jsonl_once(out / "G0E_REPLAY_REPORTS.jsonl", reports)
    write_jsonl_once(out / "G0E_TERMINALS.jsonl", terms)
    write_json_once(out / "G0E_BINDING_ADDENDUM.json", rec)
    man = None if not out.is_relative_to(PROJECT) else build_manifest(task="B6e_g0e_binding_addendum", root=PROJECT,
                         inputs={"selection": PLAN_DIR / "SELECTION.json", "plan_v3": PLAN_DIR / "PLAN_V3_FROZEN.json",
                                 "real_keys_check": PLAN_DIR / "REAL_KEYS_CHECK.json", "formal_replay": FORMAL_REPLAY,
                                 "g0e_config": REPO / "project/configs/rl1v3/G0e.json"},
                         outputs=[out / "G0E_REPLAY_REPORTS.jsonl", out / "G0E_TERMINALS.jsonl", out / "G0E_BINDING_ADDENDUM.json"],
                         code=[PROJECT / "scripts/rl1v3/B6e_g0e_binding_addendum.py",
                               PROJECT / "src/metacom_pm/rl1v3/env/bank_replay_v2.py",
                               PROJECT / "src/metacom_pm/rl1v3/generator/g0e_port.py",
                               PROJECT / "src/metacom_pm/rl1v3/generator/g0e.py",
                               PROJECT / "src/metacom_pm/rl1v3/render/request_packet.py"], code_sha=rec["code_head"])
    if out.is_relative_to(PROJECT):
        write_json_once(out / "manifest.json", dict(man, model_calls=0, gpu_used=False, status=rec["status"]))
    print(json.dumps({k: rec[k] for k in ("status", "identity_fields_changed", "terminals", "terminals_preregistered",
                                          "addendum_sha256")}, indent=1))
    print(json.dumps([dict(p=r["prefix_id"][:12], new=r["reachable_new"], pre=r["reachable_preregistered"],
                           passed=r["passed"], failures=r["failures"][:3] + r["replay_failures"][:3]) for r in summary_rows], indent=1))
    sys.exit(2 if stop else 0 if rec["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
