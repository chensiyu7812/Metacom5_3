"""Seal completed diagnostic and timing evidence; retain ordinal missingness."""
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT / 'src'))
from metacom_pm.io import sha256_file as sha
from metacom_pm.rl1.durable import save_json_once as save
from metacom_pm.rl1.schema import digest

BASE = PROJECT / 'outputs/pm_rl1'
ROOT = BASE / 'slight_positive_path_20261105_v1'
TIMING = BASE / 'reused_pair_g_latency_20261105_v1'


def read(p):
    return json.loads(p.read_text())


def main():
    cards = read(ROOT / 'CARDS_PRIVATE.json')
    reused = read(ROOT / 'REUSED_PRIVATE.json')
    reqs = read(ROOT / 'alternate_G_resume/REQUESTS_PRIVATE.json')
    old = read(ROOT / 'OLD_HUMAN_REFERENCE_PRIVATE.json')
    registry_path = BASE / 'incremental_help_human_review_20261105_v1/ANSWER_REGISTRY_PRIVATE.json'
    registry = read(registry_path)
    rows = []
    for card in cards:
        key = card['input_identity']
        if card['reused']:
            source = Path(reused[key]['source'])
        else:
            req = next(r for r in reqs if r['input_identity'] == key)
            source = ROOT / 'alternate_G_resume/raw' / (req['identity'] + '.json')
        raw = read(source)
        rows.append(dict(**card, reply=raw['text'], reply_identity=digest(raw['text']),
            raw_source=str(source.resolve()), raw_sha256=sha(source), finish_reason=raw['finish_reason'],
            format_failure=any(m in raw['decoded_with_special_tokens'] for m in ('<channel|>', '<|channel', '[channel]', '<think>', '</think>')),
            output_tokens=raw['output_tokens'], G_seconds=raw['generation_seconds'],
            G_first_token_seconds=raw['first_token_seconds'],
            exact_old_preferred_reply=raw['text'] == old['raw']['text'], human_preference_transferred=False))
    ids = {r['reply_identity'] for r in rows}
    reuse_check = [dict(asset_id=r['asset_id'], kind=r.get('kind', r.get('task_family', 'supplement')),
        overlapping_reply_identities=sorted(set(r.get('reply_identities', [])) & ids),
        both_pair_replies_match=bool(r.get('reply_identities')) and len(set(r['reply_identities'])) == 2
                               and set(r['reply_identities']) <= ids)
        for r in registry]
    assert not any(r['both_pair_replies_match'] for r in reuse_check)
    save(ROOT / 'RESULTS_PRIVATE.json', rows)
    save(ROOT / 'REFERENCE_REUSE_PRIVATE.json', dict(registry_sha256=sha(registry_path), records=reuse_check,
        exact_pair_matches=0, reply_match_alone_is_not_label_transfer=True))
    save(ROOT / 'CONTENT_REVIEW_PRIVATE.json', dict(author='Codex source/content inspection, not human preference',
        observations=[
            dict(depth=0, text='Asks how to handle the relationship moving forward; this exact reply was the G01 nonpreferred side.'),
            dict(depth=1, text='Again asks how to handle things moving forward. Different reply, not automatically assigned G01 label.'),
            dict(depth=2, text='Validates hurt and disappointment, no follow-up question; target friendship session not yet acquired.'),
            dict(depth=3, text='Asks how the person feels about those friendships now. Not identical to the future-action question, no preference inferred.'),
            dict(depth=4, text='Validates hurt/disappointment, no follow-up question. Target present, but explicit adoption of its distinct facts is not established.')],
        interpretation='No monotonic benefit with read count is established. The no-follow-up style also appears without the target at depth 2; target-specific necessity for that stylistic change is not supported.',
        helpfulness=None, quality_difference=None, PPO_reward=None))
    replay = read(ROOT / 'FROZEN_LOCATOR_REPLAY_PRIVATE.json')
    timing = read(TIMING / 'SUMMARY.json')
    save(ROOT / 'SUMMARY.json', dict(branch_endpoints=5, reused=2, new_branch_G_calls=3,
        natural_branch_endpoints=sum(r['finish_reason'] == 'natural_stop' for r in rows),
        format_failures=sum(r['format_failure'] for r in rows), branch_exact_human_pair_matches=0,
        alternative_static_locator_G01_exact_reuse=True, alternative_actions=[3, 0],
        full_original_MS_coverage_prefixes=sum(r['complete_frozen_replay_available'] for r in replay['coverage']),
        total_train_prefixes=24, timing_calls=10, timing_warmups=2, timing_pairs=4,
        new_G_calls_total=13, actual_G_loads=2, rejected_preload_attempts=1,
        old_human_records_preserved=len(registry), new_human_answers=0, new_qualified_scalar_rewards=0,
        new_training_updates=0, prior_cost_negative_control_updates=24, API_cost_usd=0,
        timing_summary=timing))
    for folder in (ROOT, TIMING):
        save(folder / 'OUTPUT_MANIFEST.json', {str(p.relative_to(folder)): sha(p)
             for p in sorted(folder.rglob('*')) if p.is_file() and p.name != 'OUTPUT_MANIFEST.json'})
    print(json.dumps(read(ROOT / 'SUMMARY.json'), ensure_ascii=False))


if __name__ == '__main__':
    main()
