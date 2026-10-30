"""Complete S/A development adapter and durable, OFFLINE dependency rehearsal.

No credentials or live transport are implemented here. Development does not
require qualification, and can never issue a qualified receipt. The live budget
broker and researcher authorization remain a separate launch boundary.
"""
from copy import deepcopy
import fcntl
import json
from pathlib import Path

from . import diagnostic_engine as engine
from . import feedback_score_audit as audit
from . import feedback_prototype as prototype
from . import score_audit_validation as audit_input
from . import strict_audit_delivery as strict
from .durable import publish
from .recovery_schedule import RecoverySchedule, Slot
from .schema import digest

VERSION = 'pmrl1-complete-development-adapter-v1-20261030'


def save_once(path, value):
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n'
    if path.exists():
        if path.read_text() != data:
            raise ValueError('immutable development journal changed')
    else:
        publish(path, lambda f: f.write(data.encode()))


def candidate_scores(primary, routing, resolution):
    """Deterministic S/A handoff; failed resolution never falls back to S.

    These numbers remain diagnostic candidates, not qualified training rewards.
    """
    def numeric(evaluation):
        if not evaluation or not evaluation.get('technical_valid') or evaluation.get('model_unknown'):
            return None
        return {k: evaluation[k] for k in ('q', 'm', 'U')}
    s = numeric(primary)
    if routing['action'] == 'retain_numeric_candidate':
        a, source = s, 'same_primary'
    elif routing['action'] == 'supplement_candidate':
        a, source = numeric(resolution), 'single_resolution' if numeric(resolution) is not None else 'missing_or_uncertain_resolution'
    else:
        a, source = None, 'missing_audit_or_predecessor'
    return dict(S=s, A=a, A_source=source, reward_eligible=False, qualification_granted=False)


class DevelopmentAdapter:
    def __init__(self, *, prompt, config):
        if not all(s in prompt for s in ('QUALITY q (integer):', 'MISUSE m:', '0.25 for a localized error')):
            raise ValueError('complete frozen q/m rubric required')
        self.prompt, self.config = prompt, deepcopy(config)
        self.identity = digest(dict(version=VERSION, prompt=prompt, config=config,
            audit_interface=audit.INTERFACE, delivery=strict.DELIVERY))

    def prepare(self, item, component, *, score=None, review=None):
        if set(item) != {'reply', 'evidence'}:
            raise ValueError('only reply and complete legal evidence may enter scoring')
        item = deepcopy(item)
        if component == 'S':
            if score is not None or review is not None:
                raise ValueError('single scoring must not see later audit')
            messages, schema = engine.payload(item, 'joint')
            messages[0]['content'] = self.prompt + '\nOUTPUT CONTRACT pmrl1-primary-full-schema-v1:\n' + json.dumps(schema, ensure_ascii=False)
        elif component == 'A':
            if score is None or review is not None:
                raise ValueError('audit requires exactly one bound preliminary score')
            slot = dict(item_key='current', reply_identity=digest(item['reply']),
                evidence_identity=digest(item['evidence']), preliminary_score_identity=digest(score))
            messages, schema = strict.payload(slot, item, {'current': dict(evaluation=dict(value=score))}, engine, self.prompt)
        elif component == 'R':
            # The old repair_payload accepts an obsolete audit interface. Keep it
            # frozen; validate the CURRENT full source/score-linked audit here.
            audit.validate_audit(review, item, score, engine)
            j = dict(technical_valid=True, evaluation=dict(technical_valid=True, value=score,
                     model_unknown=score['status'] == 'uncertain', U=None))
            a = dict(technical_valid=True, evaluation=dict(technical_valid=True, value=review, interface_version=audit.INTERFACE))
            if audit.decision(j, a)['action'] != 'supplement_candidate':
                raise ValueError('no score issue: extra sampling forbidden')
            messages, schema = engine.payload(item, 'joint')
            data = json.loads(messages[1]['content'])
            data.update(preliminary_score=score, machine_audit=review)
            messages[1]['content'] = json.dumps(data, ensure_ascii=False)
            messages[0]['content'] = (self.prompt + prototype.REPAIR_ADDITION +
                '\nOUTPUT CONTRACT pmrl1-resolution-full-schema-v1:\n' + json.dumps(schema, ensure_ascii=False))
        else:
            raise ValueError('unknown development component')
        body = strict.wire_body(self.config, messages, schema, engine) if component == 'A' else engine.api_body(self.config, messages)
        engine.input_guard(messages)
        if len(engine.s.canonical(body).encode()) + 8192 + body['max_tokens'] > 1048576:
            raise ValueError('complete actual wire including tool schema exceeds frozen native context screen')
        data = json.loads(body['messages'][1]['content'])
        expected = {'legal_evidence', 'reply', 'response_units'}
        if component == 'A': expected |= {'preliminary_score', 'preliminary_score_sha256', 'rubric_reference'}
        if component == 'R': expected |= {'preliminary_score', 'machine_audit'}
        if set(data) != expected or data['legal_evidence'] != item['evidence'] or data['reply'] != item['reply']:
            raise ValueError('actual outbound sources/field contract changed')
        if component == 'A' and data['rubric_reference'] != dict(identity=digest(self.prompt), text=self.prompt):
            raise ValueError('audit missing complete unchanged rubric')
        request = dict(component=component, adapter_identity=self.identity, wire_body=body,
            local_schema=schema, evidence_identity=digest(item['evidence']), response_identity=digest(item['reply']),
            predecessor_score_identity=digest(score) if score is not None else None,
            predecessor_review_identity=digest(review) if review is not None else None,
            endpoint=strict.ENDPOINT if component == 'A' else 'https://api.deepseek.com/chat/completions')
        # Preserve exact primary identity from preparation 125 for comparison.
        request['primary_preparation_identity'] = digest(dict(config=self.config, messages=messages, schema=schema)) if component == 'S' else None
        request['identity'] = digest(request)
        return request

    def evaluate(self, request, item, raw, *, score=None):
        if raw.get('request_identity') != request['identity'] or raw.get('adapter_identity') != self.identity:
            raise ValueError('raw response identity drift')
        if request['component'] == 'A':
            value = strict.evaluate(raw, item, score, engine)
        else:
            value = engine.evaluate(item, 'joint', raw, self.identity, request['identity'])
        if not value['technical_valid']:
            # Distinguish serialization from schema/source errors for the
            # existing three-consecutive-same-class circuit; never repair text.
            try:
                if request['component'] == 'A':
                    choice = raw['choices'][0]; message = choice['message']
                    calls = message.get('tool_calls') or []
                    if (raw.get('delivery') != strict.DELIVERY or len(raw['choices']) != 1
                            or choice['finish_reason'] != 'tool_calls' or message.get('content') not in (None, '')
                            or len(calls) != 1 or calls[0].get('type') != 'function'
                            or not calls[0].get('id') or calls[0]['function']['name'] != strict.TOOL):
                        raise ValueError('invalid tool delivery')
                    _, _, adaptation = engine.envelope.unwrap(calls[0]['function']['arguments'])
                    if adaptation['transformation'] != 'bare_json_unchanged': raise ValueError('not bare arguments')
                else:
                    text, finish = engine.final_content(raw)
                    if finish != 'natural_stop': raise ValueError('incomplete final')
                    engine.envelope.unwrap(text)
                value['failure_kind'] = 'schema_failure'
            except (KeyError, IndexError, TypeError, ValueError):
                value['failure_kind'] = 'format_failure'
        return value


class OfflineDevelopmentStage:
    """Rehearse ALL primary/audit/conditional-repair slots, not the old 20 calls.

    RecoverySchedule handles each frozen wave. Later waves bind actual first
    schema-valid predecessor outputs (including uncertain scores). Unknown scores
    can be audited; they are never numerical rewards. Failed prerequisites are
    excluded with explicit statuses. Recovery allowances are shared across waves.
    This class deliberately refuses every non-synthetic transport.
    """
    def __init__(self, root, materials, adapter, *, recovery_cap=16):
        if type(recovery_cap) is not int or recovery_cap < 0:
            raise ValueError('finite recovery cap required')
        self.root = Path(root); self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.adapter = adapter
        self.materials = deepcopy(materials)
        self.items = {}; self.mapping = []
        seen = set()
        for material in self.materials:
            if material['key'] in seen or material['purpose'] not in ('known_regression', 'new_development_not_independent_validation'):
                raise ValueError('unique development materials required; no qualification/test slots')
            seen.add(material['key'])
            item = {k: material[k] for k in ('reply', 'evidence')}
            request = adapter.prepare(item, 'S'); key = request['identity']
            self.items[key] = item
            self.mapping.append(dict(key=material['key'], purpose=material['purpose'], logical_identity=key))
        if not self.items:
            raise ValueError('nonempty stage required')
        self.recovery_cap = recovery_cap
        self.protocol = dict(version=VERSION, adapter=adapter.identity, mapping=self.mapping,
            unique_inputs=len(self.items), recovery_cap=recovery_cap, max_attempts=3 * len(self.items) + recovery_cap,
            mode='synthetic_only', qualification_granted=False, reward_eligible=False)
        self.identity = digest(self.protocol)
        save_once(self.root/'PROTOCOL.json', self.protocol)

    def _wave(self, component, requests, remaining):
        directory = self.root/component; directory.mkdir(exist_ok=True, mode=0o700)
        save_once(directory/'REQUESTS.json', requests)
        slots = [Slot(k, r['identity'], digest([self.adapter.identity, component])) for k, r in requests.items()]
        return RecoverySchedule(directory/'attempts.sqlite', slots, protocol_identity=self.identity,
            max_attempts=len(slots) * 3, recovery_cap=remaining)

    def _results(self, component, report):
        valid = {}
        for row in report['attempts_log']:
            claim, result = row['claim'], row['result']
            if result is None: continue
            path = self.root/component/(claim['attempt_id']+'.result.json')
            record = json.loads(path.read_text())
            if digest(record) != result['result_identity']:
                raise ValueError('persisted evaluation changed')
            raw = json.loads((self.root/component/(claim['attempt_id']+'.raw.json')).read_text())
            if digest(raw) != record['raw_identity']:
                raise ValueError('raw history changed')
            if record['evaluation']['technical_valid']:
                valid.setdefault(claim['slot_id'], record['evaluation'])
        return valid

    def advance(self, transport):
        if getattr(transport, 'synthetic_only', False) is not True:
            raise ValueError('offline stage refuses live transport; budget/approval bridge required')
        with (self.root/'.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            remaining = self.recovery_cap; primary = {}; reviews = {}; waves = []
            for component in ('S', 'A', 'R'):
                requests = {}
                for key, item in self.items.items():
                    if component != 'S' and key not in primary: continue
                    if component == 'R':
                        if key not in reviews: continue
                        route = audit.decision(dict(technical_valid=True, evaluation=primary[key]),
                                               dict(technical_valid=True, evaluation=reviews[key]))
                        if route['action'] != 'supplement_candidate': continue
                    requests[key] = self.adapter.prepare(item, component,
                        score=primary[key]['value'] if component != 'S' else None,
                        review=reviews[key]['value'] if component == 'R' else None)
                if not requests:
                    waves.append(dict(component=component, slots=0, attempts=0)); continue
                schedule = self._wave(component, requests, remaining)
                report = schedule.report()
                if report['global_stop']:
                    return dict(status='RECONCILIATION_REQUIRED', component=component, reason=report['global_stop'])
                claim = schedule.claim_next(lambda c: dict(attempt_id=c['attempt_id'], reservation_identity=digest(['synthetic', c]),
                                                           synthetic_only=True, nanodollars=0))
                if claim is not None:
                    key = claim['slot_id']; request = requests[key]
                    # A crash/exception after claim leaves an outstanding journal,
                    # never a license to send again. Raw and result are immutable.
                    raw = transport.send(deepcopy(request), attempt_id=claim['attempt_id'])
                    save_once(self.root/component/(claim['attempt_id']+'.raw.json'), raw)
                    if raw.get('synthetic_only') is not True:
                        raise ValueError('non-synthetic response refused; reconcile outstanding claim')
                    evaluation = self.adapter.evaluate(request, self.items[key], raw,
                        score=primary[key]['value'] if component == 'A' else None)
                    record = dict(evaluation=evaluation, raw_identity=digest(raw), synthetic_only=True,
                                  real_cost_usd=0, reward_eligible=False)
                    save_once(self.root/component/(claim['attempt_id']+'.result.json'), record)
                    # Here VALID means delivered + schema/source validated, NOT
                    # q/m certainty or qualification. Preserve model_unknown.
                    outcome = 'valid' if evaluation['technical_valid'] else evaluation['failure_kind']
                    schedule.settle(claim['attempt_id'], outcome=outcome,
                        input_identity=request['identity'], config_identity=claim['config_identity'],
                        settlement_identity=digest(['synthetic_zero', claim['attempt_id']]), result_identity=digest(record))
                    return dict(status='ATTEMPT_RECORDED', component=component, outcome=outcome,
                                ordinal=claim['ordinal'], real_calls=0)
                remaining -= report['recovery_attempts']
                results = self._results(component, report)
                if component == 'S': primary = results
                if component == 'A': reviews = results
                waves.append(dict(component=component, slots=len(requests), attempts=report['attempts'],
                                  states=report['states'], recovery_attempts=report['recovery_attempts']))
            candidates = []
            for row in self.mapping:
                key = row['logical_identity']
                p, a = primary.get(key), reviews.get(key)
                route = audit.decision(dict(technical_valid=True, evaluation=p) if p else None,
                                       dict(technical_valid=True, evaluation=a) if a else None)
                resolution = results.get(key) if component == 'R' and requests else None
                candidates.append(dict(row, S_candidate=p, audit=a, routing=route,
                    A_resolution=resolution, route_candidates=candidate_scores(p, route, resolution),
                    qualification_granted=False, reward_eligible=False))
            report = dict(status='CLOSED_OFFLINE_REHEARSAL', protocol_identity=self.identity, waves=waves,
                materials=candidates, real_calls=0, training_updates=0, qualified_receipt=None,
                route_selected=None, independent_review_status='not_supplied')
            save_once(self.root/'CLOSED.json', report)
            return report
