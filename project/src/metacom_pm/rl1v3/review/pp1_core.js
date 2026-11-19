/* PP1 blind-review tool: core logic (no DOM).
 *
 * Runs in a browser (window.PP1Core) and in Node (module.exports), so the same code is exercised by the
 * offline HTML tool and by the CPU tests.  A Python verifier (review/pp1_tool.py) re-implements the
 * hashing and replay rules independently; tests cross-check both.
 *
 * Integrity model
 *   - Every package carries package_sha256 = sha256(canon(package without package_sha256)).
 *   - The work log is append-only: event.h = sha256(event.prev + canon(body)); the first prev is
 *     "genesis:" + base package sha.  A later package part (e.g. the QH/F part, which adds the history)
 *     can only be loaded when the log contains the anchoring stage_lock event named in part.requires.
 *   - replay() is the single rule book: stage order, lock immutability, answer validity.  The UI only
 *     appends events that replay() accepts.  An edited export fails replay or the chain check.
 *   - Without a secret key the log is tamper-evident, not tamper-proof: a full rewrite is caught by the
 *     coordinator's anchors (stage exports whose head hashes are recorded on receipt).
 */
(function (root, factory) {
  'use strict';
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.PP1Core = factory();
}(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  var SCHEMA_EXPORT = 'pmrl1v3-pp1-review-export-1';
  var CORE_VERSION = 'pp1-core-1';

  // ------------------------------------------------------------------ SHA-256 (FIPS 180-4) over UTF-8
  var K = [
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2];

  function rotr(x, n) { return (x >>> n) | (x << (32 - n)); }

  function utf8(s) {
    if (typeof TextEncoder !== 'undefined') return new TextEncoder().encode(s);
    return Uint8Array.from(Buffer.from(s, 'utf8'));  // eslint-disable-line no-undef
  }

  function sha256Bytes(msg) {
    var H = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19];
    var l = msg.length;
    var total = (((l + 9) + 63) >> 6) << 6;
    var buf = new Uint8Array(total);
    buf.set(msg);
    buf[l] = 0x80;
    var dv = new DataView(buf.buffer);
    var bits = l * 8;
    dv.setUint32(total - 8, Math.floor(bits / 0x100000000));
    dv.setUint32(total - 4, bits >>> 0);
    var W = new Array(64);
    for (var off = 0; off < total; off += 64) {
      var i;
      for (i = 0; i < 16; i++) W[i] = dv.getUint32(off + i * 4);
      for (i = 16; i < 64; i++) {
        var a15 = W[i - 15], a2 = W[i - 2];
        var s0 = rotr(a15, 7) ^ rotr(a15, 18) ^ (a15 >>> 3);
        var s1 = rotr(a2, 17) ^ rotr(a2, 19) ^ (a2 >>> 10);
        W[i] = (W[i - 16] + s0 + W[i - 7] + s1) >>> 0;
      }
      var a = H[0], b = H[1], c = H[2], d = H[3], e = H[4], f = H[5], g = H[6], h = H[7];
      for (i = 0; i < 64; i++) {
        var S1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
        var ch = (e & f) ^ (~e & g);
        var t1 = (h + S1 + ch + K[i] + W[i]) >>> 0;
        var S0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
        var maj = (a & b) ^ (a & c) ^ (b & c);
        var t2 = (S0 + maj) >>> 0;
        h = g; g = f; f = e; e = (d + t1) >>> 0; d = c; c = b; b = a; a = (t1 + t2) >>> 0;
      }
      H[0] = (H[0] + a) >>> 0; H[1] = (H[1] + b) >>> 0; H[2] = (H[2] + c) >>> 0; H[3] = (H[3] + d) >>> 0;
      H[4] = (H[4] + e) >>> 0; H[5] = (H[5] + f) >>> 0; H[6] = (H[6] + g) >>> 0; H[7] = (H[7] + h) >>> 0;
    }
    var out = '';
    for (var j = 0; j < 8; j++) out += ('00000000' + H[j].toString(16)).slice(-8);
    return out;
  }

  function sha256(str) { return sha256Bytes(utf8(str)); }

  // ------------------------------------------------------------------ canonical JSON
  // Sorted keys, compact separators, UTF-8 kept (no \u escapes beyond JSON.stringify's own), integers
  // only, printable-ASCII keys, no lone surrogates.  Python: json.dumps(sort_keys=True,
  // separators=(",", ":"), ensure_ascii=False) with the same restrictions gives identical text.
  var LONE = /[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(^|[^\uD800-\uDBFF])[\uDC00-\uDFFF]/;

  function canon(v) {
    if (v === null) return 'null';
    var t = typeof v;
    if (t === 'boolean') return v ? 'true' : 'false';
    if (t === 'number') {
      if (!Number.isSafeInteger(v)) throw new Error('canon: only safe integers allowed, got ' + v);
      return String(v);
    }
    if (t === 'string') {
      if (LONE.test(v)) throw new Error('canon: lone surrogate');
      return JSON.stringify(v);
    }
    if (Array.isArray(v)) return '[' + v.map(canon).join(',') + ']';
    if (t === 'object') {
      var keys = Object.keys(v).sort();
      return '{' + keys.map(function (k) {
        if (!/^[\x20-\x7e]+$/.test(k)) throw new Error('canon: non-ASCII key ' + k);
        return JSON.stringify(k) + ':' + canon(v[k]);
      }).join(',') + '}';
    }
    throw new Error('canon: unsupported value of type ' + t);
  }

  function packageSha(pkg) {
    var body = {};
    Object.keys(pkg).forEach(function (k) { if (k !== 'package_sha256') body[k] = pkg[k]; });
    return sha256(canon(body));
  }

  function verifyPackage(pkg) {
    if (!pkg || typeof pkg !== 'object') return 'not an object';
    if (pkg.schema !== 'pmrl1v3-pp1-review-package-1') return 'unknown schema ' + pkg.schema;
    var got = packageSha(pkg);
    if (got !== pkg.package_sha256) return 'package_sha256 mismatch (file ' + pkg.package_sha256 + ', computed ' + got + ')';
    return null;
  }

  // ------------------------------------------------------------------ text helpers
  function norm(s) { return String(s || '').replace(/\s+/g, ' ').trim(); }

  function isQuoteOf(quote, text) {
    var q = norm(quote);
    return q.length >= 2 && norm(text).indexOf(q) !== -1;
  }

  // ------------------------------------------------------------------ merged view of loaded packages
  function mergedView(pkgs) {
    var v = { cases: {}, replies: {}, pairs: {}, stages: [], forms: {}, items: {}, disputes: {}, audit: {} };
    pkgs.forEach(function (p) {
      Object.keys(p.forms || {}).forEach(function (k) { v.forms[k] = p.forms[k]; });
      Object.keys(p.cases || {}).forEach(function (k) {
        var c = v.cases[k] || {};
        var n = p.cases[k];
        Object.keys(n).forEach(function (f) { c[f] = n[f]; });
        v.cases[k] = c;
      });
      ['replies', 'pairs', 'disputes', 'audit'].forEach(function (sect) {
        Object.keys(p[sect] || {}).forEach(function (k) { v[sect][k] = p[sect][k]; });
      });
      (p.stages || []).forEach(function (st) {
        v.stages.push(st);
        st.items.forEach(function (it) { v.items[it.key] = { stage: st.id, form: it.form || st.form, ref: it }; });
      });
    });
    return v;
  }

  function historyRefs(view, caseId) {
    var c = view.cases[caseId];
    var refs = {};
    if (c && c.history) c.history.sessions.forEach(function (s) {
      refs[s.ref] = true;
      s.turns.forEach(function (t) { refs[t.ref] = true; });
    });
    return refs;
  }

  // Text an F/ADJ quote must come from.
  function itemReplyText(view, item) {
    var rid = item.ref.reply_id;
    return rid && view.replies[rid] ? view.replies[rid].text : null;
  }

  // ------------------------------------------------------------------ answer validation
  function fieldVisible(field, ans) {
    if (!field.show_if) return true;
    var v = ans[field.show_if.field];
    return field.show_if['in'].indexOf(v) !== -1;
  }

  function fieldRequired(field, ans) {
    if (field.required_if) {
      var v = ans[field.required_if.field];
      return field.required_if['in'].indexOf(v) !== -1;
    }
    return !!field.required;
  }

  function optionValues(field) { return (field.options || []).map(function (o) { return o.v; }); }

  // Returns a list of problems (empty = valid).  complete=false checks types only (drafts).
  function validateAnswer(view, item, ans, complete) {
    var form = view.forms[item.form];
    var errs = [];
    if (!form) return ['unknown form ' + item.form];
    if (!ans || typeof ans !== 'object' || Array.isArray(ans)) return ['answer must be an object'];
    var known = {};
    form.fields.forEach(function (f) { known[f.id] = true; });
    Object.keys(ans).forEach(function (k) { if (!known[k]) errs.push('unknown field ' + k); });
    var caseId = item.ref.case_id;
    var refs = historyRefs(view, caseId);
    var replyText = itemReplyText(view, item);
    form.fields.forEach(function (f) {
      var v = ans[f.id];
      var present = v !== undefined && v !== null && !(typeof v === 'string' && norm(v) === '') &&
        !(Array.isArray(v) && v.length === 0);
      if (!present) {
        if (complete && fieldVisible(f, ans) && fieldRequired(f, ans)) errs.push(f.id + ': required');
        if (complete && f.type === 'spans' && f.require_role_if &&
            f.require_role_if['in'].indexOf(ans[f.require_role_if.field]) !== -1) {
          errs.push(f.id + ': at least one ' + f.require_role_if.role + ' span required');
        }
        return;
      }
      if (!fieldVisible(f, ans)) { errs.push(f.id + ': answered but not applicable'); return; }
      if (f.type === 'choice') {
        if (optionValues(f).indexOf(v) === -1) errs.push(f.id + ': invalid option ' + v);
      } else if (f.type === 'multi') {
        if (!Array.isArray(v)) { errs.push(f.id + ': must be a list'); return; }
        var ok = optionValues(f);
        var seen = {};
        v.forEach(function (x) {
          if (ok.indexOf(x) === -1) errs.push(f.id + ': invalid option ' + x);
          if (seen[x]) errs.push(f.id + ': duplicate ' + x);
          seen[x] = true;
        });
        if (f.exclusive && v.indexOf(f.exclusive) !== -1 && v.length > 1) errs.push(f.id + ': ' + f.exclusive + ' is exclusive');
      } else if (f.type === 'text') {
        if (typeof v !== 'string') errs.push(f.id + ': must be text');
        else if (f.max_chars && v.length > f.max_chars) errs.push(f.id + ': longer than ' + f.max_chars);
        if (complete && f.min_chars && norm(v).length < f.min_chars) errs.push(f.id + ': shorter than ' + f.min_chars);
      } else if (f.type === 'spans') {
        if (!Array.isArray(v)) { errs.push(f.id + ': must be a list'); return; }
        var roles = optionValues(f);
        var seenRef = {};
        v.forEach(function (x) {
          if (!x || !refs[x.ref]) errs.push(f.id + ': unknown history ref ' + (x && x.ref));
          else if (roles.indexOf(x.role) === -1) errs.push(f.id + ': invalid role ' + x.role);
          else if (seenRef[x.ref]) errs.push(f.id + ': ref listed twice ' + x.ref);
          if (x) seenRef[x.ref] = true;
        });
        if (complete && f.require_role_if) {
          var need = ans[f.require_role_if.field];
          if (f.require_role_if['in'].indexOf(need) !== -1 &&
              !v.some(function (x) { return x && x.role === f.require_role_if.role; })) {
            errs.push(f.id + ': at least one ' + f.require_role_if.role + ' span required');
          }
        }
      } else if (f.type === 'fitem') {
        if (typeof v !== 'object' || Array.isArray(v)) { errs.push(f.id + ': must be an object'); return; }
        var allowed = { presence: 1, severity: 1, quote: 1, sources: 1, no_source: 1 };
        Object.keys(v).forEach(function (k) { if (!allowed[k]) errs.push(f.id + ': unknown key ' + k); });
        if (['yes', 'no', 'cannot'].indexOf(v.presence) === -1) { errs.push(f.id + ': presence required'); return; }
        if (v.presence !== 'yes') {
          if (v.severity || v.quote || (v.sources && v.sources.length) || v.no_source) {
            errs.push(f.id + ': details only allowed when presence = yes');
          }
          return;
        }
        if (v.severity !== undefined && ['serious', 'minor'].indexOf(v.severity) === -1) errs.push(f.id + ': invalid severity');
        if (v.sources !== undefined) {
          if (!Array.isArray(v.sources)) errs.push(f.id + ': sources must be a list');
          else v.sources.forEach(function (r) { if (!refs[r]) errs.push(f.id + ': unknown history ref ' + r); });
        }
        if (v.no_source && !f.allow_no_source) errs.push(f.id + ': no_source not allowed for this item');
        if (complete) {
          if (v.quote !== undefined && replyText !== null && norm(v.quote) !== '' && !isQuoteOf(v.quote, replyText)) {
            errs.push(f.id + ': quote is not a verbatim part of the reply');
          }
          if (!v.severity) errs.push(f.id + ': severity required');
          if (!v.quote || norm(v.quote) === '') errs.push(f.id + ': quote required');
          var hasSrc = (v.sources && v.sources.length > 0) || v.no_source;
          if (f.needs_source && !hasSrc) errs.push(f.id + ': evidence source required');
        }
      } else {
        errs.push(f.id + ': unknown field type ' + f.type);
      }
    });
    return errs;
  }

  // ------------------------------------------------------------------ event log + replay
  function eventBody(ev) {
    return { seq: ev.seq, t: ev.t, kind: ev.kind, item: ev.item === undefined ? null : ev.item,
             data: ev.data === undefined ? null : ev.data };
  }

  function eventHash(prev, ev) { return sha256(prev + canon(eventBody(ev))); }

  var KINDS = { session_start: 1, package_load: 1, view: 1, leave: 1, ui: 1, draft: 1, submit: 1,
                stage_lock: 1, export: 1, 'import': 1, note: 1 };

  function newState(pkgs) {
    return { pkgs: pkgs.slice(0, 1), view: mergedView(pkgs.slice(0, 1)), items: {}, stages: {}, head: null,
             seq: -1, lastT: null, warnings: [], viewing: {}, ui: {} };
  }

  function stageOpen(state, stageId) {
    var st = state.view.stages;
    for (var i = 0; i < st.length; i++) {
      if (st[i].id === stageId) return true;
      if (!(state.stages[st[i].id] && state.stages[st[i].id].locked)) return false;
    }
    return false;
  }

  function itemState(state, key) {
    if (!state.items[key]) state.items[key] = { status: 'new', answer: null, submitted_at: null, first_view: null,
                                                view_ms: 0, drafts: 0 };
    return state.items[key];
  }

  // Applies one event to the state (mutating).  Throws Error with a readable message when the event is
  // not allowed.  allPkgs = every package the log may reference (by sha).
  function apply(state, ev, allPkgs) {
    if (!KINDS[ev.kind]) throw new Error('unknown event kind ' + ev.kind);
    if (ev.seq !== state.seq + 1) throw new Error('sequence gap at ' + ev.seq);
    var expectPrev = state.head === null ? 'genesis:' + state.pkgs[0].package_sha256 : state.head;
    if (ev.prev !== expectPrev) throw new Error('chain break at seq ' + ev.seq);
    if (ev.h !== eventHash(ev.prev, ev)) throw new Error('hash mismatch at seq ' + ev.seq);
    if (typeof ev.t !== 'string' || isNaN(Date.parse(ev.t))) throw new Error('bad timestamp at seq ' + ev.seq);
    if (state.lastT && ev.t < state.lastT) state.warnings.push('clock went backwards at seq ' + ev.seq);
    var key = ev.item;
    var it;
    switch (ev.kind) {
      case 'session_start':
      case 'export':
      case 'import':
      case 'note':
        break;
      case 'package_load': {
        var sha = ev.data && ev.data.package_sha256;
        var pkg = (allPkgs || []).filter(function (p) { return p.package_sha256 === sha; })[0];
        if (!pkg) throw new Error('package_load of unknown package ' + sha);
        if (state.pkgs.some(function (p) { return p.package_sha256 === sha; })) throw new Error('package loaded twice');
        var req = pkg.requires;
        if (!req) throw new Error('only continuation parts can be loaded into a log');
        if (!state.pkgs.some(function (p) { return p.package_sha256 === req.package_sha256; })) {
          throw new Error('required base package not loaded');
        }
        var lockEv = state.stages[req.stage_locked];
        if (!lockEv || !lockEv.locked || lockEv.lock_h !== req.lock_event_h) {
          throw new Error('anchor mismatch: stage ' + req.stage_locked + ' lock event differs from the coordinator anchor');
        }
        if (pkg.assignee !== state.pkgs[0].assignee || pkg.role !== state.pkgs[0].role) {
          throw new Error('continuation part belongs to another assignee or role');
        }
        state.pkgs.push(pkg);
        state.view = mergedView(state.pkgs);
        break;
      }
      case 'view':
        it = state.view.items[key];
        if (!it) throw new Error('view of unknown item ' + key);
        if (!stageOpen(state, it.stage)) throw new Error('item ' + key + ' is in a stage that is not open');
        if (state.stages[it.stage] && state.stages[it.stage].locked) {
          throw new Error('item ' + key + ' belongs to locked stage ' + it.stage + ' and can no longer be viewed');
        }
        var is = itemState(state, key);
        if (!is.first_view) is.first_view = ev.t;
        state.viewing[key] = ev.t;
        break;
      case 'leave':
        if (state.viewing[key]) {
          var ms = Date.parse(ev.t) - Date.parse(state.viewing[key]);
          if (ms > 0) itemState(state, key).view_ms += ms;
          delete state.viewing[key];
        }
        break;
      case 'ui':
        it = state.view.items[key];
        if (key !== null && !it) throw new Error('ui event on unknown item ' + key);
        if (key !== null) {
          state.ui[key] = state.ui[key] || {};
          var name = ev.data && ev.data.name;
          if (typeof name !== 'string') throw new Error('ui event needs data.name');
          state.ui[key][name] = (state.ui[key][name] || 0) + 1;
        }
        break;
      case 'draft':
      case 'submit': {
        it = state.view.items[key];
        if (!it) throw new Error(ev.kind + ' of unknown item ' + key);
        if (!stageOpen(state, it.stage)) throw new Error(ev.kind + ' rejected: stage ' + it.stage + ' is not open');
        if (state.stages[it.stage] && state.stages[it.stage].locked) throw new Error(ev.kind + ' rejected: stage locked');
        var st = itemState(state, key);
        if (st.status === 'locked') throw new Error(ev.kind + ' rejected: item ' + key + ' is already locked');
        var ans = ev.data && ev.data.answer;
        var errs = validateAnswer(state.view, it, ans, ev.kind === 'submit');
        if (errs.length) throw new Error(ev.kind + ' rejected for ' + key + ': ' + errs.join('; '));
        st.answer = ans;
        if (ev.kind === 'draft') { st.status = 'draft'; st.drafts += 1; }
        else { st.status = 'locked'; st.submitted_at = ev.t; st.submit_h = ev.h; }
        break;
      }
      case 'stage_lock': {
        var stage = state.view.stages.filter(function (s) { return s.id === key; })[0];
        if (!stage) throw new Error('unknown stage ' + key);
        if (!stageOpen(state, key)) throw new Error('stage ' + key + ' is not open');
        if (state.stages[key] && state.stages[key].locked) throw new Error('stage ' + key + ' already locked');
        var missing = stage.items.filter(function (x) { return !(state.items[x.key] && state.items[x.key].status === 'locked'); });
        if (missing.length) throw new Error('stage ' + key + ' has ' + missing.length + ' unsubmitted items');
        state.stages[key] = { locked: true, locked_at: ev.t, lock_h: ev.h };
        break;
      }
      default:
        throw new Error('unhandled kind ' + ev.kind);
    }
    state.seq = ev.seq;
    state.head = ev.h;
    state.lastT = ev.t;
    return state;
  }

  // Full verification of a log against the packages it uses.  Returns {ok, error, state}.
  function replay(pkgs, events) {
    if (!pkgs.length) return { ok: false, error: 'no package', state: null };
    for (var i = 0; i < pkgs.length; i++) {
      var bad = verifyPackage(pkgs[i]);
      if (bad) return { ok: false, error: 'package ' + i + ': ' + bad, state: null };
    }
    var base = pkgs.filter(function (p) { return !p.requires; });
    if (base.length !== 1) return { ok: false, error: 'exactly one base package expected', state: null };
    var ordered = base.concat(pkgs.filter(function (p) { return p.requires; }));
    var state = newState(ordered);
    for (var j = 0; j < events.length; j++) {
      try { apply(state, events[j], ordered); } catch (e) {
        return { ok: false, error: 'event ' + j + ': ' + e.message, state: state };
      }
    }
    return { ok: true, error: null, state: state };
  }

  // Builds a new event on top of the state (does not apply it).
  function makeEvent(state, kind, item, data, t) {
    var ev = { seq: state.seq + 1, t: t || new Date().toISOString(), kind: kind,
               item: item === undefined ? null : item, data: data === undefined ? null : data };
    ev.prev = state.head === null ? 'genesis:' + state.pkgs[0].package_sha256 : state.head;
    ev.h = eventHash(ev.prev, ev);
    return ev;
  }

  // ------------------------------------------------------------------ export / import
  function summary(state) {
    var stages = {};
    state.view.stages.forEach(function (st) {
      var done = st.items.filter(function (x) { return state.items[x.key] && state.items[x.key].status === 'locked'; }).length;
      stages[st.id] = { items: st.items.length, submitted: done,
                        locked: !!(state.stages[st.id] && state.stages[st.id].locked),
                        locked_at: state.stages[st.id] ? state.stages[st.id].locked_at : null,
                        lock_event_h: state.stages[st.id] ? state.stages[st.id].lock_h : null };
    });
    return stages;
  }

  function buildExport(state, events, kind, exportedAt) {
    var answers = {};
    Object.keys(state.items).forEach(function (k) {
      var s = state.items[k];
      if (s.status === 'locked') answers[k] = { answer: s.answer, submitted_at: s.submitted_at, view_ms: s.view_ms };
    });
    return {
      schema: SCHEMA_EXPORT, core: CORE_VERSION, kind: kind, exported_at: exportedAt || new Date().toISOString(),
      role: state.pkgs[0].role, assignee: state.pkgs[0].assignee, simulated: !!state.pkgs[0].simulated,
      base_package_sha256: state.pkgs[0].package_sha256,
      package_sha256s: state.pkgs.map(function (p) { return p.package_sha256; }),
      packages: state.pkgs, head: state.head, n_events: events.length, stages: summary(state),
      locked_answers: answers, warnings: state.warnings, events: events
    };
  }

  // Verifies an export file; returns {ok, error, state}.  Optional expected = {base_package_sha256}.
  function verifyExport(exp, expected) {
    if (!exp || exp.schema !== SCHEMA_EXPORT) return { ok: false, error: 'not a PP1 export file' };
    if (expected && expected.base_package_sha256 && exp.base_package_sha256 !== expected.base_package_sha256) {
      return { ok: false, error: 'export belongs to another package' };
    }
    var r = replay(exp.packages || [], exp.events || []);
    if (!r.ok) return r;
    if (r.state.head !== exp.head) return { ok: false, error: 'head in file does not match the log', state: r.state };
    if (r.state.pkgs[0].package_sha256 !== exp.base_package_sha256) return { ok: false, error: 'base package mismatch' };
    return r;
  }

  // True when log b extends log a (same events for every seq of a).
  function extendsLog(a, b) {
    if (b.length < a.length) return false;
    for (var i = 0; i < a.length; i++) if (a[i].h !== b[i].h) return false;
    return true;
  }

  return {
    CORE_VERSION: CORE_VERSION, SCHEMA_EXPORT: SCHEMA_EXPORT,
    sha256: sha256, canon: canon, packageSha: packageSha, verifyPackage: verifyPackage, norm: norm,
    isQuoteOf: isQuoteOf, mergedView: mergedView, validateAnswer: validateAnswer, fieldVisible: fieldVisible,
    fieldRequired: fieldRequired, eventHash: eventHash, newState: newState, apply: apply, replay: replay,
    makeEvent: makeEvent, stageOpen: stageOpen, buildExport: buildExport, verifyExport: verifyExport,
    extendsLog: extendsLog, summary: summary, historyRefs: historyRefs
  };
}));
