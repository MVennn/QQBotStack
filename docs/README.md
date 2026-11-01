# docs/ 索引

> **一句话**：这里只有索引与定位，不放正文 —— 每篇文档一句话说明「它管什么」，
> 规则本身按 [DOC-RULES.md](DOC-RULES.md) 的单一正本原则只在对应文档里定义。

文档分四类。每篇开头都有一个「一句话」引言块，先看它再决定要不要往下读。
带 **（正本）** 标记的文档是该主题的**唯一权威定义处**；别处只留一句话概述 + 指向它的链接。

---

## 一、架构与机制

| 文档 | 一句话定位 |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | 边界（**正本**）：三块组件的数据流、会改目标机哪些状态、端口与绑定、目录约定、自启策略、回退 |
| [DESIGN-DEPLOY.md](DESIGN-DEPLOY.md) | 部署设计与决策记录：组件核实、目标机实测、方案取舍、风险与验收口径 |
| [DESIGN-MEDIA.md](DESIGN-MEDIA.md) | 媒体解析与点歌设计：上游 parser/music 插件、guard 的 `parse_share_link` 工具、B站兜底、配置与验收 |
| [DESIGN-FOLLOWUP.md](DESIGN-FOLLOWUP.md) | 接话窗口与统一回复设计：窗口/防抖、相关度权重、第二人引用、同内容合并、配置与验收 |
| [DESIGN-MEMORY.md](DESIGN-MEMORY.md) | 用户记忆与认人设计：官方能力边界、候选插件对比、按 QQ 号分人记忆的推荐方案、验收与回滚 |
| [DESIGN-MEME-EXPORT.md](DESIGN-MEME-EXPORT.md) | 账号收藏表情导出与导入：NapCat 动作、本地包结构、分类方案、验收与待确认项 |

## 二、工具专项

| 文档 | 一句话定位 |
|---|---|
| [TOOLS.md](TOOLS.md) | 工具与组件清单（**正本**）：脚本参数与退出码、组件来源与版本、目录结构、配置要点 |
| [PITFALLS.md](PITFALLS.md) | 踩坑总汇（**正本**）：每条写清「现象 → 根因 → 怎么避」，现象那一行即搜索词 |
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | 排错手册（**正本**）：按「现象 → 排查步骤 → 原因 / 解法」组织，标题即检索词 |

## 三、流程与规范

| 文档 | 一句话定位 |
|---|---|
| [DOC-RULES.md](DOC-RULES.md) | 文档规则（**正本**）：分类定位、脱敏纪律、单一正本映射表、链接纪律、变更触发矩阵、孤儿零容忍 |
| [PROMPT-SPEC.md](PROMPT-SPEC.md) | 提示词规范（**正本**）：分层与字数预算、必留/禁写、世界书键与优先级、压缩规则、变更与验收流程 |
| [VERSIONING.md](VERSIONING.md) | 版本规则（**正本**）：三段式进位、怎么判有没有功能更新、不发版就不动号 |
| [SECRETS.md](SECRETS.md) | 凭据与账号配置（**正本**，只写位置不写值）：本仓存什么、不存什么、真值在哪、脱敏口径 |

## 四、参考资料

| 位置 | 一句话定位 |
|---|---|
| 仓库根 [README.md](../README.md) | 门面：这是什么、环境要求、使用、反馈、免责声明、开源鸣谢、许可证 |
| 仓库根 [AGENTS.md](../AGENTS.md) | 机器协议：PROGRESS 归属、主机与账号值外置、CodeGraph |
| 仓库根 [CONTRIBUTING.md](../CONTRIBUTING.md) | 参与贡献：怎么跑起来、改脚本守什么规矩、提交前跑什么 |
| 仓库根 [SECURITY.md](../SECURITY.md) | 安全策略：安全问题怎么报、这套栈会改机器哪些状态、账号风险 |
| 仓库根 [CHANGELOG.md](../CHANGELOG.md) | 开发者记录；**版本号本身**在这里维护，**进位规则**见 [VERSIONING.md](VERSIONING.md) |
| 仓库根 [PROGRESS.md](../PROGRESS.md) | 本仓进度台账（追加式批次日志） |
| 仓库根 [NOTICE](../NOTICE) | 第三方声明：AstrBot（AGPL-3.0）、Launcher（MIT）、NapCat（自定义）、workbuddy2api（MIT） |
| 仓库根 [LICENSE](../LICENSE) | 许可证全文（**MIT**） |
| [release-notes/](release-notes/README.md) | 面向使用者的 Release 说明，**文件名 = 版本号**（不带 `v` 前缀）；格式规范在它的 README |

---

> 新增 / 删除文档后**必须同步更新本索引**（规则见 [DOC-RULES.md](DOC-RULES.md)）；
> 新文档至少要被一处既有文档引用，不允许孤儿。
