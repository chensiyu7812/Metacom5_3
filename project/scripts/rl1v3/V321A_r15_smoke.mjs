// R15 smoke check of one final page in a real headless Chrome: Chinese first, English expandable, progress export,
// import into a fresh browser profile restores the same log head.  Usage: node V321A_r15_smoke.mjs <cfg.json>
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

const cfg = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const results = { checks: [], errors: [] };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const LAUNCHED = [];
function check(name, ok, detail) { results.checks.push({ name, ok: !!ok, detail: detail === undefined ? null : detail }); }

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


async function main() {
  const out = cfg.out;
  const html = 'file://' + cfg.html;
  let b = await Browser.launch(path.join(out, 'prof1'));
  await b.downloadsTo(path.join(out, 'dl_raw'));
  let page = await b.open(html);
  const fatal = await page.exists('#fatal');
  check('page opens without error', !fatal);
  const first = await page.eval(`(document.querySelector('[data-nav]')||{}).getAttribute ? document.querySelector('[data-nav]').getAttribute('data-nav') : null`);
  check('task list present', !!first, first);
  await page.click(`[data-nav="${first}"]`);
  await page.waitFor(`document.querySelector('#form')`);
  const zhp = await page.count('.zhp');
  const en = await page.count('details.en');
  const closed = await page.eval(`[...document.querySelectorAll('details.en')].every(d => !d.open)`);
  check('Chinese shown first; every Chinese line has its English original (collapsed)', zhp > 0 && en === zhp && closed, { zhp, en });
  if (await page.exists('[data-act="toggle-en"]')) {
    await page.click('[data-act="toggle-en"]');
    check('English originals can all be expanded', await page.eval(`[...document.querySelectorAll('details.en')].every(d => d.open)`));
    await page.click('[data-act="toggle-en"]');
  } else check('English originals can all be expanded', false, 'no toggle');
  const before = fs.readdirSync(b.dlDir);
  await page.click('[data-act="export"]');
  let f = null;
  for (let i = 0; i < 200 && !f; i++) {
    const now = fs.readdirSync(b.dlDir).filter((x) => x.endsWith('.json') && !before.includes(x));
    if (now.length) f = path.join(b.dlDir, now[0]);
    await sleep(50);
  }
  check('progress export downloads', !!f);
  const head = f ? JSON.parse(fs.readFileSync(f, 'utf8')).head : null;
  await b.close();
  fs.mkdirSync(path.join(out, 'dl'), { recursive: true });
  if (f) fs.copyFileSync(f, path.join(out, 'dl', 'progress.json'));
  b = await Browser.launch(path.join(out, 'prof2'));
  page = await b.open(html);
  if (f) {
    await page.setFile('#file-import', path.join(out, 'dl', 'progress.json'));
    const cond = `window.PP1UI.state().events.some(e => e.kind === 'import' && e.data && e.data.from_head === ${JSON.stringify(head)})`;
    await page.waitFor(cond, 8000).catch(() => null);
    const ok = await page.eval(cond);
    const has = await page.eval(`window.PP1UI.state().events.some(e => e.h === ${JSON.stringify(head)})`);
    check('import on a fresh machine restores the exported log (same head)', ok && has, { head });
  }
  await b.close();
}

main().catch((e) => { results.errors.push(String(e && e.stack || e)); })
  .finally(() => { LAUNCHED.forEach((p) => { try { p.kill('SIGKILL'); } catch (e) { /* gone */ } });
    fs.writeFileSync(path.join(cfg.out, 'result.json'), JSON.stringify(results, null, 1)); process.exit(0); });
