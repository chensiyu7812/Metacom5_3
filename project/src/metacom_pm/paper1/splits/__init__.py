"""Primary exact-evidence group-component construction for Paper-1 targets.

``evidence`` is a separate submodule (not re-exported at top level as a
default import) so that reading ``SplitEvidenceRecord``/
``enumerate_split_evidence`` is always an explicit, visible act -- see its
module docstring for why (B8 gold-adjacent evidence isolation).

B9 terminology: what this module calls a "fold" in the shared
``FoldAssignment`` contract is a **group component**
(``group_component_id`` / ``GROUP_COMPONENT_STATUS`` = a
``PREPACK_EXACT_EVIDENCE_COMPONENT``), not an outer cross-validation fold.
``pack_components_into_outer_folds`` implements the actual outer-fold
packer; see ``exact_evidence_folds`` module docstring for why it is not yet
invoked to produce a frozen artifact this round
(``OUTER_FOLD_PACKING_STATUS`` = ``OUTER_FOLD_PACKING_PENDING_M2_FREEZE``).
"""

from . import evidence
from .exact_evidence_folds import (
    GROUP_COMPONENT_STATUS,
    OUTER_FOLD_PACKING_STATUS,
    GroupComponent,
    build_fold_assignments,
    build_group_components,
    build_shared_session_sensitivity_components,
    canonical_evidence_fingerprint,
    pack_components_into_outer_folds,
    summarize_outer_fold_packing,
)

__all__ = [
    "GROUP_COMPONENT_STATUS",
    "OUTER_FOLD_PACKING_STATUS",
    "GroupComponent",
    "build_fold_assignments",
    "build_group_components",
    "build_shared_session_sensitivity_components",
    "canonical_evidence_fingerprint",
    "evidence",
    "pack_components_into_outer_folds",
    "summarize_outer_fold_packing",
]
