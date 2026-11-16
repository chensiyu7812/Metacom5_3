# 四配置实际入口与复现清单

当前plan身份：`d8671e36f5ea83eb6813225553c2c9141f48d690e9cd15bd335fce1154595e8e`。同目录根部为当前唯一草案；history_two_config_20261014和four_config_build_00为保留历史，不执行。旧66次与mock严格分开。

本轮已完成：33项选型单测+23项原流程测试、160次四配置mock和2次额外故障mock、12组dry-run、帮助检查、从开发来源重建逐字一致。日志：`verification_four_config_20261015_release/verification.json`。Gemma指定py312解释器的thinking-on首4 dry-run亦通过。原9个工作文件及真实共享账本哈希未变；真实推理、付费、权重下载、封存访问均0。mock全部uncertain，不是质量或资格通过。

可复现离线检查（本轮已实际执行同样入口）：
```bash
cd /home/tokkio/Metacom5_3
/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python project/outputs/pm_rl1/judge_selection_preparation_20261014_v1/verify_offline.py --out /tmp/pmrl1_four_config_verification_NEW
```
新输出目录必须不存在。测试覆盖原生模板开关、四配置相同消息/schema、配对seed/顺序、未知/失败分母、同模型配对/四项交集、授权隔离、共享在途预留、未结费用、失败配置不阻塞其它配置、AB后CD独立范围接续、不重复调用、来源复核绑定、原140守卫。实际加载/流式网络/usage返回/吞吐/语义质量仍未验证。

## 以下仅展示，获准后才执行

命令来自本轮实际CLI帮助。使用现有环境，不安装。审批文件尚不存在，PENDING模板不是批准。确认后代理据用户消息制作范围副本，绑定本plan/config身份；本地首8限定A/B、engineering、new_calls_limit=8、cumulative_calls_limit=74；全16则16/82。旧合同140不提高。API后来补获准时，总池上限须记16/82而非重新从0计8，保留本地8次记录。

本地约24GB固定revision下载须先另获准（一次下载A/B共享），保存于拟定路径，不能换checkpoint。两模式下载后核对官方文件哈希和完整输入长度，无推理：
```bash
cd /home/tokkio/Metacom5_3/project/outputs/pm_rl1/judge_selection_preparation_20261014_v1
/opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python runtime_receipts.py local --candidate gemma4_12b_bf16 --model-dir /opt/tokkio-data0/tokkio_models/gemma-4-12B-it-707f0a3 --out gemma_A_readiness.json
/opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python runtime_receipts.py local --candidate gemma4_12b_bf16_thinking --model-dir /opt/tokkio-data0/tokkio_models/gemma-4-12B-it-707f0a3 --out gemma_B_readiness.json
/opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python selection.py run-stage --phase engineering --candidates gemma4_12b_bf16 gemma4_12b_bf16_thinking --approval approval_engineering_AB.json --execute-live
```

先将两项readiness路径分别写入审批副本local_snapshot_receipts对应的配置identity；local_model_path须为上述核验目录。GPU不空闲就阻塞，不终止别人任务。该入口最多8次，AB/BA交替，结束即停，不自动跑余下28或诊断。

若API权限先补齐，可合并全部16按完整平衡顺序运行；若AB已执行，只运行CD，不能再跑全四项重复收费。账户读取另获准后：
```bash
/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python runtime_receipts.py api --candidate deepseek_flash_off --approval approval_engineering_CD.json --out approved_API_account_readiness
/opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python selection.py run-stage --phase engineering --approval approval_engineering_ABCD.json --execute-live
```
第二条是“全部尚未执行且四项均获准”的选项；不与前面的AB实际命令顺序全执行。只有CD待跑时用：
```bash
/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python selection.py run-stage --phase engineering --candidates deepseek_flash_off deepseek_flash_high --approval approval_engineering_CD.json --execute-live
```
API审批须含具体数据权限证据、服务数据条件确认、账户余额和账外责任、无并发旧付费writer、价格/服务元数据回执及至多5美元已批准停止线。账户管理GET仅2次、0J，不发送研究内容；不会自行把余额GET等同于权限或账外对账。密钥仅在本机安全环境读取，不打印/复制到审批。

真实结果固定`live_runs/<candidate>/`，每次started/raw/response/result及范围schedule/stage_result记录不可覆盖。加载失败不计J，已开始的网络/生成失败计J。失败只停止所属配置；预算不足或权限缺失不冒充语义失败，其他已授权配置继续本阶段。没有自动重试/恢复。run-stage不接收sealed阶段，旧独立execute真实入口已退役，防止绕过配对调度。

## 分析与后续边界

```bash
/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python analyze.py --compare-pool --run-dir live_runs --out paired_analysis_NEW
```
可另传`--review completed_semantic_review_private.csv`（在模板副本填写），必须与当前raw输出哈希和合法来源引文绑定。缺字段保留pending/unknown。输出各配置逐题表、配对表、风险/重复/纯格式稳定性、token/耗时/费用覆盖，以及A/B、C/D和四项共同可比集合。没有review时不自动选胜。不要向真实分析加入--allow-mock。

后续development/diagnostics仍需对应阶段授权和前阶段完整工程回执；首阶段4次不做语义淘汰或选冠军。完整160方案需单独增补原140预算；4恢复全池共享，当前入口不派发恢复。选定一个配置后59验收另审；没有本目录可执行封存/训练入口。
