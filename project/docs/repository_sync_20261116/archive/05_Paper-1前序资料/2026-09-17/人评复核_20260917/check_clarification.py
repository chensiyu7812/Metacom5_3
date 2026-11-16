from pathlib import Path
import json,hashlib,tempfile
from playwright.sync_api import sync_playwright

OUT=Path(__file__).resolve().parent
checks=[]
with sync_playwright() as pw:
    b=pw.chromium.launch(executable_path='/usr/bin/google-chrome',headless=True,args=['--no-sandbox'])
    context=b.new_context(accept_downloads=True,viewport={'width':1280,'height':1000})
    page=context.new_page();page.route('http://**',lambda r:r.abort());page.route('https://**',lambda r:r.abort())
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto((OUT/'判题口径澄清_6例.html').as_uri())
    assert page.locator('article').count()==6
    assert page.locator('input[type=radio]:checked').count()==0
    assert page.locator('#progress').inner_text()=='已记录 0/6'
    page.screenshot(path=str(OUT/'review_desktop.png'))
    page.locator('article').nth(0).scroll_into_view_if_needed()
    page.screenshot(path=str(OUT/'review_case.png'))
    page.set_viewport_size({'width':390,'height':1000});page.evaluate('scrollTo(0,0)')
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.screenshot(path=str(OUT/'review_mobile.png'))
    for i in range(6):
        card=page.locator('article').nth(i)
        assert card.locator('details pre').count()==4
    page.locator('article[data-case="clarify_A03"] input[value="different_understanding"]').check()
    page.locator('article[data-case="clarify_A03"] textarea').fill('TEST ONLY: 中文导出与恢复 <script> 不应执行')
    assert page.locator('#progress').inner_text()=='已记录 1/6'
    page.reload()
    assert page.locator('#progress').inner_text()=='已记录 1/6'
    assert page.locator('article[data-case="clarify_A03"] textarea').input_value().startswith('TEST ONLY')
    with tempfile.TemporaryDirectory(prefix='metacom-comprehension-qa-') as td:
        with page.expect_download() as download:
            page.locator('#export').click()
        output=Path(td)/'test_notes.json';download.value.save_as(output)
        data=json.loads(output.read_text())
        assert data['record_type']=='assisted_comprehension_notes_not_ratings'
        assert len(data['notes'])==6 and data['notes'][0]['understanding_status']=='different_understanding'
        assert all(n['understanding_status'] is None for n in data['notes'][1:])
        assert all('verdict' not in n and 'rationale' not in n for n in data['notes'])
        page.evaluate('localStorage.clear()');page.reload()
        assert page.locator('#progress').inner_text()=='已记录 0/6'
        page.locator('#import').set_input_files(str(output))
        page.wait_for_function("document.getElementById('progress').textContent==='已记录 1/6'")
        bad=Path(td)/'wrong_version.json';data['source_digest']='wrong';bad.write_text(json.dumps(data))
        page.locator('#import').set_input_files(str(bad))
        page.wait_for_function("document.getElementById('status').textContent.includes('文件不是本版')")
        assert page.locator('#progress').inner_text()=='已记录 1/6'
    assert not errors,errors
    page.evaluate('localStorage.clear()');context.close();b.close()
payload=json.loads((OUT/'clarification_examples.json').read_text())
sources=json.loads(Path('/home/tokkio/paper1_pairwise_teacher_rater_a_sheet_v2_zh_v1_rated.json').read_text())
source_by_pid={r['presentation_id']:r for r in sources['items']}
for e in payload['examples']:
    original=source_by_pid[e['presentation_id']]
    for k in ['task_input','response_A','response_B']:assert original[k]==e['english_source'][k]
    assert not set(e)&{'A_arm','B_arm','human_verdict','ai_verdict','head','target_id'}
report={'six_cases':True,'no_default_answers':True,'english_candidate_and_input_identity':True,
        'no_arms_or_AI_verdicts_in_examples':True,'mobile_no_horizontal_overflow':True,
        'local_save_reload':True,'partial_export_restore':True,'wrong_version_rejected':True,
        'download_JSON_valid':True,'new_outcome_labels_written':False,'fixture_responses_retained':False,
        'browser_errors':errors,'source_hashes':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path('/home/tokkio/paper1_pairwise_teacher_rater_a_sheet_v2_zh_v1_rated.json'),Path('/home/tokkio/AI_B_中文评审结果.html')]}}
(OUT/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(report,ensure_ascii=False))
