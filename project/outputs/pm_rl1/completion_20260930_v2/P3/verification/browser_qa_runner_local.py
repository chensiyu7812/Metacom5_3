import base64,json,pathlib,sys
sys.path.insert(0,'/tmp/pmrl1_p3_ui_vendor')
sys.path.insert(0,'/home/tokkio/Metacom5_3/project/src')
from playwright.sync_api import sync_playwright
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from metacom_pm.rl1.human_calibration import decrypt_item
from metacom_pm.rl1.schema import digest
P=pathlib.Path('/home/tokkio/Metacom5_3/project');R=P/'outputs/pm_rl1/completion_20260930_v2/P3/calibration';out=P/'outputs/pm_rl1/completion_20260930_v2/P3/verification';checks=[];errors=[];network=[]
def check(name,v):
 assert v,name
 checks.append(name)
with sync_playwright() as pw:
 browser=pw.chromium.launch(executable_path='/home/tokkio/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome',headless=True,args=['--no-sandbox'])
 for rater in ('rater_1','rater_2'):
  f=json.loads((R/(rater+'_form.json')).read_text());ctx=browser.new_context(viewport={'width':1300,'height':1000});ctx.route('http://**/*',lambda route:(network.append(route.request.url),route.abort()));ctx.route('https://**/*',lambda route:(network.append(route.request.url),route.abort()));page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.goto((R/'human_handoff_final'/(rater+'.html')).as_uri());check(rater+':blank',page.locator('#progress').text_content()=='0/40 已完成');check(rater+':options',page.locator('#nav option').count()==40)
  for n,item in enumerate(f['items']):
   page.select_option('#nav',str(n));source=f['sources'][item['source_key']]
   assert page.locator('#replyA').text_content()==item['A'] and page.locator('#replyB').text_content()==item['B']
   current=page.locator('#current .turn').evaluate_all('(els)=>els.map(el=>el.lastChild.textContent)');history=page.locator('#history .turn').evaluate_all('(els)=>els.map(el=>el.lastChild.textContent)')
   assert source['current_date'] in page.locator('#current').evaluate('(el)=>el.previousElementSibling.textContent')
   assert current==[t['text'] for t in source['current_prefix']]
   assert history==[t['text'] for s in source['legal_past_sessions'] for t in s['turns']]
  check(rater+':all_40_exact_sources_and_replies',True)
  page.fill('#search','the');check(rater+':search',page.locator('#matches').text_content().startswith('找到'));page.click('#clearSearch');check(rater+':clear_search',page.locator('#matches').text_content()=='');page.set_viewport_size({'width':390,'height':850});check(rater+':mobile',page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
  page.screenshot(path=str(out/(rater+'_mobile.png')));check(rater+':still_no_labels',page.locator('#progress').text_content()=='0/40 已完成');ctx.close()
 # Isolated fake material, fake labels and fresh key. Never fills a real item.
 temp=pathlib.Path('/tmp/pmrl1_p3_ui_fixture');temp.mkdir(exist_ok=True)
 key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
 f=dict(protocol='pm-rl1-p3-human-calibration-v1',packet_identity='f'*64,rater_slot='SYNTHETIC_UI_TEST',role_contract='UI TEST ONLY',public_key_spki=base64.b64encode(key.public_key().public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)).decode(),items=[dict(item_id=f'fixture{i}',source_key='s',A='Synthetic response. </script><script>window.XSS=true</script>',B='Synthetic second response.') for i in range(40)],sources={'s':dict(current_date='2000-01-01',legal_past_sessions=[],current_prefix=[dict(id='C:T000',role='seeker',text='UI TEST ONLY')])});f['form_identity']=digest(f)
 html=(P/'src/metacom_pm/rl1/calibration_form.html').read_text().replace('__FORM_DATA__',json.dumps(f).replace('<','\\u003c'));(temp/'fake.html').write_text(html)
 ctx=browser.new_context();page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.goto((temp/'fake.html').as_uri());check('synthetic_xss_not_executed',page.evaluate('window.XSS !== true'));page.select_option('#preference','tie');page.select_option('#risk_A','none_detected');page.select_option('#risk_B','none_detected');page.fill('#reason','SYNTHETIC UI TEST');page.fill('#reviewer','UI_TEST_NOT_A_HUMAN');page.reload();check('synthetic_local_save_reload',page.locator('#progress').text_content()=='1/40 已完成')
 page.click('#export');check('synthetic_incomplete_export_rejected','第 2 题' in page.locator('#exportStatus').text_content())
 page.evaluate('''()=>{for(const item of form.items){answers[item.item_id]={item_id:item.item_id,preference:'tie',risk_A:'none_detected',risk_B:'none_detected',quote_A:'',quote_B:'',source_ids:[],reason:'SYNTHETIC UI TEST ONLY',uncertainty:''}};current=0;render();persist()}''')
 exported=page.evaluate('makeSubmission()');check('synthetic_export_all_40_encrypted',len(exported['items'])==40 and 'SYNTHETIC UI TEST ONLY' not in json.dumps(exported))
 for envelope in exported['items']:
  label=decrypt_item(envelope,key,packet_identity=f['packet_identity'],form_identity=f['form_identity']);assert label['reason']=='SYNTHETIC UI TEST ONLY'
 check('webcrypto_to_python_roundtrip_40',True)
 with page.expect_download() as d:page.click('#export')
 check('synthetic_download_filename',d.value.suggested_filename.endswith('_sealed_answers.json'))
 ctx.close();check('no_browser_errors',not errors);check('no_network',not network)
 result=dict(status='PASS',checks=checks,browser=browser.version,real_form_items_read_only=80,real_labels_created=0,synthetic_items=40,errors=errors,network=network)
 (out/'browser_qa_final.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False));browser.close()
