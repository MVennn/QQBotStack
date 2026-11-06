# 安全策略

> **一句话**：发现安全问题怎么报、**这套栈会改目标机的哪些状态**、账号风险与边界。

## 支持的版本

| 分支 | 收修 |
|---|---|
| `main` | ✅ 修 bug 与安全问题 |

## 怎么报告

**请不要开公开 Issue 报告安全问题。** 用 GitHub 的
「Security → Report a vulnerability」提私有报告：
<https://github.com/MVennn/QQBotStack/security/advisories/new>

报告里请写清：受影响的文件 / 触发条件 / 影响面（谁能做什么）/ 你建议的修法。

## 这套栈会改你的机器

| 操作 | 会改什么 | 触发方式 |
| --- | --- | --- |
| `tools/deploy-stack.ps1 -Stage gateway` | 建 `runtime/workbuddy`、落 `wb2api.exe` 与配置、建计划任务 `QQBotStack-wb2api`（SYSTEM，开机启动） | 手动 |
| `-Stage napcat` | 解包 NapCat 一键包；**运行安装器会装 QQ NT 到系统** | 手动（安装器需交互） |
| `-Stage astrbot` | 静默安装 AstrBot Launcher；写 `%APPDATA%\com.github.raven95676.astrbot-launcher\.data-dir.json` 把数据目录指到 `runtime/astrbot` | 手动 |
| `tools/verify-stack.py` | 只读探测 + 一次端到端问答（会消耗少量模型额度） | 手动 |

它**不会**做的事（设计约束）：

- ❌ 除 AstrBot WebUI（6185）在面板密码已改且防火墙限定局域网网段（`<LAN-SUBNET>`）的例外外，其余面板只绑 `127.0.0.1`；边界见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) §3
- ❌ 不做端口转发、不碰路由器 NAT
- ❌ 不修改上游组件（AstrBot / NapCat / wb2api）的代码
- ❌ 不在仓库里保存任何 token、账号或 QQ 号

## 账号风险（重点）

- **QQ 协议端登录有封号风险**。请使用小号，不要用主号。
- **WorkBuddy 账号池不要在两台机器上同时跑**：签到与保活任务会重复触发，
  token 刷新会互相顶掉。迁移前必须先停用一侧。
- 网关的 `api_key` 与账号 token 一旦泄漏，等于把账号借给别人用。
  它们只存在于 `runtime/`，该目录已被 `.gitignore` 排除。

## 凭据

**本仓不存放任何凭据。** 位置索引见 [docs/SECRETS.md](docs/SECRETS.md)。

如果你在任何地方看到明文 token、QQ 号或账号邮箱（包括历史记录、示例配置、日志），
请当作缺陷报上来 —— **不要在公开 Issue 里贴出凭据本身**。
