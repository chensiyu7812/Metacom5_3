"""Small typed RS candidates and fair input preparation, never method approval."""
from dataclasses import dataclass

from ..io import object_sha256


@dataclass(frozen=True)
class MethodCandidate:
    name: str
    source_url: str
    source_section: str
    source_quote: str
    license_scope: str
    when_to_use: str
    when_not_to_use: str
    action_options: tuple[str, ...]
    common_misuse: str
    limits: str
    external_version: str
    available_from: str
    review_status: str = 'pending_applicability_and_license_review'

    def __post_init__(self):
        if not all((self.name,self.source_url,self.source_section,self.source_quote,
                    self.license_scope,self.when_to_use,self.when_not_to_use,self.action_options,
                    self.common_misuse,self.limits,self.external_version,self.available_from)):
            raise ValueError('method provenance/boundaries are required')

    @property
    def identity(self):
        return 'method-candidate:' + object_sha256(self)

    def text(self):
        return (f'{self.name}\nConsider only: {self.when_to_use}\nAvoid: {self.when_not_to_use}\n'
            + '\n'.join(self.action_options) + f'\nMisuse: {self.common_misuse}\nLimits: {self.limits}')


@dataclass(frozen=True)
class CaseCandidate:
    record_id: str
    family_id: str
    text: str
    source_span_sha256: str
    license_scope: str
    source_split: str
    review_status: str = 'unreviewed_external_case'


def fair_rs_inputs(prefix, methods, case, *, external_version, experiment_date):
    """Fixed-source counterfactual inputs: identical prefix/G, no RAG assumed.

    External corpus version is available at experiment preparation time, not
    compared with a personal session rank. This is not a claim that this corpus
    existed in a historical deployment. All non-R0 arms remain review-blocked.
    """
    if not methods or any(m.external_version != external_version or m.available_from > experiment_date for m in methods):
        raise ValueError('external version unavailable')
    if case.source_split != 'train' or case.family_id in prefix.ancestor_family_ids:
        raise ValueError('CASE train/family violation')
    directory = '\n'.join(f'{m.name}: {m.when_to_use}' for m in methods)
    # First supplied method is a predeclared deterministic candidate, not a ranker.
    method = methods[0].text()
    extra = 'External case; never the current user or assistant\'s experience.\n'+case.text
    common = dict(prefix_context_sha256=prefix.runtime_sha256,
        external_version=external_version, method_ids=[m.identity for m in methods],
        g_condition='same frozen G0e weights/system/decode; no execution',
        other_memory='OFF', outcome=None, native_token_ids=None,
        token_status='pending_native_tokenization; count all resident text and CASE')
    rows = []
    for arm,text in [('R0',''),('F-resident',directory),('METHOD',method),('METHOD+CASE',method+'\n'+extra)]:
        row = dict(common, arm=arm, extra_text=text,
            readiness='input_prepared_review_pending' if arm != 'R0' else 'input_prepared',
            runtime_callable=False, method_effectiveness='unknown')
        rows.append(dict(row, input_identity='rs-input:'+object_sha256(row)))
    return rows
