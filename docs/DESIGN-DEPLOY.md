# 三合一部署设计：QQBotStack

> **一句话**：把 AstrBot（bot 大脑）、NapCat（QQ 协议端）、workbuddy2api（模型网关）
> 在目标机上整合成一套可运维的栈 —— 可行性、架构、改动清单、风险与待确认项。

- 日期：2026-10-26
- 状态：**待确认**（未动目标机、未建仓、未传数据）
- 目标机：局域网 Windows 主机（地址与账户见不入库的 `.work/`，下文记 `<HOST>`）
- 部署位置：`<HOST>:F:\Tools\AITool\QQBotStack`

---

## 一、结论

**可行。** 三块组件的版本、运行平台、许可证、默认端口都已核实；目标机环境满足要求。
但有三个前提必须你拍板，否则做完也会出问题：

1. **启动器是 GUI/托盘程序**，只有你登录桌面后才跑 —— 要不要接受（§八.1）；
2. **账号池归属**：同一批 WorkBuddy 账号不能两台机器同时跑（§八.3）；
3. **QQ 登录必须扫码一次**，需要你在目标机屏幕前（§八.4）。

---

## 二、踩点结果

### 2.1 三块组件

| 组件 | 版本 | 运行平台 | 许可 | 作用 | 端口 |
|---|---|---|---|---|---|
| AstrBot | v4.29.3 | Python | **AGPL-3.0** | bot 大脑：LLM 对话、插件、平台适配 | WebUI 6185；OneBot 反向 WS 6199 |
| astrbot-launcher | 0.3.13 | Rust / Tauri（GUI） | MIT | 隔离安装、多实例管理、托盘驻留 | — |
| NapCatQQ | 4.18.41 | TypeScript（跑在 QQ NT 之上） | **自定义**（限再分发、非商业） | QQ 协议端，对外提供 OneBot 11 | WebUI 6099 |
| workbuddy2api | 本地已构建 `wb2api.exe`（13.8 MB） | Go | 见上游仓库 | WorkBuddy 账号池 → OpenAI 兼容 API | 7863 |

三个关键事实（都查过源码/文档，不是推测）：

- **NapCat 的 `NapCat.Shell.Windows.OneKey.zip` 会自动部署 QQ**。目标机目前**没装 QQ**，
  所以必须走 OneKey，不能用手动 Shell 包（那要求先自己装 QQ）。
- **AstrBot 的 aiocqhttp 适配器是「反向 WebSocket 服务端」**：默认监听 `0.0.0.0:6199`，
  NapCat 作为 WS 客户端连过来。所以 **NapCat 不需要开任何入站端口**，方向是 NapCat → AstrBot。
- **启动器的数据目录可改**（默认 `~/.astrbot_launcher`，可用 `.data-dir.json` 覆盖），
  因此可以把 AstrBot 实例也收进整合目录，不必散落在用户家目录。

### 2.2 目标机现状

| 项 | 值 |
|---|---|
| 系统 | Windows 11 专业版 Insider Preview，10.0.26340 |
| 硬件 | 8 逻辑核 / 15.9 GB 内存 |
| 磁盘 | C 剩 188 GB、**F 剩 190 GB**、K 剩 10.5 GB |
| 运行时 | Python 3.13.7、Node v24.13.1、Go 1.26.0、Git、Docker 全部就绪 |
| `F:\Tools\AITool` | **已存在**，内含 `MySillyTavern`（我们的目录与它平级） |
| QQ | **未安装**（无 `C:\Program Files\Tencent`，无 QQ 进程） |
| 目标端口 | 6099 / 6185 / 6199 / 7863 / 7871 均空闲 |

### 2.3 本地 workbuddy2api 数据

来源：`F:\Project\ZcodeAIModels\gateways\upstream\workbuddy`（已构建好 `wb2api.exe`）。

| 内容 | 大小/数量 | 说明 | 是否迁移 |
|---|---|---|---|
| `config.json` | 2.2 KB | 监听地址、api_key、签到/保活计划、超时与冷却 | ✅ |
| `auths/*.json` | **6 个账号** | 每个含 account 元信息 + accessToken | ✅ |
| `data/state.json` | 8.2 KB | 账号运行状态 | ✅（可重建） |
| `data/usage.json` | 74 KB | 用量统计 | ✅（可重建） |
| `data/request-logs/` | — | 请求归档，保留 7 天 | ❌ 不迁，历史日志无意义 |
| `.git` | ~35 MB | 上游仓库 | ❌ 不迁 |

**zgate 不迁**：`zgate.json` 依赖 `~/.zcode/v2/provider_config.json` 与
`model-alias-map.json`（本机 ZCode 的配置），目标机没有 ZCode。搬它等于顺带搬一套 ZCode
配置，收益为零 —— 因为 **`wb2api` 本身就是 OpenAI 兼容网关**，AstrBot 直接指向它即可（§八.2）。

### 2.4 模型侧实测（2026-10-26，本机现有实例）

| 项 | 结果 |
|---|---|
| `GET /v1/models` | **55 个模型**；hy3 系列三条：`cn:hy3`、`cn:hy3-x`、`global:hy3` |
| `POST /v1/chat/completions`，`model=global:hy3` | 正常返回，响应里 `model` 回显为 `hy3` |
| **hy3 是推理模型** | 响应同时带 `content` 与 `reasoning_content`；`max_tokens=16` 时 **16 个 token 全花在思考上、`content` 为空**；`max_tokens=300` 时正常返回 `"OK"` |

> **对 AstrBot 的影响**：`max_tokens` 必须给足（建议 ≥ 2048）。给太小会出现
> 「模型有响应但回复是空的」这种极难排查的现象。已记为风险项 §六。

> **注意**：本机 7863 现在**正在运行**（由本机 zgate 按需拉起）。
> 这正是 §八.3 那个「账号池冲突」风险的现实版本 —— 同一批 `auths/` 若在两台机器同时跑，
> 签到与保活任务会重复触发，token 刷新也会互相顶掉。


---

## 三、架构

```text
                         目标机 <HOST>（F:\Tools\AITool\QQBotStack\runtime\）
  ┌──────────────────────────────────────────────────────────────────────────┐
  │                                                                          │
  │   QQ 用户 ──消息──▶  NapCat (QQ NT + 协议端)                                │
  │                        │  OneBot 11 反向 WS（NapCat 主动连出）              │
  │                        ▼                                                 │
  │                    AstrBot  127.0.0.1:6199  ◀── 反向 WS 端点               │
  │                        │  OpenAI 兼容请求                                 │
  │                        ▼                                                 │
  │                    wb2api   127.0.0.1:7863/v1                             │
  │                        │                                                 │
  │                        └──▶ WorkBuddy 上游（腾讯）                          │
  │                                                                          │
  │   WebUI（全部只绑 127.0.0.1）：AstrBot 6185、NapCat 6099                    │
  └──────────────────────────────────────────────────────────────────────────┘

  运维侧（操作机）：ssh -L 6185 / -L 6099 建立隧道 → 用浏览器操作两个 WebUI
```

**为什么全部绑 127.0.0.1**：三个服务的 WebUI 都有管理权限（AstrBot 能改模型与插件、
NapCat 能收发 QQ 消息、wb2api 面板能看账号池）。绑回环 + SSH 隧道，等于复用已经加固过的
SSH 通道，不需要在目标机上再开任何入站端口。

---

## 四、改动清单

### 4.1 目标机（全部在 `F:\Tools\AITool\QQBotStack\` 之内）

```text
QQBotStack\
├── README.md / AGENTS.md / docs/ / tools/    ← 仓库内容（入库）
└── runtime\                                  ← 运行时（.gitignore 排除）
    ├── workbuddy\        wb2api.exe + config.json + auths\ + data\
    ├── napcat\           OneKey 安装的 QQ + NapCat
    └── astrbot\          启动器数据目录（实例、Python 运行时、AstrBot 源码与 data）
```

| 改动 | 具体 |
|---|---|
| 新建目录 | `F:\Tools\AITool\QQBotStack\`（与既有 `MySillyTavern` 平级） |
| 传文件 | `wb2api.exe`、`config.json`、`auths/`、`data/state.json`、`data/usage.json` |
| 安装 | NapCat OneKey（自动装 QQ）；AstrBot Launcher |
| 服务/自启 | wb2api 与 NapCat 需要开机自启；AstrBot 由启动器托管 |
| 防火墙 | **不改** —— 三个服务都只绑回环，不需要入站规则 |

### 4.2 本机

| 改动 | 具体 |
|---|---|
| 建仓 | `F:\Project\QQBotStack`（GSAuxiliary 骨架 + docs 四分类） |
| 停用旧网关 | 若确认「迁走」，把本机 `zgate.json` 里 `children.workbuddy` 停用（§八.3） |
| 运维脚本 | `tools/deploy-*.ps1` / `tools/verify-stack.py`（可重复执行，幂等） |

### 4.3 仓库里放什么、不放什么

| 放 | 不放 |
|---|---|
| 部署脚本、验证脚本、配置**模板**（占位符） | `auths/*.json`（含 accessToken） |
| 架构/工具/踩坑/排错文档 | `config.json` 里的真实 `api_key` |
| 端口与目录约定 | NapCat / AstrBot 的二进制或源码（许可证不允许再分发） |

> **许可证约束**：NapCat 是「限再分发 + 非商业」自定义许可，AstrBot 是 AGPL-3.0。
> 本仓**不分发**它们的任何代码或二进制，只在部署脚本里从官方 Release 下载。
> NOTICE 要写清这一点。

---

## 五、实现方案

分六步，每步都有可验证的产出，失败即停：

1. **建仓** —— `F:\Project\QQBotStack`，GSAuxiliary 门面 + docs 四分类 + `.gitignore`
   （排除 `runtime/`、`auths/`、`*.log`、`.work/`）。跑 `check-docs.py` / `check-secrets.py`。
2. **铺运行时目录并迁数据** —— 目标机建 `runtime\workbuddy`，scp 传 `wb2api.exe` + 数据；
   先跑 `wb2api.exe -config config.json` 验证 `/v1/models` 能列出 `global:hy3`。
3. **装 NapCat** —— OneKey 装 QQ + NapCat，启动，扫码登录，WebUI 里加一条
   **WebSocket 客户端**指向 `ws://127.0.0.1:6199/ws`（带 token）。
4. **装 AstrBot** —— 装 Launcher，数据目录指向 `runtime\astrbot`，建一个实例并启动。
5. **配置 AstrBot** —— 通过 SSH 隧道打开 6185：
   - 服务提供商：OpenAI 兼容，`base_url=http://127.0.0.1:7863/v1`，
     `api_key` 取 `config.json` 里的值，模型 `global:hy3`；
   - **`max_tokens` 设 ≥ 2048** —— hy3 是推理模型，预算太小会把 token 全花在思考上，
     正文返回空（§2.4）；
   - 平台适配：aiocqhttp，`ws_reverse_host=127.0.0.1`、`port=6199`、token 与 NapCat 一致。
6. **端到端验收 + 自启** —— 见 §七；然后配开机自启（wb2api / NapCat / Launcher）。

---

## 六、风险与回退

| 风险 | 说明 | 对策 |
|---|---|---|
| **账号池冲突**（高） | 两台机器跑同一批 6 个账号：签到（9/21 点）、保活（22 点）会重复触发，token 刷新可能互相顶掉 | **迁走并停用本机的**（§八.3 推荐） |
| **依赖桌面会话**（中） | Launcher 是托盘程序，注销/未登录时不跑；重启后要等登录才恢复 | 开自动登录；或改无 GUI 服务化（§八.1 备选） |
| **QQ 新设备风控**（中） | 新机器登录可能触发验证、甚至临时冻结 | 扫码时人在场，按提示验证；必要时用手机 QQ 辅助确认 |
| **登录态过期**（中） | NapCat 的 QQ 登录会掉线，需要重新扫码 | 保留 NapCat WebUI 的访问路径（隧道），掉线时远程也能看状态 |
| **端口冲突**（低） | 6099/6185/6199/7863 已确认空闲 | 部署前再确认一次 |
| **推理模型空回复**（中） | hy3 是推理模型，`max_tokens` 给小了会「有响应但正文为空」，看着像模型坏了 | AstrBot 侧 `max_tokens ≥ 2048`；排错时先看响应的 `reasoning_tokens` 占了多少（§2.4） |
| **磁盘增长**（低） | wb2api 请求归档最多 100 MB、AstrBot 日志与插件 | 配置保留天数；`docs/MAINTENANCE` 写清理口径 |
| **许可证**（低但必须守） | NapCat 不允许公开再分发修改版 | 仓库只放脚本与文档，二进制从官方下载 |

**回退**：三步即可完全撤除 ——
① 停 Launcher 实例与 NapCat、`taskkill /IM wb2api.exe /F`；
② 删 `F:\Tools\AITool\QQBotStack\runtime`；
③ 本机 `zgate.json` 恢复 `children.workbuddy` 的原策略。
QQ 与 Launcher 是独立安装的，如需彻底清理由「应用和功能」卸载。

---

## 七、验收

| # | 验收项 | 判定 |
|---|---|---|
| 1 | `curl http://127.0.0.1:7863/v1/models` | 返回列表含 `global:hy3`（或 `cn:hy3`） |
| 2 | `curl http://127.0.0.1:7863/v1/chat/completions` 直发一条 | 正常返回，且 wb2api 面板显示用量 +1 |
| 3 | AstrBot WebUI 里对 `global:hy3` 做一次「测试」 | 返回模型回复，不是 4xx/5xx |
| 4 | AstrBot 平台页显示 aiocqhttp 已连接 | NapCat 侧 WS 客户端状态为已连接 |
| 5 | QQ 里给 bot 发一条私聊 | 不回复（`private_reply_enabled` 默认 false） |
| 6 | 在允许群 @ 一次 bot | 收到模型回复 |
| 7 | 重启目标机并登录桌面 | 三块自动恢复，第 5、6 项复验通过 |

---

## 八、需要你确认的选项

### 1. 启动器的运行模型（推荐：接受）

| 选项 | 说明 |
|---|---|
| **A. 用 Launcher（推荐）** | 你指定的方案。它负责 Python 运行时隔离与依赖安装，省掉手工配环境；代价是**托盘程序，需要登录桌面才跑**。配套建议开「自动登录」，这样重启后无需人工介入。 |
| B. 无 GUI 服务化 | 用 uv 装 AstrBot，用 WinSW 包成 Windows 服务，开机即跑、不依赖登录。更稳，但偏离你指定的 launcher，且以后升级要手工做。 |

### 2. 网关选型（推荐：wb2api 直连）

| 选项 | 说明 |
|---|---|
| **A. wb2api 直连（推荐）** | `wb2api` 本身就是 OpenAI 兼容网关，AstrBot 直接指向 `127.0.0.1:7863/v1`。零额外组件。 |
| B. 搬 zgate | 能拿到 alias 映射与按需拉起子进程，但依赖本机 ZCode 的 `provider_config.json`，目标机得一并迁 ZCode 配置。为一个 bot 接一个模型，不值得。 |

### 3. 账号池归属（推荐：迁走并停用本机）

| 选项 | 说明 |
|---|---|
| **A. 迁走，本机停用 workbuddy 子进程（推荐）** | 6 个账号只在目标机跑。本机 zgate 的 `children.workbuddy` 改为不启用，避免签到/保活重复触发与 token 互顶。本机 ZCode 若还需要 WorkBuddy 模型，改为指向目标机的 7863（需要把监听改成局域网，另议）。 |
| B. 两台同时跑 | **不建议** —— 同一批账号双跑会互相顶掉登录态，签到任务也会重复。 |
| C. 只迁一部分账号 | 可行：目标机只放用于 bot 的账号，其余留本机。需要你指定哪些。 |

### 4. QQ 账号与登录（必须你参与）

- 需要你提供**要挂的 QQ 号**（或者你到机器前扫码时临时决定，不用告诉我）；
- 扫码登录必须**在目标机屏幕前**完成一次；
- 建议用**小号**而不是主号 —— 协议端登录有风控风险。

### 5. 仓库远端（推荐：先本地，确认后再建）

本地先建 `F:\Project\QQBotStack` 并跑自检；是否建 GitHub 仓、什么时候推，等你说。
按系列惯例，建仓要补 Issue 表单 + CONTRIBUTING + SECURITY。

---

## 九、命名

整合目录定为 **`QQBotStack`**（`F:\Tools\AITool\QQBotStack`）。
理由：系列仓用 PascalCase + 平台/职能（`OpenwrtOpsToolkit`、`WindowsRemoteOps`），
`QQBotStack` 一眼看出是「QQ bot 的一套组件栈」，且不绑定其中某一个上游项目
（叫 `AstrBotStack` 会盖住 NapCat，叫 `QQBot` 又太泛）。
