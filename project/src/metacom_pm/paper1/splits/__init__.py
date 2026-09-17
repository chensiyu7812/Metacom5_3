"""Primary exact-evidence group-component construction for Paper-1 targets.

B12: the ``evidence`` submodule (``SplitEvidenceRecord`` /
``enumerate_split_evidence``) is deliberately *not* imported or re-exported
here. Reading QA/Summary evidence must always be an explicit
``from metacom_pm.paper1.splits.evidence import ...`` submodule import, never
reachable via ``from metacom_pm.paper1.splits import evidence`` or
``import *`` on this package -- see that module's docstring for why (B8
gold-adjacent evidence isolation).

B9/B14 terminology: what this module builds is a **group component**
(``GroupComponentAssignment.group_component_id`` / ``GROUP_COMPONENT_STATUS``
= a ``PREPACK_EXACT_EVIDENCE_COMPONENT``), not an outer cross-validation
fold. B14: this is a type owned entirely by this package -- it is never
written into the shared, frozen ``contracts.FoldAssignment`` (that field is
named ``fold_id`` and reads as "the outer fold" no matter how it's
documented; ``contracts.py`` itself is not modified, this package simply no
longer uses that type for this purpose).
``pack_components_into_outer_folds`` implements the actual outer-fold
packer; see ``exact_evidence_folds`` module docstring for why it is not yet
invoked to produce a frozen artifact this round
(``OUTER_FOLD_PACKING_STATUS`` = ``OUTER_FOLD_PACKING_PENDING_M2_FREEZE``).

B26: ``outer_fold_decision_surface`` enumerates that packer over a grid of
(K, seed) pairs purely as a diagnostic decision *surface* -- see that
module's docstring for why it never selects or freezes one point.
"""

from .exact_evidence_folds import (
    GROUP_COMPONENT_STATUS,
    OUTER_FOLD_PACKING_STATUS,
    GroupComponent,
    GroupComponentAssignment,
    build_group_component_assignments,
    build_group_components,
    build_shared_session_sensitivity_components,
    canonical_evidence_fingerprint,
    pack_components_into_outer_folds,
    summarize_outer_fold_packing,
)
from .outer_fold_decision_surface import (
    DEFAULT_K_VALUES,
    DEFAULT_SEED_VALUES,
    FoldDiagnostics,
    PackingSurfacePoint,
    enumerate_packing_surface,
    summarize_packing_surface,
)

__all__ = [
    "DEFAULT_K_VALUES",
    "DEFAULT_SEED_VALUES",
    "FoldDiagnostics",
    "GROUP_COMPONENT_STATUS",
    "GroupComponent",
    "GroupComponentAssignment",
    "OUTER_FOLD_PACKING_STATUS",
    "PackingSurfacePoint",
    "build_group_component_assignments",
    "build_group_components",
    "build_shared_session_sensitivity_components",
    "canonical_evidence_fingerprint",
    "enumerate_packing_surface",
    "pack_components_into_outer_folds",
    "summarize_outer_fold_packing",
    "summarize_packing_surface",
]
