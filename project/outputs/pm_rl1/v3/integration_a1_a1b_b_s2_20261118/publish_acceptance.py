"""Publish integration evidence/state only after real code-HEAD acceptance succeeds.

This is an integration receipt writer, not a production implementation change.
The final metadata commit still requires its own push CI after this script.
"""
import hashlib, json, re, shutil, subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

root = Path('/home/tokkio/Metacom5_3-integration')
scratch = Path(__file__).resolve().parent
rel = Path('project/outputs/pm_rl1/v3/integration_a1_a1b_b_s2_20261118')
out = root / rel
state_rel = Path('project/docs/plans/pm_rl1_v3_20261116/EXECUTION_STATE.json')
head = '16644abb3cc28aa1a2f16b0309b84402ac854d5c'
base = '8bcd326e5158482e3e4ad1760f82b117a58d1e2c'

def read(p): return json.loads(Path(p).read_text())
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def git(*args): return subprocess.check_output(['git', *args], cwd=root, text=True).strip()
def put(p, value):
    with p.open('x') as f:
        json.dump(value, f, ensure_ascii=False, indent=2); f.write('\n')

assert git('rev-parse', 'HEAD') == head
assert git('branch', '--show-current') == 'pmrl1-v3/integration'
assert not git('status', '--porcelain')
local = read(scratch / 'validation/VALIDATION_RESULTS.json')
ci = read(scratch / 'code_ci/ATTESTATION.json')
run = read(scratch / 'code_ci/run.json')
assert local['head'] == ci['head'] == run['head_sha'] == head
assert ci['all_jobs_success'] and ci['integration_base_actually_passed']
assert ci['same_v3_test_identity_set_as_local']
assert run['event'] == 'push' and run['head_branch'] == 'pmrl1-v3/integration'
assert run['status'] == 'completed' and run['conclusion'] == 'success'
assert local['v3']['passed'] == ci['v3_gate']['passed'] == 466
assert local['B5']['passed'] == 24 and local['B5']['reachable'] == 360 and local['B5']['orders'] == 1413
assert local['cross_check']['zero_content_difference']
assert local['needcard_preflight']['statuses']['ready'] == 20
assert read(root/state_rel) == read(scratch/'STATE_BEFORE.json')
before = read(scratch/'PROTECTED_BOUNDARIES_BEFORE.json')
for branch, expected in before['refs'].items():
    assert git('ls-remote','origin','refs/heads/'+branch).split()[0] == expected
old = read(scratch/'HISTORICAL_OUTPUTS_BEFORE.json')
for f in old: assert sha(root/f['path']) == f['sha256']
diff = git('diff','--name-status',base,head,'--','project/outputs/pm_rl1/v3').splitlines()
assert all(line.startswith('A\t') for line in diff)
freeze = read(root/'project/outputs/pm_rl1/v3/integration_c0_freeze_20261117/C0_FREEZE_MANIFEST.json')
for f in freeze['shared_files']: assert sha(root/f['path']) == f['sha256']
out.mkdir(parents=True, exist_ok=False)

# No caches or pytest fixtures enter the evidence package. All source reports
# are copied byte-for-byte, including the failed invocation and its correction.
for p in scratch.iterdir():
    if p.is_file() and p.suffix in ('.json','.py'): shutil.copy2(p,out/p.name)
shutil.copytree(scratch/'code_ci',out/'code_ci')
for name in ('v3','cpu','guards','guards_retry','real'):
    shutil.copytree(scratch/'validation'/name,out/'validation'/name)
shutil.copy2(scratch/'validation/VALIDATION_RESULTS.json',out/'validation/VALIDATION_RESULTS.json')
shutil.copytree(Path('/opt/tokkio-data0/tokkio_projects/pmrl1-validation/wsb-sync-b591-20261118-delivery'),out/'wsb_sync_review')
audit = read(scratch/'PR8_PREMERGE_AUDIT.json')
put(out/'HISTORICAL_PRESERVATION.json',dict(code_sha=head,checked=len(old),all_unchanged=True,
    existing_output_modifications_since_base=0,shared_files_unchanged=len(freeze['shared_files']),
    main_and_plan_refs_unchanged=True,H0_and_adoption_unchanged=True))

state = read(root/state_rel)
report = str(rel/'RESULTS_ZH.md')
manifest = str(rel/'MANIFEST.json')
for name in ('A1','A1b','B5'):
    state['tasks'][name].update(status='completed',commit=head,results_doc=report,
        acceptance_manifest=manifest,evidence_tier='engineering_only')
state['tasks']['A1']['integration_note'] = ('PR #8/#9 已合入且在真实 integration 16644abb 完成验收；'
    '1276 来源（401 历史会话、875 ESConv train），401/4119 来源内容与前缀 cross_check 零差异；'
    'esc1198 多 owner family 保留，84 重叠 family 在 RS 侧隔离。preparation 是历史审计记录。')
state['tasks']['A1']['source_version'] = audit['source_version']
state['tasks']['A1b']['integration_note'] = ('真实 bank 3188（MP387/ME1525/MS401/RS875），324 MP 隔离、'
    '2 MP 转 ME、1 ME 修复映射保留；真实四头读取、原生 token 计费与 A 端口 B5 回放正式通过。'
    '3185 unverified + 3 development_reviewed；目录不是 A4 正式方法卡，未声称召回/回复收益。')
state['tasks']['A1b'].update(bank_version=audit['bank_version'],index_version=audit['index_version'],
    read_port='pmrl1v3-a1b-read-port-v1')
state['tasks']['B5']['integration_note'] = ('有限域/C0 绑定、DP 和真实 A bank 回放正式通过；24 前缀，'
    '21×16+3×8 可达子集，360 终点、1413 顺序；24 容量压力及失败不推进状态通过。'
    'STOP 真实终点仍 pending，未生成回复/奖励；不等于 B6e 终点表完成。')
for name, note in {
    'B1':'writer v2、分层输入与20/20 CPU预检已集成；真实 NeedCard 未生成，仍未 completed。GPU/模型调用须另行授权。',
    'B2':'检查表/判官/奖励/评价 v2 协议和代码已集成；真实检查表及 J1/J2 验收未完成，仍未 completed。'
}.items():
    state['tasks'][name].update(status='in_progress',commit=head,results_doc=report,integration_note=note)
assert state['tasks']['A0']['status'] == 'in_progress'
assert state['tasks']['B6e']['status'] == state['tasks']['B8e']['status'] == 'pending'
assert state['tasks']['C0']['status'] == state['tasks']['B0']['status'] == 'completed'
assert state['adopted_by_researcher'] is False and state['g0_identity'] is None
assert state['human_touchpoints'] == read(scratch/'STATE_BEFORE.json')['human_touchpoints']
state['integration_s2_acceptance'] = dict(tested_integration_sha=head,results_doc=report,
    manifest=manifest,github_push_ci=run['html_url'],github_push_ci_status='success',
    code_acceptance_complete=True,all_S1_tasks_complete=False,
    record_commit_ci_rule='状态/报告提交自身 HEAD 的 push CI 仍须核对；最终凭据随 PR 交接评论和最终报告交付。')
with (root/state_rel).open('w') as f:
    json.dump(state,f,ensure_ascii=False,indent=2); f.write('\n')
put(out/'STATE_AFTER.json',state)
changes={k:dict(before=read(scratch/'STATE_BEFORE.json')['tasks'][k]['status'],after=v['status'])
         for k,v in state['tasks'].items() if v['status'] != read(scratch/'STATE_BEFORE.json')['tasks'][k]['status']}
put(out/'STATE_TRANSITIONS.json',dict(code_sha=head,changes=changes,ci=run['html_url']))

cpu=local['cpu_counts']; remote=ci['pytest-results.xml']
local_deselected = int(re.findall(r'(\d+) deselected', (scratch/'validation/cpu/pytest.log').read_text())[-1])
ci_deselected = int(re.findall(r'(\d+) deselected', (scratch/'code_ci/job.log').read_text())[-1])
text=f'''A1、A1b 与 B5 已在真实 integration 提交 `{head}` 验收通过。本记录只确认工程能力；B1/B2 的真实模型与判官任务仍未完成，S1 没有整体完成。

| 集成事件 | SHA / 证据 |
|---|---|
| 起始 integration | `{base}` |
| PR #8，审阅 HEAD ca4db1a3 | merge `b591863e4439014872dd076c72b20b99983a52e4` |
| PR #9，同步 HEAD 59607355 | merge `{head}` |
| 两项合入后的实际 push CI | [run {run['id']}]({run['html_url']})，success；integration-base 实际执行成功 |
| C0 | pmrl1v3-contracts-0.2.0 / pmrl1v3-json-1，34 个共享文件（含32 Schema）与原冻结 SHA 一致 |

PR #8 已先行合入，B 在原工作分支普通 merge integration，PR #9 改 base 并转为 ready 后合入。B 同步后的差异仅 46 个 B-owned 文件，无 A 文件重复引入。两个 PR 的最新 HEAD CI 均通过。PR #7 未重复处理；main、PR #4、H0、研究者采用状态和旧失败/原始输出均未改动。

| 真实 integration 验收 | 结果 |
|---|---|
| 本地严格 V3 + verify_v3_junit | 466 passed，0 fail/error/skip/xfail |
| 本地完整 Paper-1/RL1/V3 CPU | {cpu['passed']} passed，{len(cpu['skipped'])} 历史 skip；{local_deselected} GPU 测试排除 |
| 实际 push CI 严格 V3 | 466 passed，0 fail/error/skip/xfail；与本地测试身份集合一致 |
| 实际 push CI 完整 CPU | {remote['passed']} passed，{remote['skipped']} 历史 skip；0 fail/xfail，{ci_deselected} GPU 测试排除 |
| GPU 隔离保护 | 单项通过 |
| Schema / integration-base | 32 份一致；本地及 CI integration-base 通过 |
| B5_real_replay_v2.py --port a | 24/24；21 个前缀有16子集、3个有8子集；360终点、1413合法读取顺序 |
| B1_A1_cross_check.py | 401会话、4119前缀，内容/前缀/覆盖差异均为0 |
| B1_needcard_cpu_preflight.py | 20/20 ready；3739–27009 token；0截断、0 writer调用 |

B5 读取身份、正文、token、可达性与此前 173bed 报告完全一致；两次独立磁盘加载和24/24容量压力、失败不推进状态均通过。21条 `ready_at == cutoff` 边界合法。24个覆盖前缀的合法性检查未发现未来、跨 owner、跨 family 的违规读取；非法/超容量请求被拒绝且不推进状态。全部真实 STOP 终点仍为 pending，未填零。来源适配器的 license/provenance/URI/split 各401处元数据标注差异按设计单独记录，内容零差异；85条 ESConv 派生个人会话对应84个重叠 family，含 esc1198 多 owner。

本地/CI 的历史 skip 逐项保存在 `validation/VALIDATION_RESULTS.json` 与 `code_ci/ATTESTATION.json`。CI 缺本地研究输入、旧 tokenizer、rg 和 sentence_transformers；这些跳过不计作完整覆盖。完整 CPU 范围已运行，不等于所有历史环境分支都被覆盖。

首次 Schema 命令从 project 工作目录运行且未给 --out，产生 FileNotFoundError。集成负责人修正的是验收包装器的调用路径：显式指向现有32份 Schema，检查通过；未改共享代码、Schema 或测试。原始失败日志、命令收据和 v1/v2 包装器均保留（`HARNESS_INVOCATION_FAILURE.json`、`validation/guards/`、`validation/guards_retry/`）。除此之外，无代码测试、CI或真实跨线验收失败，未 skip/xfail 绕过。

| 已集成资源 | 实际数量 / 状态 |
|---|---|
| 来源 registry | 1276：401 MS-RAW 会话 + 875合法 ESConv train 来源 |
| bank-v0 | 3188：MP387、ME1525、MS401、RS875 |
| 质量状态 | 3185 unverified，3 development_reviewed；非研究级事实认证 |
| MP/ME 迁移 | 713 MP / 1523 ME逐条映射保留；324 MP隔离、2 MP转ME、1 ME修复 |
| RS-v0类别目录 | 8类、7类可选；unknown/unverified，875案例映射，不是A4正式方法卡 |

source/bank/index 在合入前内存重建身份一致；未重复生成或覆盖旧资产。完整输入哈希见 INPUT_MANIFEST，读取接口可直接使用 `bank.v0_port.make_port_factory(root=repo)`；返回 PrefixPort 使用 `read(head, acquired=...)`，actual token before/after 和 TerminalKey/ExecutionTrace 由回放绑定。本轮未执行 A5，GET 成功或工程回放通过不能证明检索准确率或回复收益。

| 正式任务状态 | 当前结论与后续依赖 |
|---|---|
| C0 / B0 | 保持 completed；原冻结记录不变 |
| A1 / A1b / B5 | completed，绑定本次真实 integration 验收 |
| A0 | in_progress；CPU准备可继续，GPU吞吐/显存/时间仍缺，另行授权后才能实测 |
| B1 | in_progress；A1b来源与目录依赖已满足，可做CPU准备；真实NeedCard生成需另行GPU/模型授权 |
| B2 | in_progress；v2代码/协议已合入，仍待真实B1需求卡、检查表及判官验收；未放行模型或付费调用 |
| B6e / B8e | pending；B6e仍待A0、B2与完整G0/终点输入身份，B8e依赖真实B6e；不得用pending STOP填表 |

本次 GPU、模型推理、Generator、Judge、实验训练、付费调用均为0；仅CPU回归（含既有测试fixture）和原生 tokenizer 计数。G0仍未冻结，g0_identity/scale_tier/lambda_main未自行设置。

本报告绑定已验收的代码合并 SHA；随后状态与报告记录提交还须检查其自身 HEAD 的 push CI。该最终 HEAD/CI 凭据通过本轮 PR 交接评论与最终汇报提供，避免将中间提交的成功冒称最终 HEAD 成功。
'''
(out/'RESULTS_ZH.md').write_text(text)
files=[]
for p in sorted(out.rglob('*')):
    if p.is_file():files.append(dict(path=str(p.relative_to(root)),bytes=p.stat().st_size,sha256=sha(p)))
files.append(dict(path=str(state_rel),bytes=(root/state_rel).stat().st_size,sha256=sha(root/state_rel)))
put(out/'MANIFEST.json',dict(protocol='pmrl1v3-integration-a1-a1b-b-s2-v1',status='accepted',
    recorded_at_utc=datetime.now(timezone.utc).isoformat(),tested_integration_sha=head,
    merges={'8':read(scratch/'MERGE8.json'),'9':read(scratch/'MERGE9.json')},
    github_push_ci=run['html_url'],contract_version=freeze['contract_version'],
    canonical_json_version=freeze['canonical_json_version'],shared_identity_sha256=freeze['shared_identity_sha256'],
    source_version=audit['source_version'],bank_version=audit['bank_version'],index_version=audit['index_version'],
    output_hash_scope='all package files except this manifest itself; global state after acceptance',
    inputs_manifest=str(rel/'INPUT_MANIFEST.json'),files=files,model_calls=0,gpu_used=False,paid_calls=0,
    terminal_outcomes='pending',evidence_tier='engineering_only',state_changes=changes,
    final_metadata_head_ci='must be verified separately after committing this record'))
print('ACCEPTANCE_PUBLISHED',head,len(files),'hashed outputs')
