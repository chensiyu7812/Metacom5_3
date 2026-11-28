"""Modified WP3 short-answer protocol, separate from official WP2 semantics."""
import re
from .mcq import extract_final_answer
from ..data.short_protocol import PROTOCOL,MAX_NEW_TOKENS,SHORT_SUFFIX,instruction


def extract_short_answer(output):
    match = re.fullmatch(r'\s*Final Answer: ([ABCD])\s*', output)
    return match[1] if match else ''


def score_short(output, task, evaluation):
    if task.task_id != evaluation.task_id or task.task_mode != 'mcq':
        raise ValueError('task/evaluation mode or identity mismatch')
    options = {o['id']:o['text'] for o in task.options}
    if options.get(evaluation.gold_choice_id) != evaluation.reference_answer:
        raise ValueError('frozen option/gold mapping changed')
    choice = extract_short_answer(output)
    official = extract_final_answer(output)
    if choice and choice != official:
        raise ValueError('short accepted output incompatible with pinned official parser')
    return dict(task_id=task.task_id, predicted_choice=choice, parse_valid=bool(choice),
                correct=bool(choice and choice==evaluation.gold_choice_id),
                scoring_protocol=PROTOCOL, official_parser_choice_diagnostic=official)
