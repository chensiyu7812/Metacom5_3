"""Independent read-only checks of source selection, requests, reuse and UI."""
from collections import Counter
from html.parser import HTMLParser
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT / 'src'))
from metacom_pm.io import sha256_file as sha
from metacom_pm.rl1.calibration_workflow import verify_identity
from metacom_pm.rl1.evidence import prefix_from_dict
from metacom_pm.rl1.resource_organization import OrganizedItem
from metacom_pm.rl1.schema import digest

OUT = PROJECT / 'outputs/pm_rl1/history_necessity_probe_20261105_v1'
read = lambda p: json.loads(p.read_text())


def main():
    from transformers import AutoTokenizer
    protocol = read(OUT / 'SCREENING_PROTOCOL.json'); verify_identity(protocol)
    selection = read(OUT / 'SELECTION_PRIVATE.json'); verify_identity(selection)
    run = read(OUT / 'alternate_G/PROTOCOL.json'); verify_identity(run)
    packet = read(OUT / 'HUMAN_PACKET_PRIVATE.json'); verify_identity(packet)
    for obj, groups in [(selection, ['source_hashes']), (run, ['sources', 'code']), (packet, ['source_hashes'])]:
        for group in groups:
            for path, expected in obj[group].items(): assert sha(Path(path)) == expected, path
    assert selection['screening_protocol'] == protocol['identity'] == run['screening_identity']
    assert packet['selection_identity'] == run['selection_identity'] == selection['identity']
    notes = read(OUT / 'SOURCE_ANNOTATIONS_PRIVATE.json')
    source = {r['case']: r for r in read(OUT / 'SOURCE_SCREEN_PRIVATE.json')}
    assert len(notes) == len(source) == 96
    assert {r['case'] for r in selection['cases']} == {r['case'] for r in notes if r['decision'] == 'candidate_with_controls'}
    assert max(Counter(r['owner'] for r in selection['cases']).values()) <= 2
    tokenizer = AutoTokenizer.from_pretrained(run['runtime']['model_dir'], local_files_only=True)
    for row in selection['cases']:
        prefix = prefix_from_dict(row['prefix'])
        assert prefix.split == 'train' and prefix.identity == row['prefix_identity']
        original = read(Path(row['source_path']))
        for arm in ('C', 'D'):
            item = row[arm]
            assert item in original['memory']
            assert OrganizedItem(**item).identity == row[arm + '_identity']
            assert item['owner_id'] == row['owner'] and item['source_rank'] < prefix.cutoff_rank
            assert item['reported_at'] < prefix.timestamp and item['source_check'] != 'unverified'
            assert json.loads(item['content'])['full_source_conversation'] == item['search_text']
        candidates = [m for m in source[row['case']]['MS'] if m['source_ids'][0] in row['distractor_eligible_sessions']]
        count = lambda m: len(tokenizer.encode(m['content'], add_special_tokens=False))
        assert min(candidates, key=lambda m: (abs(count(m)-count(row['C'])), m['key'])) == row['D']
        assert (count(row['C']), count(row['D'])) == (row['C_tokens'], row['D_tokens'])
    inputs = read(OUT / 'INPUTS_PRIVATE.json')
    requests = read(OUT / 'alternate_G/REQUESTS_PRIVATE.json')
    assert len(requests) == run['max_calls'] == 24 and digest(requests) == run['requests_identity']
    reuse = read(OUT / 'REUSED_PRIVATE.json')
    results = read(OUT / 'RESULTS_PRIVATE.json')
    assert len(inputs) == len(results) == 30 and len(reuse) == 6
    assert len(list((OUT / 'alternate_G/raw').glob('*.started.json'))) == 24
    assert len(list(OUT.glob('**/LOAD_STARTED.json'))) == 1
    closed = read(OUT / 'alternate_G/CLOSED.json'); verify_identity(closed)
    assert closed['completed'] == closed['natural'] == 24 and closed['training_updates'] == 0
    for result in results:
        assert result['valid'] and result['quality'] is result['reward'] is None
        raw = result['raw']; assert digest(raw['text']) == raw['text_identity']
        assert raw['completed_assistant_turn'] and raw['output_token_ids'][-1] in (1, 106)
        assert raw['runtime_identity'] == run['runtime']['identity'] and raw['api_cost_usd'] == 0
        item = inputs[result['input_identity']]
        native = tokenizer.apply_chat_template(item['messages'], tokenize=True, add_generation_prompt=True,
            enable_thinking=False, return_dict=False)
        req = (reuse[result['input_identity']]['request'] if result['reused'] else
               next(r for r in requests if r['input_identity'] == result['input_identity']))
        verify_identity(req)
        assert req['messages'] == item['messages'] and req['messages_identity'] == digest(item['messages'])
        assert req['token_ids_identity'] == digest(native) and len(native) == raw['input_tokens']
        assert req['selected_keys'] == item['selected_keys']
        assert req['selected_resource_identities'] == item['selected_resource_identities']
        assert item['usage']['within_native_context'] and not item['usage']['truncation']
        assert read(Path(result['source'])) == raw
    old = read(OUT / 'REUSED_HUMAN_PRIVATE.json')
    assert set(old) == {'H34', 'H79'} and [old[c]['C_over_OFF'] for c in ('H34', 'H79')] == [1, 0]
    for entry in old.values():
        assert sha(Path(entry['registry'])) == entry['registry_sha256']
        assert entry['record'] in read(Path(entry['registry']))
    mapping = packet['mapping']; assert len(mapping) == 10
    assert Counter(m['mode'] for m in mapping) == {'rank': 8, 'pair': 2}
    assert sum(len(m['display']) for m in mapping) == 28
    for m in mapping:
        assert m['case'] in {r['case'] for r in selection['cases']}
        assert {v['arm'] for v in m['display'].values()} == ({'C', 'D'} if m['mode'] == 'pair' else {'C', 'D', 'OFF'})
        for label, shown in m['display'].items():
            raw = next(r['raw'] for r in results if r['case'] == m['case'] and r['arm'] == shown['arm'])
            assert shown['reply_identity'] == raw['text_identity']
    class Parser(HTMLParser):
        def __init__(self): super().__init__(); self.ids = []; self.tags = Counter()
        def handle_starttag(self, tag, attrs):
            self.tags[tag] += 1
            attrs = dict(attrs)
            if 'id' in attrs: self.ids.append(attrs['id'])
            assert not attrs.get('src', '').startswith(('https:', 'http:'))
    page = (OUT / 'HUMAN_REVIEW_ZH.html').read_text(); parser = Parser(); parser.feed(page)
    assert len(parser.ids) == len(set(parser.ids)) and parser.tags['section'] == 10 and parser.tags['article'] == 28
    assert packet['identity'] in page and 'fetch(' not in page and 'XMLHttpRequest' not in page
    assert all(f'id="{m["question"]}-order"' in page for m in mapping)
    assert not (OUT / 'HUMAN_ANSWERS.json').exists(), 'Pending-state verifier must be revised after real answers arrive'
    manifest = OUT / 'OUTPUT_MANIFEST.json'
    if manifest.exists():
        for name, expected in read(manifest).items(): assert sha(OUT / name) == expected, name
    print(json.dumps(dict(status='VERIFIED', screened=96, selected=10, owners=7, conditions=30,
        new_calls=24, cached_replies=6, old_human_pairs_reused=2, human_questions=10,
        new_human_answers=0, new_training_updates=0, API_cost_usd=0), ensure_ascii=False))


if __name__ == '__main__': main()
