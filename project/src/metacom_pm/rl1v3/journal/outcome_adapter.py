"""Task outcomes through existing terminal validation and RealInstance interfaces.

This is a distinct Y protocol, never an ER-v3/GSC rename. Only fully qualified,
mechanically valid, complete task endpoints enter a training TerminalTable.
No generation is performed, and missing/uncertain endpoints are never zero.
"""
from __future__ import annotations

import copy
import re
from collections import Counter
from pathlib import Path

from ..env.finite_head import TerminalOutcome
from ..env.c0_binding import TerminalTable
from ..evaluate.terminal_registry import TerminalRegistry, RegistryError, subset_name
from ..train.real_instances import RealInstance
from ..io import object_sha256, write_json_once

PROTOCOL = 'pmrl1-j-task-outcomes-1'
SHA = re.compile(r'^[0-9a-f]{64}$')


def task_success(requirements, prohibitions, *, technical_status='ok', integrity='pass'):
    """Necessary-item rule: failure dominates uncertainty; E0 failures cannot win.

    prohibition verdicts are compliance verdicts (pass means no prohibited act).
    """
    if technical_status != 'ok':
        return dict(status='technical_failure', lower=None, upper=None, reward=None)
    if integrity != 'pass':
        return dict(status='integrity_failure', lower=None, upper=None, reward=None)
    values = list(requirements) + list(prohibitions)
    if not values or any(v not in ('pass', 'fail', 'uncertain') for v in values):
        raise ValueError('nonempty pass/fail/uncertain judgments required')
    if 'fail' in values:
        return dict(status='complete', lower=0, upper=0, reward=0)
    if 'uncertain' in values:
        return dict(status='pending', lower=0, upper=1, reward=None)
    return dict(status='complete', lower=1, upper=1, reward=1)


class FrozenEvalLedger:
    """Duck-typed ledger for TerminalRegistry.register, freezing private EvalSpec.

    Every output is write-once and private. Freeze must precede any registered
    response; the historical ChecklistLedger and C0 schemas are unchanged.
    """
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._specs = {}
        self._candidates = {}
        for p in self.root.glob('eval-*.json'):
            import json
            row = json.loads(p.read_text())
            self._specs[row['prefix_id']] = row
        for p in self.root.glob('candidate-*.json'):
            import json
            row = json.loads(p.read_text())
            self._candidates[row['key_sha256']] = row

    def freeze(self, prefix_id, evalspec):
        if any(r['prefix_id'] == prefix_id for r in self._candidates.values()):
            raise RegistryError('cannot revise EvalSpec after response registration')
        requirements = evalspec.get('requirements', ())
        prohibitions = evalspec.get('prohibitions', ())
        if not requirements:
            raise RegistryError('EvalSpec needs at least one necessary criterion')
        ids = [x.get('id') for x in [*requirements, *prohibitions]]
        if any(not isinstance(x, str) or not x for x in ids) or len(ids) != len(set(ids)):
            raise RegistryError('EvalSpec criterion IDs must be unique nonempty strings')
        if not SHA.fullmatch(prefix_id):
            raise RegistryError('prefix_id must be a C0 digest')
        row = dict(protocol=PROTOCOL, prefix_id=prefix_id, evalspec=copy.deepcopy(evalspec),
                   evalspec_sha256=object_sha256(evalspec))
        if prefix_id in self._specs and self._specs[prefix_id] != row:
            raise RegistryError('EvalSpec is write-once')
        if prefix_id not in self._specs:
            write_json_once(self.root / f'eval-{prefix_id}.json', row)
            self._specs[prefix_id] = row
        return row['evalspec_sha256']

    def register_candidate(self, prefix_id, key_sha256, response_sha256):
        if prefix_id not in self._specs:
            raise RegistryError('no frozen EvalSpec')
        if any(not SHA.fullmatch(x) for x in (key_sha256, response_sha256)):
            raise RegistryError('candidate identities must be digests')
        if key_sha256 in self._candidates:
            raise RegistryError('response is write-once')
        row = dict(prefix_id=prefix_id, key_sha256=key_sha256, response_sha256=response_sha256,
                   checklist_sha256=self._specs[prefix_id]['evalspec_sha256'])
        write_json_once(self.root / f'candidate-{key_sha256}.json', row)
        self._candidates[key_sha256] = row
        return copy.deepcopy(row)


class TaskTerminalRegistry(TerminalRegistry):
    """Reuse canonical key, trace, reachable subset and freeze-before-response checks."""
    def __init__(self, *, identity, ledger, qualification_receipt=None, table_tag='journal'):
        super().__init__(identity=identity, ledger=ledger, table_tag=table_tag)
        self.qualification = copy.deepcopy(qualification_receipt)

    def add_er(self, *_args, **_kwargs):
        raise RegistryError('historical ER is not a journal task outcome')

    def add_task_outcome(self, prefix_id, *, key_sha256, response_sha256, evalspec_sha256,
                         requirements, prohibitions, evidence, technical_status='ok', integrity='pass'):
        row = next((r for r in self.rows.get(prefix_id, {}).values() if r['key_sha256'] == key_sha256), None)
        if row is None:
            raise RegistryError('unregistered terminal')
        if 'task_outcome' in row:
            raise RegistryError('task outcome is write-once')
        if (response_sha256, evalspec_sha256) != (row['response_sha256'], row['checklist_sha256']):
            raise RegistryError('response or frozen EvalSpec mismatch')
        spec = self.ledger._specs[prefix_id]['evalspec']
        required_ids = {x['id'] for x in spec['requirements']}
        prohibited_ids = {x['id'] for x in spec.get('prohibitions', ())}
        if not isinstance(requirements, dict) or set(requirements) != required_ids:
            raise RegistryError('necessary item coverage differs from frozen EvalSpec')
        if not isinstance(prohibitions, dict) or set(prohibitions) != prohibited_ids:
            raise RegistryError('prohibition coverage differs from frozen EvalSpec')
        if not evidence:
            raise RegistryError('evaluation evidence is required')
        outcome = task_success(requirements.values(), prohibitions.values(), technical_status=technical_status, integrity=integrity)
        row['task_outcome'] = dict(protocol=PROTOCOL, **outcome, evidence=copy.deepcopy(evidence))
        row['status'] = 'computed' if outcome['status'] == 'complete' else outcome['status']

    def table(self, prefix_id):
        _, binding = self.prefixes[prefix_id]
        rows = self.rows[prefix_id]
        counts = Counter(r['status'] for r in rows.values())
        qualified = bool(self.qualification and self.qualification.get('qualified') is True
                         and self.qualification.get('protocol') == PROTOCOL
                         and self.qualification.get('evalspec_sha256') == self.ledger._specs[prefix_id]['evalspec_sha256']
                         and self.qualification.get('evaluator_id')
                         and self.qualification.get('evidence_sha256')
                         and SHA.fullmatch(self.qualification['evidence_sha256']))
        measured_complete = counts['computed'] == len(binding.reachable)
        complete = measured_complete and qualified
        report = dict(protocol=PROTOCOL, prefix_id=prefix_id, reachable=len(binding.reachable),
                      registered=len(rows), computed=counts['computed'], pending=counts['pending'],
                      refused=counts['technical_failure'] + counts['integrity_failure'],
                      missing=[subset_name(m) for m in binding.reachable if m not in rows],
                      complete=complete, measured_complete=measured_complete, reward_qualified=qualified,
                      missing_or_refused_filled_with_zero=False, is_gsc=False, is_er=False)
        out = {r['key_sha256']: TerminalOutcome(float(r['task_outcome']['reward']), r['key_sha256'],
                                                dict(protocol=PROTOCOL))
               for r in rows.values() if qualified and r['status'] == 'computed'}
        table_id = PROTOCOL + ':' + object_sha256(dict(identity=self.identity, qualification=self.qualification,
                                                       prefix_id=prefix_id, tag=self.table_tag))
        return TerminalTable(out, table_id=table_id), report

    def real_instance(self, prefix_id, port_factory):
        _, binding = self.prefixes[prefix_id]
        table, report = self.table(prefix_id)
        return RealInstance(prefix_id, port_factory, self.identity, table, report, binding.reachable)
