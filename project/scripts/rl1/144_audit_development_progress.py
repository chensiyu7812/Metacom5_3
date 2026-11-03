#!/usr/bin/env python3
"""Read-only, source-bound S/A progress and reuse of existing human references.

Each invocation writes a new snapshot. It neither sends requests nor selects a
reward route, opens sealed labels, modifies old answers, or grants qualification.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / 'src'))
from metacom_pm.rl1.development_feedback import thaw_inputs, candidate_scores
from metacom_pm.rl1.development_dispatch import DevelopmentBudget
from metacom_pm.rl1.feedback_score_audit import decision
from metacom_pm.rl1.diagnostic_support import nanodollars, usd
from metacom_pm.rl1.human_reference_reuse import reuse_map
from metacom_pm.rl1.schema import digest
from metacom_pm.rl1.supervised_learning import save_json


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def single_comparison(score, reference):
    """An interval is set membership, never an invented midpoint target."""
    available = score is not None
    q_ok = None if not available else (
        score['q'] == reference['q_value'] if reference['q_status'] == 'single'
        else reference['q_min'] <= score['q'] <= reference['q_max'])
    m_ok = None if not available else score['m'] == reference['m_value']
    return dict(reference_id=reference['record_id'], reference_source=reference['source'],
                q_status=reference['q_status'], q_value=reference['q_value'],
                q_interval=[reference['q_min'], reference['q_max']] if reference['q_status'] == 'range' else None,
                human_m=reference['m_value'], candidate=score, q_agrees=q_ok, m_agrees=m_ok,
                both_agree=(q_ok and m_ok) if available else None,
                scope='existing exposed development reference; not qualification')


def audit(package, bank_root, output):
    if output.exists():
        raise ValueError('new immutable snapshot directory required')
    config = read(package / 'J_CONFIG_PRIVATE.json')
    materials, adapter = thaw_inputs(config['inputs'])
    policy = config['policy']; root = Path(policy['run_directory'])
    protocol = read(root / 'PROTOCOL.json')
    if (digest(protocol) != config['protocol_identity'] or protocol['adapter'] != adapter.identity
            or protocol['financial_policy'] != policy):
        raise ValueError('stage identity changed')
    rows = protocol['mapping']
    items = {m['key']: {k:m[k] for k in ('reply', 'evidence')} for m in materials}
    if len(items) != len(materials) or set(items) != {r['key'] for r in rows}:
        raise ValueError('material mapping changed')
    by_slot = {r['logical_identity']:items[r['key']] for r in rows}
    values = {k:{} for k in ('S', 'A', 'R')}; attempts = []; journals = {}
    for component in ('S', 'A', 'R'):
        folder = root / component; dbpath = folder / 'attempts.sqlite'
        values[component] = {}
        if not dbpath.exists():
            continue
        requests = read(folder / 'REQUESTS.json')
        with sqlite3.connect('file:' + str(dbpath.resolve()) + '?mode=ro', uri=True) as db:
            meta = dict(db.execute('SELECT key,value FROM meta'))
            stored = db.execute('SELECT claim,result FROM attempts ORDER BY rowid').fetchall()
        journals[component] = dict(snapshot_utc=datetime.now(timezone.utc).isoformat(),
                                   rows=len(stored), schedule_identity=meta['identity'])
        for claim_json, result_json in stored:
            claim = json.loads(claim_json); result = json.loads(result_json) if result_json else None
            aid, slot = claim['attempt_id'], claim['slot_id']
            core = {k:v for k,v in claim.items() if k not in ('attempt_id', 'reservation')}
            request = requests[slot]; item = by_slot[slot]
            primary = values['S'].get(slot); review = values['A'].get(slot)
            rebuilt = adapter.prepare(item, component,
                score=primary['value'] if component != 'S' and primary else None,
                review=review['value'] if component == 'R' and review else None)
            if (aid != digest(core) or claim['protocol_identity'] != config['protocol_identity']
                    or claim['schedule_identity'] != meta['identity'] or rebuilt != request
                    or claim['input_identity'] != request['identity']):
                raise ValueError('claim/request/source binding changed')
            row = dict(component=component, attempt_id=aid, logical_identity=slot,
                       ordinal=claim['ordinal'], settled=result is not None)
            if result is not None:
                record = read(folder / (aid + '.result.json'))
                raw = read(folder / (aid + '.raw.json'))
                if (digest(record) != result['result_identity'] or digest(raw) != record['raw_identity']
                        or raw['attempt_id'] != aid or raw['request_identity'] != request['identity']
                        or raw['adapter_identity'] != adapter.identity):
                    raise ValueError('raw/result/journal binding changed')
                evaluated = adapter.evaluate(request, item, raw,
                    score=primary['value'] if component == 'A' else None)
                if record.get('outcome') != 'global_risk' and evaluated != record['evaluation']:
                    raise ValueError('stored evaluation differs from current exact reparse')
                e = record['evaluation']
                row.update(outcome=result['outcome'], technical_valid=e['technical_valid'],
                           model_unknown=e.get('model_unknown'), q=e.get('q'), m=e.get('m'), U=e.get('U'),
                           accounted_nanodollars=record['accounted_nanodollars'],
                           raw_sha256=sha(folder / (aid + '.raw.json')))
                if e['technical_valid']:
                    values[component].setdefault(slot, e)  # first valid, including model unknown
            attempts.append(row)
    bank_manifest = read(bank_root / 'OUTPUT_MANIFEST.json')
    if sha(bank_root / 'REFERENCE_BANK_PRIVATE.json') != bank_manifest['REFERENCE_BANK_PRIVATE.json']:
        raise ValueError('historical reference bank changed')
    bank = read(bank_root / 'REFERENCE_BANK_PRIVATE.json')
    reused = reuse_map(materials, bank['pairs'], bank['singles'], bank['supplements'])
    references = {r['key']:r for r in reused['reply_rows']}; compared = []
    for row in rows:
        slot = row['logical_identity']; p, a, r = (values[k].get(slot) for k in ('S', 'A', 'R'))
        route = decision(dict(technical_valid=True, evaluation=p) if p else None,
                         dict(technical_valid=True, evaluation=a) if a else None)
        candidates = candidate_scores(p, route, r); ref = references[row['key']]
        compared.append(dict(row, reply_identity=ref['reply_identity'], evidence_identity=ref['evidence_identity'],
            candidates=candidates, routing=route,
            comparisons={arm:[single_comparison(candidates[arm], s) for s in ref['single_references']]
                         for arm in ('S', 'A')},
            prior_clarifications=ref['prior_clarifications'],
            no_existing_single_reference=not ref['single_references']))
    # Only pairs with BOTH exact evidence/reply endpoints can be compared.
    pair_comparisons = []
    indexed = {(r['evidence_identity'], r['reply_identity']):r for r in compared}
    for ref in bank['pairs']:
        ends = [indexed.get((ref['evidence_identity'], rid)) for rid in ref['reply_identities']]
        if any(e is None for e in ends):
            continue
        for arm in ('S', 'A'):
            scores = [e['candidates'][arm] for e in ends]
            missing = any(s is None for s in scores)
            winner = None if missing or scores[0]['U'] == scores[1]['U'] else ref['reply_identities'][int(scores[1]['U'] > scores[0]['U'])]
            direction = None if missing else 'preferred_reply' if winner else 'tie'
            pair_comparisons.append(dict(reference_id=ref['record_id'], source=ref['source'], arm=arm,
                pair_identity=ref['pair_identity'], human_direction=ref['direction'], candidate_direction=direction,
                human_preferred_reply=ref['preferred_reply_identity'], candidate_preferred_reply=winner,
                agrees=None if missing or ref['direction'] == 'uncertain' else
                    direction == ref['direction'] and winner == ref['preferred_reply_identity'],
                interpretation='holistic preference vs candidate U direction; a human tie is not an exact U target'))
    data = Path(config['ledger']).read_bytes(); n = policy['opening_ledger_bytes']
    if hashlib.sha256(data[:n]).hexdigest() != policy['opening_ledger_sha256'] or not data.endswith(b'\n'):
        raise ValueError('financial prefix changed or incomplete append; take a later snapshot')
    events = [json.loads(s) for s in data[n:].splitlines() if s.strip()]
    reserved = {e['reservation_id']:e for e in events if e['event'] == 'RESERVED'}
    settled = {e['reservation_id']:e for e in events if e['event'] == 'SETTLED'}
    if not set(settled) <= set(reserved) or any(e['binding']['development_stage'] != config['protocol_identity'] for e in reserved.values()):
        raise ValueError('unexpected financial writer')
    for row in attempts:
        if row['attempt_id'] not in reserved:
            raise ValueError('unreserved attempt')
        if row['settled'] and nanodollars(settled[row['attempt_id']]['actual_cost_usd']) != row['accounted_nanodollars']:
            raise ValueError('result/financial settlement mismatch')
    cost = sum(nanodollars(e['actual_cost_usd']) for e in settled.values())
    liability = sum(nanodollars(e['maximum_cost_usd']) for k,e in reserved.items() if k not in settled)
    isolation_path = root/'RETAINED_LIABILITY_CONTINUATION.json'
    isolated = read(isolation_path)['attempt_id'] if isolation_path.exists() else None
    total, _, _, _ = DevelopmentBudget(config['ledger'], policy=policy, stage_identity=config['protocol_identity'])._totals(
        [json.loads(s) for s in data.splitlines() if s.strip()])
    first = [r for r in attempts if r['ordinal'] == 0 and r['settled']]
    summary = dict(status='CLOSED_DEVELOPMENT_SNAPSHOT' if (root/'CLOSED.json').exists() else 'OPEN_STAGE_SNAPSHOT',
        captured_utc=datetime.now(timezone.utc).isoformat(), protocol_identity=config['protocol_identity'],
        journal_attempts=len(attempts), journal_settled=sum(r['settled'] for r in attempts),
        reserved_attempts=len(reserved), cumulative_reserved_attempts=policy['baseline_cumulative']+len(reserved),
        by_component={k:dict(attempts=sum(r['component']==k for r in attempts),
            settled=sum(r['component']==k and r['settled'] for r in attempts),
            first_settled=sum(r['component']==k for r in first),
            first_technical_valid=sum(r['component']==k and r['technical_valid'] for r in first)) for k in ('S','A','R')},
        accounted_usd=usd(cost), unresolved_liabilities=len(set(reserved)-set(settled)),
        isolated_unknown_liabilities=int(isolated in reserved and isolated not in settled) if isolated else 0,
        reserved_liability_usd=usd(liability), historical_ledger_prefix_unchanged=True,
        conservative_stage_settled_plus_reserved_usd=usd(cost+liability),
        conservative_followup_settled_plus_reserved_usd=usd(total-policy['baseline']+policy['external_liability']),
        max_attempts=policy['max_attempts'], shared_stage_cap_usd=usd(policy['stage_cap']),
        overall_followup_cap_usd=usd(policy['shared_cap']),
        existing_single_reference_slots=sum(not r['no_existing_single_reference'] for r in compared),
        comparisons={arm:dict(available=sum(c['both_agree'] is not None for r in compared for c in r['comparisons'][arm]),
            both_agree=sum(c['both_agree'] is True for r in compared for c in r['comparisons'][arm])) for arm in ('S','A')},
        new_human_labels=0, independent_validation_created=False, qualified_reward=False, natural_updates=0,
        limitation='Development snapshot only. In-flight financial and journal snapshots can differ; pending is not zero.')
    output.mkdir(parents=True, mode=0o700)
    save_json(output/'SUMMARY.json', summary)
    save_json(output/'DETAILS_PRIVATE.json', dict(journals=journals, attempts=attempts,
        materials=compared, pair_comparisons=pair_comparisons, reuse_summary=reused['summary']))
    save_json(output/'SOURCE_HASHES.json', dict(config_sha256=sha(package/'J_CONFIG_PRIVATE.json'),
        protocol_sha256=sha(root/'PROTOCOL.json'), reference_bank_sha256=sha(bank_root/'REFERENCE_BANK_PRIVATE.json'),
        ledger_snapshot_bytes=len(data), ledger_snapshot_sha256=hashlib.sha256(data).hexdigest(), script_sha256=sha(__file__)))
    save_json(output/'OUTPUT_MANIFEST.json', {p.name:sha(p) for p in output.iterdir() if p.is_file()})
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--package', type=Path, required=True)
    p.add_argument('--bank', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); audit(a.package, a.bank, a.output)
