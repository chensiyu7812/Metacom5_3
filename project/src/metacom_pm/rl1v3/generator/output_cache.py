"""Write-once outcome cache. Technical failures never become valid terminals."""
from pathlib import Path
import json
import math

from ..io import object_sha256, sha256_text, write_json_once

PROTOCOL = 'pmrl1v3-g0e-output-cache-1'
FINISHES = ('eos','length','timeout','oom','error','cancelled')


def cache_key(packet):
    return object_sha256(dict(protocol=PROTOCOL,terminal=packet.key.sha256,
        request=packet.request_sha256, binding=packet.binding.sha256))


def record(packet, *, response, generated_token_ids, finish_reason, elapsed_seconds,
           execution_identity, model_called):
    """Caller must attest actual execution; no pending/unrun placeholder records.

    This only records generation completion, never a judge/quality verdict.
    The complete generated token IDs (including EOS) are retained for billing.
    """
    if model_called is not True: raise ValueError('unrun requests are not generation outcomes')
    if execution_identity != packet.binding.g_id: raise ValueError('execution/G0e identity mismatch')
    if finish_reason not in FINISHES: raise ValueError('unknown finish reason')
    if (not isinstance(response,str) or not isinstance(elapsed_seconds,(int,float)) or
        not math.isfinite(elapsed_seconds) or elapsed_seconds < 0): raise ValueError('invalid execution result')
    ids = tuple(generated_token_ids)
    if any(type(x) is not int or x < 0 for x in ids): raise ValueError('invalid generated IDs')
    bound = packet.binding.spec['decode']['max_new_tokens']
    if len(ids)>bound: raise ValueError('decoder exceeded the frozen output bound')
    complete = finish_reason=='eos' and bool(response.strip()) and bool(ids)
    if finish_reason=='eos' and (not ids or ids[-1] not in packet.binding.spec['decode']['eos_token_id']):
        raise ValueError('claimed natural stop without an allowed EOS')
    status = ('complete' if complete else 'technical_truncation' if finish_reason=='length'
              else 'empty_output' if finish_reason=='eos' else 'technical_'+finish_reason)
    row = dict(protocol=PROTOCOL,cache_key=cache_key(packet),terminal_key_sha256=packet.key.sha256,
        request_sha256=packet.request_sha256,g_id=execution_identity,response=response,
        response_sha256=sha256_text(response),generated_token_ids=list(ids),output_tokens=len(ids),
        input_tokens=packet.token_ledger['input_tokens'],finish_reason=finish_reason,status=status,
        elapsed_seconds=elapsed_seconds,reusable_as_complete=complete,
        evaluation_status='pending',reward=None,model_called=True,qualification_tier='engineering_only')
    return dict(row, outcome_sha256=object_sha256(row))


def validate(packet, row):
    expected = record(packet, response=row['response'], generated_token_ids=row['generated_token_ids'],
        finish_reason=row['finish_reason'], elapsed_seconds=row['elapsed_seconds'],
        execution_identity=row['g_id'], model_called=row['model_called'])
    if row != expected:
        raise ValueError('cache identity/content corruption')


def save(directory, packet, outcome):
    validate(packet, outcome)
    directory=Path(directory)
    write_json_once(directory/(cache_key(packet)+'.json'),outcome)


def load(directory, packet):
    path=Path(directory)/(cache_key(packet)+'.json')
    if not path.exists(): return None
    row=json.loads(path.read_text())
    validate(packet,row)
    # A timeout/truncation remains an auditable failed attempt, never a response hit.
    return row if row['reusable_as_complete'] and row['status']=='complete' else None
