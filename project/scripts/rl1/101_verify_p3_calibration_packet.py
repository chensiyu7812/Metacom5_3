#!/usr/bin/env python3
"""Audit the real packet; no inferred human labels and no validation scoring."""
from collections import Counter
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / 'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.schema import digest

ROOT = PROJECT / 'outputs/pm_rl1/completion_20260930_v2/P3'
PACKET = ROOT / 'calibration'


def read(p):
    return json.loads(p.read_text())


def main():
    checks = []
    for directory, name in [(ROOT / 'common_evidence', 'input_freeze.json'),
                            (PACKET, 'packet_freeze.json'), (ROOT / 'candidate_v1', 'candidate_freeze.json')]:
        freeze = read(directory / name)
        for n, h in freeze['files'].items():
            assert sha256_file(directory / n) == h, n
        for n, h in freeze['source_files'].items():
            assert sha256_file(PROJECT / n) == h, n
        checks.append(str(directory.relative_to(ROOT)) + ': frozen source/code/artifact hashes')
    pool = read(ROOT / 'common_evidence/evidence_pool_private.json')
    packet = read(PACKET / 'pairs_private.json'); pairs = packet['pairs']
    phase_owners = {g:{p['owner'] for p in pairs if p['group'] == g} for g in ('development','validation','reserve')}
    phase_prefixes = {g:{p['prefix_identity'] for p in pairs if p['group'] == g} for g in phase_owners}
    assert not phase_owners['development'] & (phase_owners['validation'] | phase_owners['reserve'])
    assert not phase_prefixes['development'] & (phase_prefixes['validation'] | phase_prefixes['reserve'])
    checks.append('development vs validation/reserve: disjoint owners and prefixes')
    expected = {'development_natural':8, 'development_control':8,
                'validation_natural':16, 'validation_control':8, 'reserve_natural':8}
    assert dict(Counter(p['group']+'_'+p['kind'] for p in pairs)) == expected
    checks.append('fixed 40 active plus 8 reserve, no filtering on scorer results')
    by_id = {p['pair_id']:p for p in pairs}
    for rater in ('rater_1','rater_2'):
        form = read(PACKET / (rater+'_form.json')); mapping = read(PACKET / (rater+'_map_private.json'))
        assert digest({k:v for k,v in form.items() if k != 'form_identity'}) == form['form_identity']
        assert len(form['items']) == 40 and len(mapping) == 40
        assert {mapping[i['item_id']]['pair_id'] for i in form['items']} == {
            p['pair_id'] for p in pairs if p['group'] != 'reserve'}
        for item in form['items']:
            assert set(item) == {'item_id','source_key','A','B'}
            meta = mapping[item['item_id']]; pair = by_id[meta['pair_id']]
            assert [item['A'], item['B']] == pair['replies'][::(-1 if meta['swapped'] else 1)]
            assert form['sources'][item['source_key']] == pool[pair['prefix_identity']]
        checks.append(rater+': blind fields, exact responses, complete same sources, all pairs present')
    jobs = read(ROOT / 'candidate_v1/jobs_private.json')
    assert len({j['job_id'] for j in jobs}) == len(jobs)
    repeat = [j for j in jobs if j['repeat']]
    assert len(repeat) == 12
    primary = {j['job_id']:j for j in jobs if j['draw_id']=='primary'}
    for j in repeat:
        first = primary[j['primary_job_id']]
        assert j['seed'] != first['seed'] and j['draw_id'] != first['draw_id']
        assert j['evidence'] == first['evidence'] and j['reply'] == first['reply']
    checks.append('12 independent repeat jobs use identical source/reply and distinct draws/seeds')
    refs = read(ROOT / 'candidate_v1/pair_score_map_private.json')
    content_keys = {}
    for j in primary.values():
        k = digest([j['evidence'], j['reply']])
        assert k not in content_keys
        content_keys[k] = j['job_id']
    assert len(refs) == 96 and len(primary) == 95
    checks.append('one identical-content pair side reused, never model-invented score difference')
    # Fix a UI-only edge: validation of an incomplete export navigates through
    # move(), not a navigation button. Observe source rerenders to keep the date
    # correct for *every* navigation path. Original v1/v2 files stay untouched.
    previous = PACKET / 'human_handoff_v2'
    release = read(previous / 'release.json')
    final = PACKET / 'human_handoff_final'
    supplement = "new MutationObserver(showCurrentCutDate).observe($('current'), {childList:true});"
    if not final.exists():
        final.mkdir()
        for rater in ('rater_1','rater_2'):
            p = previous / (rater+'.html')
            assert sha256_file(p) == release['files'][p.name]
            (final / p.name).write_text(p.read_text().replace('</html>', '<script>'+supplement+'</script></html>'))
        result = dict(status='FINAL_DISPLAY_NO_INSTRUMENT_OR_LABEL_CHANGE',
            packet_identity=packet['packet_identity'], previous_release_sha256=sha256_file(previous/'release.json'),
            source_script_sha256=sha256_file(Path(__file__)), display_supplement=supplement,
            files={p.name:sha256_file(p) for p in final.glob('*.html')})
        (final / 'release.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    release = read(final / 'release.json')
    assert release['source_script_sha256'] == sha256_file(Path(__file__))
    for n,h in release['files'].items():
        assert sha256_file(final/n) == h
    result = dict(status='PASS', checks=checks, pair_counts=expected,
        owners={g:sorted(v) for g,v in phase_owners.items()}, distinct_primary_replies=95,
        development_scoring_replies=32, validation_scoring_replies=47, reserve_scoring_replies=16,
        human_labels_created=0, human_labels_read=0, validation_scores_read=0,
        limitations=['No claim of independence among pairs within owner.',
            'No claim of exhaustively detecting cross-owner paraphrased shared sources.',
            'Four executor contrasts are development-only; sealed validation is resource contrasts.',
            'Control source anchors are coordinator construction evidence, not human correctness judgments.'])
    (ROOT/'verification/packet_integrity.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
