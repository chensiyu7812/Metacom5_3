#!/usr/bin/env python3
"""CPU Chrome verification on explicitly synthetic B fixtures; no human selections."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess

from metacom_pm.rl1v3.compile import dp_selection as V1, dp_selection_v2 as D
from metacom_pm.rl1v3.journal.dp_selector import selection_html


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--b-root',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    path=a.b_root/'project/scripts/rl1v3/V321A_dpv2_harness.py'
    spec=importlib.util.spec_from_file_location('fixed_b_harness',path);h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
    bundle,*_=h.fixtures(D,V1)
    page=a.out/'SYNTHETIC_ONLY.html';page.write_text(selection_html(bundle))
    src=(a.b_root/'project/scripts/rl1v3/V321A_r15_smoke.mjs').read_text()
    client=src[src.index('// ---------------------------------------------------------------- minimal CDP client'):src.index('async function main()')]
    client=client.replace('!!document.querySelector(".top, #fatal, .main")','true')
    js='''import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
const cfg=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const res={checks:[],errors:[]};const LAUNCHED=[];
const sleep=(ms)=>new Promise(r=>setTimeout(r,ms));
const check=(name,ok,detail)=>res.checks.push({name,ok:!!ok,detail});
'''+client+'''
async function main(){
 const b=await Browser.launch(cfg.out+'/profile');await b.downloadsTo(cfg.out+'/downloads');
 const p=await b.open('file://'+cfg.html);await p.waitFor("document.getElementById('prefix').options.length>0");
 await p.select('#decision','selected');
 check('selection starts empty',(await p.eval("document.getElementById('source').value"))==='');
 check('placeholder exists',await p.eval("document.getElementById('source').options[0].value===''") );
 await p.type('#selector','CUR1');await p.type('#need','SIMULATED need');await p.type('#rationale','SIMULATED reason');
 await p.select('#coverage','full');await p.select('#staleness','false');await p.select('#stage','false');
 await p.click('#rankBlind');await p.click('#blind');await p.click('#download');
 check('empty source blocks download',(await p.text('#status')).includes('请明确选择'));
 check('blocked form created no files',fs.readdirSync(cfg.out+'/downloads').length===0);
 await p.select('#source',await p.eval("document.getElementById('source').options[1].value"));await p.click('#download');
 let files=[];for(let i=0;i<50&&!files.length;i++){files=fs.readdirSync(cfg.out+'/downloads').filter(x=>x.endsWith('.json'));await sleep(50);}
 check('explicit source creates one draft',files.length===1);
 if(files.length){const r=JSON.parse(fs.readFileSync(cfg.out+'/downloads/'+files[0]));check('draft binds explicit source',r.selected_record_id==='rec-ownA-0');}
 await p.select('#prefix','1');await p.select('#decision','selected');
 check('new prefix resets source',(await p.eval("document.getElementById('source').value"))==='');
 await p.select('#decision','none_suitable');check('none remains valid',(await p.eval("document.getElementById('coverage').value"))==='none');
 await b.close();
}
main().catch(e=>res.errors.push(String(e.stack||e))).finally(()=>{for(const p of LAUNCHED){try{p.kill('SIGKILL')}catch{}}
fs.writeFileSync(cfg.out+'/RESULT.json',JSON.stringify(res,null,2));process.exit(res.errors.length||res.checks.some(x=>!x.ok)?1:0);});
'''
    (a.out/'check.mjs').write_text(js)
    # Chromium creates Unix sockets under TMPDIR; keep that path short on the data volume.
    short_tmp=Path('/opt/tokkio-data0/tokkio_runs/pmrl1-j-chrome-tmp');short_tmp.mkdir(exist_ok=True)
    config=dict(chrome='/usr/bin/google-chrome',html=str(page),out=str(a.out),tmpdir=str(short_tmp))
    (a.out/'config.json').write_text(json.dumps(config))
    subprocess.run(['node',str(a.out/'check.mjs'),str(a.out/'config.json')],check=True,timeout=60)
    print((a.out/'RESULT.json').read_text())

if __name__=='__main__':main()
