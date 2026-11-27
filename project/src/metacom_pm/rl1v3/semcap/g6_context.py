"""G6 interface v2 on top of g4_context (version semcap-g6-context-v1; g4_context unchanged).

Changes driven by G4 error attribution:
  1. the latest user message is an enumerable record (U0) for claim formation and checking
     (for the Generator it stays the final native user turn; records shown to G exclude U0);
  2. question-answer linking: a cited answer automatically brings its immediately preceding
     question by the other speaker, and a cited question brings the immediately following
     answer (host rule over record order; logged as auto_added_ids);
  3. risk-claim formation: the system lists what a reply might take for granted that the
     records may not establish; NONE is allowed; plain undisputed facts are not wanted;
  4. P vs B_prime blocks share the same claims and evidence IDs; B_prime only adds the T1i
     result phrase per claim.
"""
from __future__ import annotations

from . import g4_context as X

PROTOCOL = 'semcap-g6-context-v1'

RISK_TASK = (
    'Before a reply is written, list statements about the user or other people that a natural reply to the latest '
    'message might take for granted but that the records may NOT actually establish - for example that a planned or '
    'suggested step was actually done, who did or experienced something, whether something is still true now, or what '
    'happened after an earlier report. Do not list facts that are plainly stated and undisputed. If nothing like that '
    'is at stake, output exactly NONE. Otherwise output at most 3 lines of the form\n'
    'RISK: <one plain sentence about "the user" or another named role (never "I" or "you")> || EVIDENCE: <record IDs, '
    'U0 for the latest message> || SUBJECT: user|supporter|third_party || TIME: as_of_latest_evidence|at_report_time\n'
    'Use only these record IDs: {ids}.')

PHRASE = {'supported': 'supported by these records',
          'contradicted': 'contradicted by these records',
          'not_established': 'not established by the records; do not assume it either way',
          'implied': 'only implied, not stated; treat it as tentative',
          'unprocessed': 'could not be checked'}


def with_u0(state):
    """Evidence list including the latest user message as record U0 (current conversation)."""
    ev = list(state['evidence'])
    ev.append(dict(evidence_id='U0', speaker='seeker', text=state['user_turn'], reported_at=state.get('current_date'),
                   origin='current_visible'))
    return ev


def risk_messages(state):
    ev = with_u0(state)
    ctx = X.render_records(ev, state['situation'], state['current_date'])
    return [dict(role='system', content=X.CLAIM_SYSTEM),
            dict(role='user', content=ctx + '\n\n' + RISK_TASK.format(ids=', '.join(X.allowed_ids(ev))))]


def is_none(text):
    t = text.strip().strip('.').upper()
    return t == 'NONE' or (t.startswith('NONE') and 'RISK:' not in t)


def link_qa(evidence, ids):
    """Deterministic question-answer pairing over record order (no semantics)."""
    order = [e['evidence_id'] for e in evidence]; idx = {e: i for i, e in enumerate(order)}
    out = set(ids); added = []
    for i in ids:
        k = idx[i]; e = evidence[k]
        if k > 0:
            p = evidence[k - 1]
            if p['speaker'] != e['speaker'] and p['text'].rstrip().endswith('?') and p['evidence_id'] not in out:
                out.add(p['evidence_id']); added.append(p['evidence_id'])
        if e['text'].rstrip().endswith('?') and k + 1 < len(evidence):
            n = evidence[k + 1]
            if n['speaker'] != e['speaker'] and n['evidence_id'] not in out:
                out.add(n['evidence_id']); added.append(n['evidence_id'])
    return sorted(out, key=idx.get), added


def claims_block(claims, results=None):
    """P (results=None) or B_prime (results = list of INSPECT outcomes aligned with claims)."""
    if not claims:
        return None
    if results is None:
        head = ('Statements a reply might take for granted (not checked; compare them with the records yourself '
                'before relying on them):')
    else:
        head = ('Statements a reply might take for granted, with an automatic check against the records '
                '(tool results, not verified facts):')
    lines = [head]
    for k, c in enumerate(claims):
        line = f'- "{c["claim"]}" (records: {", ".join(c["evidence_ids"])})'
        if results is not None:
            r = results[k]; j = r.get('judgement', 'unprocessed'); conf = r.get('conflict')
            if conf and conf.get('kind') == 'conflict':
                phrase = 'the records conflict; do not resolve it yourself'
            elif conf and conf.get('kind') == 'cross_session_difference':
                phrase = ('earlier and later reports differ - this may be a change over time or a conflict between '
                          'reports; do not decide which')
            else:
                phrase = PHRASE.get(j, PHRASE['unprocessed'])
            line += f' - check result: {phrase}'
        lines.append(line)
    return '\n'.join(lines)


import re as _re
ID_RE = _re.compile(r'\b([HCU]\d+(?:\.\d+)?)\b')   # v2: U0 is a legal record ID


def parse_risk(text, allowed, max_n=3):
    """Same validation as g4_context.parse_claims (legal-ID enumeration, illegal IDs dropped
    and logged, claims without a legal ID rejected), with U0 recognised. Prefix 'RISK'."""
    allowed = set(allowed); claims, rejects = [], []
    for raw in text.splitlines():
        line = raw.strip().lstrip('-*• ').strip()
        if not line.upper().startswith('RISK:'):
            continue
        parts = [p.strip() for p in line[5:].split('||')]
        claim = parts[0].strip().strip('"'); fields = {}
        for p in parts[1:]:
            k, _, v = p.partition(':'); fields[k.strip().upper()] = v.strip()
        ids = ID_RE.findall(fields.get('EVIDENCE', ''))
        legal = [i for i in dict.fromkeys(ids) if i in allowed]; bad = [i for i in ids if i not in allowed]
        subj = X.SUBJECTS.get(fields.get('SUBJECT', '').lower().strip(), 'unknown')
        tm = fields.get('TIME', '').strip().lower(); tm = tm if tm in X.TIMES else 'as_of_latest_evidence'
        if not claim or len(claim) > 400:
            rejects.append(dict(line=line, reason='claim empty/too long')); continue
        if not legal:
            rejects.append(dict(line=line, reason='no legal evidence id', illegal_ids=bad)); continue
        claims.append(dict(action='INSPECT_CLAIM', claim=claim, evidence_ids=legal[:16], subject=subj, time_scope=tm,
                           dropped_illegal_ids=bad))
        if len(claims) >= max_n:
            break
    return claims, rejects
