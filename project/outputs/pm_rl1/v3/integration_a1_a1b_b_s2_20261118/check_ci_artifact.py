"""Inspect downloaded GitHub JUnit evidence, including historical skips."""
import argparse, hashlib, json, zipfile, xml.etree.ElementTree as ET
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('--zip', type=Path, required=True)
p.add_argument('--metadata', type=Path, required=True)
p.add_argument('--jobs', type=Path, required=True)
p.add_argument('--head', required=True)
p.add_argument('--out', type=Path, required=True)
p.add_argument('--local-v3', type=Path)
a = p.parse_args()
artifact = json.loads(a.metadata.read_text())
jobs = json.loads(a.jobs.read_text())['jobs']
assert artifact['workflow_run']['head_sha'] == a.head
digest = hashlib.sha256(a.zip.read_bytes()).hexdigest()
assert artifact['digest'] == 'sha256:' + digest
assert jobs and all(j['status'] == 'completed' and j['conclusion'] == 'success' for j in jobs)
steps = [s for j in jobs for s in j['steps']]
for name in ('Run all V3 acceptance tests', 'Reject missing, skipped, xfailed or failed V3 acceptance',
             'Run blocking public-only Paper-1 suite', 'Validate Paper-1 integration base and outcome lock'):
    assert any(s['name'] == name and s['status'] == 'completed' and s['conclusion'] == 'success' for s in steps), name
out = dict(head=a.head, artifact_id=artifact['id'], artifact_sha256=digest,
           integration_base_actually_passed=True, all_jobs_success=True)
with zipfile.ZipFile(a.zip) as z:
    assert set(z.namelist()) == {'pytest-results.xml', 'v3-results.xml', 'v3-gate.json'}
    gate = json.loads(z.read('v3-gate.json'))
    assert gate['passed'] == 466 and all(gate[k] == 0 for k in ('errors','failures','skipped','xfailed'))
    out['v3_gate'] = gate
    for name in ('pytest-results.xml','v3-results.xml'):
        cases = list(ET.fromstring(z.read(name)).iter('testcase'))
        assert not any(c.find('error') is not None or c.find('failure') is not None for c in cases)
        skips = [dict(test=c.attrib.get('classname','')+'::'+c.attrib['name'],
                      reason=c.find('skipped').get('message'), detail=c.find('skipped').text)
                 for c in cases if c.find('skipped') is not None]
        assert not any('rl1v3' in s['test'] for s in skips)
        out[name] = dict(passed=len(cases)-len(skips), skipped=len(skips), skip_details=skips)
        if name == 'v3-results.xml' and a.local_v3:
            local = list(ET.parse(a.local_v3).getroot().iter('testcase'))
            key = lambda c: (c.attrib.get('classname'), c.attrib['name'])
            assert sorted(map(key,cases)) == sorted(map(key,local))
            out['same_v3_test_identity_set_as_local'] = True
        dest = a.out.parent / name
        with dest.open('xb') as f:
            f.write(z.read(name))
    with (a.out.parent/'v3-gate.json').open('xb') as f:
        f.write(z.read('v3-gate.json'))
with a.out.open('x') as f:
    json.dump(out,f,ensure_ascii=False,indent=2); f.write('\n')
print(json.dumps({k:v for k,v in out.items() if k not in ('pytest-results.xml','v3-results.xml')},ensure_ascii=False))
print('CPU:', out['pytest-results.xml']['passed'], 'passed;', out['pytest-results.xml']['skipped'], 'historical skips')
