"""Export a fixed, content-free result allowlist; never export private readbacks.

Requires the completed CPU diagnostics. Does not load a model, rebuild requests,
repair evaluations or infer new semantic labels. Output must be a new directory.
"""
import argparse
import json
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

from metacom_pm.rl1v3.io import file_sha256, write_json_once


def export(root, historical, out):
    root, historical, out = map(Path, (root, historical, out))
    out.mkdir(parents=True, exist_ok=False)
    sources = {
        'STOP_MS_SUMMARY.json': root/'selective-v1/SUMMARY_PUBLIC.json',
        'STOP_MS_TASKWISE.json': root/'selective-v1/TASKWISE_PUBLIC.json',
        'C1_RULE_AND_VALIDATION_PROPOSAL.json': root/'C1_RULE_AND_VALIDATION_PROPOSAL.json',
        'CONSTRAINED_CATALOG.json': root/'structured/packages-v3/CATALOG_CONSTRAINED.json',
        'CONSTRAINED_CPU_VALIDATION.json': root/'structured/CPU_VALIDATION_CONSTRAINED_V3.json',
        'CONSTRAINED_FEASIBILITY.json': root/'structured/FEASIBILITY_CONSTRAINED_V2.json',
        'CONSTRAINED_EVALUATION_FREEZE.json': root/'structured/EVALUATION_FREEZE_CONSTRAINED_V2.json',
    }
    for name in ('COUNTS', 'VALIDATION', 'FOCUSED_COUNTS', 'SCOPE', 'STEP2_JUDGMENT'):
        sources['ATTRIBUTION_'+name+'.json'] = root/('attribution/validated-v3/'+name+'_PUBLIC.json')
    for destination, source in sources.items():
        shutil.copyfile(source, out/destination)
    history = []
    for source, old in (
        ('HISTORY_TS_MEASUREMENTS.json', 'TS58_TECHNICAL_MEASUREMENTS.json'),
        ('HISTORY_JOINT_MEASUREMENTS.json', 'JOINT96_TECHNICAL_MEASUREMENTS.json'),
    ):
        current = json.loads((root/source).read_text())
        assert current == json.loads((historical/old).read_text())
        history.append(dict(recomputed_file_sha256=file_sha256(root/source),
            original_public_file=old, original_public_sha256=file_sha256(historical/old), exact_object_equal=True))
    ts = json.loads((root/'HISTORY_TS_MEASUREMENTS.json').read_text())
    joint = json.loads((root/'HISTORY_JOINT_MEASUREMENTS.json').read_text())['totals']
    suite = ET.parse(root/'CPU_TESTS_FINAL.xml').getroot()[0]
    tests = {k: int(suite.attrib[k]) for k in ('tests', 'errors', 'failures', 'skipped')}
    assert tests == dict(tests=267, errors=0, failures=0, skipped=0)
    preservation = dict(protocol='selection-diagnostic-history-preservation-v1',
        base_commit='35650aa2d63a52d59e73d549a19ac64996b9314a',
        scope='Existing T22/S36/J96 only; historical M36 attribution is a separate cohort.',
        historical_calls=ts['physical_calls']+joint['physical_calls'],
        historical_loads=ts['model_loads']+joint['loads'],
        historical_input_tokens=ts['total_input_tokens']+joint['input_tokens_observed'],
        historical_output_tokens=ts['total_output_tokens']+joint['output_tokens_observed'],
        comparisons=history, new_model_calls=0, new_model_loads=0, paid_api_calls=0,
        old_j06_all_96_observations_reconciled=True, original_evaluations_changed=False,
        new_semantic_judge_calls=0, old_five_human_reviews='pending_unchanged',
        tests=tests, cpu_test_xml_sha256=file_sha256(root/'CPU_TESTS_FINAL.xml'))
    assert preservation['historical_calls'] == 154 and preservation['historical_loads'] == 10
    write_json_once(out/'CPU_AND_HISTORY_RECEIPT.json', preservation)
    data = json.loads((out/'STOP_MS_TASKWISE.json').read_text())
    pairs = {}
    for row in data['rows']:
        pairs.setdefault(row['task'], {})[row['arm']] = row
    selections = {name: {r['task']: r for r in rows} for name, rows in data['selection_diagnostics'].items()}
    table = ['# 24题 STOP/MS 逐题诊断\n',
        '旧联合完成区间原样保留；1=确定完成，0=确定未完成，?=[0,1]。成本来自实际调用。',
        '五题方案、特权选择及C1都是事后开发诊断；C1不是已验证策略。完整四格、实际输入/输出tokens和时长见STOP_MS_TASKWISE.json。\n',
        '|题|组|STOP结果|MS结果|STOP输入/输出|MS输入/输出|五题方案|特权STOP/MS|C1|C1相对MS|',
        '|---|---|---|---|---:|---:|---|---|---|---|']
    label = {(0, 0): '0', (1, 1): '1', (0, 1): '?'}
    reason = dict(same_endpoint='保持MS', both_confirmed_success='共同成功节省',
        both_confirmed_failure='共同失败节省', uncertain_selection='不确定选择',
        confirmed_success_lost='确定退步', confirmed_repair='确定修复')
    for task, arms in pairs.items():
        stop, ms = arms['STOP'], arms['MS']
        chosen = [selections[n][task] for n in ('requested_five_switch', 'privileged_STOP_MS', 'C1_current_report_candidate')]
        values = [task, stop['source_group'], label[tuple(stop['joint'])], label[tuple(ms['joint'])],
            f"{stop['input_tokens']}/{stop['output_tokens']}", f"{ms['input_tokens']}/{ms['output_tokens']}",
            *[c['selected_arm'] for c in chosen], reason[chosen[-1]['category']]]
        table.append('|'+'|'.join(values)+'|')
    (out/'STOP_MS_TASKWISE_ZH.md').write_text('\n'.join(table)+'\n')
    manifest = dict(protocol='public-selection-allowlist-v1',
        source_file_sha256={name: file_sha256(path) for name, path in sources.items()},
        generated_files_sha256={p.name: file_sha256(p) for p in sorted(out.iterdir())},
        excluded='RAW, gold/reference values, full responses, queries, private reviews, source adapter, approval files',
        formal_reward=None)
    write_json_once(out/'EXPORT_MANIFEST.json', manifest)
    return preservation


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for name in ('root', 'historical', 'out'):
        parser.add_argument('--'+name, required=True)
    print(json.dumps(export(**vars(parser.parse_args())), indent=2))
