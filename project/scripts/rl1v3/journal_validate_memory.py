#!/usr/bin/env python3
"""Independent memory artifact checks and real journal-bound read episodes."""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys
# Use caller-selected temporary A+B+G stack; never silently prepend the incomplete base.
from metacom_pm.rl1v3.io import file_sha256,canonical_json,decode_contract,write_json_once,write_bytes_once
from metacom_pm.rl1v3 import contracts as K
from metacom_pm.rl1v3.sources import source_registry as S
from metacom_pm.rl1v3.compile import asof as A
from metacom_pm.rl1v3.retrieve.native_tokens import NativeTokenizer
from metacom_pm.rl1v3.journal.memory_port import SnapshotPrefixPort
from metacom_pm.rl1v3.journal.runtime_binding import VerifiedEpisode,binding_for
p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--memory',type=Path,required=True);p.add_argument('--validation-output',default='MEMORY_RUNTIME_VALIDATION.json')
a=p.parse_args();m=a.memory;r=json.loads((m/'MEMORY_BUILD_REPORT.json').read_text())
for name,entry in r['outputs'].items():
    assert file_sha256(m/name)==entry['sha256'],name
registry=S.load(a.root/'project/outputs/pm_rl1/v3/A1_preparation/final/registry')
ledger=A.Ledger(m/'ledger')
tok=NativeTokenizer('/opt/tokkio-data0/tokkio_models/gemma-4-12B-it-707f0a3',a.root/'project/outputs/pm_rl1/v3/A1_reuse/ASSET_REUSE_MANIFEST.json')
model_native=tok.native_context_tokens;tok.native_context_tokens=16384
rows=[json.loads(x) for x in (m/'readings24_private.jsonl').read_text().splitlines()]
# Simulate a changed whole-corpus file digest with unchanged legal session bytes.
changed_entries=[]
for entry in registry.entries:
    changed=replace(entry.source,raw_sha256='f'*64)
    changed_entries.append(replace(entry,source=changed,source_id=S._source_id(changed)))
assert not registry.operations, 'mutation fixture requires original unmodified registry'
changed_registry=S.Registry(changed_entries,inputs=registry.inputs,folds=registry.folds,
    excluded_families=registry.excluded_families,rejected=registry.rejected,operations=())
assert changed_registry.version!=registry.version
episodes=[]
for row in rows[:2]:
    prefix=decode_contract(K.PrefixSpec,canonical_json(row['prefix']))
    snapshot=A.materialize(registry,prefix,ledger,writer=ledger.rows[0].writer_identity)
    port=SnapshotPrefixPort(registry,prefix,snapshot,tok,g_id='G0e-tokenizer-only-not-generated',
        decode_id='CPU_read_only',step2_id='journal-snapshot-port-v1',output_reserve_tokens=320)
    binding=binding_for(registry,prefix,snapshot,port)
    changed_snapshot=A.materialize(changed_registry,prefix,ledger,writer=ledger.rows[0].writer_identity)
    assert changed_snapshot['snapshot_sha']==snapshot['snapshot_sha']
    changed_port=SnapshotPrefixPort(changed_registry,prefix,changed_snapshot,tok,
        g_id='G0e-tokenizer-only-not-generated',decode_id='CPU_read_only',
        step2_id='journal-snapshot-port-v1',output_reserve_tokens=320)
    assert changed_port.identity==port.identity, 'whole-file digest renamed the local port'
    assert binding_for(changed_registry,prefix,changed_snapshot,changed_port)==binding
    ep=VerifiedEpisode(registry=registry,prefix=prefix,snapshot=snapshot,port=port,binding=binding)
    state=ep.reset();state,info=ep.try_step(state,'GET_MS');assert state.order==('MS',)
    terminal,info=ep.try_step(state,'STOP');assert terminal.done
    _,invalid=ep.try_step(terminal,'GET_MS');assert invalid.reason=='after_stop'
    assert ep.stop_value(terminal).status=='pending'
    episodes.append(dict(prefix_id=prefix.prefix_id,binding_sha256=binding.sha256,
        snapshot_sha256=snapshot['snapshot_sha'],bank=port.bank_version,
        path=['GET_MS','STOP'],reading_record_ids=state.readings[0].record_ids,
        exact_snapshot_grounding=True,after_stop='rejected',reward='pending',
        delivered_tokens=state.readings[0].tokens if hasattr(state.readings[0],'tokens') else None))
materials=[json.loads(x) for x in (m/'request_material_private.jsonl').read_text().splitlines()]
cap=dict(protocol='pmrl1-j-memory-runtime-capacity-amendment-v1',
    original_report_sha256=file_sha256(m/'MEMORY_BUILD_REPORT.json'),
    model_config_max_position_embeddings=model_native,g0e_runtime_max_model_len=16384,output_reserve_tokens=320,
    original_max_memory_sessions=4,max_actual_DP_sessions=max(len(x['private_source_session_ids']) for x in materials if x['arm']=='DP'),
    max_base_renderer_prompt_tokens=max(x['base_renderer_prompt_tokens'] for x in materials),
    base_renderer_capacity_failures=sum(x['base_renderer_prompt_tokens']+320>16384 for x in materials),
    final_journal_renderer_capacity='must be checked by final request builder; old v0 token count is not authorization',
    actual_snapshot_bound_episodes=episodes,whole_corpus_digest_mutation_port_identity_unchanged=True,
    mask_cost='private unit measurement still occurs; separate prefetch CPU cost not yet measured, no online cost-fairness claim',qualification='CPU engineering/source grounding only; no G outputs or qualified rewards')
write_json_once(m/a.validation_output,cap)
evals={x['task_id']:x for x in map(json.loads,(m/'evalspec_private.jsonl').read_text().splitlines())}
tasks=[json.loads(x) for x in (m/'tasks_runtime.jsonl').read_text().splitlines()]
preview=['# Memory 私有可读样例','原问题、原答案与原文仅留本机；未生成模型答案。','']
for task in tasks[:2]:
    taskid=task['task_id'];e=evals[taskid]
    direct=next(x for x in materials if x['task_id']==taskid and x['arm']=='DP')
    preview += ['## '+taskid, '**原问题**：'+task['visible_prefix']['turns'][0]['text'],
        '**原 gold（仅评价）**：'+e['gold'],'**能力**：'+e['capability'],
        '**证据来源集合**：'+', '.join(e['evidence_sets'][0]),
        '**评价**：完全规范化相等可确定；复杂语义必须独立判定，否则 pending [0,1]。',
        '**DP 完整来源（非部署检索）**：','```text',direct['readings'][0]['reading_text'] if direct['readings'] else '(空)', '```','']
write_bytes_once(m/'MEMORY_SAMPLES_PRIVATE.md',('\n'.join(preview)+'\n').encode())
print(json.dumps(dict(snapshot_bound_episodes=len(episodes),g0e_runtime_limit=16384,base_renderer_capacity_failures=cap['base_renderer_capacity_failures'],max_DP_sessions=cap['max_actual_DP_sessions'],reward='pending'),indent=2))
