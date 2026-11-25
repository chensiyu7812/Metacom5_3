# 独立运行申请：优先表示、复杂方法与Writer

本轮批准的18次已完成。以下均为新身份、当前未授权，旧A0、20次冒烟和18次批准不能转用。建议优先分别批准M1、R1、W1：合计42次物理调用、3次加载、总硬上界3600秒；不自动执行其他批次。

所有申请使用原指定 `GPU-ba5f65be-ecfa-7fda-b239-af9efd468db4`、原本地 Gemma-4-12B-it `707f0a3…`、冻结decode与320输出上限。每个独立作业1次加载、0 warmup、0重试、1200秒总硬限，加载600秒、单请求300秒；设备占用不加载、不换GPU、不干预其他项目，保留原停止规则。每个计划均已完成CPU准入检查及完整配对检查。

| 身份 | 完整配对 | 物理调用 | 输入tokens | 保守情景秒 | 当前状态 |
|---|---|---:|---:|---:|---|
| M1 | 表示6题×3臂 | 18 | 14,720 | 1039 | 待独立批准 |
| M2 | 其余表示6题×3臂 | 18 | 18,782 | 1039 | 待独立批准 |
| R1 | 复杂RS3题×6臂 | 16（复用2） | 8,597 | 约939* | 待独立批准 |
| R2 | 复杂RS3题×6臂 | 18 | 9,021 | 约1039* | 待独立批准 |
| R3 | 复杂RS3题×6臂 | 17（复用1） | 8,618 | 约989* | 待独立批准 |
| R4 | 复杂RS3题×6臂 | 17（复用1） | 9,896 | 约989* | 待独立批准 |
| W1 | source-only Writer8 | 8 | 6,637 | 536 | 待独立批准 |
| U1 | source-only MP/ME两个序列×3条件 | 6 | 7,928 | 435 | 后续小规模候选 |

情景由已完成20次冒烟的实际固定开销与生成分量，按输入／输出上限较大比例放大并再乘2得到；它不是拟合吞吐或完成保证。星号项按相同公式列出，仍以各PLAN中的1200秒硬限为准。全部八个作业若逐一获批，上界118次／8次加载／9600秒，这不是本次建议的一揽子自动授权。

M1：

- 计划对象 SHA256：`670f8d08a864b8dde6ca685ae93e42167aef01e551a98ce79ef95a664f89ee6c`
- 请求文件 SHA256：`e9c654a87c3a61d7445e864f3789ecacc2d1fbcafead847c9654151ecc865de3`
- 私有计划：`memory_packages/final-v2/representation-batch-1/PLAN.json`

M2：

- 计划对象 SHA256：`c435369a25f668f459b37f461187fa8689aa61ad0935fb908b034195d39ca37f`
- 请求文件 SHA256：`5e55e84744620245ed7d6630ba297adbc4aad92eceeefe37d7d92e81071ee172`
- 私有计划：`memory_packages/final-v2/representation-batch-2/PLAN.json`

R1（活跃审查版package-v2，保留旧v1）：

- 计划对象 SHA256：`4ff17d9e71f5c6977e74c1477970b61c99d0c8d9105021b33c2009389c1cdd51`
- 请求文件 SHA256：`7df65c8f22be32a160f81b87d95e84cf8e1a0f95e0c09bd9abd5d2dc86edf1a2`
- 私有计划：`rs_complex/package-v2/batch-01/PLAN.json`

R2／R3／R4计划对象：

- `c3f71c59595164c1f4d063d261f5b11cec58f132de553a96b03d553a3435c532`
- `a5fbb93eb41d9aebfaa43449f37a0569ec0c1f518b2d94ea2a7b56bf8f63685a`
- `9437bbc23a0652d6689fe001ffadf72017d9dfd55318e4b3af28912a0cf39af9`

对应完整请求hash见 [八个计划身份清单](capability_results_v1/RUN_REQUEST_IDENTITIES.json)，配对及成本见 [RS复杂包](capability_results_v1/RS_COMPLEX_PACKAGE.json) 与各私有PLAN。DP与RET的相同payload只执行一次，不能算独立重复。

W1：

- 计划对象 SHA256：`4c602927c8f04494eee7498a1bcd85e8f1fff35f342617185b55772dce8507e6`
- 请求文件 SHA256：`44ee6b73407b6aaf49e8438e276f053d4973dc1151051645bb43777b6fc7a1c6`
- 私有计划：`memory_packages/final-v2/writer8/PLAN.json`

U1：

- 计划对象 SHA256：`0317dd13d7ed7b08d5302b7c4a7b52293f6ec60e1cdcd0ddcc6a59776a3f6b9b`
- 请求文件 SHA256：`2e39bc8901dcbc008ec7598f6ed54303db63f18cb850652736314323d54d135b`
- 私有计划：`memory_packages/final-v2/mpme6/PLAN.json`

私有根目录为 `/opt/tokkio-data0/tokkio_runs/pmrl1-j-capability-20261125`。上述hash均为计划对象hash，不能与PLAN文件hash混用。执行器快照、代码与源文件清单已绑定；不同运行目录需独立授权文件，不得复用原已执行请求。所有原冻结请求和失败记录保留。
