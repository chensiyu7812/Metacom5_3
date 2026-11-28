"""Minimal end-to-end text companion chain (NAA v1.1 decision of 2026-11-28, section 8).

  current user input -> need decision -> on-demand Memory / applicable support skill
  -> applicability (U1+ rule layer over the delivered records) -> Generator reply -> traceable history

Only existing parts are wired; nothing here is a new model or a new research module:
  need decision   J06 visible-query rule (rl1v3.journal.joint_policies.visible_rule: STOP/MS/RS/MS_RS) and the
                  fixed comparators always/never memory, always memory+support; base-G self-selection is a
                  port (one prompt to the same generator), never a trained selector
  memory          NAA MemoryWriter over the live history (append-only, hash-chained) + the WP3 evidence
                  supply (OwnerIndex ranking, reader packing; dense when an encoder is given, BM25 on CPU)
  applicability   behavior.rule_view(plus=True): the U1+ holder / served-person rules, same records only
  support skills  TIP35 SkillRecords (rl1v3.journal.skills.build_skills), offered only when the visible rule
                  sees an explicit help request and a skill's own text overlaps the request; at most one
  generator       any callable messages -> {'text': ...} (plumbing on CPU; the bounded HF runner on GPU)
A learned PM or sequential RL is NOT part of this chain; it would be studied only after a measured
decision gain over these fixed comparators.
"""
from __future__ import annotations

import json
from pathlib import Path
import re

from ..data.contracts import EvidenceRecord, digest, text_hash
from ..memory import reader as R
from ..memory.writer import MemoryWriter
from ...rl1v3.journal.joint_policies import HELP_PATTERN, NO_HELP_PATTERN, visible_rule
from . import arms as WP2
from . import behavior as B
from .retrieval import OwnerIndex, RetrievalSpec

COMPANION_VERSION = 'naa-companion-v2'
NEED_POLICIES = ('visible_rule', 'always_memory', 'never_memory', 'always_memory_support', 'base_self_select')
ARMS = ('STOP', 'MS', 'RS', 'MS_RS')
SELF_SELECT_PROMPT = ('Before answering, decide what this request needs. Reply with one word only: STOP (answer '
                      'directly), MS (needs our earlier conversation), RS (needs a support method), or MS_RS (both).')
SKILL_HEADER = ('A support method that may help. Use it only if it fits what the user asks now; '
                'do not mention its name or source:')


class History:
    """Append-only, hash-chained interaction history of one user. Every turn becomes a legal memory record."""

    def __init__(self, owner_id, *, path=None, source_family='naa-live'):
        self.owner_id, self.source_family, self.path = owner_id, source_family, Path(path) if path else None
        self.turns = []
        if self.path and self.path.exists():
            for line in self.path.read_text().splitlines():
                self.turns.append(json.loads(line))
            self.verify()

    def head(self):
        return self.turns[-1]['turn_sha256'] if self.turns else 'genesis'

    def add(self, role, text, **meta):
        if role not in ('user', 'assistant') or not isinstance(text, str):
            raise ValueError('user/assistant text turns only')
        t = dict(index=len(self.turns), role=role, text=text, text_sha256=text_hash(text), previous=self.head(), **meta)
        t['turn_sha256'] = digest(t)
        self.turns.append(t)
        if self.path:
            with self.path.open('a') as f:
                f.write(json.dumps(t, sort_keys=True) + '\n')
        return t

    def verify(self):
        prev = 'genesis'
        for i, t in enumerate(self.turns):
            body = {k: v for k, v in t.items() if k != 'turn_sha256'}
            if t['index'] != i or t['previous'] != prev or digest(body) != t['turn_sha256']:
                raise ValueError('history chain broken at turn %d' % i)
            prev = t['turn_sha256']

    def records(self, upto=None):
        w = MemoryWriter()
        return [EvidenceRecord(source_id=f'{self.owner_id}:live:{t["index"]}', owner_id=self.owner_id,
                               source_family=self.source_family, session='live', order=t['index'], speaker=t['role'],
                               situation=w.situation, reported_at=t.get('reported_at'), original_text=t['text'],
                               original_text_sha256=t['text_sha256'],
                               coordinates=dict(message_index=t['index'], char_start=0, char_end=len(t['text'])))
                for t in self.turns[:upto]]

    def store(self, upto=None):
        n = len(self.turns) if upto is None else upto
        return MemoryWriter().write(self.records(n), owner_id=self.owner_id, source_family=self.source_family, cutoff=n)


class Memory:
    """On-demand reading over the legal store: one fixed ranking, reader packing, chronological delivery."""

    def __init__(self, count_tokens, budget, *, encoder=None):
        self.count, self.budget, self.encoder = count_tokens, budget, encoder

    def read(self, store, query):
        if not store.units:
            return R.pack([], self.count, self.budget)
        if self.encoder is None:
            idx = OwnerIndex(store, RetrievalSpec(backend='bm25', unit_filter='all'))
            ranked = idx.rank(query)
        else:
            vec = {u.unit_id: self.encoder(u.original_text) for u in store.units}
            idx = OwnerIndex(store, RetrievalSpec(backend='dense', unit_filter='all'), unit_vectors=vec)
            ranked = idx.rank(query, query_vector=self.encoder(query, query=True))
        return R.pack(ranked, self.count, self.budget)


_WORD = re.compile(r'[a-z]{4,}')


class SupportSkills:
    """Legal, source-bound skill records; selection is a visible-text gate, never forced into every turn."""

    def __init__(self, records):
        self.records = list(records)

    def select(self, query):
        if not re.search(HELP_PATTERN, query, re.I) or re.search(NO_HELP_PATTERN, query, re.I):
            return None
        q = set(_WORD.findall(query.lower()))
        score = lambda r: len(q & set(_WORD.findall((r['objective'] + ' ' + ' '.join(r['required_observable_conditions'])).lower())))
        ranked = sorted(self.records, key=lambda r: (-score(r), r['skill_id']))
        return ranked[0] if ranked and score(ranked[0]) > 0 else None


def need_decision(policy, query, *, self_select=None):
    if policy not in NEED_POLICIES:
        raise ValueError('unknown need policy')
    if policy == 'visible_rule':
        arm = visible_rule(query)
    elif policy == 'always_memory':
        arm = 'MS'
    elif policy == 'never_memory':
        arm = 'STOP'
    elif policy == 'always_memory_support':
        arm = 'MS_RS'
    else:
        raw = self_select(query) if self_select else ''
        arm = next((a for a in ('MS_RS', 'STOP', 'MS', 'RS') if re.search(r'\b' + a + r'\b', raw or '')), 'STOP')
    return dict(policy=policy, arm=arm, memory=arm in ('MS', 'MS_RS'), support=arm in ('RS', 'MS_RS'))


class CompanionAgent:
    def __init__(self, history, generator, memory, *, skills=None, policy='visible_rule', recent_turns=6):
        self.history, self.generator, self.memory, self.skills = history, generator, memory, skills
        self.policy, self.recent = policy, recent_turns

    def _self_select(self, query):
        out = self.generator([dict(role='system', content=SELF_SELECT_PROMPT), dict(role='user', content=query)])
        return out.get('text', '')

    def compose(self, query, packed, skill, store):
        parts = []
        if packed is not None:
            parts.append(B.rule_view(list(packed.units), query=query, plus=True)[0])
        if skill is not None:
            parts.append(SKILL_HEADER + '\n' + skill['method_reading'])
        parts.append('Current request from the user:\n' + query)
        recent = [dict(role=t['role'], content=t['text']) for t in self.history.turns[-self.recent:]] if self.recent else []
        return [dict(role='system', content=WP2.system_prompt(store.situation)), *recent,
                dict(role='user', content='\n\n'.join(parts))]

    def step(self, query, *, task_id=None):
        decision = need_decision(self.policy, query, self_select=self._self_select)
        store = self.history.store()
        older = len(self.history.turns) - self.recent if self.recent else len(self.history.turns)
        packed = None
        if decision['memory']:
            visible = self.history.store(max(older, 0))          # the recent turns are already in the prompt
            packed = self.memory.read(visible, query)
        skill = self.skills.select(query) if decision['support'] and self.skills else None
        msgs = self.compose(query, packed, skill, store)
        out = self.generator(msgs)
        reply = out['text']
        u = self.history.add('user', query)
        a = self.history.add('assistant', reply, generator=out.get('g_id'))
        trace = dict(version=COMPANION_VERSION, decision=decision,
                     memory_ids=[x.unit_id for x in packed.units] if packed else [],
                     evidence_tokens=packed.tokens if packed else 0, applicability='U1+' if packed else None,
                     skill_id=skill['skill_id'] if skill else None, messages_sha256=digest(msgs),
                     user_turn=u['turn_sha256'], assistant_turn=a['turn_sha256'], history_head=self.history.head())
        # Optional evaluation telemetry records executed operations; no synthetic role calls.
        if task_id is not None:
            event=lambda name,component,**kw:dict(task_id=task_id,event=name,component=component,**kw)
            events=[event('need_understood','PM1',decision=decision)]
            if packed is not None and packed.units:
                events.append(event('history_read','MS',owner=self.history.owner_id,cutoff=max(older,0),
                    source_ids=[x.unit_id for x in packed.units],
                    source_hashes=[x.original_text_sha256 for x in packed.units]))
            if skill is not None:
                events.append(event('skill_read','RS',skill_id=skill['skill_id'],
                    applicability_basis='explicit help request plus overlap with qualified skill conditions'))
            rh=text_hash(reply)
            events.extend([event('reply_emitted','Generator',reply_sha256=rh,g_id=out.get('g_id')),
                event('history_appended','writer',reply_sha256=a['text_sha256'],history_head=self.history.head()),
                event('followup_ready','PM2',history_head=self.history.head())])
            trace['events']=events
        return dict(reply=reply, trace=trace, messages=msgs)


def run_episode(agent, user_turns):
    """End-to-end evaluation interface: one scripted multi-turn episode -> transcript + per-turn traces."""
    return [dict(turn=i, user=q, **{k: v for k, v in agent.step(q).items() if k != 'messages'})
            for i, q in enumerate(user_turns)]
