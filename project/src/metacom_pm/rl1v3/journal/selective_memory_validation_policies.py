"""One preregistered visible-text baseline; no resource/reference/outcome input."""
import re

HISTORY_MARKERS=re.compile(r'\b(?:earlier|previous|history|historical|remember|recall|compare|changed|before)\b|\blast time\b',re.I)


def simple_visible_choice(query):
    if not isinstance(query,str):raise TypeError('only the visible query is accepted')
    return 'MS' if HISTORY_MARKERS.search(query) else 'STOP'
