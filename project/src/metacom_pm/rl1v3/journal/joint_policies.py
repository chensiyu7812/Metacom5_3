"""Pre-output fixed J06 policies. Only visible query text is a policy feature."""
import json
from pathlib import Path
import re
from ..io import file_sha256,write_json_once

PROTOCOL='pmrl1-j-joint-fixed-policies-v1'
ARMS=('STOP','MS','RS','MS_RS')
MEMORY_PATTERN=r'\b(?:earlier|previous(?:ly)?|last time|before)\b'
HELP_PATTERN=r"\b(?:please\s+(?:help|draft|suggest)|(?:can|could)\s+you\s+(?:help|draft|suggest)|(?:i(?:'d| would) like|i want)\s+(?:help|a plan)|(?:draft|suggest)\s+(?:one|a)|one\s+(?:small|practical|feasible|concrete)\s+(?:next\s+)?step)\b"
NO_HELP_PATTERN=r"\b(?:do not want|don't want|not asking for|no)\s+(?:any\s+)?(?:advice|a plan|planning)|\b(?:only|just)\s+(?:listen|listening|acknowledge|acknowledgement)\b"


def visible_rule(query):
    if not isinstance(query,str):raise TypeError('visible query string required')
    memory=bool(re.search(MEMORY_PATTERN,query,re.I))
    method=bool(re.search(HELP_PATTERN,query,re.I)) and not bool(re.search(NO_HELP_PATTERN,query,re.I))
    return 'MS_RS' if memory and method else 'MS' if memory else 'RS' if method else 'STOP'


def freeze(runtime_path,out):
    runtime_path,out=Path(runtime_path),Path(out)
    rows=[json.loads(x) for x in runtime_path.read_text().splitlines()]
    if len(rows)!=24 or len({r['task_id'] for r in rows})!=24:raise ValueError('frozen 24 runtime tasks required')
    for r in rows:
        if r['query']!='\n'.join(t['text'] for t in r['turns']):raise ValueError('query/visible turns mismatch')
    policies={f'always_{arm}':[dict(task_id=r['task_id'],arm=arm) for r in rows] for arm in ARMS}
    policies['visible_query_rule']=[dict(task_id=r['task_id'],arm=visible_rule(r['query'])) for r in rows]
    result=dict(protocol=PROTOCOL,runtime_path=str(runtime_path),runtime_sha256=file_sha256(runtime_path),
        generated_output_files_read=0,evalspec_files_read=0,stratum_files_read=0,owner_features_used=False,
        task_id_features_used=False,unread_resource_or_score_features_used=False,
        policy_features=['visible query text only'],policies=policies,
        rule=dict(memory_regex=MEMORY_PATTERN,help_regex=HELP_PATTERN,no_help_regex=NO_HELP_PATTERN,
            regex_flags='IGNORECASE',combined='memory+help=>MS_RS, memory=>MS, help=>RS, otherwise STOP',
            qualification='one deterministic development rule; no fitted classifier or guarantee of request-intent accuracy'),
        oracle=dict(status='privileged diagnostic only, never deployable policy',
            quality='report max lower bound and max upper bound separately; uncertainty is not zero',
            cost='report nondominated quality-interval/input-token points; no fitted scalar cost weight',
            ties='same lower/upper interval: lower actual input tokens, then fixed order STOP,MS,RS,MS_RS'),
        report='original four source-demand strata and six source groups are evaluation-only; no policy input',
        future_policy_tuning_after_outputs_allowed=False,formal_reward_qualified=False,code_sha256=file_sha256(__file__))
    write_json_once(out,result);return result
