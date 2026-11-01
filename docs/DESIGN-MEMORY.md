# 用户记忆与认人 · 设计

> **一句话**：先确认 AstrBot 没有第一方「按用户记忆」插件，再用社区插件 `astrbot_plugin_long_memory` 做按 QQ 号分人的轻量记忆；群昵称自动认人可作为 guard 侧的小补充。

---

## 1. 结论

**AstrBot 第一方没有「按 QQ 号分人的长期记忆」插件。** 当前实例的内置
`provider_ltm_settings` 只有群聊上下文能力：

| 内置项 | 现状 | 是不是按人记忆 |
|---|---|---|
| `group_icl_enable` | `false` | 不是，是群上下文 |
| `group_message_history_enable` | `true`，30 条 | 不是，是群消息历史 |
| `image_caption` | `true` | 不是 |
| `active_reply` | `false` | 不是 |

插件市场里 `AstrBotDevs` 名下的官方插件也没有记忆类；记忆插件全是社区插件。
最贴近需求、且和现有 guard / 人格冲突最小的是：

> **`astrbot_plugin_long_memory` v1.2.0（社区，MIT，AstrBot >= 4.24.0）**

它按 **QQ 号**一人一个 JSON 文件，自动记「称呼 / 喜好 / 厌恶 / 住处 / 工作 / 习惯」，
不额外调用模型，注入时只往 `extra_user_content_parts` 追加一段 `<user_memory>`，
**不碰 `system_prompt`**，所以不会和现有人格、世界书、guard 的注入打架。

### 1.1 落地状态（2026-10-26）

已按 **方案 A** 安装 `astrbot_plugin_long_memory` **1.2.0**：

- 插件目录：`data/plugins/astrbot_plugin_long_memory/`；
- 配置：`enable/extract/inject=true`、`max_items=30`、`inject_max_items=30`、
  `inject_max_chars=500`、`ttl_days=180`、`allow_group_cmd=false`；
- 启动日志：`[long_memory] loaded (extract=True inject=True max_items=30 ...)`，
  OneBot 已连接；
- 离线隔离测试：`我叫小林，我喜欢淡一点的咖啡` 与 `我叫阿杰，我不喜欢香菜`
  分别落到 `memory/<QQ>.json`，注入块互不串；
- 已知边界：
  - 只在 **LLM 请求触发**时抽取；群里没叫到机器人的消息不会学（`on_llm_request` 限制）；
  - 多人统一回复只注入最后说话人的记忆；
  - 称呼只认「我叫 / 你可以叫我 / 叫我」这类自报句式；
  - 未自报名字时，靠 AstrBot 当前的 `sender_name` 认人；跨会话的群昵称由下面 1.2 的 guard 名字簿补上。

### 1.2 方案 B 落地：guard 名字簿 + 每人历史（2026-10-26）

guard **1.6.1** 里加了一个独立名字簿，**每条群消息都记**，不依赖 LLM 触发：

- 文件：`data/plugin_data/qqbotstack_guard/people/<QQ>.json`，一人一份；
- 字段：`preferred_name`、`last_card`、`last_nickname`、`aliases`、`groups`、
  `messages`、`count`；
- 历史发言：单条 200 字、每人 80 条、180 天；正文只进 JSON，不进 DB / 日志；
- 回复称呼：`people_address_prob=0.25`，同一人 300 秒冷却；
  优先级 **自报名字 > 本群名片 > 备注昵称**；
- 历史注入：正常带 3 条旧发言；命中「记得 / 以前 / 上次 / 之前 / 我说过 /
  还记得」带 6 条；跳过 5 秒内的当前消息，避免和上下文重复；
- 指令：`/忘记我` 删除本人在 guard 的名字簿和发言；long_memory 的偏好用 `/忘记`；
- 日志：`[interest]` 只留长度，不再记录消息正文或称呼；名字簿和历史只落 JSON；
- 真机验证：群消息已落 `people/<QQ>.json`（1 人、3 条、`count=4`、
  `nickname` 有值、`preferred_name` 尚未设置）。

已知边界：

- 只记允许群；同一人跨群共享一份，`groups` 里保留各群名片；
- 历史是原始近邻句，不是语义摘要；不会做“很久以前那件事”的远程检索；
- `/忘记我` 只清 guard 侧；long_memory 的偏好要另用 `/忘记`；
- 称呼概率是全局的；如果觉得叫得太频繁，调 `people_address_prob` 或
  `people_address_cooldown_sec`。

---

## 2. 候选对比

| 插件 | 来源/热度 | 身份键 | 记忆内容 | 注入方式 | 额外依赖 | 适配度 |
|---|---|---|---|---|---|---|
| **astrbot_plugin_long_memory** | 社区，v1.2.0 | QQ 号 | 称呼/喜好/厌恶/住处/工作/习惯 | `extra_user_content_parts`，不碰 system_prompt | 无，标准库 | **最高**：一人一份、能记称呼、零模型成本 |
| astrbot_plugin_qq_user_memory | 社区，v1.0.1 | QQ 号，跨群 | 全部发言原文 + 每日画像 + 好感度 | `req.prompt`，默认只在 @ 时注入，且只注入**其他群** | 画像/好感需要 DeepSeek | 中：适合跨群原文检索；单群收益有限，当前实例没有 DeepSeek 供应商 |
| astrbot_plugin_memory（Bluezeamer） | 社区，AstrBot >=4.18.2 | 发送者 QQ | Soul / 画像 / 历史索引 / 备忘 / TODO | 注入 `system_prompt` + 多个 LLM 工具 | 无 | 中低：更像助理记忆，工具调用会加延迟，和人格/世界书注入有冲突面 |
| astrbot_plugin_soulmap | 社区，19★ | 发送者 QQ（可会话隔离） | 称呼/生日/忌口/爱好/健康等固定字段 | 注入 `system_prompt`；模型输出 `[Profile: ...]` 标签 | 无 | 中低：标签机制容易被角色扮演带偏，且会主动收集敏感字段 |
| astrbot_plugin_portrayal（Zhalslar） | 社区，101★ | @ 的群友 | LLM 性格画像 | 按需命令生成，不是每轮注入 | LLM | 补充：适合「画像 @某人」，不适合自动分人记忆 |
| astrbot_plugin_memory_sync | 社区 | 群/人物 | 定时扫描 DB → `user_profiles.md` | 不自动注入 | LLM 分类 | 补充：可做画像数据源，需 guard 侧自行注入 |
| LivingMemory | 社区，374★ | 会话/人物 | 向量 + 图谱 + 生命周期 | 检索注入，接管上下文 | Embedding Provider（如 BAAI/bge-m3） | 暂不推荐：重，需额外模型；当前实例没有 embedding provider |
| Iris Chat Memory | 社区，22★ | 用户/群 | 三层记忆 + 知识图谱 + 画像 | 接管上下文，注入多层 | FAISS、numpy、Embedding、2GB 内存 | 暂不推荐：重，和现有 guard/上下文管理冲突面大 |

---

## 3. 推荐方案

### 3.1 第一阶段：装 `long_memory`

- 安装：`data/plugins/astrbot_plugin_long_memory/`，版本固定 **1.2.0**。
- 配置建议：

| 键 | 建议值 | 说明 |
|---|---|---|
| `enable` | `true` | 总开关 |
| `extract_enabled` | `true` | 从消息里学称呼/偏好 |
| `inject_enabled` | `true` | 每轮注入当前说话人的记忆 |
| `max_items` | `30` | 每人最多 30 条 |
| `inject_max_items` | `30` | 每轮最多带 30 条 |
| `inject_max_chars` | `500` | 注入正文上限 |
| `ttl_days` | `180` | 半年没提到就忘 |
| `allow_group_cmd` | `false` | 命令只在私聊用，群聊仍正常注入 |
| `admins_id` | `<QQ-ID>` | 只有主人能查/清别人的记忆 |

- 它能记的称呼来自「我叫 / 我的名字是 / 你可以叫我 / 叫我」；
  偏好来自「我喜欢 / 我不喜欢 / 我讨厌 / 我住在 / 我在…工作 / 我每天…」。
- 它**不会**记手机号、地址、工资、病历等敏感内容；含 4 位以上连续数字的整句直接跳过。
- 数据在 `data/plugin_data/astrbot_plugin_long_memory/memory/<QQ号>.json`，一人一份，可直接备份/删除。

### 3.2 可选补充：guard 侧「名字簿」

`long_memory` 只记用户**自报**的称呼；如果群里有人从没说过「我叫 X」，
它不会自动把 QQ 群昵称写进记忆。AstrBot 的群消息上下文本身带 `sender_name`，
当前对话里能认人；但跨会话/换群时，缺一个稳定的「QQ → 群昵称」表。

可选加一个小名字簿（约 40–60 行，不需要模型）：

- guard 在每条群消息上记录 `sender_id -> {card, name, aliases, last_seen, groups}`，
  存 `data/plugin_data/qqbotstack_guard/namebook.json`；
- 只记昵称/群名片/别名，不记消息正文；
- `inject_lore` 时，如果当前说话人有记录，追加一句
  `[当前说话人] 群昵称：<card>；你记得的称呼：<preferred>`，控制在 100 字内；
- 可选指令 `/称呼` 查看/修改自己的称呼。

这一步不是必须的：先装 `long_memory` 就能覆盖「自报名字 + 偏好」；
名字簿解决的是「没自报名字也能认人」。不建议直接改第三方插件，
因为插件升级会覆盖补丁。

### 3.3 暂不选

- **qq_user_memory**：适合「跨群记得你说过什么」；但当前实例没有 DeepSeek 供应商，
  每日画像/好感度要额外配 key；默认只注入其他群，单群场景收益有限。可以作为第二期。
- **memory / soulmap**：都往 `system_prompt` 注入，且依赖模型工具/标签；
  和梵铭人格、世界书、guard 的注入冲突面更大。
- **LivingMemory / Iris**：需要 Embedding Provider/FAISS/更多内存，且会接管上下文；
  当前阶段过重。

---

## 4. 改动清单（确认后执行）

1. 安装 `astrbot_plugin_long_memory` **1.2.0** 到目标机插件目录；
2. 写入配置（上表），`admins_id` 用占位符替换为主人 QQ；
3. 重启 AstrBot，确认日志 `[long_memory] loaded (...)`；
4. 可选：加 guard 名字簿（新增 `namebook.json`、记录与注入逻辑、`/称呼` 指令）；
5. 更新 `PROGRESS.md`、`CHANGELOG.md`、`docs/ARCHITECTURE.md`；
6. 不改现有 `personas`、`worldbook.json`、`conversations` 结构。

---

## 5. 验收

**基础记忆**

1. 群里 A 说「我叫小林，我喜欢淡一点的咖啡」；B 说「我叫阿杰，我不喜欢香菜」。
2. `/记忆`（私聊）分别看到两人各自一条，互不串。
3. 检查 `memory/<A的QQ>.json`、`memory/<B的QQ>.json` 各自独立。
4. A 问「我叫什么」，机器人答「小林」；B 问，答「阿杰」。
5. 机器人回复仍符合梵铭口吻，世界书条目仍正常命中；回复延迟没有明显增加。

**边界**

- 含手机号/身份证/工资的句子不记；
- `/忘记` 能真删；
- 多人同时接话的统一回复，只注入最后说话人的记忆（`long_memory` 的设计限制），
  不会把 A 的偏好塞给 B；
- 关闭插件后，人格/世界书/guard 行为不变。

---

## 6. 风险与回退

| 风险 | 处理 |
|---|---|
| 第三方插件较新（v1.2.0，社区） | 固定版本；安装前备份；先只开 `inject_enabled`，观察一周 |
| 正则只认固定句式，自报名字才会记 | 需要自动认群昵称时加 guard 名字簿，或让用户说「你可以叫我 X」 |
| 多人统一回复只注入最后一人 | 先接受；需要时在 guard 里按 `items` 的 sender 逐个注入（第二期） |
| 插件升级覆盖本地改动 | 不改插件源码；名字簿放在 guard 侧 |
| 隐私 | 数据只在目标机 `plugin_data`；`/忘记` 删除；不记消息正文（long_memory） |

回退：停用/卸载插件，删除 `data/plugin_data/astrbot_plugin_long_memory/`；
名字簿删除 `data/plugin_data/qqbotstack_guard/namebook.json`；重启 AstrBot。

---

## 7. 待确认

| 选项 | 内容 | 状态 |
|---|---|---|
| **A** | 只装 `long_memory`：自报名字 + 偏好/习惯，按 QQ 号分人 | ✅ 已执行（2026-10-26） |
| **B** | A + guard 名字簿：没自报名字也能按群昵称认人；记最近发言 | ✅ 已执行（2026-10-26） |
| **C** | A + `qq_user_memory`：再加跨群原文检索/画像 | 待定；要配 DeepSeek 或改 profiler |
| **D** | 自研 guard 记忆：完全可控，但代码量最大 | 不推荐作为第一步 |

A / B 已落地。接下来观察：称呼频率、旧发言是否被自然带出、`/忘记我` 是否够用；
如果出现「记得偏好，但完全不记得很久以前聊过什么」，再考虑 **C** 的跨群原文检索。
