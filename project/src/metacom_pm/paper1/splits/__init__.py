"""Primary exact-evidence fold construction for Paper-1 memory targets.

``evidence`` is a separate submodule (not re-exported at top level as a
default import) so that reading ``SplitEvidenceRecord``/
``enumerate_split_evidence`` is always an explicit, visible act -- see its
module docstring for why (B8 gold-adjacent evidence isolation).
"""

from . import evidence
from .exact_evidence_folds import (
    build_fold_assignments,
    build_shared_session_sensitivity_components,
    canonical_evidence_fingerprint,
)

__all__ = [
    "build_fold_assignments",
    "build_shared_session_sensitivity_components",
    "canonical_evidence_fingerprint",
    "evidence",
]
