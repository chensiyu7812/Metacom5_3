"""Independent compatibility implementation of PersonaMem-v2 MCQ semantics.

Upstream d29d91d inference.py: create_mcq_options, extract_final_answer,
check_mcq_correctness. No provider/client import and no model execution.
"""
import random
import re

from ..data.prompts import RECALL_SUFFIX, instruction, official_messages

def make_options(correct_answer, incorrect_answers, seed):
    texts = [correct_answer, *incorrect_answers]
    random.Random(seed).shuffle(texts)
    options = [{"id": chr(65+i), "text": text} for i, text in enumerate(texts)]
    gold = next(o["id"] for o in options if o["text"] == correct_answer)
    return options, gold


def extract_final_answer(response):
    if not response:
        return ""
    # Priority and first-match behavior intentionally follow upstream, even
    # for contradictory answers. Plain 'A' is NOT accepted; 'A.' is.
    patterns = [r'\$\\boxed\{([A-Z])\}\$', r'\\boxed\{([A-Z])\}',
                r'Final Answer:\s*([A-Z])', r'final answer:\s*([A-Z])',
                r'Answer:\s*([A-Z])', r'answer:\s*([A-Z])',
                r'final answer is\s*\$?\\boxed\{([A-Z])\}\$?',
                r'final answer is\s*([A-Z])',
                r'the answer is\s*\$?\\boxed\{([A-Z])\}\$?',
                r'the answer is\s*([A-Z])', r'\b([A-Z])\.\s*$']
    for pattern in patterns:
        match = re.search(pattern, response, re.IGNORECASE | re.MULTILINE)
        if match:
            return match[1].upper()
    return ""


def score_one(output, task, eval_task):
    if task.task_id != eval_task.task_id or task.task_mode != "mcq":
        raise ValueError("task/evaluation identity or mode mismatch")
    mapping = {o["id"]:o["text"] for o in task.options}
    if mapping.get(eval_task.gold_choice_id) != eval_task.reference_answer:
        raise ValueError("option mapping differs from frozen evaluation")
    parsed = extract_final_answer(output)
    return {"task_id":task.task_id, "predicted_choice":parsed,
            "parse_valid":parsed in mapping,
            "correct":bool(parsed and mapping.get(parsed, "") == eval_task.reference_answer)}
