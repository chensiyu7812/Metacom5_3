/* PP1 blind-review tool: offline UI.  All rules live in PP1Core.apply(); this file only renders the package that
 * the coordinator issued and appends events that the core accepts.  Nothing here knows about conditions. */
(function () {
  'use strict';
  var C = window.PP1Core;
  var STORE = 'pp1tool:v1:';
  var ROLE = { curator: '筛查整理者', reviewer: '评审者', adjudicator: '裁决者', auditor: '审计侧（F-A）' };
  var STATUS = { 'new': '未做', draft: '草稿', locked: '已提交' };
  var S = null;
  var app = document.getElementById('app');
  var modal = document.getElementById('modal');

  // ---------------------------------------------------------------- DOM helper
  function h(tag, attrs, kids) {
    var e = document.createElement(tag);
    if (attrs) Object.keys(attrs).forEach(function (k) {
      var v = attrs[k];
      if (v === null || v === undefined || v === false) return;
      if (k === 'text') e.textContent = v;
      else if (k === 'class') e.className = v;
      else if (k.slice(0, 2) === 'on') e.addEventListener(k.slice(2), v);
      else if (k === 'checked' || k === 'disabled' || k === 'open') e[k] = !!v;
      else if (k === 'value') e.value = v;
      else e.setAttribute(k, v === true ? '' : v);
    });
    (kids || []).forEach(function (c) {
      if (c === null || c === undefined || c === false) return;
      e.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
    });
    return e;
  }
  function clone(x) { return x === undefined ? undefined : JSON.parse(JSON.stringify(x)); }
  function short(x) { return x ? x.slice(0, 8) : '—'; }
  function fmtTime(t) { return t ? t.replace('T', ' ').replace(/\.\d+Z$/, 'Z') : ''; }

  // ---------------------------------------------------------------- storage
  function storeKey(base) { return STORE + base.package_sha256; }
  function readStore(base) {
    try { var raw = localStorage.getItem(storeKey(base)); return raw ? JSON.parse(raw) : null; } catch (e) { return null; }
  }
  function persist() {
    var extra = S.pkgs.filter(function (p) { return !(S.embedded && p.package_sha256 === S.base.package_sha256); });
    try {
      localStorage.setItem(storeKey(S.base), JSON.stringify({ v: 1, events: S.events, extra: extra }));
      S.savedAt = new Date().toISOString();
      S.storageError = null;
    } catch (e) {
      S.storageError = '本机保存失败（' + e.name + '）。请立即点“导出进度”保存文件。';
    }
  }

  // ---------------------------------------------------------------- events
  function append(kind, item, data) {
    var ev = C.makeEvent(S.state, kind, item, data);
    C.apply(S.state, ev, S.pkgs);           // throws when the rule book refuses the event
    S.events.push(ev);
    persist();
    return ev;
  }
  function tryAppend(kind, item, data) {
    try { append(kind, item, data); return true; } catch (e) { flash(e.message, true); return false; }
  }
  function flash(msg, bad) { S.msg = { text: msg, bad: !!bad }; }

  // ---------------------------------------------------------------- start / resume
  function start(pkg, embedded) {
    var bad = C.verifyPackage(pkg);
    if (bad) return fatal('任务包校验失败：' + bad);
    if (pkg.requires) return fatal('这是后续部分的任务包。请先打开第一部分（或导入进度文件），再点“载入后续任务包”。');
    S = { base: pkg, pkgs: [pkg], embedded: embedded, events: [], state: null, current: null, work: {}, activeF: null,
          showZh: false, msg: null, savedAt: null, storageError: null, searched: {}, histOpened: {} };
    var stored = readStore(pkg);
    if (stored && stored.events && stored.events.length) {
      var pk = [pkg].concat((stored.extra || []).filter(function (p) {
        return p.package_sha256 !== pkg.package_sha256 && !C.verifyPackage(p);
      }));
      var r = C.replay(pk, stored.events);
      if (!r.ok) {
        return fatal('本机保存的记录未通过校验（' + r.error + '）。没有覆盖它；请联系协调人，并导入最近一次导出的进度文件。',
                     stored);
      }
      S.pkgs = pk; S.events = stored.events; S.state = r.state;
      append('session_start', null, { resumed: true, tool: C.CORE_VERSION });
      flash('已从本机恢复进度（' + S.events.length + ' 条记录）。');
    } else {
      S.state = C.newState([pkg]);
      append('session_start', null, { resumed: false, tool: C.CORE_VERSION });
    }
    render();
  }

  function startFromExport(exp) {
    var r = C.verifyExport(exp);
    if (!r.ok) return fatal('进度文件校验失败：' + r.error);
    var base = exp.packages.filter(function (p) { return !p.requires; })[0];
    S = { base: base, pkgs: exp.packages.slice(), embedded: false, events: exp.events.slice(), state: r.state, current: null,
          work: {}, activeF: null, showZh: false, msg: null, savedAt: null, storageError: null, searched: {}, histOpened: {} };
    var stored = readStore(base);
    if (stored && stored.events && stored.events.length && !C.extendsLog(stored.events, exp.events) &&
        !stored.events.every(function (e) { return e.kind === 'session_start'; })) {
      return fatal('本机已有这个任务包的另一份记录，与导入文件不一致。已拒绝导入；请联系协调人。');
    }
    append('import', null, { from_head: exp.head, n_events: exp.events.length });
    flash('已导入进度文件（' + exp.events.length + ' 条记录，校验通过）。');
    render();
  }

  function fatal(msg, raw) {
    app.innerHTML = '';
    var kids = [h('h1', { text: 'PP1 盲评工具' }), h('p', { class: 'err', id: 'fatal', text: msg })];
    if (raw) kids.push(h('button', { onclick: function () { download('PP1_local_raw.json', JSON.stringify(raw)); },
                                     text: '下载本机原始记录（交给协调人）' }));
    kids.push(h('p', {}, [loaderButtons()]));
    app.appendChild(h('div', { class: 'main' }, kids));
  }

  function loaderButtons() {
    return h('span', {}, [
      h('button', { 'data-act': 'open-package', onclick: function () { pick('file-package'); }, text: '打开任务包文件' }), ' ',
      h('button', { 'data-act': 'import', onclick: function () { pick('file-import'); }, text: '导入进度文件' })]);
  }

  function pick(id) { var i = document.getElementById(id); i.value = ''; i.click(); }

  function readFile(input, cb) {
    var f = input.files && input.files[0];
    if (!f) return;
    var rd = new FileReader();
    rd.onload = function () {
      var obj;
      try { obj = JSON.parse(rd.result); } catch (e) { alertBox('文件不是有效的 JSON：' + e.message); return; }
      cb(obj);
    };
    rd.readAsText(f, 'utf-8');
  }

  document.getElementById('file-package').addEventListener('change', function (e) {
    readFile(e.target, function (pkg) { start(pkg, false); });
  });
  document.getElementById('file-import').addEventListener('change', function (e) {
    readFile(e.target, function (exp) {
      if (!S) return startFromExport(exp);
      importInto(exp);
    });
  });
  document.getElementById('file-part').addEventListener('change', function (e) {
    readFile(e.target, loadPart);
  });

  function importInto(exp) {
    if (exp.base_package_sha256 !== S.base.package_sha256) return alertBox('这个进度文件属于另一个任务包，已拒绝。');
    var r = C.verifyExport(exp, { base_package_sha256: S.base.package_sha256 });
    if (!r.ok) return alertBox('进度文件校验失败，已拒绝：' + r.error);
    var fresh = S.events.every(function (e) { return e.kind === 'session_start'; });
    if (fresh || C.extendsLog(S.events, exp.events)) {
      leaveCurrent();
      S.pkgs = exp.packages.slice(); S.events = exp.events.slice(); S.state = r.state; S.current = null; S.work = {};
      append('import', null, { from_head: exp.head, n_events: exp.events.length });
      flash('已导入进度文件（校验通过）。');
    } else if (C.extendsLog(exp.events, S.events)) {
      flash('本机进度比导入文件更新，保留本机进度。');
    } else {
      return alertBox('导入文件与本机记录分叉（同一位置的记录不同），已拒绝。请联系协调人。');
    }
    render();
  }

  function loadPart(pkg) {
    var bad = C.verifyPackage(pkg);
    if (bad) return alertBox('任务包校验失败：' + bad);
    if (!pkg.requires || pkg.requires.package_sha256 !== S.base.package_sha256) {
      return alertBox('这个任务包不是当前任务的后续部分。');
    }
    if (S.pkgs.some(function (p) { return p.package_sha256 === pkg.package_sha256; }) &&
        S.state.pkgs.some(function (p) { return p.package_sha256 === pkg.package_sha256; })) {
      return alertBox('后续部分已经载入。');
    }
    var had = S.pkgs.slice();
    S.pkgs = S.pkgs.filter(function (p) { return p.package_sha256 !== pkg.package_sha256; }).concat([pkg]);
    try { append('package_load', null, { package_sha256: pkg.package_sha256 }); } catch (e) {
      S.pkgs = had;
      return alertBox('不能载入：' + e.message);
    }
    flash('已载入后续部分：' + pkg.title);
    render();
  }

  // ---------------------------------------------------------------- export
  function download(name, text) {
    var blob = new Blob([text], { type: 'application/json' });
    var a = h('a', { href: URL.createObjectURL(blob), download: name });
    document.body.appendChild(a); a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
  }
  function doExport(kind) {
    leaveCurrent(true);
    if (!tryAppend('export', null, { kind: kind })) return render();
    var exp = C.buildExport(S.state, S.events, kind);
    var name = 'PP1_' + S.base.role + '_' + S.base.assignee + '_' + kind + '_' + exp.head.slice(0, 8) + '.json';
    download(name, JSON.stringify(exp));
    if (S.current) tryAppend('view', S.current);
    showModal('已导出', [h('p', { text: '文件：' + name }),
      h('p', { text: '请把文件交给协调人。协调人会核对下面的校验码：' }), h('p', { class: 'mono', id: 'export-head', text: exp.head })],
      [{ text: '知道了', act: 'close' }]);
    render();
  }

  // ---------------------------------------------------------------- modal
  function showModal(title, body, buttons) {
    modal.innerHTML = '';
    var btns = buttons.map(function (b) {
      return h('button', { class: b.cls || '', 'data-act': b.act, onclick: function () { modal.hidden = true; if (b.fn) b.fn(); },
                           text: b.text });
    });
    modal.appendChild(h('div', { class: 'card' }, [h('h3', { text: title })].concat(body).concat([h('div', { class: 'actions' }, btns)])));
    modal.hidden = false;
  }
  function alertBox(msg) { showModal('提示', [h('p', { class: 'err', id: 'alert-text', text: msg })], [{ text: '关闭', act: 'close' }]); }

  // ---------------------------------------------------------------- navigation / timing
  function leaveCurrent(keep) {
    if (!S.current) return;
    flushText();
    tryAppend('leave', S.current);
    if (!keep) S.current = null;
  }
  function go(key) {
    if (S.current === key) return;
    leaveCurrent();
    if (!tryAppend('view', key)) return render();
    S.current = key;
    var st = S.state.items[key];
    S.work[key] = clone(st && st.answer) || {};
    S.activeF = null;
    window.scrollTo(0, 0);
    render();
  }
  document.addEventListener('visibilitychange', function () {
    if (!S || !S.current) return;
    if (document.hidden) { flushText(); tryAppend('leave', S.current); }
    else tryAppend('view', S.current);
  });
  window.addEventListener('beforeunload', function () {
    if (S && S.current) { flushText(); tryAppend('leave', S.current); }
  });

  // ---------------------------------------------------------------- answers
  function cleanAnswer(form, w) {
    var out = {};
    form.fields.forEach(function (f) {
      var v = w[f.id];
      if (v === undefined || v === null) return;
      if (typeof v === 'string' && v.trim() === '') return;
      if (Array.isArray(v) && !v.length) return;
      if (!C.fieldVisible(f, w)) return;
      if (f.type === 'fitem') {
        var o = { presence: v.presence };
        if (!v.presence) return;
        if (v.presence === 'yes') {
          if (v.severity) o.severity = v.severity;
          if (v.quote && v.quote.trim()) o.quote = v.quote;
          if (v.sources && v.sources.length) o.sources = v.sources.slice();
          if (v.no_source) o.no_source = true;
        }
        out[f.id] = o;
        return;
      }
      out[f.id] = clone(v);
    });
    return out;
  }
  function currentItem() { return S.current ? S.state.view.items[S.current] : null; }
  function currentForm() { var it = currentItem(); return it ? S.state.view.forms[it.form] : null; }
  function locked(key) { var s = S.state.items[key]; return !!(s && s.status === 'locked'); }

  function saveDraft(silent) {
    var it = currentItem();
    if (!it || locked(S.current)) return;
    var ans = cleanAnswer(currentForm(), S.work[S.current]);
    var prev = S.state.items[S.current] && S.state.items[S.current].answer;
    if (prev && C.canon(prev) === C.canon(ans)) return;
    if (!prev && !Object.keys(ans).length) return;
    if (tryAppend('draft', S.current, { answer: ans }) && !silent) flash('草稿已保存。');
  }
  var textDirty = false;
  function flushText() { if (textDirty) { textDirty = false; saveDraft(true); } }

  var ERR = { 'required': '未填写', 'quote is not a verbatim part of the reply': '引用的不是回复中的原句（请逐字复制）',
              'severity required': '请选择严重程度', 'quote required': '请填写回复中的原句',
              'evidence source required': '请在历史中点“引用为依据”标出依据（F5 可选“查无来源”）',
              'at least one required span required': 'S1 需要在历史中至少标注一条“必要”片段' };
  function zhErr(form, msg) {
    var i = msg.indexOf(': ');
    var fid = i > 0 ? msg.slice(0, i) : '';
    var why = i > 0 ? msg.slice(i + 2) : msg;
    var f = form.fields.filter(function (x) { return x.id === fid; })[0];
    if (/^shorter than/.test(why)) why = '内容太短';
    return (f ? '「' + f.label + '」' : '') + (ERR[why] || why);
  }

  function submit() {
    var it = currentItem(), form = currentForm();
    flushText();
    var ans = cleanAnswer(form, S.work[S.current]);
    var errs = C.validateAnswer(S.state.view, it, ans, true);
    if (errs.length) {
      S.msg = { text: '还不能提交：', list: errs.map(function (e) { return zhErr(form, e); }), bad: true };
      return render();
    }
    showModal('提交并锁定', [h('p', { text: '提交后这一项将锁定，之后不能修改。确认提交？' })], [
      { text: '确认提交', act: 'confirm', cls: 'primary', fn: function () {
        var key = S.current;
        tryAppend('leave', key);
        if (tryAppend('submit', key, { answer: ans })) flash('已提交并锁定。');
        else tryAppend('view', key);
        render();
      } },
      { text: '取消', act: 'cancel' }]);
  }

  function lockStage(stage) {
    showModal('锁定阶段', [h('p', { text: '锁定后，本阶段的所有项目都不能再查看或修改。确认锁定“' + stage.title + '”？' })], [
      { text: '确认锁定', act: 'confirm', cls: 'danger', fn: function () {
        if (S.current && S.state.view.items[S.current].stage === stage.id) leaveCurrent();
        if (tryAppend('stage_lock', stage.id)) {
          render();
          showModal('阶段已锁定', [h('p', { text: '请立即导出阶段文件，交给协调人。' })], [
            { text: '导出阶段文件', act: 'export-stage', cls: 'primary', fn: function () { doExport('stage-' + stage.id); } },
            { text: '稍后', act: 'close' }]);
        } else render();
      } },
      { text: '取消', act: 'cancel' }]);
  }

  // ---------------------------------------------------------------- render: chrome
  function render() {
    app.innerHTML = '';
    var base = S.base;
    if (base.simulated) app.appendChild(h('div', { class: 'sim', text: '模拟数据：仅用于验收测试，不是真实评审任务' }));
    var tr = S.state.pkgs.some(function (p) { return p.translation && p.translation.provided; });
    app.appendChild(h('div', { class: 'top' }, [
      h('h1', { text: base.title || 'PP1 盲评' }),
      h('span', { class: 'meta', text: ROLE[base.role] + ' ' + base.assignee + ' · 任务包 ' + short(base.package_sha256) }),
      h('span', { class: 'spacer' }),
      tr ? h('label', { class: 'meta' }, [h('input', { type: 'checkbox', 'data-act': 'toggle-zh', checked: S.showZh,
        onchange: function (e) { S.showZh = e.target.checked; render(); } }), ' 显示中文参考译文（以原文为准）']) : null,
      base.role === 'reviewer' && S.state.pkgs.length < 2 ?
        h('button', { 'data-act': 'load-part', onclick: function () { pick('file-part'); }, text: '载入后续任务包' }) : null,
      h('button', { 'data-act': 'export', onclick: function () { doExport('progress'); }, text: '导出进度' }),
      h('button', { 'data-act': 'import', onclick: function () { pick('file-import'); }, text: '导入进度' })]));
    if (S.storageError) app.appendChild(h('div', { class: 'banner', text: S.storageError }));
    var wrap = h('div', { class: 'wrap' }, [renderSide(), h('div', { class: 'main', id: 'main' }, [renderMain()])]);
    app.appendChild(wrap);
    app.appendChild(h('div', { class: 'foot', id: 'foot', text: '记录 ' + S.events.length + ' 条 · 当前校验码 ' + short(S.state.head) +
      (S.savedAt ? ' · 本机已保存 ' + fmtTime(S.savedAt) : '') }));
  }

  function renderSide() {
    var side = h('div', { class: 'side' });
    S.state.view.stages.forEach(function (st) {
      var open = C.stageOpen(S.state, st.id);
      var lk = S.state.stages[st.id] && S.state.stages[st.id].locked;
      var done = st.items.filter(function (x) { return locked(x.key); }).length;
      side.appendChild(h('h2', { text: st.title }));
      side.appendChild(h('div', { class: 'st', 'data-stage-status': st.id,
        text: lk ? '已锁定 · ' + fmtTime(S.state.stages[st.id].locked_at) + ' · 不可再查看' :
              (open ? '进行中 · 已提交 ' + done + '/' + st.items.length : '未开放（需先锁定上一阶段）') }));
      if (open && !lk) {
        var ul = h('ul');
        st.items.forEach(function (x) {
          var s = S.state.items[x.key];
          var stt = s ? s.status : 'new';
          ul.appendChild(h('li', {}, [h('button', { 'data-nav': x.key, class: S.current === x.key ? 'cur' : '',
            onclick: function () { go(x.key); } }, [itemLabel(x), h('span', { class: 'badge ' + stt, text: STATUS[stt] })])]));
        });
        side.appendChild(ul);
        if (done === st.items.length) {
          side.appendChild(h('button', { class: 'danger', 'data-act': 'lock-stage', 'data-stage': st.id,
            onclick: function () { lockStage(st); }, text: '锁定本阶段' }));
        }
      }
    });
    if (S.base.role === 'reviewer' && S.state.pkgs.length < 2) {
      side.appendChild(h('h2', { text: '第二部分' }));
      side.appendChild(h('div', { class: 'st', text: 'QH、探针、F：锁定 Q0 并把阶段文件交给协调人后领取，再点“载入后续任务包”。' }));
    }
    return side;
  }

  function itemLabel(x) {
    var v = S.state.view;
    var c = x.case_id && v.cases[x.case_id];
    var lab = c ? c.label : '';
    if (x.reply_id) lab = (lab ? lab + ' · ' : '') + '回复 ' + (Object.keys(v.replies).sort().indexOf(x.reply_id) + 1);
    if (x.dispute_id) lab += ' · ' + v.disputes[x.dispute_id].fitem;
    if (x.key.indexOf('FA:') === 0) lab += ' · ' + v.audit[x.key].fitem;
    return lab || x.key;
  }

  // ---------------------------------------------------------------- render: main
  function renderMain() {
    var box = h('div');
    if (S.msg) {
      var m = h('div', { class: 'box ' + (S.msg.bad ? 'err' : 'okmsg'), id: 'msg', text: S.msg.text });
      if (S.msg.list) m.appendChild(h('ul', {}, S.msg.list.map(function (t) { return h('li', { text: t }); })));
      box.appendChild(m);
      S.msg = null;
    }
    if (!S.current) {
      box.appendChild(h('div', { class: 'box instr' }, [h('h2', { text: S.base.title })].concat(
        (S.base.notes_zh || []).map(function (t) { return h('p', { text: t }); })).concat(
        S.state.pkgs.slice(1).map(function (p) { return h('p', { text: p.title + '：' + (p.notes_zh || []).join(' ') }); })).concat(
        [h('p', { class: 'meta', text: '请从左侧选择项目。' })])));
      return box;
    }
    var it = currentItem();
    var form = S.state.view.forms[it.form];
    var ro = locked(S.current);
    var st = S.state.view.stages.filter(function (s) { return s.id === it.stage; })[0];
    box.appendChild(h('div', { class: 'box instr' }, [h('h2', { text: form.title + ' · ' + itemLabel(it.ref) }),
      h('p', { text: form.instruction }), st.note ? h('p', { class: 'meta', text: st.note }) : null]));
    var v = S.state.view;
    var c = it.ref.case_id ? v.cases[it.ref.case_id] : null;
    if (it.form === 'FA') box.appendChild(renderAudit(v.audit[S.current]));
    if (it.form === 'ADJ') box.appendChild(renderDispute(v.disputes[it.ref.dispute_id]));
    var ctx = h('div', { class: 'cols' });
    var left = h('div');
    if (c) left.appendChild(renderPrefix(c));
    var showHist = c && c.history && ['S', 'QH', 'F', 'ADJ', 'FA'].indexOf(it.form) !== -1;
    var right = h('div');
    if (it.ref.pair_id) right.appendChild(renderPair(v.pairs[it.ref.pair_id], it.form === 'Q0' ? 'Q0' : 'QH'));
    else if (it.ref.reply_id) right.appendChild(renderReply(v.replies[it.ref.reply_id], '待检查的回复'));
    if (showHist) (right.childNodes.length ? left : right).appendChild(renderHistory(c, it, ro));
    ctx.appendChild(left); ctx.appendChild(right);
    box.appendChild(ctx);
    // forms without a reply (screening) sit under the current session, next to the long history column
    if (!it.ref.pair_id && !it.ref.reply_id) left.appendChild(renderForm(it, form, ro));
    else box.appendChild(renderForm(it, form, ro));
    return box;
  }

  function unit(u, extra) {
    var kids = [h('span', { class: 'who', text: u.speaker }), u.text];
    if (S.showZh && u.zh) kids.push(h('span', { class: 'zh', text: '译：' + u.zh }));
    var d = h('div', { class: 'turn' + (u.speaker === '求助者' ? ' seeker' : '') + (extra && extra.marked ? ' marked' : ''),
                       'data-ref': u.ref }, extra && extra.tools ? [extra.tools].concat(kids) : kids);
    return d;
  }

  function renderPrefix(c) {
    return h('div', { class: 'box' }, [h('h3', { text: '当前会话（到此刻为止）' })].concat(c.prefix.map(function (u) { return unit(u); })));
  }

  function renderReply(r, title) {
    var kids = [h('h3', { text: title }), h('div', { class: 'reply', 'data-reply': title, text: r.text })];
    if (S.showZh && r.zh) kids.push(h('div', { class: 'turn' }, [h('span', { class: 'zh', text: '译：' + r.zh })]));
    return h('div', { class: 'box reply-box' }, kids);
  }

  function renderPair(p, ch) {
    var m = p[ch];
    var v = S.state.view;
    return h('div', {}, [renderReply(v.replies[m.A], '回复甲'), renderReply(v.replies[m.B], '回复乙')]);
  }

  function renderDispute(d) {
    var rows = d.labels.map(function (l) {
      return h('li', { text: l.rater + '：' + ({ yes: '有', no: '无', cannot: '无法判断' }[l.presence] || '未答') +
        (l.severity ? '（' + (l.severity === 'serious' ? '严重' : '轻微') + '）' : '') + (l.quote ? '；引用：' + l.quote : '') +
        (l.sources ? '；依据：' + l.sources.join('、') : '') + (l.no_source ? '；查无来源' : '') });
    });
    return h('div', { class: 'box' }, [h('h3', { text: '分歧项：' + d.fitem + ' ' + d.fitem_label }), h('ul', {}, rows)]);
  }

  function renderAudit(a) {
    return h('div', { class: 'box' }, [h('h3', { text: '审计信息（非盲）' }),
      h('p', { text: '条件：' + a.condition + '；检查项：' + a.fitem }),
      h('p', { text: '该回复实际收到的材料：' }), h('div', { class: 'reply', text: a.resource_text }),
      h('p', { text: '评审标签：' + a.labels.map(function (l) {
        return l.rater + ' ' + (l.severity === 'serious' ? '严重' : '轻微') + (l.quote ? ' 「' + l.quote + '」' : '');
      }).join('；') })]);
  }

  function renderHistory(c, it, ro) {
    var key = S.current;
    var hist = c.history;
    var q = (S.searched[key] || '').toLowerCase();
    var spans = {};
    var w = S.work[key] || {};
    (w.spans || []).forEach(function (s) { spans[s.ref] = s.role; });
    var box = h('div', { class: 'box', id: 'history' }, [h('h3', { text: '过往对话（只到此刻之前；按时间排列）' })]);
    var tbl = h('table', { class: 'hist-index' }, [h('tr', {}, [h('th', { text: '次序' }), h('th', { text: '日期' }),
      h('th', { text: '轮数' }), h('th', { text: '词数' })])]);
    hist.index.forEach(function (x) {
      tbl.appendChild(h('tr', {}, [h('td', { text: '第 ' + x.order + ' 次' }), h('td', { text: x.date || '未知' }),
        h('td', { text: String(x.turns) }), h('td', { text: String(x.words) })]));
    });
    box.appendChild(tbl);
    box.appendChild(h('div', {}, [h('input', { type: 'search', placeholder: '在过往对话中搜索', 'data-act': 'hist-search',
      value: S.searched[key] || '', onchange: function (e) {
        S.searched[key] = e.target.value;
        if (e.target.value) tryAppend('ui', key, { name: 'history_search' });
        render();
      } }), ' ', h('button', { 'data-act': 'expand-all', onclick: function () { S.expandAll = !S.expandAll; markOpen(); render(); },
      text: S.expandAll ? '全部收起' : '全部展开' })]));
    hist.sessions.forEach(function (s) {
      var turns = s.turns.filter(function (t) { return !q || t.text.toLowerCase().indexOf(q) !== -1 ||
        (t.zh && t.zh.toLowerCase().indexOf(q) !== -1); });
      if (q && !turns.length) return;
      var det = h('details', { class: 'sess', open: S.expandAll || !!q, 'data-session': s.ref,
        ontoggle: function (e) { if (e.target.open) markOpen(); } },
        [h('summary', { text: '第 ' + s.order + ' 次对话 · ' + (s.date || '日期未知') + ' · ' + s.turns.length + ' 轮' +
          (q ? ' · 匹配 ' + turns.length + ' 轮' : '') })]);
      turns.forEach(function (t) {
        var tools = null;
        if (!ro && it.form === 'S') {
          var sel = h('select', { 'data-span': t.ref, onchange: function (e) { setSpan(t.ref, e.target.value); } },
            [['', '标注…'], ['required', '必要'], ['optional', '相关但可选'], ['contradict', '不得矛盾']].map(function (o) {
              return h('option', { value: o[0], text: o[1] });
            }));
          sel.value = spans[t.ref] || '';
          tools = h('span', { class: 'tools' }, [sel]);
        } else if (!ro && (it.form === 'F')) {
          tools = h('span', { class: 'tools' }, [h('button', { 'data-cite': t.ref, onclick: function () { cite(t.ref); },
            text: '引用为依据' })]);
        }
        det.appendChild(unit(t, { tools: tools, marked: !!spans[t.ref] }));
      });
      box.appendChild(det);
    });
    return box;
  }

  function markOpen() {
    if (!S.histOpened[S.current]) { S.histOpened[S.current] = true; tryAppend('ui', S.current, { name: 'history_open' }); }
  }

  function setSpan(ref, role) {
    var w = S.work[S.current];
    var list = (w.spans || []).filter(function (s) { return s.ref !== ref; });
    if (role) list.push({ ref: ref, role: role });
    w.spans = list;
    saveDraft(true);
    render();
  }

  function cite(ref) {
    var w = S.work[S.current];
    if (!S.activeF) { alertBox('请先在下方某个选了“有”的检查项里点“设为当前引用项”。'); return; }
    var v = w[S.activeF] || {};
    v.sources = (v.sources || []).filter(function (r) { return r !== ref; }).concat([ref]);
    v.no_source = undefined;
    w[S.activeF] = v;
    saveDraft(true);
    render();
  }

  // ---------------------------------------------------------------- render: form
  function renderForm(it, form, ro) {
    var key = S.current;
    var w = S.work[key];
    var box = h('div', { class: 'box', id: 'form' }, [h('h3', { text: ro ? '你的答案（已提交，锁定）' : '作答' })]);
    if (ro) box.appendChild(h('p', { class: 'readonly', text: '提交时间：' + fmtTime(S.state.items[key].submitted_at) }));
    form.fields.forEach(function (f) {
      if (!C.fieldVisible(f, w)) return;
      box.appendChild(renderField(f, w, ro));
    });
    if (!ro) {
      box.appendChild(h('div', { class: 'actions' }, [
        h('button', { 'data-act': 'save', onclick: function () { flushText(); saveDraft(false); render(); }, text: '保存草稿' }),
        h('button', { class: 'primary', 'data-act': 'submit', onclick: submit, text: '提交并锁定' })]));
    }
    var st = S.state.view.stages.filter(function (s) { return s.id === it.stage; })[0];
    var keys = st.items.map(function (x) { return x.key; });
    var i = keys.indexOf(key);
    box.appendChild(h('div', { class: 'actions' }, [
      h('button', { 'data-act': 'prev', disabled: i <= 0, onclick: function () { go(keys[i - 1]); }, text: '上一项' }),
      h('button', { 'data-act': 'next', disabled: i >= keys.length - 1, onclick: function () { go(keys[i + 1]); }, text: '下一项' })]));
    return box;
  }

  function onChoice(fid, val) {
    var w = S.work[S.current];
    w[fid] = val;
    var form = currentForm();
    form.fields.forEach(function (f) { if (!C.fieldVisible(f, w)) delete w[f.id]; });
    saveDraft(true);
    render();
  }

  function renderField(f, w, ro) {
    var v = w[f.id];
    var lab = h('span', { class: 'lab', text: f.label + (f.required ? ' *' : '') });
    var wrap = h('div', { class: 'field', 'data-fieldwrap': f.id }, [lab]);
    if (f.hint) wrap.appendChild(h('div', { class: 'hint', text: f.hint }));
    if (f.type === 'choice') {
      wrap.appendChild(h('div', { class: 'opts' }, f.options.map(function (o) {
        return h('label', {}, [h('input', { type: 'radio', name: S.current + '::' + f.id, 'data-field': f.id, value: o.v,
          checked: v === o.v, disabled: ro, onchange: function () { onChoice(f.id, o.v); } }), ' ' + o.label]);
      })));
    } else if (f.type === 'multi') {
      var cur = v || [];
      wrap.appendChild(h('div', { class: 'opts' }, f.options.map(function (o) {
        return h('label', {}, [h('input', { type: 'checkbox', 'data-field': f.id, value: o.v, checked: cur.indexOf(o.v) !== -1,
          disabled: ro, onchange: function (e) {
            var list = (S.work[S.current][f.id] || []).filter(function (x) { return x !== o.v; });
            if (e.target.checked) {
              if (o.v === f.exclusive) list = [o.v];
              else list = list.filter(function (x) { return x !== f.exclusive; }).concat([o.v]);
            }
            S.work[S.current][f.id] = list;
            saveDraft(true);
            render();
          } }), ' ' + o.label]);
      })));
    } else if (f.type === 'text') {
      wrap.appendChild(h('textarea', { 'data-field': f.id, disabled: ro, maxlength: f.max_chars || null, value: v || '',
        oninput: function (e) { S.work[S.current][f.id] = e.target.value; textDirty = true; },
        onchange: function () { flushText(); } }));
    } else if (f.type === 'spans') {
      var roles = {};
      f.options.forEach(function (o) { roles[o.v] = o.label; });
      var list = (v || []).map(function (s) {
        return h('span', { class: 'chip', 'data-spanchip': s.ref, text: s.ref + ' · ' + roles[s.role] });
      });
      wrap.appendChild(h('div', {}, list.length ? list : [h('span', { class: 'hint', text: '尚未标注（在左侧历史中逐句选择“标注…”）' })]));
    } else if (f.type === 'fitem') {
      wrap = renderFItem(f, v || {}, ro);
    }
    return wrap;
  }

  function renderFItem(f, v, ro) {
    var fid = f.id;
    var setV = function (patch) {
      var w = S.work[S.current];
      var cur = w[fid] || {};
      Object.keys(patch).forEach(function (k) { cur[k] = patch[k]; });
      if (cur.presence !== 'yes') { cur = { presence: cur.presence }; if (S.activeF === fid) S.activeF = null; }
      w[fid] = cur;
    };
    var box = h('div', { class: 'fitem' + (S.activeF === fid ? ' active' : ''), 'data-fitem': fid }, [
      h('span', { class: 'lab', text: f.label + ' *' })]);
    box.appendChild(h('div', { class: 'opts' }, [['yes', '有'], ['no', '无'], ['cannot', '无法判断']].map(function (o) {
      return h('label', {}, [h('input', { type: 'radio', name: S.current + '::' + fid, 'data-fitem': fid, 'data-sub': 'presence',
        value: o[0], checked: v.presence === o[0], disabled: ro, onchange: function () { setV({ presence: o[0] }); saveDraft(true); render(); } }),
        ' ' + o[1]]);
    })));
    if (v.presence === 'yes') {
      box.appendChild(h('div', { class: 'opts' }, [h('span', { class: 'hint', text: '严重程度：' })].concat(
        [['serious', '严重'], ['minor', '轻微']].map(function (o) {
          return h('label', {}, [h('input', { type: 'radio', name: S.current + '::' + fid + '::sev', 'data-fitem': fid,
            'data-sub': 'severity', value: o[0], checked: v.severity === o[0], disabled: ro,
            onchange: function () { setV({ severity: o[0] }); saveDraft(true); render(); } }), ' ' + o[1]]);
        }))));
      box.appendChild(h('div', { class: 'hint', text: '逐字复制回复中的原句：' }));
      box.appendChild(h('textarea', { 'data-fitem': fid, 'data-sub': 'quote', disabled: ro, value: v.quote || '',
        oninput: function (e) { setV({ quote: e.target.value }); textDirty = true; }, onchange: function () { flushText(); } }));
      if (f.needs_source || f.allow_no_source) {
        var src = (v.sources || []).map(function (r) { return h('span', { class: 'chip', 'data-srcchip': r, text: r }); });
        box.appendChild(h('div', {}, [h('span', { class: 'hint', text: '历史中的依据：' })].concat(src.length ? src : [h('span', { class: 'hint', text: '（无）' })])));
        if (!ro) {
          box.appendChild(h('button', { 'data-act': 'activate', 'data-fitem': fid,
            onclick: function () { S.activeF = fid; render(); }, text: S.activeF === fid ? '当前引用项（在历史中点“引用为依据”）' : '设为当前引用项' }));
          if (v.sources && v.sources.length) {
            box.appendChild(h('button', { 'data-act': 'clear-src', onclick: function () { setV({ sources: [] }); saveDraft(true); render(); },
              text: '清除依据' }));
          }
        }
        if (f.allow_no_source) {
          box.appendChild(h('label', {}, [h('input', { type: 'checkbox', 'data-fitem': fid, 'data-sub': 'no_source',
            checked: !!v.no_source, disabled: ro, onchange: function (e) {
              setV({ no_source: e.target.checked ? true : undefined, sources: e.target.checked ? [] : v.sources });
              saveDraft(true); render(); } }), ' 查无来源：历史中找不到对应内容']));
        }
      }
    }
    return box;
  }

  // ---------------------------------------------------------------- boot
  var emb = document.getElementById('pp1-package');
  if (emb) {
    var pkg;
    try { pkg = JSON.parse(emb.textContent); } catch (e) { fatal('内置任务包无法解析：' + e.message); return; }
    start(pkg, true);
  } else {
    app.innerHTML = '';
    app.appendChild(h('div', { class: 'main' }, [h('h1', { text: 'PP1 盲评工具（离线）' }),
      h('p', { text: '请打开协调人发给你的任务包文件，或导入之前导出的进度文件。本工具不联网，所有记录只保存在本机浏览器中，请定期导出。' }),
      loaderButtons()]));
  }
  window.PP1UI = { state: function () { return S; } };   // read-only handle for diagnostics and tests
}());
