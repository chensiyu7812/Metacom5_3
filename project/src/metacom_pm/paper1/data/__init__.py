"""Public-only ES-MemEval/EvoEmo dataset loaders for Paper-1 memory/RQ2 work.

B12: only the sanitized runtime surface (``memory_source``) is exported here.
The evaluator/split-only, evidence-bearing types
(``UserRecord``/``QuestionItem``/``SummaryItem``/``parse_users``) live in
``metacom_pm.paper1.data.es_memeval`` and are deliberately *not* re-exported
from this package -- only ``metacom_pm.paper1.splits.evidence`` should ever
import them, and it does so via an explicit submodule import
(``from metacom_pm.paper1.data.es_memeval import ...``), never through here.
"""

from .es_memeval import PAPER_QA_COUNT, PUBLIC_QA_COUNT, Session, Turn, load_users
from .memory_source import (
    MemorySourceQuestionGroup,
    MemorySourceQuestionItem,
    MemorySourceSubsequentTopic,
    MemorySourceSummaryItem,
    MemorySourceUser,
    Target,
    enumerate_targets,
    parse_memory_source_users,
    validate_es_memeval_identity,
)

__all__ = [
    "PAPER_QA_COUNT",
    "PUBLIC_QA_COUNT",
    "MemorySourceQuestionGroup",
    "MemorySourceQuestionItem",
    "MemorySourceSubsequentTopic",
    "MemorySourceSummaryItem",
    "MemorySourceUser",
    "Session",
    "Target",
    "Turn",
    "enumerate_targets",
    "load_users",
    "parse_memory_source_users",
    "validate_es_memeval_identity",
]
