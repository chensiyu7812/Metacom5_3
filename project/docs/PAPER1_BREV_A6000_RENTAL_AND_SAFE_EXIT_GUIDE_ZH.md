# Paper 1：Brev A6000 租用、双 Codex 隔离与安全退租永久教程

适用场景：Windows + WSL 开发机临时租用 NVIDIA RTX A6000，使用 Windows VS Code Remote-SSH，完成后把 Git checkpoint 恢复到本地 RTX 2070 笔记本。

原则：GitHub 是 source of truth；Brev 磁盘是可删除的临时 compute。任何 API key、GitHub token、SSH private key、实例 IP 或 credential 都不能写入本文、仓库、日志或截图。

官方入口：[Brev CLI getting started](https://docs.nvidia.com/brev/latest/cli/getting-started)、[instance management](https://docs.nvidia.com/brev/cli/instance-management)、[connectivity](https://docs.nvidia.com/brev/cli/connectivity)、[Windows VS Code + WSL](https://docs.nvidia.com/brev/troubleshooting/ide-connectivity/vscode-windows-wsl)、[Console reference](https://docs.nvidia.com/brev/guides/console-reference)、[GPU types](https://docs.nvidia.com/brev/reference/gpu-types)。库存、region 与价格会变化，每次下单必须以 Console 当时显示为准。

## A. Windows + WSL 安装并登录 Brev CLI

先在管理员 PowerShell 确认 WSL2 已安装并更新：

```powershell
wsl --update
wsl -l -v
```

进入准备作为 SSH 客户端的 WSL distro，在 WSL shell 安装 Brev CLI：

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/brevdev/brev-cli/main/bin/install-latest.sh)"
brev --version
brev login
```

`brev login` 使用浏览器完成登录。不要把登录 token 粘进 dotfile 或仓库。若同时有多个 WSL distro，以后 VS Code wrapper 要显式使用安装了 `brev`/Cloudflare helper 的那个 distro。

## B. 在 Brev Console 租 A6000

1. 打开 Brev Console 的 GPUs / Create Instance。
2. 选择单卡 NVIDIA RTX A6000（48 GB Ampere）；核对 region、实时库存、每小时 compute、storage、image 与停止时的存储收费。
3. 使用明确、唯一的实例名，例如 `pm-paper1`；选择 Ubuntu image 与足以容纳 repo/env/cache 的磁盘。
4. Launch 前截图或在 repo 外记录订单 identity、region、GPU、disk 与价格，不记录 credential。
5. 等待实例 ready。不要把某次 provider SKU/价格硬编码成永久研究条件。

## C. 刷新并检查客户端 aliases

在 WSL 客户端运行：

```bash
brev refresh
brev list
```

`brev refresh` 更新 WSL 的 `~/.brev/ssh_config` 与连接材料；`brev list` 应显示 exact instance name 和 ready/running 状态。不要把该 SSH config、HostName、IP、User、ProxyCommand 或 key 内容复制进仓库。

## D. SSH 登录正常开发目标

```bash
ssh pm-paper1
```

也可用 `brev shell pm-paper1`。首次连接后核对身份而不暴露 secret：

```bash
hostname
pwd
nvidia-smi
```

## E. Windows VS Code Remote-SSH 使用 WSL wrapper

Windows VS Code 默认调用 Windows `ssh.exe`，而 Brev 的 Cloudflare ProxyCommand/helper 常在 WSL。这会造成普通 WSL `ssh` 可连、VS Code 却失败。按官方方法在 Windows 创建：

`C:\Users\<username>\wsl-ssh.bat`

内容：

```bat
@C:\Windows\System32\wsl.exe ssh %*
```

在 Windows VS Code `settings.json` 设置：

```json
{
  "remote.SSH.path": "C:\\Users\\<username>\\wsl-ssh.bat"
}
```

多 WSL distro 时，可把 wrapper 改为显式 `wsl.exe -d <your-distro> ssh %*`，并先在该 distro 内验证 `ssh pm-paper1`。在 VS Code 的 Remote-SSH target 中选 `pm-paper1`。

## F. 为什么连接 `pm-paper1` 而不是 `pm-paper1-host`

`pm-paper1` 是 Brev 管理的默认 instance/development target，Paper-1 repo、用户路径、Conda env 与 VS Code server 都应放在这里。Brev 的 `--host`/`*-host` 语义是 underlying VM host，面向底层运维，可能具有不同 user、path、container/runtime 边界；它不是日常 Codex/VS Code workspace。

每台客户端生成的 alias 可能不同，不能只凭后缀猜配置。需要排障时只在本地检查解析结果，不粘贴 key/IP：

```bash
ssh -G pm-paper1 >/tmp/pm-paper1.sshg
ssh -G pm-paper1-host >/tmp/pm-paper1-host.sshg
```

确认后删除临时解析文件。Paper-1 正常工作始终进入 `pm-paper1`。

## G. GitHub authentication 与 clone

优先使用浏览器授权，不在 remote URL 中嵌 token：

```bash
gh auth login --web
gh auth setup-git
gh auth status
```

然后用项目 GitHub HTTPS URL clone。本文用占位符避免把账号/credential 固化：

```bash
git clone https://github.com/<owner>/<repo>.git Metacom5_3-A
```

也可使用已配置的 SSH deploy/user key，但 private key 只能存在用户 SSH store。clone 后先 `git remote -v`、`git fetch --all --prune`、核对 remote branch 和 handoff SHA。

## H. A/B 两个 Codex 必须隔离

最强隔离方式是两次独立 clone：

```bash
git clone https://github.com/<owner>/<repo>.git Metacom5_3-A
git clone https://github.com/<owner>/<repo>.git Metacom5_3-B
```

- Codex A 只写 `Metacom5_3-A` 及 A integration branch。
- Codex B 只写 `Metacom5_3-B` 及 B memory branch。
- 两个 Codex 绝不能共享同一个 working tree/checkout，也不能同时切换同一目录的 branch。
- linked worktree 是次选：它提供独立工作目录但共享 object database；使用时必须记录真实路径、branch、base SHA，且各自只写 owned paths。
- merge/cherry-pick 只由 A 在审计后执行；不要为了“工作区干净”提交 cache/secret/weights，也不要为了退租盲目合并。

## I. 恢复 Paper-1 environment

先读根 `AGENTS.md` 及全部 active authority。然后在 repo 的 `project` 目录按 tracked bootstrap 恢复：

```bash
cd Metacom5_3-A/project
bash scripts/paper1/10_create_paper1_environment.sh
conda activate metacom-paper1-py311
python --version
python -m pip check
nvidia-smi
python -c "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NO_GPU')"
```

环境创建脚本与 lock 是 source of truth，不迁移整个 Conda 目录。运行 `scripts/paper1/10_attest_paper1_environment.py` 可能需要尚未在 cache 的公开模型；只有当前任务允许下载且 exact revision 已冻结时才运行下载相关 attestation。

B checkout 测试时避免 A 的 editable install 污染：

```bash
cd /absolute/path/to/Metacom5_3-B/project
PYTHONPATH=src python -m pytest -q tests/test_paper1_*.py
```

## J. 每日与每阶段 push protocol

每个独立 checkout 执行：

```bash
git status --short --untracked-files=all
git diff --check
git diff

cd project
PYTHONPATH=src python -m pytest -q tests/test_paper1_*.py
PYTHONPATH=src python scripts/paper1/00_validate_integration_base.py
cd ..

git add -- <explicit-file-1> <explicit-file-2>
git diff --cached --name-only
git diff --cached --check
git commit -m "<scoped message>"
git push -u origin <exact-branch>

git rev-parse HEAD
git ls-remote origin refs/heads/<exact-branch>
```

要求本地 HEAD 与 remote SHA 完全相同。长期任务每天结束、每个可独立审计阶段完成、任何付费/不可重复步骤开始前后都 push。不要使用宽泛 `git add .`；不要 force-push 研究 provenance branch。

## K. 退租前 Git / secrets / artifact audit

A、B 两边分别执行并保存不含秘密的结论：

```bash
git status --short --untracked-files=all
git stash list
git log --oneline --branches --not --remotes
git diff --cached --name-only
git rev-parse --abbrev-ref HEAD
git rev-parse HEAD
git ls-remote origin refs/heads/<exact-branch>
```

再做不打印 value 的审计：

- staged/未跟踪文件名不得含 `.env`、`secret`、private key、credential；
- staged 文件不得是 `.safetensors/.gguf/.pt/.pth/.onnx/.ckpt` 或 provider model weights；
- 搜索 repository 中是否出现 key-shaped literal，只报告 match count/path，不把 value 打到终端或聊天；环境变量名称本身不是 secret；
- 核对 ignored files、repo 外 outputs、API caches/ledgers：有研究价值且不可重建者必须先 sanitize、commit/push；普通 model/pip/uv/pytest/VS Code cache 可丢；
- `project/outputs` 可能含 tracked research artifacts，绝不能按目录名整体删除；
- 检查所有 local branches/stashes，不只检查当前 `git status`；
- 运行适用 tests、validator、`git diff --check`，确认 `outcome_calls=0` 和 lock 关闭。

绝不把 secret source file、shell history、Git credential store 或 SSH config 打包进 handoff。

## L. Safe delete

只有以下全部为真才删除：

1. handoff/amendment/guide 已 commit + push；
2. A/B local HEAD == exact remote branch SHA；
3. 无 stash、local-only commit、未推送 branch 或不可重建的研究 artifact；
4. 无 secret/env/weight staged；
5. Console 与 `brev list` 均确认要删除的 exact name 是 `pm-paper1`。

删除是永久且不可逆的。由人类在本地 WSL 运行精确名字，永不使用 `--all`：

```bash
brev delete pm-paper1
```

如果 CLI 要求确认，逐字核对实例名。`brev stop` 只停止 compute，storage 仍可能计费；它不等于删除。

## M. 删除后证明实例不存在

```bash
brev refresh
brev list
ssh pm-paper1
```

验收条件：list 中不再出现该 instance，SSH 失败；同时在 Brev Console GPUs/Instances 页面确认不存在，并在 Billing/Usage 确认没有继续产生 compute/storage。只看到 “stopped” 不算删除。客户端可能保留 stale alias，所以 `brev refresh` 后仍需以 list + Console + billing 三者为准。

## N. 迁回本地 WSL + RTX 2070

1. Windows 更新 NVIDIA driver，执行 `wsl --update`；按 [CUDA on WSL guide](https://docs.nvidia.com/cuda/wsl-user-guide/index.html) 操作，不要在 WSL 内安装 Linux NVIDIA display driver。
2. 在 WSL 运行 `nvidia-smi` 与 `wsl.exe -l -v`（后者从 PowerShell）核对实际 RTX 2070 VRAM、driver、distro；不要假设与 A6000 相同。
3. 用两次独立 clone/fetch 恢复 A/B，checkout handoff 中 exact remote branches，验证 local==remote。
4. 从 tracked bootstrap/lock 重建 `metacom-paper1-py311`，先运行 torch probe、tests、integration validator。
5. RTX 2070 显存明显小于 A6000：只运行当前显存允许的本地测试/embedding batch，降低 batch 是工程参数时必须记录；不要未经 authority 改模型、ontology、feature 或 claim。
6. Generator 仍是 hosted NVIDIA NIM `meta/llama-3.1-8b-instruct`，不在 RTX 2070 本地加载。Semantic Compiler 仍是获批的 Alibaba API Qwen；只有得到重新开始 paid call 的明确许可后才 source 本地 secret 并运行。
7. tokenizer/BGE snapshots 和普通 cache 按冻结 revision/hash按需重取；不要依赖 Brev 磁盘副本，不要在未冻结 exact identity 时自动下载。

恢复完成的第一条研究命令仍不是 formal outcome，而是读 authority、验证 Git SHA/environment、重建 zero-outcome implementation checkpoint。
