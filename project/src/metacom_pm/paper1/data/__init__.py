"""Public-only ES-MemEval/EvoEmo dataset loaders for Paper-1 memory/RQ2 work.

B12/B18: only the sanitized runtime surface (``memory_source``) is exported
here, and it is entirely self-contained -- it never imports
``es_memeval``/``materializer``, and neither of those is re-exported from
this package. The evaluator/split-only, evidence-bearing types
(``UserRecord``/``QuestionItem``/``SummaryItem``/``parse_users``) live in
``metacom_pm.paper1.data.es_memeval``; the raw-JSON -> sanitized-artifact
builder lives in ``metacom_pm.paper1.data.materializer``. Both require an
explicit submodule import (``from metacom_pm.paper1.data.es_memeval import
...`` / ``from metacom_pm.paper1.data.materializer import ...``), never
reachable through this top-level package -- only
``metacom_pm.paper1.splits.evidence`` should import the former, and only the
materializer build script should import the latter.
"""

from .memory_source import (
    MemorySourceQuestionGroup,
    MemorySourceQuestionItem,
    MemorySourceSubsequentTopic,
    MemorySourceSummaryItem,
    MemorySourceUser,
    Session,
    Target,
    Turn,
    enumerate_targets,
    load_sanitized_runtime_users,
)

__all__ = [
    "MemorySourceQuestionGroup",
    "MemorySourceQuestionItem",
    "MemorySourceSubsequentTopic",
    "MemorySourceSummaryItem",
    "MemorySourceUser",
    "Session",
    "Target",
    "Turn",
    "enumerate_targets",
    "load_sanitized_runtime_users",
]
