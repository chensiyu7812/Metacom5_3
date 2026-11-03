"""Use a new account snapshot without releasing any unknown-call liability.

Project spending, attempt counts and settlements remain in the original ledger.
Only account availability is refreshed. Already-settled calls precede the new
snapshot; every outstanding maximum is charged again against its availability.
"""
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
from pathlib import Path

from .calibration_workflow import verify_identity
from .development_dispatch import sha
from .development_feedback import save_once
from .diagnostic_support import nanodollars
from .retained_liability_continuation import RetainedBudget, RetainedDevelopmentStage
from .schema import digest

STATUS = 'ACCOUNT_SNAPSHOT_REFRESH_ALL_UNKNOWN_MAXIMA_RETAINED'


def available_nanodollars(balance):
    if balance.get('is_available') is not True:
        raise ValueError('account unavailable')
    amounts = {}
    for row in balance['balance_infos']:
        currency = row['currency']
        value = Decimal(row['total_balance'])
        if currency not in ('USD', 'CNY') or currency in amounts or not value.is_finite() or value < 0:
            raise ValueError('unsupported, duplicate or invalid account currency')
        amounts[currency] = value
    if not amounts:
        raise ValueError('missing account currency')
    # Preserve the original fixed tariff-equivalent ratio, not market FX.
    return int((amounts.get('USD', Decimal(0)) + amounts.get('CNY', Decimal(0))*Decimal('.15'))*10**9)


def snapshot_fields(budget):
    data = budget.path.read_bytes()
    events = [json.loads(line) for line in data.splitlines() if line.strip()]
    _, trial, reserved, settled = budget._totals(events)
    outstanding = {key: nanodollars(value['maximum_cost_usd'])
                   for key, value in reserved.items() if key not in settled}
    if set(outstanding) != {budget.isolation['attempt_id']}:
        raise ValueError('exactly the original unknown liability must remain')
    if reserved[budget.isolation['attempt_id']]['selection_trial'] != budget.trial:
        raise ValueError('unresolved liability belongs to another account trial')
    return dict(ledger_bytes=len(data), ledger_sha256=hashlib.sha256(data).hexdigest(),
                trial_nanodollars=trial, outstanding_nanodollars=outstanding,
                opening_trial_nanodollars=trial-sum(outstanding.values()))


def validate_refresh(record, budget):
    verify_identity(record)
    if (record.get('status') != STATUS or record.get('stage_identity') != budget.stage_identity
            or record.get('financial_policy_identity') != digest(budget.policy)
            or record.get('isolation_identity') != budget.isolation['identity']
            or record.get('new_allowance') != 0 or record.get('settlement_changes') != 0):
        raise ValueError('account refresh binding changed')
    for path, expected in record['source_hashes'].items():
        if sha(path) != expected:
            raise ValueError('account refresh evidence or implementation changed')
    required = [Path(__file__).resolve(), Path(record['balance_path']).resolve()]
    if any(str(path) not in record['source_hashes'] for path in required):
        raise ValueError('account reply and refresh implementation must be bound')
    balance = json.loads(Path(record['balance_path']).read_text())
    if available_nanodollars(balance) != record['available_nanodollars']:
        raise ValueError('account amount does not match provider reply')
    data = budget.path.read_bytes()[:record['ledger_bytes']]
    if len(data) != record['ledger_bytes'] or hashlib.sha256(data).hexdigest() != record['ledger_sha256']:
        raise ValueError('account snapshot ledger prefix changed')
    _, trial, reserved, settled = budget._totals([json.loads(x) for x in data.splitlines() if x.strip()])
    outstanding = {key: nanodollars(value['maximum_cost_usd'])
                   for key, value in reserved.items() if key not in settled}
    if (set(outstanding) != {budget.isolation['attempt_id']}
            or outstanding != record['outstanding_nanodollars']
            or trial != record['trial_nanodollars']
            or trial-sum(outstanding.values()) != record['opening_trial_nanodollars']):
        raise ValueError('unknown maximum omitted from refreshed account baseline')
    return dict(available=record['available_nanodollars'], opening_trial=record['opening_trial_nanodollars'])


class RefreshedBudget(RetainedBudget):
    def __init__(self, *args, refresh, **kwargs):
        super().__init__(*args, **kwargs)
        self.refresh = deepcopy(refresh)

    def reserve(self, reservation_id, amount, binding):
        self.verified_balance = validate_refresh(self.refresh, self)
        # Original atomic stage/trial/shared/account limits and one-unknown
        # guard still execute, including the full original unknown reservation.
        return super().reserve(reservation_id, amount, binding)


class RefreshedDevelopmentStage(RetainedDevelopmentStage):
    def __init__(self, *args, refresh, **kwargs):
        super().__init__(*args, **kwargs)
        self.refresh = deepcopy(refresh)
        self.budget = RefreshedBudget(self.budget.path, policy=self.policy,
            stage_identity=self.identity, isolation=self.isolation, refresh=self.refresh)
        validate_refresh(self.refresh, self.budget)
        save_once(self.root/'ACCOUNT_REFRESH.json', self.refresh)

    def authorize_transport(self, transport):
        super().authorize_transport(transport)
        if (json.loads((self.root/'ACCOUNT_REFRESH.json').read_text()) != self.refresh
                or self.budget.refresh != self.refresh):
            raise ValueError('fixed account refresh changed')
        if not self.engineering and transport.credential_fingerprint != self.refresh['credential_fingerprint']:
            raise ValueError('refreshed account differs from transport credential')
        self.budget.verified_balance = validate_refresh(self.refresh, self.budget)

    def closed_extension(self, waves):
        return super().closed_extension(waves) | dict(account_refresh_identity=self.refresh['identity'])
