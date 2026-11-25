"""Post-J06 candidate: explicit current report scope, not a qualified policy.

Input is only the already visible user query. Resource masks remain in the port.
No files, references, task IDs, owners, demand strata or outputs are policy inputs.
This restricted English rule is a development hypothesis, not semantic coverage.
"""
import re

REPORT = re.compile(r'(?:here is|i have included) (?:my |the )?(?:earlier |previous )?statement(?:, supplied in full)?:\s*[“\"](?P<quote>.+?)[”\"]',re.I|re.S)
SCOPED = re.compile(r'please briefly (?:reflect that reported fact|acknowledge what i reported)',re.I)
EXTRA_HISTORY = re.compile(r'(?:what|which|how|when|where|who|recall|remember|compare).{0,100}(?:previous conversation|earlier conversation|last time|other sessions|other conversations|history|before that)',re.I|re.S)


def visible_features(query):
    if not isinstance(query,str):raise TypeError('only visible query text is accepted')
    report=REPORT.search(query)
    suffix=query[report.end():] if report else query
    return dict(explicit_current_report=bool(report and report['quote'].strip()),
        scope_to_current_report=bool(SCOPED.search(suffix)),
        separate_history_request=bool(EXTRA_HISTORY.search(suffix)))


def choose(query):
    f=visible_features(query)
    return 'STOP' if f['explicit_current_report'] and f['scope_to_current_report'] and not f['separate_history_request'] else 'MS'
