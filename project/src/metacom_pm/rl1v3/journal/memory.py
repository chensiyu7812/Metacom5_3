"""Journal SOURCE_EXACT bridge; reuses frozen C0, PrefixPort and A As-of.

End-history QA is a distinct task envelope, never a fabricated dialogue cut.
No semantic claim is promoted to the old human_approved status.
"""
from __future__ import annotations
from dataclasses import dataclass, replace
from pathlib import Path
import importlib.util
import sys
import types

from .. import contracts as K
from ..io import object_sha256, file_sha256
from ..sources import source_registry as S
from ..bank import bank_v0 as B

PROTOCOL = 'pmrl1-j-memory-source-exact-v1'
ASOF_SHA = 'c072ea1a3d809e62cca938c0e77e0693c344b75d4e32ec5f345e352e4543d30f'


def load_asof(path):
    """Load a pinned dependency read-only without merging A into this branch."""
    path = Path(path)
    if file_sha256(path) != ASOF_SHA:
        raise ValueError('A As-of dependency differs from fixed df21b11 bytes')
    package = 'metacom_pm.rl1v3.compile'
    if package not in sys.modules:
        module = types.ModuleType(package)
        module.__path__ = [str(path.parent)]
        sys.modules[package] = module
    name = package + '.asof'
    if name in sys.modules:
        if file_sha256(sys.modules[name].__file__) != ASOF_SHA:
            raise ValueError('conflicting loaded As-of module')
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@dataclass(frozen=True)
class EndHistoryQA:
    """Private QA envelope. Only visible() crosses runtime boundary."""
    task_id: str
    owner_id: str
    question: str
    cutoff_rank: int
    timestamp: str | None
    family_id: str
    ancestor_family_ids: tuple[str, ...]
    fold: int
    dataset: str = S.DATASET
    split: str = 'dev'
    prefix_protocol: str = 'pmrl1-j-official-end-history-qa-v1'

    @property
    def turns(self):
        return (K.SourceTurn(turn_index=0, role='seeker', text=self.question),)

    @property
    def session_id(self):
        return 'qa:' + self.task_id

    @property
    def prefix_id(self):
        return object_sha256(dict(protocol=self.prefix_protocol, owner=self.owner_id,
            question=self.question, task_id=self.task_id))

    @property
    def runtime_sha256(self):
        return object_sha256(self)

    def visible(self):
        return K.VisiblePrefix(turns=self.turns, timestamp=self.timestamp)


class QARegistry:
    """Delegate source legality to Registry, separately validate official QA cutoff."""
    def __init__(self, registry, tasks):
        self.original = registry
        self.tasks = {t.task_id: t for t in tasks}

    def __getattr__(self, key):
        return getattr(self.original, key)

    def context(self, prefix):
        if not isinstance(prefix, EndHistoryQA):
            return self.original.context(prefix)
        if self.tasks.get(prefix.task_id) != prefix:
            raise ValueError('unbound QA prefix')
        history = tuple(e.source for e in self.entries
            if e.source.owner_id == prefix.owner_id and e.source.dataset == prefix.dataset)
        if sorted(s.chronological_rank for s in history) != list(range(prefix.cutoff_rank)):
            raise ValueError('QA must bind the complete official owner archive')
        if not all(s.complete for s in history):
            raise ValueError('incomplete archive session')
        if prefix.fold != self.folds['fold_of_owner'][prefix.owner_id]:
            raise ValueError('changed frozen owner fold')
        return None, history

    def visible(self, prefix, *, rs=False):
        self.context(prefix)
        return tuple(e for e in self.entries if self.reason(e.source_id, prefix, rs=rs) is None)


def exact_raw_bank(registry, owners):
    """Complete raw sessions only; no automatic MP/ME/SUM semantic approval."""
    records = []
    for e in registry.entries:
        s = e.source
        if s.dataset != S.DATASET or s.owner_id not in owners:
            continue
        refs = tuple(S.span(s, i) for i, t in enumerate(s.turns) if t.text)
        text = ('SOURCE_EXACT completed historical session. Statements retain their original speaker; '
                'present validity and real-world truth are unknown.\n' +
                '\n'.join(f'{t.role}: {t.text}' for t in s.turns))
        record = B._base(e, 'MS', text, dict(protocol=PROTOCOL, semantic_approval=False),
                         refs, legacy_id=PROTOCOL + ':' + s.session_id)
        records.append(replace(record, writer_identity=PROTOCOL))
    inputs = dict(protocol=PROTOCOL, source_version=registry.version, code_sha256=file_sha256(__file__))
    version = B._identity(records, registry, inputs)
    return B.Bank([replace(r, bank_version=version) for r in records], registry, inputs, ())


def runtime_task(prefix, *, inventory, budget):
    """Allowlist, not recursive redaction: no owner/fold/evidence/gold fields."""
    return dict(task_id=prefix.task_id, visible_prefix=prefix.visible(),
        prefix_identity=prefix.runtime_sha256, public_inventory=inventory,
        budget=budget)
