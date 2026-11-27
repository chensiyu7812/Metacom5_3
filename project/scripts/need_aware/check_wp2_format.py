#!/usr/bin/env python3
"""Technical-only check of sealed model outputs against the pinned official parser.

No EvalTask, answers, accuracy, model/prompt changes or extra inference. Report
format validity separately by finish reason; never repair or loosen parsing.
"""
import argparse
import ast
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import subprocess

from metacom_pm.need_aware.data.personamem import UPSTREAM_COMMIT
from metacom_pm.need_aware.evaluation.mcq import extract_final_answer


def check(export, upstream):
    commit = subprocess.check_output(['git', '-C', str(upstream), 'rev-parse', 'HEAD'], text=True).strip()
    if commit != UPSTREAM_COMMIT:
        raise ValueError('upstream comparator revision changed')
    tree = ast.parse((upstream/'inference.py').read_text())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'PersonaBenchmarkEvaluator')
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'extract_final_answer')
    module = ast.Module(body=[ast.ClassDef(name='Reference', bases=[], keywords=[], body=[method], decorator_list=[])], type_ignores=[])
    namespace = {}
    exec(compile(ast.fix_missing_locations(module), '<pinned upstream parser only>', 'exec'), namespace)
    reference = namespace['Reference']()
    seal = json.loads((export/'EXPORT_SUMMARY.json').read_text())
    if seal['result_kind'] != 'model':
        raise ValueError('this technical receipt requires actual model outputs')
    counts, mismatch = defaultdict(Counter), 0
    for key, entry in sorted(seal['files'].items()):
        data = (export/Path(entry['path']).name).read_bytes()
        if hashlib.sha256(data).hexdigest() != entry['sha256']:
            raise ValueError('export file changed')
        for p in map(json.loads, data.splitlines()):
            if p['status'] != 'completed':
                continue
            output = p['output']
            predicted = extract_final_answer(output)
            mismatch += predicted != reference.extract_final_answer(output)
            group = counts[key+'/'+p['finish_reason']]
            group['completed'] += 1
            group['official_format_valid'] += predicted in ('A', 'B', 'C', 'D')
            group['official_parse_invalid'] += predicted not in ('A', 'B', 'C', 'D')
            group['empty_output'] += not output.strip()
    return dict(result_kind='model_technical_only', model_capability_result=False, gold_read=False,
                accuracy_computed=False, upstream_commit=commit, manifest_sha256=seal['manifest_sha256'],
                ledger_head_sha256=seal['ledger_head_sha256'], snapshot_final=seal['final'],
                completed_outputs=sum(c['completed'] for c in counts.values()),
                official_parser_disagreements=mismatch, by_cell_finish={k: dict(v) for k, v in counts.items()},
                interpretation='Format failures are actual returned-output failures under the unchanged official parser; not transport failures. No correctness inference or relaxed scoring.')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--export-dir', type=Path, required=True)
    p.add_argument('--upstream', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args(); result = check(a.export_dir, a.upstream)
    a.out.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))
    if result['official_parser_disagreements']:
        raise SystemExit('technical parser mismatch; investigate without changing frozen scoring rules')
