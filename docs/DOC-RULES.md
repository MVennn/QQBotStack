# 文档规则

> **一句话**：docs/ 下的文档怎么分类、怎么互相引用、怎么脱敏、改动时连带改哪些 ——
> 本篇只管「怎么写、怎么保持一致」，不承载任何具体技术规则。

---

## 1. 分类与定位

docs/ 分四类（索引见 [README.md](README.md)）：

| 类别 | 收什么 | 现有成员 |
|---|---|---|
| 架构与机制 | 边界、设计、部署决策 | ARCHITECTURE、DESIGN-DEPLOY、DESIGN-FOLLOWUP、DESIGN-MEDIA、DESIGN-MEME-EXPORT、DESIGN-MEMORY |
| 工具专项 | 组件清单、踩坑、排错 | TOOLS、PITFALLS、TROUBLESHOOTING |
| 流程与规范 | 版本、凭据、文档规则、提示词 | VERSIONING、SECRETS、DOC-RULES、PROMPT-SPEC |
| 索引 | 唯一入口（正本） | README |
| 参考资料 | Release 说明 | release-notes/ |

每篇文档开头必须有一个 **「一句话」引言块**（`> **一句话**：…` 或一行定位语）。
**例外**：根 `README.md` 与 `docs/release-notes/` 下的正文。

### 文件命名：全大写 + 连字符

`docs/` 下的 `.md` 一律 **全大写 + 连字符**：`ARCHITECTURE.md`、`DESIGN-DEPLOY.md`。
混用驼峰或下划线会让索引排序和全仓搜索都跟着散。

改名三步：① `git mv` 改名；② 全仓 grep 旧文件名同步引用；③ 跑 `python tools/check-docs.py`。

例外：`docs/release-notes/` 下的文件名是版本号本身（`0.1.0.md`），**不带 `v`** ——
`v` 前缀只属于发版 tag。

## 2. 脱敏纪律（本仓红线）

**文档里不出现任何具体主机、账号或凭据。** 这条比格式规则优先级高。

| 不许出现 | 写成 |
|---|---|
| 局域网 IP / IPv6 / DDNS | `<HOST-IP>` |
| 计算机名 / MAC / WiFi SSID | `<HOST-NAME>` / `<REDACTED-MAC>` |
| **QQ 号**（bot 号 / 管理员号 / 群号） | `<QQ-ID>` / `<GROUP-ID>` |
| WorkBuddy 账号邮箱 / uid / 昵称 | `<WB-ACCOUNT>` |
| accessToken / api_key / OneBot token | `<REDACTED-TOKEN>` |
| 本机绝对路径 | 相对路径或 `~` 推导 |
| 真机实测原始输出、面板截图 | 只放 `.work/` |

提交前跑 `python tools/check-secrets.py --all`。判断标准：
**这段文字贴到公开 Issue 里，会不会暴露某台机器或某个账号的身份？**

## 3. 单一正本原则

**每条规则只在一篇文档里定义；其余位置只允许一句话概述 + 指向正本的链接。**

| 规则 | 正本 |
|---|---|
| 会改目标机哪些状态、端口与目录约定、自启策略 | [ARCHITECTURE.md](ARCHITECTURE.md) |
| 三块组件怎么装、怎么调、版本与许可 | [TOOLS.md](TOOLS.md) |
| 部署决策的来龙去脉与方案取舍 | [DESIGN-DEPLOY.md](DESIGN-DEPLOY.md) |
| 踩过的坑与「下次怎么避」 | [PITFALLS.md](PITFALLS.md) |
| 按现象排查 | [TROUBLESHOOTING.md](TROUBLESHOOTING.md) |
| 凭据与账号配置的位置（只写位置不写值） | [SECRETS.md](SECRETS.md) |
| 版本晋升、不发版不动版本号 | [VERSIONING.md](VERSIONING.md) |

## 4. 链接纪律

- 统一用**相对链接 + 锚点**，不用绝对路径。
- 改 / 删 / 合并文档后双向点验：出链目标还在、入链改到新位置。**禁止只删文档不改引用方**。
- 历史记录里的旧文件名可保留原样；正文中指向现役文档的链接必须指向现役文档。

## 5. 变更触发矩阵

| 变更 | 必须同步 |
|---|---|
| **修一个缺陷** | [PITFALLS.md](PITFALLS.md) 补一条 **现象 → 根因 → 怎么避**；形成新判据时同步 [TROUBLESHOOTING.md](TROUBLESHOOTING.md)；CHANGELOG 不算补文档 |
| 新增 / 删除脚本 | [TOOLS.md](TOOLS.md) 工具表与目录树、[ARCHITECTURE.md](ARCHITECTURE.md) 的「会改什么」表 |
| 改端口 / 目录 / 自启方式 | [ARCHITECTURE.md](ARCHITECTURE.md)，并同步 `tools/verify-stack.py` 的探测目标 |
| 换上游版本 | [TOOLS.md](TOOLS.md) 的版本表、NOTICE 的许可说明 |
| 发版 | 根 CHANGELOG、`docs/release-notes/<版本>.md` |
| 改名 / 新增 / 删除文档 | [README.md](README.md) 索引 + 全仓 grep 旧文件名 |

## 6. 体量预算与样例时效

- **单篇 ≤ 800 行。** 超了按「正文档 + 踩坑史」拆。
- 带版本标注的样例可容忍过时（那是历史记录）；**组件清单、端口、会改什么**必须随部署同步。

## 7. 索引维护与孤儿零容忍

- [README.md](README.md) 是 docs/ 的唯一索引，新增 / 删除 / 改名必须同步。
- **孤儿文档零容忍**：新文档必须至少被一处既有文档引用。
