from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class EvalTask:
    task_id: str
    gold_choice_id: str | None
    reference_answer: str
    gold_preference: str
    related_snippet: list
    category: dict
    verified_spans: list
    direct_status: str
    scoring_protocol: str = "personamem-v2-inference-d29d91d"

    def to_dict(self):
        return asdict(self)
