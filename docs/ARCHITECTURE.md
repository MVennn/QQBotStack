# 架构与边界

> **一句话**：这套栈的边界（**正本**）：会改目标机哪些状态、端口与绑定约定、
> 目录约定、开机自启策略、怎么撤除。

---

## 1. 三块组件与数据流

| 角色 | 组件 | 职责 |
|---|---|---|
| 协议端 | NapCat（跑在 QQ NT 之上） | 收 QQ 消息 → 转成 OneBot 11 → 推给 AstrBot |
| 大脑 | AstrBot | 组装上下文、调模型、跑插件、把回复交回协议端 |
| 模型网关 | wb2api（workbuddy2api） | WorkBuddy 账号池 → OpenAI 兼容 `/v1` 接口 |

```text
QQ 用户
  │  消息
  ▼
NapCat ──OneBot 11 反向 WebSocket（NapCat 主动连出）──▶ AstrBot 127.0.0.1:6199
                                                          │
                                                          │ OpenAI 兼容请求
                                                          ▼
                                                     wb2api 127.0.0.1:7863/v1
                                                          │
                                                          ▼
                                                   WorkBuddy 上游
```

**方向是固定的**：NapCat 是 WebSocket **客户端**，AstrBot 是服务端。所以协议端
不需要开任何入站端口 —— 它只往外连。

### 1.1 账号池归属：操作机持有，目标机消费

| 机器 | 角色 | 做什么 |
|---|---|---|
| 操作机 | **账号持有者** | 唯一运行网关保活（22:00 轮换 token）的一侧；`auths/` 以它为准 |
| 目标机 | 消费者 | 每天同步一次 `auths/`；**关闭全部定时任务**（签到 / 成长 / 旅行 / 活跃 / 保活 / 夜猫子） |

**为什么必须这样分**：网关的「token 保活」每天 22:00 会重新签发 token 并**覆盖 auth 文件**
（实测：文件 mtime `22:00:00`、JWT `iat 22:00:19`）。两台机器同时跑保活会互相顶掉
`refreshToken`；只跑一台、另一台用副本，才不会打架。

同步由操作机的计划任务 `QQBotStack-authsync` 驱动：**每天 04:00 触发一次，错过则在
下次登录后补跑，成功当天不再执行**（日期记在 `%LOCALAPPDATA%\QQBotStack\authsync.state`）。
脚本是 `tools/sync-auths.ps1`，由 `tools/sync-auths-hidden.vbs` 以隐藏窗口拉起
（操作机默认终端是 Windows Terminal，直接起控制台程序会弹窗，`-WindowStyle Hidden`
压不住，见 [PITFALLS.md](PITFALLS.md) P89）；同步完会重启目标机的网关任务，让新账号生效。

### 1.2 机器人的回复策略

配置在 AstrBot 的 `cmd_config.json`，另加一个本仓自己的小插件
（`host/plugin/qqbotstack_guard/`）：

| 场景 | 行为 | 由谁实现 |
|---|---|---|
| 私聊 | 一律不回复 | 插件 `guard_private()` 直接 `stop_event()`（`private_reply_enabled=false`） |
| 指定群 · 被 @ 或引用机器人 | 回复 | 插件置位 `is_at_or_wake_command` |
| 指定群 · 文本**包含**关键词 | 回复 | 插件（`wake_prefix` 只能做前缀，见 PITFALLS P19） |
| 指定群 · 普通闲聊 | **25%** 概率随机插话，3 分钟冷却（仅纯文本） | 插件 |
| 指定群 · 纯图片 / 空文本 | 不随机插话（被 @ 或含关键词时仍会回） | 插件 |
| 指定群 · 分享链接 / QQ 小程序卡片 | 解析并发送媒体/卡片，再由人格接一两句 | `parse_share_link` LLM Tool |
| 指定群 · 想听歌 / 聊歌 | 有明确歌名就发 QQ 音乐卡片，否则自然接话/反问 | 点歌插件 `play_song_by_name` Tool |
| 指定群 · 聊视频 / 剪辑 / 电影（无链接） | 自然接话，不假装看过具体内容 | 插件 `VIDEO_INTENT_RE` + LLM 提示 |
| 指定群 · `/` 开头 | 交给内置指令 | AstrBot 默认 |
| 其他群 | 一律不回复 | 插件 `stop_event()` |

群号、关键词、随机概率、冷却、分享/点歌开关都在插件同目录的 `config.json` 里（**不入库**，
模板是 `config.example.json`）。改完需要重启 AstrBot。媒体解析与点歌的完整设计见
[DESIGN-MEDIA.md](DESIGN-MEDIA.md)。

其他相关配置：`reply_with_mention=true`（群里回复时 @ 发送者）、
`segmented_reply.enable=true`（`words_count_threshold=100000`，让长文也能进入分段；guard 只为长文插入换行，短回复没有换行，仍整条发）、
`admins_id=[<ADMIN-QQ>]`。**`active_reply` 保持关闭** —— 随机插话已由插件实现，
两处都开会重复触发。

**`streaming_response` 关闭**：AstrBot 的流式分支会直接 `return`，跳过 `segmented_reply`；
而人格平时少用句号，靠流式切句不稳定。继续关闭，用 `segmented_reply` + guard 长文切段。
这不是 1.4.0 改掉的 —— 17:42 之前它就是 false。
要提速换快模型，别靠流式（[PITFALLS.md](PITFALLS.md) P21）。

### 1.3 人格与说话风格

人格存在数据库 `core/data/data_v4.db` 的 `personas` 表（`persona_id='default'`），
由 `agent_runner.config.persona.persona_id` 选用。当前人设是**梵铭**（来教堂的人叫
拉斐尔神父，亲近的人叫小伯；拉贵尔是他自己取过、没人知道的旧名），按 EmeraldEden
设定 7.1 重写为 **2,187 字**：**苦收在里，热留在外**——先伸手迎人、对生人用敬语、
对熟人短句但不冷；爱笑、会闹会赖会赌气、对小东西认真；会担心、会高兴、会不好意思；
不是阴沉的人，也不是抖机灵的段子手。2026-10-26 又补了三层硬约束：
**身份**（梵铭不是拉斐尔，拉贵尔才是他的别名）、**对长辈的敬重**（玟德先生是长辈，
不是下属）、**长度**（认真问关系/过去/安慰时必须展开，不拿一句打发）。结构分四段：

| 段 | 作用 |
|---|---|
| 身份与名字 | 梵铭是谁、「拉贵尔 → 拉斐尔」两个名字怎么来的、为什么自报名字先停半拍 |
| 性格 | 先伸手、爱笑、会闹会赖、对小东西认真、苦只在没人时、没觉得自己该担 |
| 说话方式 | 日常一两句；认真问设定/关系/过去、安慰、讲故事时三四句以上；不列点、不用 Markdown/emoji、不夹英文单词、不自称 AI；短不等于冷 |
| 语气与习惯 | 先接住情绪、敬语分人、会担心、不顶撞、不拿难处开玩笑；话不多但会冷不丁来一句干的，不解释笑点 |

**人设正文不入库**（属于作品内容），只在本机数据库里。改人格 = 改这一条记录 + 重启。
`begin_dialogs` 保留 **12 组示例（24 条）**，用来钉住「先问人、再谈事」的腔调；
其中 4 组是长文示例（关系链、拉斐尔身份、悠塔、教堂日常），专门对抗「所有回复都短」；
另有「神父讲个笑话」「你是不是傻」两组幽默示例，钉住干冷的接梗方式。

模型链是 **Beam（短句，实测约 1.3s）→ HY3-Free（复杂轮，实测约 20s）→ HY4-Pre-Free（30s）**。
`model_simple=Beam`、`model_complex=HY3-Free`。2026-10-28 15:05 起 Beam
在群里连续要求对方「你先说清楚是哪个 cli」、模仿「名字：内容」的转写格式、
偶尔吐出 `</rfl:parameter>`；同一份人格和上下文下免费模型实测：
Beam 1.28s 但风格不稳，HY3-Free 19.9s / Iceman 26.2s 风格好但太慢，
HY4-Pre-Free 3/4 超时。折中办法是**混合路由**（guard 1.6.40）：
AI/命令行/复读抱怨等容易翻车的话题、以及多人连续发言（输入带
「以下是不同人的连续发言」）走 `model_complex=HY3-Free`，其余短句仍走 Beam。
图片轮（当前消息、引用消息、转发）由 AstrBot 的
`_select_image_chat_provider` 在 build 阶段切到 HY3-Free，失败再 HY4-Pre-Free。
开关是 `zgate-beam.modalities` 只声明 `text/tool_use`——**不要加回 `image`**，
否则引用图会被送进 Beam 并 400（[PITFALLS.md](PITFALLS.md) P88）。
guard 在 `model_image` 非空时把图片轮的 `req.model` 也指到 HY3-Free，作为双保险；
历史上下文里的图片由 `sanitize_contexts_by_modalities` 与 guard 的 `[图片]`
替换共同清理。Beam source timeout 设 20 秒，快速失败并把时间留给 fallback。
provider 的 `max_tokens=16384`，避免推理模型把预算全花在 reasoning 上、正文为空。

guard 另有按模型独立计数的断路器：主模型和 HY3 分别统计 5xx / 429 / 超时 / 断连
（4xx 内容或参数错误不计），连续 3 次就把该模型标成不可用。此后 agent 请求遇到
它会立即返回 err（不再等 source timeout），由 AstrBot 的 fallback 链切下一个：
主模型不可用 → HY3；主模型和 HY3 都不可用 → 直接选 `zgate-hy4` 的 provider。
后台每 180 秒对熔断模型发一次 `ping` 探活，成功自动恢复。后台插件（只传 prompt、
不传 contexts）不受 fail-fast 影响。
模型全挂时，guard 的 `on_decorating_result` 会把技术错误替换成人格化的
「走神」台词（P33）。
改人格后必须清旧会话（[PITFALLS.md](PITFALLS.md) P29）。

接话窗口与统一回复已实现（guard 1.4.0）：回复后 300 秒窗口、最后一条后静默 6 秒、
第二个人内容不同才引用；生成期间到达的接话等当前回复发完再单独接住，不丢。
设计见 [DESIGN-FOLLOWUP.md](DESIGN-FOLLOWUP.md)。

提示词是概率性的，所以插件里还有一道确定性的兜底：`on_decorating_result` 钩子在发送前
剥掉 Markdown 与 emoji（[PITFALLS.md](PITFALLS.md) P22）。

### 1.4 世界书：设定按关键词注入

整本设定（EmeraldEden 十三册，约 5.4 万字）、剧情总览与二十五章粗纲
**不能塞进人格提示词** —— 每轮都注入既贵，又会让模型分不清「我是谁」和「世界是什么」。
也不能把整本直接喂给**中期 RP**：第十三章以后的事件、人物结局和作者级真相
（拉斐尔=拉梵、赫尔墨斯=乌列尔代行者、火种=方舟钥匙）会被模型当成「已经知道」。

做法是把它切成世界书条目，只收**当前阶段**、只在聊到相关词时注入：

```text
.work/世界书_中期.md  →  .work/build_midworldbook.py  →  worldbook.json
   （按阶段手工编排）        （调用 tools/build-worldbook.py）      （不入库）
        →  qqbotstack_guard 的 on_llm_request（命中关键词才注入）
```

| 项 | 值 |
|---|---|
| 当前部署 | **中期版**（第七至十二章前后）：**55 条 / 10,933 字**，2 条常驻 404 字 |
| 生成命令 | `python .work/build_midworldbook.py`；它先用 `tools/build-worldbook.py --src .work/世界书_中期.md` 切分，再补常驻条目、别名与优先级 |
| 全本入口 | 设定推进到后期时，仍可用 `tools/build-worldbook.py --src 设定/02–13 --src 设定/08-人物/00–09 --src 大纲/01–05 --out ...` 生成全本；当前不要直接部署全本 |
| 单条上限 | 700 字（在句号处截断） |
| 单轮注入上限 | 2 条常驻 + 最多 2 条命中，合计 ≤ 1,400 字（`LORE_MAX_CHARS`） |
| 关键词来源 | 小节标题 + 正文里的 `**加粗**` 术语 + 生成后补的别名（神父 / 小伯 / 拉贵尔 / 赤鬼 / 阿悠 / 犹达斯 / 乌列 / 白翅膀 / 摆渡人 / 商会 / 信使 / 学者） |
| 中期范围 | 住客只有梵铭、玟德、铭；常来的是赫尔墨斯、露西；拉梵（人间体）来访；乌列尔只闻其名；卡戎、犹达斯不进入日常；不写结局、静默协议、双核、方舟 |
| 长节处理 | 超过 700 字的 `##` 节按 `###` 拆成子条目；人物「语言 / 性格」排在同人物其他条目前 |
| 优先级 | **身份辨析 95 > 人物口吻速查 85 > 四主角 84 > 悠塔 / 赫尔墨斯 80 > 关系矩阵 78 > 拉斐尔 / 露西 70 > 乌列尔 / 不在场 65 > 教堂 / 卡戎 / 硬约束 60 > 火种系 55 > 世界观 50**（插件按 `priority` 排序） |
| 泛问兜底 | 「他们怎么说话 / 口吻」命中 `人物口吻速查`；「介绍一下身边的人 / 关系」命中 `关系矩阵`；「结局 / 之后」命中 `此刻不在场的人`（只给边界，不给剧透） |

**单字人名要小心**：`铭` 是合法关键词，但会命中「梵铭」。不要把 `铭` 再加进
`关系矩阵` 的 keys，否则一句「梵铭」会给关系矩阵算两票，把人物页顶掉。
人物页的 `铭` 条目保留单字 key，靠它接住只打「铭」的问句。

世界书可以在 WebUI 里直接浏览：**插件 → qqbotstack_guard → 世界书视图**。
页面是插件自带的 `views/worldbook/index.html`（数据内联，纯静态），支持按条目名 /
关键词 / 正文搜索，常驻条目有橙色标记。生成时加 `--view <插件目录>` 一起产出。

**`worldbook.json` 不入库**（含作品正文），仓库里只有生成器；阶段源文件与产物都在
`.work/`。改了设定集或推进阶段就重新生成一次，再拷到实例的
`core/data/plugins/qqbotstack_guard/` 下并重启。

### 1.5 媒体分享与自然点歌

分享 B站/抖音/快手/小红书 链接或 QQ 小程序卡片时，guard 先唤醒 LLM，再由
`parse_share_link` 工具调用上游 `astrbot_plugin_parser` 的 parser 实例发送媒体；
工具把标题/作者/简介返回给模型，模型用当前人格接一两句。说「我想听某首歌」时，
guard 唤醒 LLM，由上游 `astrbot_plugin_music` 的 `play_song_by_name` 工具搜歌、发卡片，
模型再补一句。「起风了这首歌很好听」「我听的是起风了」这类聊歌句也会唤醒：
有明确歌名就点歌，没有（如「这首歌叫什么」）就让模型接话/反问，不拿整句去搜。
只说「这个视频好看」「刷到一个视频」这类话时，guard 走视频接话分支，注入
「不要假装看过」的提示，并按群做 60 秒冷却；带链接时仍走分享解析。

**为什么不用 parser 的自动解析**：AstrBot 的默认 LLM 请求只在
`not event._has_send_oper` 时触发；parser 先 `event.send()` 过，默认 LLM 就被跳过，
人格接话不会出现。把解析放进 LLM Tool 内部，agent 循环仍会继续生成最终回复
（[PITFALLS.md](PITFALLS.md) P24）。

| 项 | 值 |
|---|---|
| 解析插件 | `astrbot_plugin_parser` 1.6.1（MIT，插件市场安装） |
| 点歌插件 | `astrbot_plugin_music` 3.3.1（GPL-3.0，**外部安装、不 vendor**） |
| guard 接管 | `takeover_parser=true` 时把 parser 的 `cfg.whitelist` 置为哨兵值，关闭自动解析 |
| B站兜底 | parser 失败时用 yt-dlp 取标题/UP/封面，发「封面 + 标题 + 链接」 |
| 媒体上限 | parser `source_max_size=50` MB、`source_max_minute=5` |
| 分享冷却 | 同一 URL 60 秒内不重复接话（`share_reply_cooldown_sec`） |
| ffmpeg | 便携版放在 `runtime/ffmpeg`，由 `run-astrbot.cmd` 前置 PATH |

完整配置、风险与验收见 [DESIGN-MEDIA.md](DESIGN-MEDIA.md)。

### 1.6 接话窗口与统一回复

机器人回复后 300 秒内，其他人的接话不再逐条回，而是先收集；最后一条后静默 6 秒，
由默认管线统一回一次。第二个人说的内容不同时，模型用内部标记 `<<<SECOND>>>` 分出
一段，插件用 `Reply(id=...)` 单独引用回复；内容相同则合并，不引用。
`@` / 引用机器人用 1.5 秒短防抖，仍参与统一回复。生成期间才到的接话不丢：
等当前回复发完再唤醒自己，作为下一条单独接住。第一版只群聊；
指令、分享、点歌、聊视频走原链路，不进入收集。

每群有一个**心动值**（初始 70，每分钟衰减 1.0；被点名 +25，相关接话 +6，
每次回复 -2，普通无关消息 -8）。低于 20 时窗口关闭，只接 @ / 引用 / 叫他名字；
高于 60 时只把门槛压低（问句 0.05 / 陈述 0.1），仍然必须和当前话题沾边，
不再无条件接普通陈述。出圈话题（AI / 游戏 / 技术 / 娱乐圈）或和最初话题、
上一句都没有实际关系时，扣 12 分并直接关窗，让群里自己聊。
直接问你的那条永远优先，不会被更相关的第二个人顶掉。图片/表情包在直接点名或心动值 ≥50 时放行给 LLM，
AstrBot 自动切 HY3/HY4；纯图不再被随机插话分支 `stop_event()` 吞掉。

机器人反问「哪首 / 什么歌 / 什么视频」后会记一个 300 秒待答意图，
并落盘到插件目录的 `pending_media.json`，AstrBot 重启后仍有效；
用户晚回一个裸歌名 / 视频名也能唤醒。音乐提示要求**先用 `play_song_by_name` 搜一次，
搜不到再问**；视频没有「按标题找视频」的 API，带链接走分享解析，
只有标题时只接话 / 要链接。

点歌 / 分享 / 视频卡片由工具直接发送，可能没有最终文字回复；
guard 在 `on_llm_request` 先开临时接话窗口，`on_decorating_result` 再重开，
所以卡片下面仍能继续接话。慢的主因是模型 / 网关（Beam 上游超时、
DeepSeek 无健康账号、HY3 限流回退），不是插件循环。

配置项、权重算法、状态机与验收见 [DESIGN-FOLLOWUP.md](DESIGN-FOLLOWUP.md)。

## 2. 会改什么

`tools/deploy-stack.ps1` 是唯一会动手的脚本，按阶段执行：

| 阶段 | 动作 | 具体改了什么 | 幂等 | 撤销 |
|---|---|---|---|---|
| `gateway` | 建目录 + 落文件 | `runtime/workbuddy/` 下放 `wb2api.exe`、`config.json`、`run-wb2api.cmd` | ✅ 覆盖同名文件 | 删目录 |
| `gateway` | 建计划任务 | `QQBotStack-wb2api`：`onstart`，`SYSTEM`，最高权限 | ✅ `/f` 重建 | `schtasks /delete` |
| `gateway` | 启动 | 立即运行该任务 | ✅ | `schtasks /end` |
| `napcat` | 解包 | `runtime/napcat/onekey/` 展开一键安装器 | ✅ | 删目录 |
| `napcat` | **装 QQ** | 运行安装器会**在系统里安装 QQ NT** | 安装器自身判断 | 「应用和功能」卸载 |
| `astrbot` | 静默安装 | `runtime/astrbot/launcher/` 装 AstrBot Launcher | ✅ 重装覆盖 | 跑 `uninstall.exe` |
| `astrbot` | 改数据目录 | 写 `%APPDATA%\com.github.raven95676.astrbot-launcher\.data-dir.json` | ✅ | 删该文件 |
| `sync-auths`（操作机） | 建计划任务 | `QQBotStack-authsync`：每天 04:00 推送 `auths/` 到目标机并重启网关（`wscript` 隐藏启动） | ✅ 当天已同步则跳过 | `Unregister-ScheduledTask` |

> **必须用计划任务而不是直接启动进程**：Windows OpenSSH 会把会话内的子进程放进作业对象，
> SSH 一断开就全被杀掉。详见 [PITFALLS.md](PITFALLS.md) P1。

## 3. 端口与绑定约定

| 服务 | 端口 | 绑定 | 谁能访问 |
|---|---|---|---|
| wb2api API | 7863 | `127.0.0.1` | 仅本机（AstrBot） |
| wb2api 面板 | 7863 `/panel/` | `127.0.0.1` | 仅本机；运维走 SSH 转发 |
| **AstrBot WebUI** | **6185** | **`0.0.0.0`（例外）** | **局域网 10.0.0.0/24，需登录** |
| AstrBot OneBot 反向 WS | 6199 | `127.0.0.1` | 仅本机（NapCat） |
| NapCat WebUI | 6099 | `127.0.0.1` | 同上 |
| zgate | 7871 | `127.0.0.1` | 仅本机（AstrBot） |

**默认红线：WebUI 不绑 `0.0.0.0`。** 面板都有管理权限（改模型、发 QQ 消息、看账号池），
绑回环 + SSH 本地转发等于复用已经加固过的 SSH 通道。

**唯一例外：AstrBot WebUI（6185）。** 日常要看对话和调人格，每次开隧道太麻烦，
所以它绑 `0.0.0.0`，但用**防火墙限定来源**只允许局域网网段：

```powershell
New-NetFirewallRule -Name 'AstrBot-WebUI' -DisplayName 'AstrBot WebUI (6185)' `
  -Direction Inbound -Protocol TCP -LocalPort 6185 -Action Allow -RemoteAddress 10.0.0.0/24
```

前提是**面板密码已经改过**（`password_change_required=false`）。没有密码或还是初始密码时，
不要开这个例外 —— 等于把管理面板公开。NapCat 与 wb2api 的面板仍然只绑回环。

局域网内直接访问 `http://<HOST-IP>:6185`。要给别的面板也开口子，照这个规则改端口即可，
但每开一个都要先确认它有密码。

运维侧取用方式（不开例外时）：

```sh
ssh -N -L 6185:127.0.0.1:6185 -L 6099:127.0.0.1:6099 -L 7863:127.0.0.1:7863 <HOST-USER>@<HOST-IP>
```

## 4. 目录约定

```text
<部署根>/
├── README.md / AGENTS.md / docs/ / tools/ / host/    ← 仓库内容
└── runtime/                                          ← 运行时（不入库）
    ├── workbuddy/
    │   ├── wb2api.exe            网关二进制（从源码构建或官方 Release）
    │   ├── config.json           listen / api_key / 计划任务 / 冷却
    │   ├── run-wb2api.cmd        计划任务的入口（纯 ASCII + CRLF）
    │   ├── auths/*.json          WorkBuddy 账号凭据（**最敏感**）
    │   └── data/                 state.json / usage.json / request-logs
    ├── napcat/
    │   ├── onekey/               一键安装器（解包后）
    │   └── NapCat.XXXX.Shell/    安装产物（含 napcat.bat）
    └── astrbot/
        ├── launcher/             AstrBot Launcher 安装目录
        └── data/                 Launcher 数据目录（实例、Python 运行时、AstrBot 源码）
```

`runtime/` 整个被 `.gitignore` 排除。**不要在仓库里放它的副本。**

## 5. 开机自启策略

| 组件 | 方式 | 依赖登录 | 说明 |
|---|---|---|---|
| wb2api | 计划任务 `QQBotStack-wb2api`（`onstart` / `SYSTEM`） | ❌ 不依赖 | 开机即跑，无需人登录 |
| zgate | 计划任务 `QQBotStack-zgate`（`onstart` / `SYSTEM`） | ❌ 不依赖 | 开机即跑，无需人登录 |
| AstrBot | 计划任务 `QQBotStack-astrbot`（`onstart` / `SYSTEM`，跑 `run-astrbot.cmd`） | ❌ 不依赖 | 与 Launcher 解耦；Launcher 只是装实例的 GUI |
| NapCat | 计划任务 `QQBotStack-napcat`（**登录时**触发，也可随时按需跑） | ✅ 依赖 | QQ 是桌面程序，必须落在交互会话里 |
| auths 同步（操作机） | 计划任务 `QQBotStack-authsync`（每天 04:00，错过登录后补跑；`wscript` 隐藏启动） | ✅ 依赖 | 只在操作机登录后才会推；当天已同步则跳过 |

NapCat 由 `runtime\napcat\run-napcat.cmd` 拉起：脚本自己找最新的 `NapCat.*.Shell`
目录，已经在跑就直接退出；任务以**交互令牌**运行当前登录账户
（即 stack.conf 的 `user`），所以 QQ 窗口落在桌面会话里。
操作机上用 `tools\start-stack.ps1` 一条命令就能查看/拉起四块组件，
不必再远程登录、钻进 `runtime\napcat\onekey\NapCat.*.Shell` 双击 `napcat.bat`
（[TOOLS.md](TOOLS.md) §1.4）。

> 剩下的可用性缺口只有一个：**NapCat 依赖桌面会话**。目标机重启后没人登录，
> QQ 就起不来。要彻底免登录，需要开「自动登录」，或把 QQ/NapCat 换成服务化方案
> （见 [DESIGN-DEPLOY.md](DESIGN-DEPLOY.md) §八.1 的选项 B）。

## 6. 不会做什么

- ❌ 不向局域网暴露任何 WebUI
- ❌ 不做端口转发、不碰路由器 NAT
- ❌ 不修改上游组件代码（AstrBot / NapCat / wb2api）
- ❌ 不在仓库里保存 token、账号或 QQ 号
- ❌ 不代管 QQ 登录态（掉线要重新扫码，脚本不碰）

## 7. 回退

```powershell
# 1) 停掉常驻进程
schtasks /end /tn QQBotStack-wb2api
schtasks /delete /tn QQBotStack-wb2api /f
Get-Process wb2api, NapCatWinBootMain -ErrorAction SilentlyContinue | Stop-Process -Force

# 2) 关掉 AstrBot 实例（Launcher 里点停止），然后卸载启动器
& "<部署根>\runtime\astrbot\launcher\uninstall.exe" /S

# 3) 删运行时
Remove-Item -Recurse -Force "<部署根>\runtime"

# 4) 如需彻底清理由「应用和功能」卸载 QQ
```

本机侧如果之前停用过别的网关，按当时的备份恢复。
