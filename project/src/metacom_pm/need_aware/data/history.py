"""Resolve only hash-bound, owner-bound, pre-cutoff runtime history."""
import hashlib
import json
from pathlib import Path
from .contracts import EvidenceRecord, RuntimeTask, text_hash


class HistoryResolver:
    def __init__(self, runtime_root):
        self.root = Path(runtime_root).resolve()
        self._cache = {}

    def resolve(self, task):
        if not isinstance(task, RuntimeTask):
            task = RuntimeTask.from_dict(task)
        path = (self.root / task.history_ref).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("history escapes runtime root")
        key = (str(path), task.history_sha256)
        if key not in self._cache:
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != task.history_sha256:
                raise ValueError("history file hash mismatch")
            self._cache[key] = json.loads(raw)
        obj = self._cache[key]
        if set(obj) != {"owner_id", "source_family", "messages"}:
            raise ValueError("unexpected history fields")
        if obj["owner_id"] != task.persona_group or obj["source_family"] != task.source_family:
            raise ValueError("wrong owner/source family")
        if task.cutoff > len(obj["messages"]):
            raise ValueError("cutoff beyond actual history")
        records = []
        for index, msg in enumerate(obj["messages"][:task.cutoff]):
            if set(msg) != {"role", "content"} or not isinstance(msg["content"], str):
                raise ValueError("invalid source message")
            text = msg["content"]
            records.append(EvidenceRecord(
                source_id=f"{task.source_family}:m{index}", owner_id=task.persona_group,
                source_family=task.source_family, session=task.source_family, order=index,
                speaker=msg["role"], situation="synthetic_history_message", reported_at=None,
                original_text=text, original_text_sha256=text_hash(text),
                coordinates={"message_index":index,"char_start":0,"char_end":len(text)}))
        return records

    def resolve_direct(self, task, manifest, arm):
        if arm not in {"C", "D"}:
            raise ValueError("Direct diagnostic coordinates forbidden for other arms")
        if manifest["task_id"] != task.task_id or manifest["status"] != "located_unique":
            raise ValueError("Direct diagnostic not evaluable")
        records = {r.source_id:r for r in self.resolve(task)}
        selected = [records[s["source_id"]] for s in manifest["spans"]]
        for record, span in zip(selected, manifest["spans"]):
            if record.original_text_sha256 != span["original_text_sha256"] or record.coordinates != span["coordinates"]:
                raise ValueError("Direct coordinate/hash mismatch")
        return selected
