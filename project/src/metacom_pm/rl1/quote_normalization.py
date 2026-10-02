"""Optional, separately versioned typography-only citation normalization.

No word, source-ID, rating, relation or rationale repair. The original strict
result stays immutable; this is an additional offline parsing view, not a retry.
"""
from copy import deepcopy
from hashlib import sha256
import json
import re

from .evidence import evidence_turns
from .judge import _pairs, parse_measurement

VERSION='pm-rl1-qm-typographic-span-v2'
CHAR_MAP={'\u2018':"'",'\u2019':"'",'\u201c':'"','\u201d':'"'}


def canonical_with_map(text):
    out=[];positions=[]
    for i,char in enumerate(text):
        char=' ' if char.isspace() else CHAR_MAP.get(char,char)
        if char==' ' and out and out[-1]==' ':
            positions[-1][1]=i+1
        else:
            out.append(char);positions.append([i,i+1])
    return ''.join(out),positions


def matching_original(quote,source):
    if not isinstance(quote,str) or not quote.strip():return None
    if quote in source:return quote
    normalized,positions=canonical_with_map(source);query,_=canonical_with_map(quote)
    query=query.strip()
    if not query:return None
    found=set()
    for match in re.finditer(re.escape(query),normalized):
        found.add(source[positions[match.start()][0]:positions[match.end()-1][1]])
    # Multiple locations with the SAME original bytes are harmless (the strict
    # parser records all locations). Distinct original spans remain ambiguous.
    return next(iter(found)) if len(found)==1 else None


def parse_typographic_view(raw, **bindings):
    strict=parse_measurement(raw,**bindings)
    base=dict(strict_parser_status=strict['measurement_status'],parser_version=VERSION,
              raw_output_sha256=sha256(raw.encode()).hexdigest())
    if bindings['finish_reason']!='natural_stop':return dict(**strict,**{}) | base
    final=raw.strip()
    if '</think>' in final:
        if final.count('</think>')!=1:return strict | base
        final=final.split('</think>',1)[1].strip()
    if final.startswith('```json') and final.endswith('```'):final=final[7:-3].strip()
    elif final.startswith('```') and final.endswith('```'):final=final[3:-3].strip()
    try:
        obj=json.loads(final,object_pairs_hook=_pairs,
            parse_constant=lambda x:(_ for _ in ()).throw(ValueError('nonfinite JSON')))
        normalized=deepcopy(obj);turns=evidence_turns(bindings['evidence']);changes=[]
        parts=[normalized['q_rationale']]+normalized['claims']
        for i,part in enumerate(parts):
            quote=part['response_quote'];matched=matching_original(quote,bindings['reply'])
            if matched is not None and matched!=quote:
                part['response_quote']=matched;changes.append(dict(part=i,field='response_quote',provided=quote,matched_original=matched))
            for j,ref in enumerate(part['evidence']):
                source=turns.get(ref['source_id'],{}).get('text','')
                quote=ref['quote'];matched=matching_original(quote,source)
                if matched is not None and matched!=quote:
                    ref['quote']=matched;changes.append(dict(part=i,field=f'evidence[{j}].quote',
                        source_id=ref['source_id'],provided=quote,matched_original=matched))
        if not changes:return strict | base | dict(quote_transformations=[])
        reparsed=parse_measurement(json.dumps(normalized,ensure_ascii=False),**bindings)
        return reparsed | base | dict(quote_transformations=changes,
            normalized_final_json=normalized,normalization_scope='only whitespace and straight/curly quote glyphs; no word or source-ID changes',
            original_format_transformations=strict.get('format_transformations',[]))
    except (ValueError,TypeError,KeyError,IndexError):
        return strict | base | dict(quote_transformations=[])
