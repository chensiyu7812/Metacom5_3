"""GE2 shared, source-only CPU retrieval; no model, annotation or evaluation input.

Both backends score the same complete parent transcripts (all original roles,
without the old resource banner), then choose one eligible fixed-radius window
per parent. Scores remain private. BM25 is a fixed transparent comparator, not a
claim of optimal tuning or semantic retrieval. Old retrieval identities survive.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import asdict, dataclass
import math
import re

from ..io import object_sha256

PROTOCOL = 'pmrl1-j-ge2-shared-retrieval-v1'


def tokens(text):
    return re.findall(r"[a-z0-9']+", text.casefold())


@dataclass(frozen=True)
class RetrievalConfig:
    backend: str = 'time_lexical'
    top_k: int = 4
    window_radius: int = 1
    bm25_k1: float = 1.2
    bm25_b: float = .75

    def __post_init__(self):
        if (self.backend not in ('time_lexical', 'bm25') or type(self.top_k) is not int
                or not 1 <= self.top_k <= 4 or type(self.window_radius) is not int
                or self.window_radius != 1 or self.bm25_k1 != 1.2 or self.bm25_b != .75):
            raise ValueError('GE2 fixed retrieval configuration')


def union_intervals(intervals):
    """Inclusive source turn indices; adjacent intervals share one rendering."""
    result = []
    for pair in sorted(intervals):
        if (len(pair) != 2 or any(type(x) is not int for x in pair)
                or pair[0] < 0 or pair[1] < pair[0]):
            raise ValueError('invalid source interval')
        lo, hi = pair
        if result and lo <= result[-1][1] + 1:
            result[-1][1] = max(hi, result[-1][1])
        else:
            result.append([lo, hi])
    return result


def covered(index, intervals):
    return any(lo <= index <= hi for lo, hi in intervals)


def validate_record(record):
    if (record.get('head') != 'MS' or record.get('view') != 'raw'
            or not isinstance(record.get('record_id'), str) or not record['record_id']
            or not record.get('owner_id') or not record.get('parent_session_id')
            or type(record.get('source_rank')) is not int or record['source_rank'] < 0
            or not isinstance(record.get('reported_at'), dict)
            or not isinstance(record['reported_at'].get('date'), str)
            or not record['reported_at']['date']):
        raise ValueError('complete source-bound MS_RAW record required')
    refs = record.get('source_refs')
    if not isinstance(refs, list) or not refs:
        raise ValueError('complete source references required')
    indices = []
    for ref in refs:
        if (type(ref.get('turn_index')) is not int or ref['turn_index'] < 0
                or ref.get('speaker') not in ('seeker', 'supporter')
                or not isinstance(ref.get('exact_quote'), str) or not ref['exact_quote']):
            raise ValueError('invalid complete source turn')
        indices.append(ref['turn_index'])
    if indices != sorted(set(indices)):
        raise ValueError('source turns must have unique increasing original indices')


class _BM25:
    """Robertson-style positive IDF, k1=1.2/b=.75, unique query terms."""
    def __init__(self, documents, config):
        self.config = config
        self.counts = {key: Counter(tokens(text)) for key, text in documents.items()}
        self.lengths = {key: sum(count.values()) for key, count in self.counts.items()}
        self.average = sum(self.lengths.values()) / max(1, len(self.lengths))
        self.df = Counter(term for count in self.counts.values() for term in count)
        self.n = len(self.counts)

    def score(self, key, query):
        count = self.counts[key]
        length = self.lengths[key]
        c = self.config
        total = 0.
        for term in set(tokens(query)):
            tf = count[term]
            if not tf:
                continue
            idf = math.log(1. + (self.n - self.df[term] + .5) / (self.df[term] + .5))
            denominator = tf + c.bm25_k1 * (1 - c.bm25_b + c.bm25_b * length / max(1., self.average))
            total += idf * tf * (c.bm25_k1 + 1) / denominator
        return total


class SharedRetrieval:
    def __init__(self, records, config=RetrievalConfig()):
        self.config = config
        rows = deepcopy(list(records))
        for record in rows:
            validate_record(record)
        self.records = {r['record_id']: r for r in rows}
        if len(self.records) != len(rows):
            raise ValueError('duplicate record identity')
        # Explicitly index source text, not resource metadata or wrapper prose.
        self.documents = {rid: '\n'.join(x['exact_quote'] for x in r['source_refs'])
                          for rid, r in self.records.items()}
        self.turn_documents = {(rid, ref['turn_index']): ref['exact_quote']
                               for rid, r in self.records.items() for ref in r['source_refs']}
        self.parent_bm25 = _BM25(self.documents, config)
        self.turn_bm25 = _BM25(self.turn_documents, config)
        self.identity = object_sha256(dict(protocol=PROTOCOL, config=asdict(config),
            records=sorted((rid, object_sha256(r)) for rid, r in self.records.items()),
            document='all exact source quotes, all roles, no wrapper',
            rank='parent score descending, source_rank descending, record_id; anchor score descending, turn_index'))

    def _score(self, key, query, *, turn=False):
        if self.config.backend == 'bm25':
            return (self.turn_bm25 if turn else self.parent_bm25).score(key, query)
        query_words = set(tokens(query))
        text = (self.turn_documents if turn else self.documents)[key]
        return len(query_words & set(tokens(text))) / max(1, len(query_words))

    def search(self, query, *, read_intervals=None, unread_only=True):
        if not isinstance(query, str) or not query.strip() or type(unread_only) is not bool:
            raise ValueError('query and unread_only types')
        intervals = read_intervals or {}
        if set(intervals) - set(self.records):
            raise ValueError('foreign read interval parent')
        intervals = {rid: union_intervals(value) for rid, value in intervals.items()}
        candidates = []
        for rid, record in self.records.items():
            refs = record['source_refs']
            windows = []
            for position, ref in enumerate(refs):
                lo = max(0, position - self.config.window_radius)
                hi = min(len(refs), position + self.config.window_radius + 1)
                selected = refs[lo:hi]
                # Exclusion applies to the actual candidate window BEFORE anchor
                # selection, not to a parent after choosing an already-read hit.
                if unread_only and all(covered(x['turn_index'], intervals.get(rid, ())) for x in selected):
                    continue
                windows.append((self._score((rid, ref['turn_index']), query, turn=True), ref, selected))
            if not windows:
                continue
            anchor_score, anchor, selected = min(windows, key=lambda item: (-item[0], item[1]['turn_index']))
            row = dict(record_id=rid, anchor_turn=anchor['turn_index'],
                start_turn=selected[0]['turn_index'], end_turn=selected[-1]['turn_index'],
                source_refs=deepcopy(selected), reported_at=deepcopy(record['reported_at']),
                score=self._score(rid, query), anchor_score=anchor_score,
                source_rank=record['source_rank'])
            row['unit_sha256'] = object_sha256({k: v for k, v in row.items() if k not in ('score', 'anchor_score')})
            candidates.append(row)
        return sorted(candidates, key=lambda row: (-row['score'], -row['source_rank'], row['record_id']))[:self.config.top_k]

    select = search


def configuration_contract():
    return dict(protocol=PROTOCOL, defaults=asdict(RetrievalConfig()),
        backends=['time_lexical', 'bm25'], no_model=True, roles=['seeker', 'supporter'],
        score_is_fact=False, supporter_question_is_fact=False,
        corpus='same complete legal parent source texts, no wrappers',
        bm25_formula='sum_unique_q log(1+(N-df+.5)/(df+.5))*tf*(k1+1)/(tf+k1*(1-b+b*dl/avgdl))',
        anchor='same backend; fixed +/-1 original-turn window; one best eligible window per parent',
        unread='exclude fully covered candidate windows before choosing an anchor',
        ties='parent: recent source_rank then record_id; anchor: earliest original turn',
        temporal_legality='trusted SourceRegistry/As-of callback outside ranker; never score-derived')
