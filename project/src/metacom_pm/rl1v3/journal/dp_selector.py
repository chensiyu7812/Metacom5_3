"""Scoped new DP selector presentation: explicit history selection, original backend.

No historical HTML or receipt is overwritten. Missing translations remain missing;
this patch is not a new human review or a complete bilingual UI acceptance.
"""
from ..compile import dp_selection_v2 as original

PROTOCOL = 'pmrl1-j-dp-explicit-selection-1'


def selection_html(bundle):
    page = original.selection_html(bundle)
    old = '$("history").replaceChildren();$("source").replaceChildren();'
    new = old + '\n const choose=document.createElement("option");choose.value="";choose.textContent="请选择一份历史会话";$("source").append(choose);'
    if page.count(old) != 1:
        raise ValueError('upstream selector changed; inspect before applying scoped patch')
    page = page.replace(old, new)
    page = page.replace('此时点没有可选择的完整历史。', '请明确选择一份历史会话；此时点可能没有可选择的完整历史。')
    return page.replace('</head>', '<meta name="journal-selector-version" content="' + PROTOCOL + '"></head>')
