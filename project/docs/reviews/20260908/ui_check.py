"""Read-only real-sheet QA; all example ratings use isolated synthetic UI fixtures."""
import copy
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path('/opt/tokkio-data0/tokkio_projects/Metacom5_3/project/outputs/paper1_pairwise_teacher/human_sheets_v2')
AUDIT = Path('/home/tokkio/audits/Metacom5_3_20260908')
FIX = Path('/tmp/paper1-human-v2-ui-fixture')
checks = []
errors = []
network = []

def check(name, condition):
    assert condition, name
    checks.append(name)

def attach(context):
    context.route('http://**/*', lambda route: (network.append(route.request.url), route.abort()))
    context.route('https://**/*', lambda route: (network.append(route.request.url), route.abort()))
    page = context.new_page()
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('dialog', lambda dialog: dialog.accept())
    return page

def strip_ratings(sheet):
    result = copy.deepcopy(sheet)
    for item in result['items']:
        item['verdict'] = item['rationale'] = None
    return result

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path='/usr/bin/google-chrome', headless=True,
                                args=['--no-sandbox', '--disable-dev-shm-usage'])
    for rater in ('a', 'b'):
        stem = ROOT / f'RATER_{rater.upper()}' / f'paper1_pairwise_teacher_rater_{rater}_sheet_v2'
        sheet = json.loads(stem.with_suffix('.json').read_text())
        context = browser.new_context(viewport={'width': 1440, 'height': 1000}, accept_downloads=True)
        page = attach(context)
        page.goto(stem.with_suffix('.html').as_uri())
        check(f'{rater}:96_items', page.locator('#question-select option').count() == 96)
        check(f'{rater}:no_prefilled_verdict', page.locator('input[name=verdict]:checked').count() == 0)
        check(f'{rater}:own_rater', page.locator('#rater-label').inner_text() == f'评审 {rater.upper()} 专用')
        for n, item in enumerate(sheet['items']):
            page.locator('#question-select').select_option(str(n))
            visible = page.evaluate('''() => Object.fromEntries(['task-input','response-a','response-b','reference-excerpt'].map(id => [id,document.getElementById(id).textContent]))''')
            assert visible['task-input'] == item['task_input']
            assert visible['response-a'] == item['response_A']
            assert visible['response-b'] == item['response_B']
            if item['task'] == 'DG':
                view = sheet['reference_catalog'][item['reference_id']]
                assert visible['reference-excerpt'] == view['excerpt']
                rendered = page.locator('#history-sessions pre').all_text_contents()
                expected = [f"Prior session [{s['timestamp']}]:\n" + '\n'.join(f"{t['role']}: {t['content']}" for t in s['turns']) for s in view['sessions']]
                assert rendered == expected
            else:
                assert visible['reference-excerpt'] == (item['reference_material'] or '')
        check(f'{rater}:all_96_visible_text_and_full_history_exact', True)
        check(f'{rater}:all_answers_remain_blank', page.locator('#progress').inner_text() == '已完成 0 / 96')
        dg = next(n for n, item in enumerate(sheet['items']) if item['task'] == 'DG')
        page.locator('#question-select').select_option(str(dg))
        page.locator('#history-summary').click()
        view = sheet['reference_catalog'][sheet['items'][dg]['reference_id']]
        query = view['sessions'][0]['timestamp']
        page.locator('#history-search').fill(query)
        check(f'{rater}:search_finds_date', page.locator('#history-sessions details').count() >= 1 and page.locator('#history-sessions mark').count() >= 1)
        page.locator('#history-clear').click()
        check(f'{rater}:search_clear_restores_all', page.locator('#history-sessions details').count() == len(view['sessions']))
        page.locator('#history-date').select_option('1')
        check(f'{rater}:date_jump_opens_session', page.locator('#session-1').get_attribute('open') is not None)
        page.locator('#history-panel').evaluate('(el) => el.open=false')
        page.locator('#instructions').evaluate('(el) => el.open=false')
        page.locator('#question-title').scroll_into_view_if_needed()
        page.screenshot(path=str(AUDIT / f'rater_{rater}_desktop.png'))
        page.set_viewport_size({'width':375,'height':900})
        page.locator('#history-summary').click()
        check(f'{rater}:mobile_no_horizontal_overflow', page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
        page.locator('#history-panel').evaluate('(el) => el.open=false')
        page.locator('#response-a').scroll_into_view_if_needed()
        page.screenshot(path=str(AUDIT / f'rater_{rater}_mobile.png'))
        context.close()

    fixture = json.loads((FIX / 'UI_TEST_ONLY_RATER_A.json').read_text())
    context = browser.new_context(accept_downloads=True)
    page = attach(context)
    page.goto((FIX / 'UI_TEST_ONLY_RATER_A.html').as_uri())
    check('fixture:XSS_not_executed', page.evaluate('window.INJECTED !== true'))
    check('fixture:literal_script_text_visible', page.locator('#response-a').text_content() == fixture['items'][0]['response_A'])
    page.locator('input[value=equivalent]').check()
    page.locator('#rationale').fill('UI TEST ONLY — 人工构造的保存恢复测试。')
    page.locator('#next').click()
    page.reload()
    check('fixture:reload_restores_one_completed', page.locator('#progress').inner_text() == '已完成 1 / 2')
    with page.expect_download() as info:
        page.locator('#export-progress').click()
    progress = FIX / info.value.suggested_filename
    info.value.save_as(progress)
    partial = json.loads(progress.read_text())
    check('fixture:partial_export_only_ratings_change', strip_ratings(partial) == fixture and partial['items'][1]['verdict'] is None)
    page.locator('input[value=uncertain]').check()
    page.locator('#rationale').fill('UI TEST ONLY — 第二题。')
    check('fixture:complete_button_enabled', page.locator('#export-complete').is_enabled())
    with page.expect_download() as info:
        page.locator('#export-complete').click()
    rated = FIX / info.value.suggested_filename
    info.value.save_as(rated)
    complete = json.loads(rated.read_text())
    check('fixture:complete_export_only_ratings_change', strip_ratings(complete) == fixture and all(i['verdict'] and i['rationale'] for i in complete['items']))
    context.close()

    context = browser.new_context(accept_downloads=True)
    page = attach(context)
    page.goto((FIX / 'UI_TEST_ONLY_RATER_A.html').as_uri())
    page.locator('#import-file').set_input_files(progress)
    page.wait_for_function("document.getElementById('progress').textContent === '已完成 1 / 2'")
    check('fixture:progress_import', True)
    page.locator('#import-file').set_input_files(rated)
    page.wait_for_function("document.getElementById('progress').textContent === '已完成 2 / 2'")
    check('fixture:complete_import', True)
    tampered = copy.deepcopy(complete)
    tampered['items'][0]['response_A'] += ' changed'
    bad = FIX / 'UI_TEST_ONLY_tampered.json'
    bad.write_text(json.dumps(tampered))
    duplicate = FIX / 'UI_TEST_ONLY_duplicate.json'
    duplicate.write_text(rated.read_text().replace('"verdict": "equivalent"', '"verdict": "uncertain", "verdict": "equivalent"', 1))
    for label, badfile, expected in (
        ('tampered',bad,'文件与本人的 V2 题目不一致'),
        ('other_rater',FIX/'UI_TEST_ONLY_RATER_B.json','文件与本人的 V2 题目不一致'),
        ('duplicate_key',duplicate,'JSON 含重复字段'),
    ):
        page.locator('#message').evaluate('(el) => el.textContent=""')
        page.locator('#import-file').set_input_files(badfile)
        page.wait_for_function('(s) => document.getElementById("message").textContent.includes(s)', arg=expected)
        check(f'fixture:{label}_rejected_preserves_answers', page.locator('#progress').inner_text() == '已完成 2 / 2' and page.locator('input[value=equivalent]').is_checked())
    context.close()

    context = browser.new_context(accept_downloads=True)
    context.add_init_script('Storage.prototype.setItem = function(){throw Error("TEST disabled storage")};')
    page = attach(context)
    page.goto((FIX / 'UI_TEST_ONLY_RATER_A.html').as_uri())
    check('fixture:storage_disabled_warning', '无法保存本机进度' in page.locator('#save-status').inner_text())
    page.locator('input[value=uncertain]').check()
    page.locator('#rationale').fill('UI TEST ONLY — storage unavailable.')
    with page.expect_download() as info:
        page.locator('#export-progress').click()
    check('fixture:export_works_without_storage', info.value.suggested_filename.endswith('_progress.json'))
    context.close()
    check('no_javascript_errors', not errors)
    check('no_external_network_requests', not network)
    result = {'status':'PASS','checks_passed':len(checks),'checks':checks,'browser':browser.version,
              'javascript_errors':errors,'external_network_requests':network,
              'real_sheet_presentations_checked':192,'real_human_verdicts_created':0,
              'fixture_location':str(FIX)}
    (AUDIT / 'browser_qa.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    browser.close()
