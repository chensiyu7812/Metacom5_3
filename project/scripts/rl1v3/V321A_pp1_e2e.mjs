// End-to-end acceptance of the PP1 review tool in a real headless Chrome (CDP over Node's built-in WebSocket).
// Usage: node V321A_pp1_e2e.mjs <phase> <config.json>      phases: curator | q0 | rest | audit
// Every action goes through the page's DOM (clicks, typing, file inputs, downloads); the core is only called
// directly to prove that forbidden edits are refused.  Results (assertions, page texts, downloads) -> config.out.
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

const [phase, cfgPath] = process.argv.slice(2);
const cfg = JSON.parse(fs.readFileSync(cfgPath, 'utf8'));
const results = { phase, checks: [], pages: [], downloads: {}, errors: [] };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const LAUNCHED = [];                       // every Chrome we start is killed on exit, also after an error

function check(name, ok, detail) {
  results.checks.push({ name, ok: !!ok, detail: detail === undefined ? null : detail });
  if (!ok) console.error('CHECK FAILED:', name, detail === undefined ? '' : JSON.stringify(detail));
}

// ---------------------------------------------------------------- minimal CDP client
class Browser {
  static async launch(profile) {
    fs.mkdirSync(profile, { recursive: true });
    const port = path.join(profile, 'DevToolsActivePort');
    if (fs.existsSync(port)) fs.unlinkSync(port);
    const proc = spawn(cfg.chrome, ['--headless=new', '--remote-debugging-port=0', `--user-data-dir=${profile}`,
      '--no-first-run', '--no-default-browser-check', '--disable-gpu', '--no-sandbox', '--disable-extensions',
      '--disable-breakpad', '--disable-crash-reporter', `--crash-dumps-dir=${profile}`, 'about:blank'],
      { stdio: ['ignore', 'ignore', 'ignore'], env: { ...process.env, TMPDIR: cfg.tmpdir || process.env.TMPDIR } });
    LAUNCHED.push(proc);
    for (let i = 0; i < 200 && !fs.existsSync(port); i++) await sleep(50);
    const [p, wsPath] = fs.readFileSync(port, 'utf8').trim().split('\n');
    const b = new Browser();
    b.proc = proc;
    b.ws = new WebSocket(`ws://127.0.0.1:${p}${wsPath}`);
    b.id = 0; b.pending = new Map(); b.listeners = [];
    await new Promise((res, rej) => { b.ws.onopen = res; b.ws.onerror = rej; });
    b.ws.onmessage = (m) => {
      const msg = JSON.parse(m.data);
      if (msg.id && b.pending.has(msg.id)) {
        const { res, rej } = b.pending.get(msg.id);
        b.pending.delete(msg.id);
        msg.error ? rej(new Error(msg.error.message)) : res(msg.result);
      } else b.listeners.forEach((f) => f(msg));
    };
    return b;
  }
  send(method, params = {}, sessionId) {
    const id = ++this.id;
    this.ws.send(JSON.stringify({ id, method, params, sessionId }));
    return new Promise((res, rej) => this.pending.set(id, { res, rej }));
  }
  async downloadsTo(dir) {
    fs.mkdirSync(dir, { recursive: true });
    await this.send('Browser.setDownloadBehavior', { behavior: 'allow', downloadPath: dir, eventsEnabled: true });
    this.dlDir = dir;
  }
  async open(url) {
    const { targetId } = await this.send('Target.createTarget', { url: 'about:blank' });
    const { sessionId } = await this.send('Target.attachToTarget', { targetId, flatten: true });
    const page = new Page(this, targetId, sessionId);
    await page.send('Runtime.enable');
    await page.send('Page.enable');
    await page.send('Page.navigate', { url });
    await page.waitFor('document.readyState === "complete" && !!document.querySelector(".top, #fatal, .main")');
    return page;
  }
  async close() { try { await this.send('Browser.close'); } catch (e) { /* ignore */ } this.proc.kill(); await sleep(300); }
}

class Page {
  constructor(b, targetId, sessionId) { this.b = b; this.targetId = targetId; this.sessionId = sessionId; }
  send(m, p) { return this.b.send(m, p, this.sessionId); }
  async eval(expr) {
    const r = await this.send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true });
    if (r.exceptionDetails) throw new Error((r.exceptionDetails.exception && r.exceptionDetails.exception.description) || r.exceptionDetails.text);
    return r.result.value;
  }
  async waitFor(expr, ms = 8000) {
    const t0 = Date.now();
    while (Date.now() - t0 < ms) {
      try { if (await this.eval(`!!(${expr})`)) return true; } catch (e) { /* page loading */ }
      await sleep(50);
    }
    throw new Error('timeout waiting for ' + expr);
  }
  q(sel) { return JSON.stringify(sel); }
  async click(sel) { await this.eval(`(()=>{const e=document.querySelector(${this.q(sel)}); if(!e) throw new Error('missing '+${this.q(sel)}); e.click(); return 1})()`); }
  async exists(sel) { return this.eval(`!!document.querySelector(${this.q(sel)})`); }
  async count(sel) { return this.eval(`document.querySelectorAll(${this.q(sel)}).length`); }
  async text(sel = 'body') { return this.eval(`(document.querySelector(${this.q(sel)})||{}).innerText||''`); }
  async type(sel, value) {
    await this.eval(`(()=>{const e=document.querySelector(${this.q(sel)}); if(!e) throw new Error('missing '+${this.q(sel)});
      e.value=${JSON.stringify(value)}; e.dispatchEvent(new Event('input',{bubbles:true})); e.dispatchEvent(new Event('change',{bubbles:true})); return 1})()`);
  }
  async select(sel, value) {
    await this.eval(`(()=>{const e=document.querySelector(${this.q(sel)}); e.value=${JSON.stringify(value)}; e.dispatchEvent(new Event('change',{bubbles:true})); return 1})()`);
  }
  async setFile(sel, file) {
    const r = await this.send('Runtime.evaluate', { expression: `document.querySelector(${this.q(sel)})` });
    await this.send('DOM.setFileInputFiles', { files: [file], objectId: r.result.objectId });
  }
  async close() { await this.b.send('Target.closeTarget', { targetId: this.targetId }); await sleep(200); }
  async snapshot(label) { results.pages.push({ label, text: await this.text('body') }); }
  async modalButton(act) { await this.waitFor(`!document.getElementById('modal').hidden && document.querySelector('#modal [data-act="${act}"]')`); await this.click(`#modal [data-act="${act}"]`); }
  async events() { return this.eval('window.PP1UI.state().events.length'); }
}

async function waitDownload(b, before, label) {
  for (let i = 0; i < 200; i++) {
    const now = fs.readdirSync(b.dlDir).filter((f) => f.endsWith('.json') && !before.includes(f));
    if (now.length) { await sleep(150); results.downloads[label] = path.join(b.dlDir, now[0]); return results.downloads[label]; }
    await sleep(50);
  }
  throw new Error('no download for ' + label);
}

async function exportFile(b, page, label, viaStageModal) {
  const before = fs.readdirSync(b.dlDir);
  if (viaStageModal) await page.modalButton('export-stage');
  else await page.click('[data-act="export"]');
  const f = await waitDownload(b, before, label);
  await page.modalButton('close');
  return f;
}

// ---------------------------------------------------------------- form helpers
async function choose(page, field, value) { await page.click(`input[data-field="${field}"][value="${value}"]`); }
async function submitItem(page) {
  await page.click('[data-act="submit"]');
  await page.modalButton('confirm');
  await page.waitFor(`document.querySelector('#msg') && document.querySelector('#msg').innerText.includes('已提交')`);
}
async function navKeys(page, prefix) {
  return page.eval(`[...document.querySelectorAll('[data-nav^="${prefix}"]')].map(e=>e.getAttribute('data-nav'))`);
}
async function lockStage(page, stage, keepModal = false) {
  await page.click(`[data-act="lock-stage"][data-stage="${stage}"]`);
  await page.modalButton('confirm');
  await page.waitFor(`document.querySelector('[data-stage-status="${stage}"]').innerText.includes('已锁定')`);
  if (!keepModal) await page.modalButton('close');
}

// curator answers: case index -> pattern
async function fillCurator(page, key, i, submit = true) {
  await page.click(`[data-nav="${key}"]`);
  await page.waitFor(`document.querySelector('#form')`);
  const isS7 = await page.exists('input[data-field="s7_confirm"]');
  if (isS7) {
    await choose(page, 's7_confirm', 'none');
  } else {
    const need = ['S1', 'S2', 'S0', 'unclear'][i % 4];
    await choose(page, 'need', need);
    if (need === 'S1') {
      await page.type('textarea[data-field="reason"]', 'Simulated reason: without the earlier talk the reply would repeat a failed idea.');
      await page.select('select[data-span]', 'required');
    }
    const rv = i % 3 === 0 ? 'refused' : 'none';
    if (!(await page.eval(`document.querySelector('input[data-field="risk"][value="${rv}"]').checked`))) {
      await page.click(`input[data-field="risk"][value="${rv}"]`);
    }
  }
  if (submit) await submitItem(page);
}

async function fillPairForm(page, key, rater, i, extraSub) {
  await page.click(`[data-nav="${key}"]`);
  await page.waitFor(`document.querySelector('#form')`);
  const ov = rater === 'R1' ? ['A', 'B', 'same', 'A', 'unsure', 'B', 'A', 'same'][i] : ['A', 'A', 'same', 'B', 'B', 'B', 'unsure', 'same'][i];
  await choose(page, 'overall', ov);
  if (ov === 'A' || ov === 'B') await choose(page, 'strength', String(1 + (i % 3)));
  for (const f of ['sub_natural', 'sub_empathy', 'sub_need', 'sub_advice', 'sub_autonomy'].concat(extraSub ? ['sub_history'] : [])) {
    await choose(page, f, ['A', 'B', 'same', 'unsure'][(i + f.length) % 4]);
  }
  await choose(page, 'suff_A', 'partial');
  await choose(page, 'suff_B', i % 2 ? 'full' : 'partial');
  await submitItem(page);
}

async function fillF(page, key, rater, i, opts = {}) {
  await page.click(`[data-nav="${key}"]`);
  await page.waitFor(`document.querySelector('[data-fitem="F1"]')`);
  const reply = await page.text('[data-reply="待检查的回复"]');
  for (const f of ['F1', 'F2', 'F3', 'F4', 'F5', 'F6', 'F7', 'F8']) {
    let pres = 'no';
    if (f === 'F5' && i === 0) pres = rater === 'R1' ? 'yes' : 'no';           // planted serious disagreement
    if (f === 'F6' && i === 1) pres = 'yes';                                      // both: minor, with a source
    await page.click(`input[data-fitem="${f}"][data-sub="presence"][value="${pres}"]`);
    if (pres === 'yes') {
      await page.click(`input[data-fitem="${f}"][data-sub="severity"][value="${f === 'F5' ? 'serious' : 'minor'}"]`);
      if (opts.badQuote && f === 'F5') {
        await page.type(`textarea[data-fitem="${f}"][data-sub="quote"]`, 'this sentence is not in the reply at all');
      } else {
        await page.type(`textarea[data-fitem="${f}"][data-sub="quote"]`, reply.slice(0, 28));
      }
      if (f === 'F5') await page.click(`input[data-fitem="F5"][data-sub="no_source"]`);
      else {
        await page.click(`[data-act="activate"][data-fitem="${f}"]`);
        await page.click('[data-cite]');
      }
    }
  }
  if (opts.badQuote) {
    await page.click('[data-act="submit"]');
    await page.waitFor(`document.querySelector('#msg')`);
    const msg = await page.text('#msg');
    check('F: a quote that is not verbatim in the reply is refused at submit', msg.includes('原句'), msg.slice(0, 160));
    await page.type(`textarea[data-fitem="F5"][data-sub="quote"]`, reply.slice(0, 28));
  }
  await submitItem(page);
}

async function refusedByCore(page, kind, item, answer) {
  return page.eval(`(()=>{const S=window.PP1UI.state(); const C=window.PP1Core;
    const st=JSON.parse(JSON.stringify(S.state, (k,v)=>k==='pkgs'||k==='view'?undefined:v));
    st.pkgs=S.state.pkgs; st.view=S.state.view;
    try { C.apply(st, C.makeEvent(st, ${JSON.stringify(kind)}, ${JSON.stringify(item)}, ${JSON.stringify(answer === undefined ? null : { answer })}), S.pkgs); return 'ACCEPTED'; }
    catch(e) { return e.message; } })()`);
}

// ---------------------------------------------------------------- phases
async function phaseCurator() {
  const P = cfg.curator;
  let b = await Browser.launch(P.profile1);
  await b.downloadsTo(P.downloads);
  let page = await b.open('file://' + P.html);
  await page.snapshot('curator:start');
  const keys = await navKeys(page, 'S:');
  check('curator: all screening items listed', keys.length === P.n_items, keys.length);
  // validation: S1 without reason/spans cannot be submitted
  await page.click(`[data-nav="${keys[0]}"]`);
  await page.waitFor(`document.querySelector('#form')`);
  if (await page.exists('input[data-field="need"]')) {
    await choose(page, 'need', 'S1');
    await page.click('input[data-field="risk"][value="none"]');
    await page.click('[data-act="submit"]');
    await page.waitFor(`document.querySelector('#msg')`);
    const msg = await page.text('#msg');
    check('curator: S1 without reason and required span is refused', msg.includes('未填写') && msg.includes('必要'), msg.slice(0, 200));
  }
  for (let i = 0; i < 4; i++) await fillCurator(page, keys[i], i);
  await fillCurator(page, keys[4], 4, false);      // draft only
  const evBefore = await page.events();
  await page.close();                                 // "quit" mid-way
  page = await b.open('file://' + P.html);
  const evAfter = await page.events();
  check('curator: reopening restores the local log', evAfter >= evBefore + 1, { evBefore, evAfter });
  const sub = await page.count('[data-nav^="S:"] .badge.locked');
  check('curator: 4 submitted items survive the restart', sub === 4, sub);
  await page.click(`[data-nav="${keys[4]}"]`);
  await page.waitFor(`document.querySelector('#form')`);
  const draftKept = await page.eval(`[...document.querySelectorAll('input[type=radio]:checked')].length > 0`);
  check('curator: the unsent draft is restored after restart', draftKept);
  const prog = await exportFile(b, page, 'curator_progress');
  await page.snapshot('curator:after-restart');
  await b.close();

  // a different machine: empty profile, import the progress file
  b = await Browser.launch(P.profile2);
  await b.downloadsTo(P.downloads);
  page = await b.open('file://' + P.html);
  const fresh = await page.count('[data-nav^="S:"] .badge.locked');
  check('curator: a fresh machine starts empty', fresh === 0, fresh);
  await page.setFile('#file-import', prog);
  await page.waitFor(`document.querySelector('#msg') && document.querySelector('#msg').innerText.includes('导入')`);
  const imp = await page.count('[data-nav^="S:"] .badge.locked');
  check('curator: import restores the 4 submitted items on the new machine', imp === 4, imp);
  // a locked item cannot be edited: UI disables inputs, core refuses the event
  await page.click(`[data-nav="${keys[0]}"]`);
  await page.waitFor(`document.querySelector('#form')`);
  const enabled = await page.count('#form input:not([disabled]), #form textarea:not([disabled])');
  check('curator: a submitted item is read-only in the UI', enabled === 0, enabled);
  const refused = await refusedByCore(page, 'draft', keys[0], { need: 'S0', risk: ['none'] });
  check('curator: core refuses an edit of a locked item', /already locked/.test(refused), refused);
  for (let i = 4; i < keys.length; i++) await fillCurator(page, keys[i], i);
  await lockStage(page, 'S', true);
  const stageFile = await exportFile(b, page, 'curator_stage', true);
  const nav = await page.count('[data-nav^="S:"]');
  check('curator: a locked stage can no longer be opened', nav === 0, nav);
  const refusedView = await refusedByCore(page, 'view', keys[1]);
  check('curator: core refuses viewing an item of a locked stage', /locked stage/.test(refusedView), refusedView);
  await page.snapshot('curator:locked');
  const fin = await exportFile(b, page, 'curator_final');
  await b.close();

  // the generic tool (no embedded package) can open a package file
  b = await Browser.launch(P.profile3);
  await b.downloadsTo(P.downloads);
  page = await b.open('file://' + cfg.generic_html);
  await page.setFile('#file-package', P.package_file);
  await page.waitFor(`document.querySelector('[data-nav^="S:"]')`);
  check('generic tool: opens a package file', (await page.count('[data-nav^="S:"]')) === P.n_items);
  await b.close();
  results.files = { progress: prog, stage: stageFile, final: fin };
}

async function phaseQ0() {
  for (const R of cfg.reviewers) {
    const b = await Browser.launch(R.profile1);
    await b.downloadsTo(R.downloads);
    const page = await b.open('file://' + R.html);
    const keys = await navKeys(page, 'Q0:');
    check(`${R.id}: 8 Q0 pairs`, keys.length === 8, keys.length);
    const histShown = await page.exists('#history');
    for (let i = 0; i < keys.length; i++) {
      await fillPairForm(page, keys[i], R.id, i, false);
      if (i === 0) await page.snapshot(`${R.id}:Q0-page`);
      if (await page.exists('#history')) check(`${R.id}: Q0 page shows no history`, false, keys[i]);
    }
    check(`${R.id}: Q0 shows no history`, !histShown && !(await page.exists('#history')));
    const qhBefore = await page.exists('[data-nav^="QH:"]');
    check(`${R.id}: QH not available before part 2`, !qhBefore);
    await lockStage(page, 'Q0', true);
    const f = await exportFile(b, page, `${R.id}_q0_stage`, true);
    await page.snapshot(`${R.id}:Q0-locked`);
    await b.close();
    results.files = results.files || {};
    results.files[R.id] = f;
  }
}

async function phaseRest() {
  for (const R of cfg.reviewers) {
    let b = await Browser.launch(R.profile1);
    await b.downloadsTo(R.downloads);
    let page = await b.open('file://' + R.html);
    // a part 2 whose anchor does not match this log is refused
    await page.setFile('#file-part', R.bad_part2);
    await page.waitFor(`!document.getElementById('modal').hidden`);
    const msg = await page.text('#alert-text');
    check(`${R.id}: part 2 with a wrong anchor is refused`, msg.includes('anchor'), msg.slice(0, 160));
    await page.modalButton('close');
    await page.setFile('#file-part', R.part2);
    await page.waitFor(`document.querySelector('[data-nav^="QH:"]')`);
    check(`${R.id}: Q0 items are no longer listed`, (await page.count('[data-nav^="Q0:"]')) === 0);
    const qh = await navKeys(page, 'QH:');
    for (let i = 0; i < qh.length; i++) {
      await page.click(`[data-nav="${qh[i]}"]`);
      await page.waitFor(`document.querySelector('#form')`);
      const preChecked = await page.count('#form input[type=radio]:checked');
      check(`${R.id}: QH page starts empty (no Q0 answer shown)`, preChecked === 0, preChecked);
      check(`${R.id}: QH page shows the history`, await page.exists('#history'));
      if (i === 0) {
        await page.click('[data-act="expand-all"]');
        await page.snapshot(`${R.id}:QH-page`);
      }
      await fillPairForm(page, qh[i], R.id, i, true);
    }
    const q0View = await refusedByCore(page, 'view', 'Q0:' + qh[0].slice(3));
    check(`${R.id}: core refuses re-opening a Q0 item during QH`, /locked stage/.test(q0View), q0View);
    await lockStage(page, 'QH');
    const pr = await navKeys(page, 'PROBE:');
    for (let i = 0; i < pr.length; i++) {
      await page.click(`[data-nav="${pr[i]}"]`);
      await page.waitFor(`document.querySelector('#form')`);
      await choose(page, 'guess', ['A', 'B', 'both', 'neither', 'unsure'][i % 5]);
      await submitItem(page);
    }
    await lockStage(page, 'PROBE');
    const fk = await navKeys(page, 'F:');
    check(`${R.id}: 16 F items`, fk.length === 16, fk.length);
    const half = R.id === 'R1' ? 5 : 7;
    for (let i = 0; i < half; i++) await fillF(page, fk[i], R.id, i, { badQuote: R.id === 'R1' && i === 0 });
    await page.snapshot(`${R.id}:F-page`);
    if (R.id === 'R1') {
      await page.close();                                  // crash mid-F, same machine
      page = await b.open('file://' + R.html);
      check(`${R.id}: restart keeps part 2 and F progress`,
        (await page.count('[data-nav^="F:"] .badge.locked')) === half);
    } else {
      const prog = await exportFile(b, page, `${R.id}_progress_midF`);
      await b.close();
      b = await Browser.launch(R.profile2);               // new machine
      await b.downloadsTo(R.downloads);
      page = await b.open('file://' + R.html);
      await page.setFile('#file-import', prog);
      await page.waitFor(`document.querySelector('[data-nav^="F:"]')`);
      check(`${R.id}: import on a new machine restores part 2 and F progress`,
        (await page.count('[data-nav^="F:"] .badge.locked')) === half);
    }
    for (let i = half; i < fk.length; i++) await fillF(page, fk[i], R.id, i);
    await lockStage(page, 'F', true);
    const fin = await exportFile(b, page, `${R.id}_final`, true);
    results.files = results.files || {};
    results.files[R.id] = fin;
    await b.close();
  }
}

async function phaseAudit() {
  results.files = {};
  for (const A of cfg.audit) {
    const b = await Browser.launch(A.profile);
    await b.downloadsTo(A.downloads);
    const page = await b.open('file://' + A.html);
    const stage = A.stage;
    const keys = await navKeys(page, stage + ':');
    check(`${A.id}: items listed`, keys.length === A.n_items, keys.length);
    for (const k of keys) {
      await page.click(`[data-nav="${k}"]`);
      await page.waitFor(`document.querySelector('#form')`);
      if (stage === 'ADJ') {
        await choose(page, 'decision', 'yes_minor');
        await page.type('textarea[data-field="reason"]', 'Simulated adjudication reason: the quoted line is not in the history.');
      } else {
        await choose(page, 'attribution', 'generator');
      }
      await submitItem(page);
    }
    await page.snapshot(`${A.id}:page`);
    await lockStage(page, stage, true);
    results.files[A.id] = await exportFile(b, page, `${A.id}_final`, true);
    await b.close();
  }
}

const PHASES = { curator: phaseCurator, q0: phaseQ0, rest: phaseRest, audit: phaseAudit };
try {
  await PHASES[phase]();
} catch (e) {
  results.errors.push(String(e && e.stack || e));
  console.error(e);
}
for (const p of LAUNCHED) { try { p.kill('SIGKILL'); } catch (e) { /* already gone */ } }
fs.writeFileSync(cfg.out, JSON.stringify(results, null, 1));
const failed = results.checks.filter((c) => !c.ok).length + results.errors.length;
console.log(`${phase}: ${results.checks.length} checks, ${failed} failed`);
process.exit(failed ? 1 : 0);
