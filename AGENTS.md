# AGENTS —— 机器协议

> **一句话**：三条硬规矩 —— **PROGRESS 按逻辑任务分家**、**主机与账号相关的值一律外置**、
> **有 CodeGraph 就先用 CodeGraph**。其它都能从 [docs/](docs/README.md) 里查到。

---

## 1. PROGRESS：路径由逻辑任务决定，不是物理目录

- 每个逻辑任务目录内有**且仅有一个** `PROGRESS.md`（追加式批次日志）。
- 子代理**只写自己的分片文件**（`evidence/agent-<name>.md` 这类），
  **绝不写任何共享文件**。
- 分片写完同步根 `PROGRESS.md`。

## 2. 主机与账号相关的值一律外置（脱敏红线）

**不许把下面这些写进源码、文档、示例、日志、提交信息**：

| 类别 | 例子 | 该放哪 |
|---|---|---|
| 主机地址 | 局域网 IP、IPv6、DDNS 名 | `host/stack.conf`（不入库） |
| 主机标识 | 计算机名、MAC、WiFi SSID | 哪都不该放 |
| **QQ 号** | bot 自己的号、管理员号、群号 | `host/stack.conf`（不入库） |
| **WorkBuddy 账号** | 邮箱、uid、昵称 | `runtime/workbuddy/auths/`（不入库） |
| 凭据 | accessToken、网关 api_key、OneBot token | 同上，只在本机运行时目录 |
| 本机绝对路径 | `C:\Users\<你>` / `/home/<你>` | 相对路径或 `~` 推导 |
| 真机实测记录 | 探测输出、`ssh -v` 日志、面板截图 | `.work/`（不入库） |

**占位符写法**：`<REDACTED-...>`（凭据）、`<REPLACE-...>`（需要你自己填的值）、
`<HOST-IP>` / `<QQ-ID>`（主机与账号）。

判断标准：**这段文字贴到公开 Issue 里，会不会暴露某台机器或某个账号的身份？**

## 3. CodeGraph

仓库根有 `.codegraph/` 时，**先 `codegraph_explore` 找代码，再 grep**。
没有就跳过 —— 别为此手动建索引。

```bash
codegraph explore "verify-stack.py 验收逻辑"
```

---

## 其他约定（详见 docs/DOC-RULES.md）

- 每篇文档开头必须有 `> **一句话**：…` 引言块（根 README 与 `docs/release-notes/` 除外）。
- 相对链接 + 半角括号；改文档后跑 `python tools/check-docs.py`。
- 提交前跑 `python tools/check-secrets.py --all` —— 脱敏红线的可执行版本。
- `tools/*.ps1` **必须纯 ASCII**：Windows PowerShell 5.1 读无 BOM 的 UTF-8 中文会乱码。
- 计划任务用的 `.cmd` **必须纯 ASCII、不用多行 if 块**，且 CRLF 落盘。
- 提交信息用 Conventional Commits，**按对象拆行**。
- **不要**把上游组件（AstrBot / NapCat / wb2api）的源码或二进制放进仓库 —— 许可证不允许，
  `.gitignore` 已排除 `*.exe` / `*.zip`。
