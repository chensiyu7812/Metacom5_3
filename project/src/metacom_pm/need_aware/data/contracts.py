"""Versioned A/B exchange. Unknown fields fail closed, including nested gold keys."""
from dataclasses import asdict, dataclass, field
import hashlib
import json

SCHEMA_VERSION = "naa-v1"


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":")).encode()).hexdigest()


def text_hash(text):
    return hashlib.sha256(text.encode()).hexdigest()


@dataclass(frozen=True)
class RuntimeTask:
    task_id: str
    dataset_revision: str
    split: str
    persona_group: str
    source_family: str
    history_ref: str
    history_sha256: str
    cutoff: int  # exclusive message index; no synthetic wall-clock time
    current_messages: list
    user_query: str  # retrieval uses ONLY this and current_messages, never options
    task_mode: str
    options: list = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self):
        if self.schema_version != SCHEMA_VERSION or self.split not in {"train", "val"}:
            raise ValueError("unsupported schema/split; formal test is closed")
        if self.task_mode not in {"mcq", "generation"} or type(self.cutoff) is not int or self.cutoff < 0:
            raise ValueError("invalid mode/cutoff")
        if not all(isinstance(x, str) and x for x in [self.task_id, self.dataset_revision,
                   self.persona_group, self.source_family, self.history_ref, self.history_sha256, self.user_query]):
            raise ValueError("missing identity")
        if self.history_ref.startswith("/") or ".." in self.history_ref.split("/"):
            raise ValueError("history path must remain within runtime root")
        for msg in self.current_messages:
            if set(msg) != {"role", "content"} or msg["role"] not in {"user", "assistant"} or not isinstance(msg["content"], str):
                raise ValueError("invalid current message")
        if self.task_mode == "generation" and self.options:
            raise ValueError("generation must not receive options")
        if self.task_mode == "mcq" and len(self.options) != 4:
            raise ValueError("PersonaMem MCQ must have four options")
        for i, option in enumerate(self.options):
            if set(option) != {"id", "text"} or option["id"] != chr(65+i) or not isinstance(option["text"], str):
                raise ValueError("invalid option; answer markers prohibited")

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        return cls(**data)


@dataclass(frozen=True)
class EvidenceRecord:
    source_id: str
    owner_id: str
    source_family: str
    session: str
    order: int
    speaker: str
    situation: str
    reported_at: object
    original_text: str
    original_text_sha256: str
    coordinates: dict
    validity: str = "unknown"

    def __post_init__(self):
        if self.speaker not in {"user", "assistant", "system"} or self.validity not in {"unknown", "excluded"}:
            raise ValueError("unverified identity/validity")
        if text_hash(self.original_text) != self.original_text_sha256:
            raise ValueError("text hash mismatch")
        if set(self.coordinates) != {"message_index", "char_start", "char_end"}:
            raise ValueError("invalid coordinates")
        if self.coordinates != {"message_index": self.order, "char_start": 0, "char_end": len(self.original_text)}:
            raise ValueError("v1 records are complete source messages")

    def to_dict(self):
        return asdict(self)


def load_runtime(path):
    with open(path) as stream:
        tasks = [RuntimeTask.from_dict(json.loads(line)) for line in stream if line.strip()]
    if len({t.task_id for t in tasks}) != len(tasks):
        raise ValueError("duplicate task_id")
    return tasks
