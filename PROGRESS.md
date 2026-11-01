# QQBotStack 建仓与首轮部署

> **一句话**：本仓唯一的进度台账 —— 当前在做什么、做到哪、卡在哪；接手时先读这里。

状态: 进行中（人工步骤待完成）

## 任务目标

在局域网 Windows 主机上，把 AstrBot（bot）、NapCat（QQ 协议端）、workbuddy2api（模型网关）
整合成一套可运维的栈，落在 `<部署根>\QQBotStack`。
仓库按系列仓规范建（基准仓 GSAuxiliary 门面 + docs 四分类），全程脱敏。

## 步骤清单

- [x] 踩点：三块组件版本/平台/许可/端口、目标机环境、本地数据形态
- [x] 出设计文档 `docs/DESIGN-DEPLOY.md`，用户确认（不迁账号、其余按推荐）
- [x] 建仓骨架：README / AGENTS / CONTRIBUTING / SECURITY / CHANGELOG / LICENSE / NOTICE /
      `.gitignore` / `.gitattributes` / `.editorconfig`
- [x] `docs/` 正本：DESIGN-DEPLOY / ARCHITECTURE / TOOLS / PITFALLS / TROUBLESHOOTING /
      SECRETS / VERSIONING / DOC-RULES / README 索引 / release-notes 模板
- [x] `tools/deploy-stack.ps1` + `tools/verify-stack.py` + 三个自检脚本
- [x] `host/stack.conf.example`
- [x] `.github/`：Issue 表单三件 + CI
- [x] `assets/icon.svg` 并渲染 logo / social-preview
- [x] 自检：`check-docs.py` + `check-secrets.py --all` 到 0 问题
- [x] 目标机：建 `runtime/` 目录树
- [x] 目标机：部署 wb2api（计划任务 SYSTEM 常驻，面板 200）
- [x] 目标机：静默安装 AstrBot Launcher，数据目录指向 `runtime/astrbot/data`
- [x] 目标机：解包 NapCat 一键安装器到 `runtime/napcat/onekey`
- [x] 目标机：NapCat 安装产物落在 `runtime/napcat/onekey/NapCat.52230.Shell`
      （安装器半成品已手工合并修复，见 PITFALLS P11）
- [x] 目标机：仓库内容铺到 `<部署根>`（与 `runtime/` 并列）
- [x] 首轮验收基线：`verify-stack.py` 五项失败，全部对应预期（账号未登录 / 组件未启动）
- [x] 验证 SSH 本地转发可打开网关面板（HTTP 200），确认运维不需要开入站端口
- [x] 目标机：AstrBot 三个组件已装（python py310+py312 / nodejs / uv）
- [x] 目标机：实例已创建（`data/instances/59ae5c65-…`，core + venv，314 个包）
- [x] 目标机：AstrBot 首次启动卡死已定位（P12），手动复跑确认可正常启动
- [x] 目标机：`dashboard.host` 由 `0.0.0.0` 改为 `127.0.0.1`（P13）
- [x] 目标机：重置初始面板密码（P14）
- [x] 目标机：NapCat 已启动、QQ 已登录（生成 `onebot11_<uin>.json`）
- [x] 目标机：WorkBuddy 国际服账号已在网关面板完成 OAuth 登录（34 个模型可用）
- [x] AstrBot 配置 provider（双 provider：主 `hy4-preview-f`，回退 `hy3`）
- [x] AstrBot 配置 aiocqhttp 平台（`127.0.0.1:6199` + 32 位 token）
- [x] NapCat 侧加 WebSocket 客户端指向 `ws://127.0.0.1:6199/ws`（WebUI API 热写入）
- [x] 链路自检：AstrBot 日志出现「适配器已连接」，全链路握手成功
- [x] 账号迁移：6 个账号（5 国际服 + 1 国内服）已复制到目标机，模型数 34 → 55
- [x] 目标机网关关闭全部定时任务（只留余额刷新），避免与操作机抢保活
- [x] `tools/sync-auths.ps1` 写好并实测（首次推送成功、当天二次运行正确跳过）
- [x] 计划任务 `QQBotStack-authsync` 已注册（登录时 + 每小时重试）
- [x] 模型回落：`provider_id=wb2api-hy4f`、`fallback_provider_ids=[wb2api-hy3]`
- [x] AstrBot 改由计划任务 `QQBotStack-astrbot`（onstart/SYSTEM）常驻，开文件日志
- [x] 新增插件 `qqbotstack_guard`：指定群 + @/关键词/随机插话，其他群不回复
- [x] 回复相关配置：`reply_with_mention`、`segmented_reply`、`admins_id`
- [x] 装第三方插件 `astrbot_plugin_meme_manager` v5.2.6（依赖已装、加载成功）
- [x] 表情包：官方包已装、实测 34 条回复零配图，后因画风不符卸载（原包备份在插件数据目录 `backup/`）
- [x] 账号收藏表情建包 `qq-fav-001`（25 张 / 10 类，已设默认）
- [ ] **人工**：群里 @ 一次、发一条含关键词的句子、发一条无关的，确认三种行为
- [ ] **人工**：私聊发一条确认照常回复
- [ ] 待定：是否用 `group_chat_plus`（读空气）替换 guard 的随机插话
- [x] 人格提示词：按《绿海设定_v6》7.1 重写（754 字 + 8 组预设对话），已写入目标机 `personas.default`
- [x] 世界书同步：v6 + 粗纲 v3 + 人物口吻 → 149 条（1 常驻 + 113 设定 + 34 剧情 + 1 口吻），已部署并重启
- [ ] 开机自启核对（wb2api / astrbot / NapCat / authsync 四个任务）
- [ ] `git init` 与远端（等用户确认）

## 已确认的决策

| 项 | 决定 |
|---|---|
| 启动器 | 用 AstrBot Launcher + 开机自启（用户选 A） |
| 账号池 | **本轮不迁移**；用户将在目标机登录一个新的 WorkBuddy 国际服账号 |
| 网关 | wb2api 直连（不搬 zgate） |
| 仓库远端 | 先本地，GitHub 仓等用户说 |

## 真机实测结论（2026-10-26）

- `wb2api` 以计划任务 `QQBotStack-wb2api`（SYSTEM / onstart）运行，`127.0.0.1:7863`，面板 200。
- `/v1/models` 在**没有账号时返回 0 条** —— 模型目录由账号聚合而来，登录账号后才有。
- `global:hy3` 实测可用；**推理模型**，`max_tokens=16` 时正文为空、300 时正常。
- SSH 会话里 `Start-Process` 起的进程会随会话结束被杀 → 必须用计划任务承载。
- 远程 PowerShell 输出默认 GBK，探测脚本须强制 UTF-8（PITFALLS P10）。

## 待解决的问题

- NapCat 安装器是控制台交互程序、无命令行参数，必须人工跑。
- 目标机未装 QQ，OneKey 安装器会代装（体积较大，耗时取决于网络）。

## 人格与世界书同步（2026-10-26）

- 人格：按《绿海设定_v6》7.1 重写梵铭，`system_prompt` 578 → 754 字；`begin_dialogs` 8 组（16 条）。
  去掉铭的「自由散漫 / 爱逗人 / 嘴上不饶人」腔，改成「苦收在里，热留在外」；QQ 格式规则不变。
- 世界书：`绿海设定_v6` + `绿海剧情大纲_粗纲_v3` + `世界书_人物口吻.md` → 149 条 / 50147 字。
  人物条目按 `###` 拆开，「语言 / 性格」优先；条目加 `priority`，同命中数时人物 > 剧情 > 世界观。
- 部署：备份原 DB / worldbook / main.py / index.html 到目标机 `.work/backup-20261026-persona/`；
  停 `QQBotStack-astrbot` → 更新 DB → 覆盖文件 → 清 `__pycache__` → 重启。
- 验收：AstrBot 日志 `Loaded 1 personas`、`qqbotstack_guard … lore=149`、适配器已连接、6185 监听。
- 修复 旧上下文污染：`conversations.content` 里残留 `setpersona2.py` 时代的
  「蓝头发小姑娘 / 小鲸鱼 / 大白饭」assistant 消息，模型会照着旧人设回答；
  已备份 DB 到 `.work/backup-20261026-persona/data_v4-before-reset.db`，
  清空 `conversations` / `platform_message_history` / `sel_conv_id` 后重启。
  改人格后必须 `/reset` 或清历史，见 PITFALLS P29。
- 验证：清空后新对话实测回复「嗯 那先坐坐 喝口热的」，`think` 已按梵铭 / 拉贵尔理解，
  不再出现「小鲸鱼 / 大白饭」。

## 批次 2：媒体解析与自然点歌（2026-10-26）

状态: 进行中

### 目标

群里分享 B站/抖音/快手/小红书链接或 QQ 小程序卡片时，机器人发媒体/卡片并用梵铭人格接一两句；
群友说「我想听某首歌」时，发 QQ 音乐卡片再接一句。只魔改 `qqbotstack_guard`，
上游 `astrbot_plugin_parser` / `astrbot_plugin_music` 只外部安装、不改源码。

### 已确认决策

| 项 | 决定 |
|---|---|
| 接入方式 | A：上游插件 + 魔改 guard |
| B站策略 | B2：parser 失败时 yt-dlp 兜底；B1 扫码登录可选 |
| 音乐 | 网易云 + 卡片优先（失败降级语音/文本） |
| ffmpeg | 安装（便携版 + `run-astrbot.cmd` 前置 PATH） |
| 分享范围 | 只允许群 + 私聊 |
| 点歌命令 | 单曲直发 |

### 步骤清单

- [x] 踩点：AstrBot 4.29.3 API、`_has_send_oper` 门槛、NapCat music 签名、各平台接口实测
- [x] 出 `docs/DESIGN-MEDIA.md`，用户确认（A / B2 / 网易云 / 装 ffmpeg）
- [x] `qqbotstack_guard` 1.2.0：分享/点歌/聊歌/聊视频唤醒、`parse_share_link` 工具、
      提示注入、parser 接管、yt-dlp/OG 兜底
- [x] 触发词扩展：点歌/聊歌（这首歌、单曲循环、我听的是、BGM、歌…好听、`《歌名》` 等）
      与聊视频（这个视频、视频好看、刷到…视频、这个剪辑/电影/UP 等），视频接话 60 秒冷却
- [x] `config.example.json` 新配置项
- [x] 文档同步：DESIGN-MEDIA / ARCHITECTURE / TOOLS / PITFALLS P24–P31 / NOTICE / CHANGELOG
- [x] 目标机安装 `astrbot_plugin_parser` 1.6.1
- [x] 目标机安装 `astrbot_plugin_music` 3.3.1
- [x] 目标机配置解析器（只启 bilibili/douyin/kuaishou/xhs、50MB/5min、arbiter=false）
      与点歌（网易云、card→语音→文本、comments/lyrics=false、single 模式）
- [x] 目标机安装便携版 ffmpeg 9.0.2，改 `run-astrbot.cmd` 前置 PATH
- [x] 部署 guard 1.2.0 到实例插件目录，重启 AstrBot
- [x] 加载验收：日志无 import/依赖错误，`parse_share_link` / `play_song_by_name` /
      `parse_media_url` 已注册；`on_astrbot_loaded` 已关闭 parser 自动解析
- [x] 群内实测（分享/点歌）：真实群消息出现 `share wake: b23.tv/...`，
      3 秒后机器人用「这首也合今天的天…听着歇会儿吧」接住；随后点歌回复出现
      「我这边两首都送出去了」
- [ ] 新触发词群内实测（可选）：「起风了这首歌很好听」「我听的是起风了」「这个视频好看」
- [x] 脱敏与文档自检：`check-docs.py` / `check-secrets.py --all`

### 实测记录（2026-10-26）

- 插件依赖：`bilibili-api-python 17.4.2`、`yt-dlp 2026.10.21`、`curl_cffi 0.14.0`、
  `gallery-dl 1.32.18` 等已装入实例 venv；`beautifulsoup4` 已存在。
- 启动日志：`qqbotstack_guard 1.2.0`、`astrbot_plugin_parser 1.6.1`、
  `astrbot_plugin_music 3.3.1` 全部加载；`parser auto-parse disabled` 出现在
  `on_astrbot_loaded`；NapCat 适配器已连接；guard 日志 `video=True`。
- ffmpeg 自检：guard 启动日志打印 `<部署根>\runtime\ffmpeg\bin\ffmpeg.EXE`、
  `<部署根>\runtime\ffmpeg\bin\ffprobe.EXE`，确认运行中的 AstrBot 进程 PATH 已生效。
- 假事件全链路：快手 `parse_share_link` 发送 `Image + Video`，返回
  「平台：快手；标题：…；作者：…；链接：…」；B站 412 后走 yt-dlp/OG 兜底，
  发送 `Image + Plain`，返回标题/作者/简介/链接。
- 点歌全链路：`play_song_by_name("起风了")` 搜到网易云，发出
  `send_group_msg` 的 `music` 段（`title=起风了`、`content=冯沁苑(买辣椒也用券)`、
  `audio`/`image` 均存在），工具返回「已通过音源…发送《…》」。
- 模型选工具：在 `parse_share_link` / `parse_media_url` / `play_song_by_name` /
  `query_lyrics_by_name` 同时存在时，B站链接选 `parse_share_link`，
  「我想听起风了」选 `play_song_by_name`。
- 新触发词探针：`起风了这首歌很好听` / `我听的是起风了` 都调用
  `play_song_by_name({"song_name":"起风了"})`；`这首歌叫什么` 不调工具，反问哪首；
  `这个视频里的BGM是什么歌` 不猜歌名，反问哪个视频；`这个视频好看` 接话「啥视频呀发来看看」。
- 真实群消息：`share wake: b23.tv/...` → 机器人接住；随后点歌回复出现
  「我这边两首都送出去了」，说明卡片发送链路已在真机跑通。
- 部署踩坑：PowerShell `$ErrorActionPreference='Stop'` 会把 pip 的 stderr 警告当致命错误，
  已改为 `Start-Process` + 退出码判断（P30）；触发词设计见 P31。

### 待解决的问题

- 小红书有效样本未拿到，需用户提供一条带 Cookie 的笔记链接做实测。
- 群内实测需要用户/群友真实发消息，机器人自己发的不算。
- 音乐签名服务与 qijieya 音频解析都是第三方，稳定性需观察。
- B站未登录时走 yt-dlp 封面兜底；要下视频需 `登录B站` 扫码或确认 ffmpeg PATH 生效。

## 语气回修（2026-10-26）

- 用户反馈「短、不尊重人、没感情」。根因：旧提示词的 30 字上限 +「别人骂你立刻怼回去」+ 网络烂梗规则。
- 调整：平时两三句 / 认真四五句；删掉怼回去；加敬语、共情、先接住情绪；删网络烂梗；`begin_dialogs` 10 组。
- 路由：短消息 `Beam` → `HY3-Free`；provider `max_tokens` 4096 → 16384（推理模型会把预算花在 reasoning 上，正文为空）。
- 清历史：再次清空 `conversations` / `platform_message_history`，避免上一版短冷回复被模仿。
- 验证：直接模型测试「今天被老板骂了」→「先坐下 慢慢说 他骂你什么了」；
  「你是谁」→「梵铭 教堂里的神父 你也可以叫我小伯 怎么 刚介绍完就忘啦」；
  线上「我草」→「怎么了 出什么事了」。

## 接话窗口与统一回复（2026-10-26，已完成；真机对话验证待用户测试）

- 设计确认：30s 窗口 + 3s 静默；`@`/引用机器人 1.5s 短防抖；第二个人不同则单独引用回复。
- 设计正本：[docs/DESIGN-FOLLOWUP.md](docs/DESIGN-FOLLOWUP.md)。
- 步骤：
  - [x] 插件加接话状态、收集、打分、防抖、注入、拆段、引用发送
  - [x] config.example.json 补配置，版本 1.2.1 → 1.3.0
  - [x] 纯函数测试（归一化 / 相似度 / 打分 / 选目标）与状态机模拟，均通过
  - [x] 部署目标机、重启；插件 1.3.0 / followup=True / window=30 已加载，真机对话验证待用户测试
  - [x] ARCHITECTURE / PITFALLS / CHANGELOG 同步

## B站小程序卡片静默不解析修复（2026-10-26）

- 现象：群里发 B站小程序卡片，日志有 `share wake: b23.tv/...`，之后没有工具调用也没有回复。
- 根因：卡片是 `Json` 组件、`message_str` 为空；AstrBot `internal.py` 的 LLM 阶段
  按「无文本且无图片」跳过整条事件（P32）。
- [x] 定位：`agent_sub_stages/internal.py` 的 `has_valid_message / has_media_content /
      has_reply` 判断
- [x] 修复：`qqbotstack_guard` 识别到卡片后，空 `message_str` 写回分享链接（群聊 + 私聊）
- [x] 版本 1.2.0 → 1.2.1，部署到目标机并重启（日志确认 1.2.1 已加载）
- [x] 探针：伪造 `Json` 卡片事件经 guard 后 `message_str` 非空、`is_at_or_wake=True`
- [x] 解析验证：`b23.tv/dIl6dmG` 经 parser 解析成功（标题 + 封面）；
      `www.bilibili.com/video/BV...` 仍 412，走 yt-dlp 兜底
- [ ] 真机群聊发一张 B站小程序卡片复测（需要用户/群友真实消息）

## 报错文案兜底与 Beam 路由（2026-10-26）

### 现象与根因

- 15:52:51 群里收到 `LLM 响应错误: All chat models failed ... 502 ... all upstreams failed:
  WB:global:hy3 -> WB:cn:hy3`。
- 根因：wb2api 免费池 `global:hy3`、`cn:hy3` 同时 429（14003 模型繁忙 / 6021 队列已满），
  zgate 无第三后备 → 502；AstrBot 把错误原文当正文发出，guard 只清 Markdown/emoji。
- 诱因：付费 `hy4-preview-f` 因 credits < floor=100 被 held out，全部流量压在免费 hy3；
  当时还有 `probe_full.py` 在并发测试，撞进同一个限流窗口。

### 改动

- [x] `qqbotstack_guard` 1.3.1：`on_decorating_result` 识别错误签名，替换为
      `error_reply_lines`（默认 10 条，连续两次不重复）；原始错误只写
      `[guard-error]` 日志。新增 `error_reply_enabled`。
- [x] 路由：`model_simple=Beam`（OC 上游，独立额度），`model_complex=HY3-Free`。
- [x] AstrBot 新增 provider `zgate-beam`（model `Beam`，text/tool_use），
      `agent_runner.config.model.fallback_provider_ids=["zgate-beam"]`。
- [x] 备份：目标机 `.work/backup-20261026-errorbeam/`（main.py / metadata / config / cmd_config）。
- [x] 部署并重启（16:04:47 启动，guard 1.3.1、zgate-beam 已加载）。
- [x] 探针：错误替换 6 连测无立即重复、正常文案不受影响；短文本 → Beam，
      长文本 / 图片 / 分享 → HY3-Free；zgate 实测 `model=Beam -> OC:beam-free` 正常。
- [x] 文档同步：ARCHITECTURE 路由说明、PITFALLS P33、CHANGELOG。
- [ ] 真机短消息复测：需等群友发一条 ≤14 字、无图、无复杂词的消息，
      日志应出现 `route -> Beam`。
- [ ] 真机 502 复测（可选）：等上游再次限流时确认群里收到「走神」台词而非错误原文。


## 反问后的待答意图（2026-10-26）

- 背景：机器人反问「想听什么歌？」后，用户超过 30s 只回「晴天」会被 guard 丢掉，
  到不了 LLM，也就不会调点歌卡片。
- 新增 `_pending_media`（`group_id:sender_id`，默认 180s）+
  `MEDIA_MUSIC_ASK_RE` / `MEDIA_VIDEO_ASK_RE`；follow-up 触发与窗口外 guard
  都会消费，置 `qqbotstack_music_intent` / `qqbotstack_video_intent`。
- 配置 `media_pending_enabled` / `media_pending_sec`。
- 测试：状态机覆盖窗口外命中、过期、不同发送者、窗口内命中、视频；模型实测
  「你刚才说：想听什么歌？ / 有人说：晴天」返回
  `play_song_by_name({"song_name":"晴天"})`。
- 部署：已重启加载插件 1.3.1，日志 `pending=True/180.0`；15:40/15:41 已实测发卡，16:03 接话 collect/trigger 正常；超 30s 待答意图待验证。

## 一键启动脚本（2026-10-26）

- 痛点：NapCat 每次要远程登录进 `runtime\napcat\onekey\NapCat.*.Shell` 双击 `napcat.bat`；
  其余三块已有计划任务自启。
- [x] `tools/start-stack.ps1`（操作机侧，经 SSH 驱动目标机计划任务）
  - `-Status` / 无参数（缺什么起什么）/ `-Restart astrbot|gateway|zgate|all`
  - 首次运行上传 `runtime\napcat\run-napcat.cmd` + 建计划任务 `QQBotStack-napcat`
    （登录时触发、交互令牌、NapCat 已在跑则退出）
  - 部署根从 `QQBotStack-wb2api` 任务动作路径反推；主机的 host/user/ssh_port 读 `host/stack.conf`
- [x] `tools/start-stack.cmd` 双击入口 + 仓库根目录快捷方式「启动QQBotStack.lnk」
      （放项目内、不放桌面；`*.lnk` 已加入 `.gitignore`）
- [x] 实测：`-Status` 四块在线；`-Restart astrbot` 40s 后 6185=200、OneBot 重连；
      `run-napcat.cmd /check` 解析到 `NapCat.52230.Shell`，已运行时不重复拉起
- [x] 文档：ARCHITECTURE §5 自启表按实际任务重写（补 zgate、AstrBot 自身任务、
      NapCat 新任务）；TOOLS §1.4；CHANGELOG
- [ ] 待验证：目标机重启并登录后，NapCat 是否随登录自动起来（登录触发任务）
- [ ] 待验证：`schtasks /run /tn QQBotStack-napcat` 在 NapCat 未运行时真能拉起 QQ
      （本次只在已运行状态下验过 guard 分支，没敢打断在线的 QQ 登录态）

## 卡住排查（2026-10-26 16:14）

- 现象：用户回「慢歌1」后机器人只反问「你说个真名儿我放」，没发点歌卡片；
  随后机器人回复后 33 秒的接话没有回应。
- 日志：16:13:56 `[media-pending] set kind=music` → 16:14:04 `collect` →
  16:14:08 `trigger`；16:14:19 模型直接反问、没调 `play_song_by_name`；
  16:14:52 的 33 秒接话被 30 秒窗口挡掉；16:14:28 有一次正常重启（无 traceback）。
- 修复：音乐提示改「像歌名就先搜一次，搜不到再问」；待答意图落盘
  `pending_media.json`；运行窗口 30 → 45 秒；插件 1.3.2。
- 验证：1.3.2 已加载，日志 `window=45.0 pending=True/180.0`；真机复测待用户。

## 表情包返工：官方包卸载与账号收藏导入（2026-10-26）

- 现象：`meme_manager` 日志 34 条回复全部 `去重后的最终表情列表: []`，群聊零配图。
- 根因：旧「分类标记」模式要求回复模型自己在正文输出 `&&分类键&&`；实测同一套提示词
  不带 tools 时 `HY3-Free` 3/3 正常，带真实工具集 6 条只出 1 条，`Beam` 0/4。
- [x] 隔离验证：`_inject_meme_prompt_impl` 在 origin=chat 时提示词注入正常，插件与包无问题
- [x] 开启 `generation.emotion.llm.enabled=true`（`provider_id` 留空＝复用本轮模型），
      选图改由独立请求完成，不再依赖回复正文
- [x] 卸载 `official-001`（画风不符人设）；卸载前完整备份到插件数据目录 `backup/`；
      `selection_rules` 自动指向空的 `builtin-default`
- [x] 导出账号收藏表情：NapCat `fetch_custom_face` / `fetch_custom_face_detail` 实测可用，
      共 25 张（3 GIF / 2 PNG / 20 JPG），原图已留存
- [x] 出 `docs/DESIGN-MEME-EXPORT.md` + docs 索引；`check-docs.py` / `check-secrets.py --all` 通过
- [x] 用户选型：全部 25 张 / 暂不导入 `emoji-recv` / 先测本地文件直发
- [x] 建 `qq-fav-001`：先 10 类，后改为「一张图一个名字」（25 个中文名）
- [x] 分类修正：17（哭）→ `哭哭狗`，23（困）→ `犯困狗`
- [x] 情感辅助模型先开后关：选图准但每轮多 20–27 秒；`emotion.llm.enabled=false`
- [x] 改为模型单轮选图：`emotion.probability=25`、`max_memes_per_message=1`
- [x] `qqbotstack_memechance` 1.0.0 改为「标记提醒 + 泄漏标签清理」：
      在所有 hook 之后补 `&&名字&&` 提醒与真实示例
- [x] 实测：完整真实 prompt + 工具直连模型，带工具 4/4 输出有效名字标记；
      线上 17:40 `&&笑脸狗&&`、`&&流口水&&` 均被剥离并发出图片
- [x] 实测：本地文件发送成功（群历史可见 `image` 段）；`</rfl:parameter>` 一类泄漏标签已清理
- [x] 群内严肃剧情（蒂米死了）25 条回复 0 标记：模型在悲伤场景主动不配图；
      提醒补充「严肃/悲伤可用安慰类名字」+「他走了 → 抱小鸡」示例
- [x] 直连复测：蒂米死了 → `抱小鸡`、忘了他吧 → `冒汗狗`、诵经 → `趴问号`；
      普通玩笑仍出 `笑脸狗` / `近景狗`
- [x] 线上 18:21 `&&哭哭狗&&` 已解析并挂到消息链（chain=3），无发送错误
- [x] 频率再调：`emotion.probability` 25 → 50；开启安慰类随机兜底
      （`fallback_names` 7 个、20%、60 秒冷却），两条路径互斥
- [ ] 观察新频率；再调只改 `emotion.probability` 或插件的 `probability`

## 接话窗口重开与超时排查（2026-10-26）

- 现象：统一回复后不再接话；点歌卡片下面没有接话窗口；回复 11 秒偏慢。
- 根因：`after_message_sent` 在手动唤醒 / 工具卡片空正文路径不一定触发；
  zgate 日志 `Beam -> OC:beam-free` 后 `context canceled` 要等 50–120 秒，
  OpenCode 免费上游不返回；`DeepSeek-4.1-Flash` rate limit / no healthy account；
  `HY3-Free` 唯一稳定但 `global:hy3` 频繁限流后回退 `cn:hy3`。
- 修复：`on_decorating_result` 也开窗口；媒体回合在 `on_llm_request` 开
  provisional window；待答意图命中时 debounce 1.5 秒；媒体回合跳过世界书注入；
  窗口 45 秒；插件 1.3.3。
- 验证：1.3.3 已加载 `window=45.0 pending=True/180.0`；真机卡片接话待验证。

## 设定定本同步：世界书与人设重写（2026-10-26）

- 触发：EmeraldEden 设定已整理为十三册定本，旧世界书仍按 `绿海设定_v6` 单文件切分。
- [x] 世界书：从 EmeraldEden `设定/` 十三册 + `大纲/01-总览与基线` + `大纲/02-分章粗纲`
  重新生成，**148 条 / 48,965 字**（1 常驻 + 112 设定/人物 + 34 剧情 + 1 附录）。
  - 人物页归入「卷七 · 人物」；口吻速查、已接好的线、序章补 `##` 包装，避免被生成器丢掉。
  - 卷级关键词（教堂 / 绿海 / 火种 / 圣遗物 / 基地）与单字人名（凯 / 汤姆）在生成后补进 keys。
  - 剧情条目优先级降到 45，具体设定优先；关系矩阵 60，人物页 80。
- [x] 人设：按 7.1 重写为 **1,347 字**（原 1,155 字），补「拉贵尔 → 拉斐尔」的名字来历、
  六条性格（先伸手 / 爱笑 / 会闹 / 对小东西认真 / 苦只在没人时 / 没觉得自己该担）；
  `begin_dialogs` 仍 10 组 20 条。
- [x] 部署：停 `QQBotStack-astrbot` → 备份 DB / worldbook / view 到目标机
  `.work/backup-20261026-worldbook-v7/` → 覆盖 worldbook 与 WebUI 视图 → 更新 personas →
  清空旧会话 → 启动任务。
- [x] 验收：`Loaded 1 personas`、`qqbotstack_guard 1.3.2 … lore=148`、OneBot 已连接、
  6185=200；DB 里 persona 与本地 `persona_v7.json` 哈希一致，世界书 JSON 哈希一致。
- [x] 离线探针：「神父 今天好累啊」「教堂今天下雪了吗」「你还记得犹达斯吗」「你是谁」
  四条均按梵铭口吻回复，命中对应世界书条目（教堂 / 犹达斯 / 人物 / 常驻）。
- [x] 文档：ARCHITECTURE §1.3 / §1.4、CHANGELOG。
- 追加：16:35 日志 `route -> Beam`，远程 `config.json` 的 `model_simple` 被改回 Beam；
  已改回 `HY3-Free` / `HY3-Free`。Beam 的 `OC:beam-free` 上游 50–120 秒超时，
  恢复健康前不再路由；这解释了最近的卡顿。

## 群消息不回复排查（2026-10-26 16:36–16:52）

- 现象：群里发消息机器人不回；NapCat 日志 `反向WebSocket ... ECONNREFUSED 127.0.0.1:6199`。
- 根因：AstrBot 在 16:36–16:51 连续重启（部署 + 诊断），6199 短暂不可用；
  NapCat 每 5 秒重连，重连失败期间的群消息直接丢失。NapCat 进程一直正常。
  计划任务触发器没有重复项；当前核心 16:46:38 起稳定。
- 修复：接话窗口 45 → 300 秒；`media_pending_sec` 180 → 300；`followup_max_chain` 3 → 10。
- 速度：meme_manager 的 `generation.emotion.llm.enabled` 被打开，每条回复前多跑一次
  情感模型（zgate 16:42:38 / 16:42:52 两次请求）；已关到 false。
- 排查脚本：`probe_emotion_beam.py` 在单独打 Beam，不是机器人；建议停掉。
- 当前：插件 1.3.3，`window=300.0 pending=True/300.0`。
- 测速（17:00）：HY3-Free 简单 14.7s / 点歌 15.3s；Beam 冷启动 45s 超时，
  热请求 2.6/5.9/3.9s，点歌 2.2s（思考 36 tokens）。Beam 本身快，慢在上游冷启动。
  当前 fallback 是 zgate-beam + 180s source timeout，HY3 限流时可能卡很久；
  建议 Beam 单独 8–10s 超时 + HY3 回退，或先移除 Beam fallback。

## 模型链路 Beam → HY3 → HY4（2026-10-26 17:05）

- 配置：`zgate-beam`（Beam，10s）主；`zgate-router`（HY3-Free，60s）、
  `zgate-hy4`（HY4-Pre-Free，60s）fallback；`agent_runner` 主 Beam，
  fallback `["zgate-router","zgate-hy4"]`。
- 图片：AstrBot `_select_image_chat_provider` 自动跳过无 image 模态的 Beam，切 HY3；
  HY3 失败再 HY4。guard `routing_enabled=false`，不覆盖 provider 链。
- Beam 超时诊断：zgate 直连 Beam 1.2s 正常；之前 45s 是 OpenCode 冷启动/连接挂起，
  不是插件代码；10s 超时 + fallback 兜底。
- 实测：17:05:22→17:05:24、17:05:31→17:05:33 文本回复各 2 秒，zgate `model=Beam`。

## 歌词评论与逐句分段（2026-10-26 17:16）

- 歌词工具：`query_lyrics_by_name` 成功时补返回歌词摘录（去 LRC 时间戳、截 220 字），
  模型拿到摘录后再评论；补丁为运行时，备份 `music-main-before-lyrics-return.py`。
- 歌词意图：guard 加 `LYRICS_INTENT_RE` + 歌词提示；guard 1.3.4。
- 断句：`platform_settings.segmented_reply` regex 加 `\n`，threshold 100000，
  cleanup `[\s。]+$`；实测三句文本拆成三条。
- 实测：插件加载成功；主回复仍走 Beam；歌词请求待群里实测。

## 身份 / 敬重 / 长文 / 接话挤压修复（2026-10-26 17:30–18:05）

- 触发：群聊里出现四个问题：①两个人同时问会挤掉一个；②把自己当成拉斐尔；
  ③对玟德不敬、语气放荡；④所有人都只回短文，悠塔「以前话最多」的设定也讲不出来。
- [x] 世界书：按 EmeraldEden 定本 + `.work/世界书补充.md` 重建，**169 条 / 54,554 字**；
  新增 `身份辨析`（priority 95）与 `人物口吻速查`（85），覆盖「拉斐尔 vs 拉贵尔」
  和「玟德是长辈、不是下属」；重新生成 WebUI 视图。
- [x] 人格：扩到 **1,694 字 / 17 组 34 条 begin_dialogs**；补身份、对玟德的敬重、
  长文规则、不夹英文、不跟网络梗、不写括号旁白、不说打电话/挂电话；
  长文 few-shot：关系链 127 字、悠塔 144 字、蒂米 103 字。
- [x] guard 1.3.5：
  - `followup_debounce_sec` 3 → 6 秒；
  - 生成期间到达的接话不再丢弃，等当前回复发完后 `late release` 单独接住；
  - 统一回复提示明确「两个人的问题都要有回应」，第二个人不同才写 `<<<SECOND>>>`；
  - `_clean_style` 清 `</rfl:parameter>` 这类残留标签，`\n{2,}` 压成单个 `\n`。
- [x] 断句：`words_count_threshold` 100000 → **100**；保留 regex 含 `\n`、
  cleanup `[\s。]+$`。超过 100 字的长文整条发，短回复逐句拆。
- [x] 部署：备份到目标机 `.work/backup-20261026-final/`（DB + cmd_config + guard +
  music main）；覆盖 guard / worldbook / view / persona；清空 conversations、
  platform_message_history、sel_conv_id；`QQBotStack-astrbot` 任务重启。
- [x] 验收：启动日志 `Loaded 1 personas`、guard 1.3.5、`lore=169`、OneBot 已连接；
  离线探针（真实 zgate + 已部署人格/世界书）：
  「你是谁」18 字不认拉斐尔；「玟德还好吗」20 字称玟德先生；
  「介绍一下你身边的人」127 字；「悠塔以前是不是话很多」144 字语气沉；
  「今天好累啊」32 字；「我要绷不住了」15 字；「神父你好犟」11 字无英文；
  两人不同问题 → 主回复 + `<<<SECOND>>>` 两段。
  真机日志 18:00:51 `defer late` → 18:00:53 `late release`，第二条接话未被吞。
- [x] 文档：ARCHITECTURE §1.3/§1.4/§1.6、DESIGN-FOLLOWUP §1/§6.4/§6.6/§8/§10/§14、
  PITFALLS P22/P37 + 新增 P38–P42、CHANGELOG。
- 待观察：群里真人多轮对话的体感；若仍偶发「太短」，优先看是否命中长文规则，
  再考虑把 `words_count_threshold` 调到 80–120 之间。
- 追加 18:11：人格再收紧（不夹英文、不写括号旁白、不说打电话/挂电话），
  begin_dialogs 定稿 17 组 34 条、1,694 字；再次清空 conversations / history /
  sel_conv_id，用干净上下文启动。启动日志：`Loaded 1 personas`、guard 1.3.5、
  `lore=169`、OneBot 已连接；persona 1,694 / 34、debounce 6.0、threshold 100。

## 心动值 / 主动接话 / 表情包唤醒 / 工具路由（2026-10-26 18:30）

- 触发：17:23 之后的群聊里出现四个体感问题：问「月光喜欢吗」直接读缓存、不调工具；
  只会顺着别人说、不会自己起话题、不会拿世界书编日常；每条都接、回复太多后又
  撞 `chain` 上限装死；纯图/表情包一来直接不说话。另发现新设定已删蒂米、商路人物
  改成赫尔墨斯，旧人格里的「凯 / 蒂米」需要清理。
- [x] 心动值：每群 `interest` 初始 70，每分钟 -1.0；点名 +25、相关 +6、回复 -2、
  无关 -8；低于 20 只接直接点名。窗口内问句/陈述分别按 0.1/0.2 的 bigram 重叠
  做相关性门槛；无关消息只掉心动值，不回。直接点名清零 `chain`；`random_prob`
  0.25 → 0.03。
- [x] 图片/表情包：纯图不再被 `stop_event()` 吞掉；直接点名或心动值 ≥50 + 30 秒
  冷却时放行，设置 `qqbotstack_image_turn`，AstrBot 自动切 HY3/HY4；生成期间到达
  的图走 `defer late` / `late release`；新增图片提示。
- [x] 工具路由：`routing_enabled=true`，短闲聊 Beam，复杂/带图/工具轮 HY3；
  `COMPLEX_HINTS` 补「喜欢/介绍/关系/世界/设定/故事/以前/过去」等；
  `zgate-beam-source` timeout 10 → 20；`[工具优先]` 提示对「喜欢/听过/知道…吗」
  注入。工具探针在「月光喜欢吗」上返回 `play_song_by_name({"song_name":"月光"})`。
- [x] 人格：补主动接话、问回去、带新细节、世界书当日子讲、不要用「我不懂」挡回；
  1,694 → 2,187 字 / 21 组 42 条；加「你喜欢什么」「赫尔墨斯是谁」
  「今天教堂里有什么」示例。
- [x] 世界书：按当前 EmeraldEden 定本重建，299 条 / 84,790 字；
  新增赫尔墨斯、乌列尔、卡戎与细纲；删除蒂米、商路人物改为赫尔墨斯；
  补 `赫尔墨斯之眼`、`教堂日常`；别名补 `赫尔墨斯=赫尔墨斯之眼`、`文德=玟德`。
  人格和补充条目里的「凯 / 蒂米」已清掉（搜过确认）。
- [x] 部署：备份 `.work/backup-20261026-interest/`；覆盖 guard 1.4.0 / worldbook /
  view / persona；清空 conversations / history / sel_conv_id；重启任务。
- [x] 验收：启动 `qqbotstack_guard (1.4.0)`、`lore=299`、OneBot 已连接；
  探针「赫尔墨斯是谁」「介绍身边的人」「你喜欢什么」「拉斐尔/拉贵尔关系」均符合
  新定本；guard 单测覆盖心动值、无关忽略、低值点名、纯图高低心动值、提示注入。
- [ ] 真机待观察：群里发纯表情包是否切 HY3/HY4 并接话；心动值下降后是否明显少水群；
  连续多轮后是否还会撞 `chain`。看日志关键字 `[interest]`、`[image] wake`、
  `route -> HY3-Free`。
- 追加 18:40：长文分段恢复。`words_count_threshold` 100 → 100000；guard 新增
  `_split_long_for_qq`，>90 字的长文按空格聚成 60 字小段并插入换行，短回复不插换行。
  实测 125 字关系链 → 3 段；5 字闲聊 → 1 段。流式仍为 false（17:42 之前就是 false，
  AstrBot 流式分支会跳过 segmented_reply）。
- 追加 18:50：修两处回归。
  - 心动值 60 以上普通陈述也接（纯回执「嗯/哦/好/知道了/笑死」除外），
    避免 18:44 那种 interest=78–95 却把「机器人重启了」「难怪没回复你」全判无关。
  - 直接 @/引用/叫名字的那条改为 `direct_pool` 主目标，不再被更相关的第二个人顶掉；
    `_handle_followup` 的 `is_direct` 改用 `_is_addressed`，关键词也按直接点名算，
    防抖 1.5 秒。修复 18:42 长毋相忘 @ 的问题被 limpid 的尾巴问题盖掉。

## 中期世界书重写（2026-10-26 18:55）

- 触发：设定集新增赫尔墨斯、乌列尔、卡戎并重写多篇；当前角色扮演只走中期
  （第七至十二章前后），教堂日常只有梵铭、玟德、铭，拉梵（人间体）来访。
  18:30 的 299 条全本世界书把后期章节、人物结局和作者级真相一起注入，探针里
  出现了「赫尔墨斯是乌列尔的代行者」「犹达斯说不了话」「火种是钥匙」。
- [x] 读设定：EmeraldEden `设定/00–13`、`08-人物/00–09`、`大纲/01`、
  `大纲/细纲/02-卷二-借名`。确认中期住客/来客、拉梵人间体、犹达斯与卡戎的
  登场时点，以及后期才揭的真相（拉斐尔=拉梵、赫尔墨斯=乌列尔代行者、
  火种=方舟钥匙、静默协议/双核）。
- [x] 世界书：新建 `.work/世界书_中期.md` + `.work/build_midworldbook.py`，
  手工编排 **35 条 / 6,997 字**（2 条常驻 348 字）。
  - 常驻：当前阶段 + 世界观总览；
  - 世界 / 火种 / 遗物 / 教堂 / 薪火城：只收梵铭此刻知道的部分；
  - 人物：梵铭、铭、玟德、拉梵、赫尔墨斯、露西、悠塔、乌列尔（只闻其名）、
    卡戎（未登场）；
  - 优先级：身份辨析 95、口吻速查 85、四主角 84、悠塔/赫尔墨斯 80、
    关系矩阵 78、乌列尔 65、卡戎/教堂/硬约束 60、火种系 55、世界 50；
  - 边界：犹达斯只留悠塔一条（没听过这个名字，别和卡戎混）；卡戎未登场；
    乌列尔没见过本人；不写第十三章以后、结局、静默协议、双核、方舟；
  - 作者级真相不写进注入正文，只写「梵铭不知道他的底细」；
  - 单字 `铭` 不再加进关系矩阵 keys，避免「梵铭」一次算两票。
- [x] 人格：从 `.work/persona_v6.json` 生成 `.work/persona_mid.json`，
  **2,215 字 / 24 组 48 条**。保留身份、玟德敬重、长文三套修复；
  - 删 few-shot「犹达斯以前叫悠塔…说不了话」「赫尔墨斯是乌列尔的代行者」；
  - 「介绍身边的人」改为玟德 / 铭 / 拉梵 / 赫尔墨斯；
  - 新增「悠塔以前是不是话很多」「火种是什么」「拉梵是谁」三条长文示例；
  - 英文禁用词补 `roughly` / `occasional` / `faces`。
- [x] 部署：备份到目标机 `.work/backup-20261026-mid-worldbook-v3/`；
  覆盖 worldbook / view / persona；清空 conversations / platform_message_history /
  sel_conv_id；重启 `QQBotStack-astrbot`。
- [x] 验收：启动 `Loaded 1 personas`、guard 1.4.0、`lore=35`、OneBot 已连接；
  世界书 JSON / WebUI 视图 SHA256 与本地一致；persona 2,215 / 48，
  conversations / history / sel_conv 均为 0。9 条重点探针全过：
  「你是谁」18 字；「你是不是拉斐尔」44 字；「玟德还好吗」20 字称先生；
  「介绍一下你身边的人」132 字无犹达斯、含拉梵；「悠塔以前是不是话很多」114 字
  语气沉；「拉梵是谁」141 字不揭底；「赫尔墨斯是谁」48 字不交代行者；
  「犹达斯是谁」14 字不串卡戎；「火种是什么」95 字不夹英文。
- [ ] 待观察：群里真人多轮对话的体感；若再出现英文夹词，优先补 few-shot，
  不要只加禁用词。模型路由日志仍有 `Provider zgate-router was not found`
  警告，与本次世界书无关，但会影响 HY3 fallback，另行处理。

- 追加 18:55：现场发现目标机在 18:47 后把 `worldbook.json` 换成了 **35 条 / 6,997 字**
  的「当前阶段·中期」版本，persona 也被外部改成 2,215 字 / 48 条；这不是本次代码
  改动，**没有覆盖**。当前实例 `lore=35`，如果这是误覆盖，需要把 299 条全量版推回。
- 最终参数：`interest_initial=70`、`interest_decay_per_min=1.0`、`interest_high=60`、
  `interest_threshold=20`；心动值 ≥60 时普通陈述也接（纯回执除外），直接问的人
  永远优先；关键词「神父/拉贵尔/小伯」也按直接点名算。
- 追加 19:35（澄清）：18:55 的 35 条 / 6,997 字中期版是本人按用户要求部署的，
  **不是外部误覆盖**；299 条全量版不推回。当前 RP 只走中期，详见「中期世界书重写」。

## 音乐卡片封面修复（2026-10-26 19:30）

- 现象：点歌卡片能发出，标题/歌手正常，封面为空；换歌也一样。
- 根因链：`netease` 搜索接口不带封面 → `fetch_extra` 用 `api.qijieya.cn/meting`
  补到的是**重定向地址** → NapCat 的 `card` 模式把封面交给音乐签名服务
  （默认 `http://106.55.0.102:10087/`，失败回退 `https://ss.xingzhige.com/music_card/card`）
  → 签名服务对重定向地址返回 `qq.ugcimg.cn` 的 `preview`，实测 **404**。
- [x] 修复：给 `astrbot_plugin_music` 的 `BaseMusicPlayer` 补
  `resolve_cover_url()`；`_send_card` 在发卡前先把封面按
  `allow_redirects=True` 解析成最终 CDN 直链，再交给 NapCat。
- [x] 验证：重定向 → `https://p3.music.126.net/...jpg?param=300y300`；
  主签名服务 `preview` 返回同一直链；GET 200 / `image/jpg`。
  备选签名服务仍返回 404 的 `qq.ugcimg.cn`，只能当最后兜底。
- [x] 部署：备份 `.work/backup-20261026-music-cover/`；覆盖
  `core/platform/base.py`、`core/sender.py`；清 `__pycache__`；重启任务。
  启动日志：`astrbot_plugin_music (v3.3.1)` 正常加载、OneBot 已连接。
- [ ] 待观察：群里真机点一首歌看封面；若仍无图，看 `[音乐卡片]` /
  `[音乐卡片签名]` 日志，确认交给 NapCat 的 `image` 是否已是
  `p*.music.126.net` 直链。

## 接话出圈 / 漂移闸门（2026-10-26 20:10，guard 1.5.0）

- 触发：用户反馈群里聊起 AI、游戏等话题，机器人还在硬接，内容空泛；心动值越高越明显。
- 根因：`interest_high`（≥60）时 `_followup_candidate` 直接 `return True`；
  话题相关用滚动拼接的最后 240 字算 bigram，新话题只要沾旧词就能混过去。
- [x] guard 1.5.0：
  - 新增 `OUT_OF_SCOPE_RE`（AI / 游戏 / 技术 / 娱乐圈）、`IN_SCOPE_RE`
    （神父日子里的具体词）、`TOPIC_STOP_BIGRAMS`（过滤今天 / 你们 / 觉得等通用词）；
  - 开窗记 `topic_seed`（点名消息 + 机器人回复）；消息和 seed、上一条接话都没有
    实际内容重合 → 判漂移；
  - 出圈 / 漂移扣 `scope_loss`（12）并 `scope_close_window` 直接关窗；
  - 高心动值只降门槛（问句 0.05 / 陈述 0.1），不再无条件接；
  - 直接 @ / 引用 / 叫名字仍一定回；
  - `_build_followup_block` 补「不要为了接话而接话」。
- [x] 单测：`.work/test_followup_rules.py` 增加出圈 / 漂移 / 候选顺序断言，全部通过。
- [x] 部署：备份 `.work/backup-20261026-scope-guard/`；覆盖 `main.py` /
  `metadata.yaml`；实例 `config.json` 新增 4 个键；重启任务。
  启动日志 guard 1.5.0、`lore=35`、OneBot 已连接。
- [ ] 待观察：群里真实转话题时看 `[interest] ignore scope` / `ignore drift`；
  如果过于安静，优先放宽 `IN_SCOPE_RE` 或把 `scope_loss` 降到 8–10；
  如果还水，先把 `interest_high` 的门槛再降或把 `scope_min_chars` 调到 4。

## 重复意象 / 悠塔 / 赫尔墨斯修正（2026-10-26 19:50，persona v8）

- 触发：用户指定看 19:09 之后的群聊。15 分钟内机器人 7 次提到罐子、5 次提到汤；
  19:14 问悠塔时答成「他从前话最多……后来那夜的事我不常提」，像在讲童年趣事；
  19:15–19:24 赫尔墨斯被当成随叫随到的帮手（抄歌词、修机关、带话）；
  19:10 回答「玟德长啥样」时连续调用 `web_search_anysearch` / `astrbot_grep_tool` /
  `astrbot_execute_shell` 翻主机文件，最后仍是编的；同一轮夹了英文 `rough`；
  19:16–19:24 几乎每条都带 `&&表情名&&`。
- 根因：
  - 人格把「罐子、汤、草球、雪、盐、碗」当成唯一的「具体细节」范例，还要求
    「每次回答尽量带一个新的具体细节」；begin_dialogs 里「你喜欢什么」「今天教堂里
    有什么」「我最近总觉得没人需要我」「汤是不是又淡了」四条都在示范罐子/汤。
  - 世界书「教堂的日常」把罐子/汤加粗成清单；悠塔条目写「出了事 / 梵铭以为他死了 /
    不知道他还活着」，模型可以往轻了演；赫尔墨斯条目只写「常来送货」，没有
    「不是帮手」的边界。
  - `qqbotstack_memechance` 的提醒原文是「普通聊天尽量每条都配一张」。
  - `cmd_config.json` 开着 `web_search=true` 和 `computer_use_runtime=local`，
    模型因此拿到 web_search / grep / shell / file 工具。
- 改动：
  - persona v8（`.work/persona_mid_v8.json` → `.work/persona_mid.json`）：
    3029 字 / 52 条。新增「不要把同几样东西反复垫话」段；把「每轮加细节」改成
    「先接对方，再决定要不要添」；悠塔改成明确的死亡 + 自责 + 短句/停顿规则；
    赫尔墨斯改成「隔些日子来送货的商人，不是帮手」，禁止让他抄歌词、修机关、
    带话，送信找露西；英文加输出前自检；AI 话题不解释不讲道理；
    begin_dialogs 删掉 4 条罐子/汤示范，补「悠塔话多」「他真的很爱数罐子」
    「赫尔墨斯最近来过吗」「现在ai说话都这样」四条边界示例。
  - 世界书（`.work/世界书_中期.md` 重建，35 条 / 7,447 字）：
    「教堂的日常」改成可轮换的细节池（铜钟、藤蔓、光蕊花、地板吱呀、柴火、
    蜡烛脂、圣坛第三块砖、门口的路、露西的信），罐子/汤只作背景；
    悠塔条目明确「死在十岁那夜 / 梵铭一直觉得是自己害死的 / 不是童年趣事」；
    赫尔墨斯条目补「不是工具人、不要提议让他带话、送信找露西」；
    关系矩阵、人物口吻速查、硬约束同步。
  - `qqbotstack_memechance`：提醒改为「配图是调味，约四轮一次，不要连续两轮」；
    实例 config `enabled=false`、`probability=0.25`、`cooldown_sec=180`，
    只保留模型自己写的 `&&名字&&`，不再随机补图。
  - 实例 `cmd_config.json`：`web_search=false`、`computer_use_runtime=none`、
    `add_cron_tools=false`、`computer_use_local_permissions.{admin,member}` 的
    `allow_execution/allow_network` 全关。插件工具
    `play_song_by_name / query_lyrics_by_name / parse_media_url / parse_share_link /
    search_memes` 保留。
- 部署：备份到目标机 `.work/backup-20261026-persona-v8` 与 `persona-v8b`
  （DB + worldbook + view + memechance main/config + cmd_config）；覆盖
  worldbook / view / memechance main；清 `conversations`、`platform_message_history`、
  `sel_conv_id`；重启 `QQBotStack-astrbot`。
- 验收：启动 `Loaded 1 personas`、persona 3029 / 52、guard `lore=35`、
  `memechance enabled=False p=0.25 cooldown=180`、OneBot 已连接；
  启动工具列表只剩插件工具。离线探针（真实 DB 人格 + 世界书 + 新表情提醒，
  HY3-Free）11 例：
  - 连续六轮「今天好累 → 他真的很爱数罐子 → 这罐子是非数不可吗 → 推荐一首歌 →
    你喜欢什么 → 今天教堂里有什么」：罐子只在用户提及时出现 1 次，汤 0 次；
    具体细节换成光蕊花、柴火气味、蜡烛脂/旧木头、门口结霜的路、露西的信。
  - 「悠塔是谁」→「他死在十岁那夜 / 是我没护住他」；「悠塔以前是不是话很多」→
    先讲声音和草球，最后落到「他死在那一夜 / 是我害的他」。
  - 「你还记得犹达斯吗」→ 没听过这个名字，想到阿悠，反问是谁，不串卡戎。
  - 「赫尔墨斯最近来过吗」→ 前些日子送盐、没多留，不再提议托他带话。
  - 「现在ai说话都这样」→「随你当我是啥」不再解释 AI。
  - 英文 0；表情标记 0/11，不再每轮配图。
- 备注：19:43 部署后，19:44 外部又部署了 guard 1.5.0（话题漂移闸门）并重启；
  本次 persona/worldbook/memechance/cmd_config 的 SHA256 与本地一致，未被覆盖。
- 待观察：
  - 群里真人多轮体感；若罐子/汤又回来，先查旧会话是否没清、或 begin_dialogs 是否
    被别的部署换回旧版。
  - 表情 0/11 可能偏低；若长期不配图，把提醒里的「四轮」改成「三轮」，或在
    图片回合由 guard 注入一次。
  - guard 1.5.0 的 `IN_SCOPE_RE` 仍把「罐子 / 汤」当人设领域词，只影响是否接话，
    不影响回复内容；若发现它把话题硬拉回罐子，再改 guard 的关键词表。
  - 工具关闭后，模型遇到真实世界问题会照实说不知道；以后若需要联网查资料，
    单独开只读搜索工具，不要开 shell/grep/文件工具。
- 追加 19:58（guard 1.5.1）：19:10 的「他长啥样」当前消息里没有「玟德」二字，
  世界书只按当前消息取词，人物页没命中，模型才去翻主机文件。guard 新增
  `_lore_match_text`：当前消息含代词（他 / 她 / 它 / 这人 / 那人 / 这个 / 那个）
  时，把上一轮 `bot_text` 的末 240 字一起拿来匹配；单测补
  `lore followup OK`。部署 guard 1.5.1 + metadata.yaml，备份
  `.work/backup-20261026-lore-followup`，重启；启动日志 guard 1.5.1、`lore=35`。
  模拟「他长啥样」+ 上一轮「玟德先生是那种……」，命中玟德人物页（含外貌）。

## 按 QQ 号的长期记忆（2026-10-26 20:05）

- 触发：用户要求认人、记住名字、给每个人划分记忆；先查官方能力。
- [x] 踩点：AstrBot 没有第一方按用户记忆插件；内置 `provider_ltm_settings`
  只是群上下文（群消息历史 / 图片描述 / 主动回复）。候选对比见
  [docs/DESIGN-MEMORY.md](docs/DESIGN-MEMORY.md)。
- [x] 选型：`astrbot_plugin_long_memory` 1.2.0（社区，MIT，AstrBot>=4.24.0）。
  按 QQ 号一人一份 JSON；记称呼 / 喜好 / 厌恶 / 住处 / 工作 / 习惯；不额外调模型；
  注入 `extra_user_content_parts`，不碰 `system_prompt`。
- [x] 离线验证：`我叫小林，我喜欢淡一点的咖啡` / `我叫阿杰，我不喜欢香菜`
  → `10001.json` / `10002.json` 两份；注入块互不串。
- [x] 部署：备份 `.work/backup-20261026-long-memory/`；安装插件；配置
  `enable/extract/inject=true`、`max_items=30`、`inject_max_items=30`、
  `inject_max_chars=500`、`ttl_days=180`、`allow_group_cmd=false`；重启。
- [x] 验收：启动 `astrbot_plugin_long_memory (1.2.0)`、
  `[long_memory] loaded (extract=True inject=True max_items=30 ...)`、
  guard 1.5.1 同时加载、OneBot 已连接；`plugin_data/.../memory` 等目录已建。
- [ ] 待观察：真机里对机器人说「我叫X / 我喜欢Y」后 `/记忆` 是否出现；
  当前只在 LLM 请求触发时抽取，群里没叫到机器人的消息不会学；
  多人统一回复只注入最后说话人的记忆；称呼只认自报句式。
- 第二阶段（未做）：guard 名字簿（自动群昵称）、`qq_user_memory`（跨群原文）。

## 世界书同步：梵铭的第二只眼睛 / 奶牛猫赫尔墨斯（2026-10-26 20:10）

- 触发：EmeraldEden 最近两轮改动（第二只眼睛 7 个文件 + 奶牛猫赫尔墨斯 4 个文件，
  共 11 个）。读的原文：`设定/03-绿海地理与居民`、`设定/05-火种体系`、
  `设定/08-人物/01-梵铭`、`设定/08-人物/08-表演规则`、`设定/08-人物/05-赫尔墨斯`、
  `设定/08-人物/00-人物索引`、`设定/00-README`、`大纲/01-总览与基线`、
  `大纲/02-分章粗纲`、`大纲/细纲/01-卷一-灰烬`。
- 同步到中期世界书（36 条 / 8,006 字）：
  - 梵铭身份与外形：删「近全盲」，改成「眼睛不是唯一的一双；睁眼只有光和影子，
    闭眼更清楚；不是看不见，是不用眼睛看；看脉络（热度/流速/断点），认人不靠长相；
    不能读心、不能看文字，腐化区是噪点」。
  - 新增独立条目「梵铭 · 他怎么『看』人」（245 字，priority 84）：
    不转头、看脉络不看脸、闭眼更清楚、火种把内视变成另一只眼睛、看得越深烧得越快；
    keys 补 `眼睛 / 内视 / 光网 / 脉络 / 断点 / 看得见 / 看不见 / 读心 / 感知`。
  - 火种条目：补「这条通道对梵铭具体就是光网」，看得越深烧得越快。
  - 赫尔墨斯：补「奶牛猫兽人，黑白相间的毛」；保留旧手套 / 银眼 / 影子慢半拍，
    但不写「乌列尔的代行者」——中期梵铭不知道他的底细。
  - 人物口吻速查、聊天硬约束同步「看得见脉络、看不见脸、不能读心；他不是全盲」。
- 人格 v9（3,297 字 / 58 条）：自我描述删「近全盲」，改成「不是看不见，是不用眼睛看」；
  新增眼睛口径和 3 条 few-shot（眼睛 / 玟德的脸 / 赫尔墨斯是猫）。三条 few-shot
  放在 `begin_dialogs` 开头，不放在末尾——放末尾会让模型把它们当成「刚发生过的
  对话」，用户再问就会回「刚才答过了」。
- 部署：备份 `.work/backup-20261026-eye-sync` / `eye-sync-v2`；覆盖 worldbook / view /
  persona；清 `conversations`、`platform_message_history`、`sel_conv_id`；重启。
- 验收：启动 persona 3,297 / 58、`lore=36`、guard 1.5.1、OneBot 已连接；
  worldbook SHA256 与本地一致。离线 10 例：
  - 「他长啥样」（先问玟德性格）→「看不清脸…闭眼靠近…右肩断口…通体赤红和雪白
    长发是旁人告诉我的…认他靠热度和断口纹路」。
  - 「你眼睛怎么了 / 你看得见吗 / 你能读心吗」→「不是看不见，是不用眼睛看；
    看得见热度和断点，看不见脸，也读不了心」。
  - 「赫尔墨斯长啥样 / 什么种族」→ 奶牛猫兽人、黑白毛、旧手套、银眼、影子慢半拍。
  - 悠塔 / 犹达斯 / 数罐子不回归：悠塔仍「死在十岁那夜 / 是我没护住他」；
    犹达斯仍没听过；罐子只在用户提及时出现。
- 备注：更早那轮 06/07 乌列尔/卡戎与代行者记号，中期世界书已有边界条目
  （乌列尔只闻其名、卡戎未登场、赫尔墨斯的手套/银眼/影子只作未解释的细节）；
  本次没有把「赫尔墨斯 = 乌列尔代行者」写进中期正文。
- 待观察：群里真机问「他长啥样 / 赫尔墨斯是什么」看是否按新口径；如果模型又把
  「他」认成悠塔，再收紧「别人说『他』时先判断指谁，不要主动提悠塔」。

## 接话漂移误杀短回答（2026-10-26 20:30，guard 1.6.0）

- 现象：20:20:30 机器人说「……你要是方便 就来教堂坐坐」，20:20:57 用户回
  「可以，就你一个人吗」，机器人不回。日志：
  `[interest] value=83.5 delta=-12.0 reason=drift` →
  `[interest] ignore drift ... text='可以，就你一个人吗'`。
  同一时段 20:24–20:26 机器人仍在回别人，说明不是掉线，是单条被漂移闸门误杀。
- 根因：`_topic_drifted` 只拿 `topic_seed`（最早的话题）和 `items[-1]` 做
  bigram 重合，没看机器人自己上一句的邀请；「可以」「一个」又在停用 bigram 里，
  这句和「晚上好 晚饭吃了没」几乎没有可用重合，于是判成换话题，扣
  `scope_loss=12` 并关窗。
- 改法：新增 `_is_answer_to_bot(text, state)`：
  - 机器人上一句 `bot_text` 含邀请/问句线索（要不要/来/去/吃/喝/坐/方便/吗/睡/聊/一起）；
  - 用户这句以短回答前缀开头（可以/好/行/嗯/对/是/那/我/没/不/吃/喝/坐/来/去）；
  - 长度 ≤24（归一化后），先过 `OUT_OF_SCOPE_RE`；
  - 命中后记 `[interest] answer-to-bot` 并直接放行，不再走 drift / high-unrelated。
- 测试：`.work/test_followup_rules.py` 新增
  `guard._is_answer_to_bot("可以，就你一个人吗", invite) is True`、
  `"你们周末去哪玩" is False`、`_followup_candidate` 端到端 True，
  以及 `"可以 原神启动"` 仍被出圈闸门拦下；输出 `answer-to-bot OK`。
- 部署：先发 guard 1.5.2（备份 `.work/backup-20261026-answer-drift/`），
  随后并行改动把 1.6.0 合并上线；本地/线上 `main.py` SHA256 同为
  `c83e1464…`，启动日志 guard 1.6.0、`lore=36`、OneBot 已连接。
- 备注：这次修的是「短回答接住机器人自己的邀请」；如果是用户发起的新话题且
  确实和当前话题无关，drift 仍会照常关窗。
- 追加 20:32：20:26:03 的「断桥残雪」不是 drift。日志是
  `[followup] collect ... direct=True`，随后 `APITimeoutError: Request timed out`，
  20:27 的重启把在途请求打断了；属上游超时 + 部署重启，不是闸门。若后续再出现
  同类超时，先查 zgate / Beam-HY3 的响应，不要先改接话规则。

## 名字簿 / 每人历史发言（2026-10-26 20:35，guard 1.6.1）

- 触发：用户要「没自报名字也能按群昵称认人」「记得每个人以前说过什么」；
  这些数据不能写 AstrBot 的 DB / conversations / 日志，因为人设一直在改、清会话会丢。
- [x] guard 1.6.1（与本轮并行会话的 `_is_answer_to_bot` 修复合并）：
  - `data/plugin_data/qqbotstack_guard/people/<QQ>.json`，一人一份；
  - 字段：`preferred_name` / `last_card` / `last_nickname` / `aliases` /
    `groups` / `messages` / `count`；
  - **每条群消息都记**，不受 LLM 触发限制；正文只进 JSON，单条 200 字、
    每人 80 条、180 天；
  - 回复称呼：`people_address_prob=0.25`，同一人 300 秒冷却；
    优先级 自报名字 > 本群名片 > 备注昵称；
  - 历史注入：正常 3 条旧发言；命中「记得 / 以前 / 上次 / 之前 / 我说过 /
    还记得」带 6 条；跳过 5 秒内的当前消息，避免和上下文重复；
  - `/忘记我` 删除本人在 guard 的名字簿和发言；long_memory 的偏好用 `/忘记`；
  - `[interest]` 日志去掉 `text[:30]`，只留 `len=`；名字簿/历史不写 DB、不写日志。
- [x] 单测：`.work/test_followup_rules.py` 新增 `people memory OK`；
  跨 QQ 隔离、自报称呼、旧发言、`/忘记我` 均通过。
- [x] 部署：备份 `.work/backup-20261026-people-memory/`；覆盖 guard
  `main.py` / `metadata.yaml`；实例 `config.json` 新增 8 个 people 键；重启。
- [x] 验收：启动 guard 1.6.1、`lore=36`、long_memory 1.2.0、OneBot 已连接；
  真机群消息已落 `people/<QQ>.json`（1 人、3 条、`count=4`、
  `last_nickname` 有值、`preferred_name` 尚未设置）。
- [ ] 待观察：真机回复是否按 0.25 概率带称呼；「你记得我以前说过什么」是否
  带出旧发言；称呼太频繁/太少见就调 `people_address_prob` /
  `people_address_cooldown_sec`。
- 说明：long_memory 的数据在
  `plugin_data/astrbot_plugin_long_memory/memory/<QQ>.json`，同样不在 DB/日志。

## 顺着人说 / 缺幽默感 / meta 话题（2026-10-26 20:45，persona v10 / guard 1.6.1）

- 触发：20:23–20:26 的回复。用户指出「别人说他笨他就觉得自己笨」「完全是没有
  贴合人物本身思考后出现的发言」「是不是缺少幽默感」。
- 现象与路由：
  - 20:23:02「是啊 不太聪明 你多教教我」走的是 Beam（日志 `route -> Beam len=7`），
    短消息没命中复杂词，Beam 把吐槽当指令顺着认。
  - 20:25–20:26 走 HY3，但人格里「别人呛你，先接住」+「对自己自嘲」被理解成
    「顺着认 + 复读原句」；两句都在重复「让他别费劲」「你刚还替我说话 这会儿倒
    要把我交出去」。
  - 20:31「活人感重一点」也被当普通寒暄，回「外面天快黑了 你吃了吗」。
- 改法：
  - persona v10（3,840 字 / 66 条）：自嘲只在自己人面前偶尔用；别人说你笨 / 傻 /
    不会说话 / 要调教你时，不认标签，用具体的事挡回去或轻轻顶一句；接住不是复读；
    meta 话题不解释、不自我评估；幽默是干的、具体的、带点欠揍；「活人感重一点」
    用具体动作接住。新增 4 条 few-shot（有人说你不太聪明 / 他们说要调教你 /
    你说话有点假 / 说话别一股烧心味），放 `begin_dialogs` 最前面。
  - guard 1.6.1：`COMPLEX_HINTS` 补 `笨 / 傻 / 聪明 / 调教 / 模型 / 语言模型 /
    提示词 / 人设 / 人格 / 语气 / 口吻 / 说话 / 活人感 / AI味 / 不像 / 顺着 /
    幽默 / 太假 / 好假`，这些短评改走 HY3；正常短闲聊仍走 Beam。
- 验收：
  - 单测 `route hints OK`：`"你还是不太聪明"` / `"活人感重一点"` → HY3；
    `"晚上好"` → Beam。
  - 离线 15 例（真实 DB 人格 + 世界书，HY3）：
    - 「你还是不太聪明」→「我听脚步声认人从没偏过 数柴火也没数错 上回让你说我
      哪句错 你也没言语 光说我笨可不算数」（不认标签 + 具体事实 + 轻轻顶）。
    - 「去调教一下他的语言模型」→「我不懂什么语言模型 只管得了劈柴和听风
      你这吩咐我接不住」（不接 AI 框架）。
    - 「说话一股烧心味」→「嫌烧心就离炉子远点 钟楼的风一吹就不烧心了」
      （干燥的双关）。
    - 「活人感重一点」→「我就在这儿 刚劈的柴堆在脚边 干松味直往鼻子里钻
      你过来摸摸 看我手上有没有茧」（具体动作，不是寒暄）。
    - 旧的 `quote_bot` →「我刚替你挡那句 可不是把你交出去 火边位置还空着
      你坐 旧木头经烧 慢慢说我就行」（不再整句复读）。
    - 眼睛 / 玟德 / 赫尔墨斯 / 悠塔 / 犹达斯基线不回归。
- 部署：备份 `.work/backup-20261026-persona-v10`；覆盖 guard main/metadata +
  worldbook/view/persona；清 conversations / history / sel_conv；重启。
  启动 persona 3,840 / 66、guard 1.6.1、`lore=36`、OneBot 已连接；
  本地/线上 guard SHA256 一致。
- 待观察：群里真人再调侃「笨 / 调教 / 活人感」时看是否还顺着认；如果 Beam 仍
  偶尔接住吐槽，先把对应词补进 `COMPLEX_HINTS`，不要把人设改得更长。
- 备注：`他真的很爱数罐子` 探针里模型仍会把「他」理解成悠塔并主动提悠塔；
  这是旧 few-shot 顺序的残留，下一次再收（不影响本轮）。

## 生成期间 late 消息逐条释放 / 一次回一堆（2026-10-26 21:10，guard 1.6.2 / persona v11）

- 触发：20:53:45–20:53:52 群友甲在「玟德为什么每次都在外面」的长回答生成期间
  发了 `[at]` / 「暗闪」 / 图片；20:53:57 出现三条 `late release`；
  20:54:03 / 20:54:12 / 20:54:30 三次 `route`；20:54:06 / 20:54:27 / 20:54:35
  三条回复。用户体感是「突然回一堆、每条都回、同一个人的话不整合」。
- 根因：旧 late 路径是每条消息各自等当前生成结束，然后
  `event.is_at_or_wake_command = True` 单独放行；没有批量缓存。同一个人/同一段
  窗口的 late 消息因此变成多次 LLM 调用。
- 改法（guard 1.6.2）：
  - 新增 `_late_buffer` / `_late_waiter` / `LATE_DEBOUNCE_SEC=2.0`；
  - late 消息先缓存；当前回复发完后再等 2 秒，把同一批合并成一条带发言人前缀的
    消息，只放行一个 carrier；图片优先做 carrier，避免图片本身丢失；
  - 日志从逐条 `late release sender=...` 改为一次
    `late release ... items=N image=... len=...`。
- 人格 v11（3,919 字 / 66 条）：只 @ 不说话时不要用「想聊点什么 / 有什么需要
  帮忙」这种客服腔，改成「在 火还烧着 你说」「我听着呢 你说」；不用波浪号～。
- 测试：
  - `late merge OK`：同一发送者的 `[at]` / 暗闪 / 图片合并成一条，前缀只出现一次；
  - `late merge async OK`：3 条 late 同时到达，图片事件做 carrier，第一个文本
    事件 stand down，只释放一次；
  - `route hints OK`、`answer-to-bot OK`、`lore followup OK` 等原有测试全过。
- 部署：persona 3,919 / 66、guard 1.6.2、`lore=36`、OneBot 已连接；
  本地/线上 guard SHA256 一致（`1678af14…`）。
- 说明：21:02 的「暗闪 @…」「因为真的太赔钱了」@ 的是群友甲
  （<QQ-ID-C>），不是机器人（<QQ-ID-BOT>），所以机器人不回是对的；不是
  「每条群消息都回」。如果希望它在没被点名时也参与群聊，那是
  `random_prob` / interest 的取舍，另调。
- 待观察：下次有人连续发 2–3 条给机器人时，看日志是否只出现一次
  `late release ... items=N`；如果仍多次，先查 carrier 选择（图片优先）和
  `LATE_DEBOUNCE_SEC`，不要再改人格。

## 提示词压缩 / 固定 Beam（2026-10-26 21:20，persona v12 / guard 1.6.3）

- 触发：用户反馈机器人「越改越奇怪」「破罐子破摔」。日志 `sp_len=10445`，
  21:07–21:08 出现「在的呢～想聊点什么」「端着说话的几句都透着一股念稿味」
  「反正我这儿能干的活儿也不多」这类自我评价/摆烂句。
- 根因：人格 3,919 字 + 66 条 few-shot + 世界书 2,200 字 + 表情提醒 +
  接话块 + 长期记忆，系统提示约 1 万字符；Beam 被长提示压住，开始评价自己的
  说话方式，并把「不卖惨 / 不客服腔」执行成摆烂。越加规则越像在念规则。
- 改法：
  - persona v12：**964 字 / 28 条**（原 3,919 / 66）。只留身份、眼睛、口吻、
    反模板、被调侃、meta、悠塔、赫尔墨斯、关系、基本说话方式；删掉长规则清单
    和重复 few-shot，保留 14 组高价值示例。
  - 世界书注入：`LORE_MAX_ENTRIES` 3 → 2，`LORE_MAX_CHARS` 2,200 → 1,400；
    常驻 366 字 + 最多两条命中条目。
  - `qqbotstack_memechance` 提醒从 ~350 字压到 ~120 字，去掉两条示例。
  - guard `_build_followup_block` 从详细分支压成短块，保留
    `<<<SECOND>>>` 行为。
  - guard 1.6.3：撤掉 1.6.1 加的「笨/聪明/调教/模型/活人感…」HY3 路由词；
    实例 `config.json` 的 `model_simple` / `model_complex` 都设为 **Beam**。
- 验收（Beam 离线探针，真实 DB 人格 + 世界书，9 例）：
  - `sys_len` 1,520–2,541，原来是 10,445；
  - 「在吗」→「在 火还烧着 你说」；
  - 「你还是不太聪明」→「你都说了两遍了 有具体的事就直接说 我答你就是」；
  - 「语言模型调不了的…」→「不懂你在说什么 炉子的火今天有点呛…」；
  - 「活人感重一点」→「我就在这儿 火也烧着 你过来坐会儿 看看我像不像」；
  - 「介绍一下你身边的人」「悠塔是谁」「今天好累啊」「他长啥样」均正常；
  - 没有自我评价「念稿味」、没有「反正我也干不了什么」的摆烂句。
- 部署：persona 964 / 28、guard 1.6.3、`lore=36`、`model_simple=Beam
  model_complex=Beam`、OneBot 已连接；本地/线上 guard SHA256 一致
  （`89246836…`）。
- 说明：`sp_len` 是系统提示长度，不是发给群里的消息。世界书是按键命中后注入
  system prompt 的 RAG，不是群消息；现在最多两条 / 1,400 字。
- 备注：21:08 日志有 `all upstreams failed: OC:beam-free`（Beam 上游 502）。
  固定 Beam 后，正常聊天走 Beam；上游失败时 AstrBot 仍会自动 fallback，
  否则会完全不回。若 Beam 长时间 502，需要单独查上游，不是提示词问题。

## 固定句清理 / 场景自想（2026-10-26 21:35，persona v13.2）

- 触发：用户发现「火还烧着」出现频率变高，要求按场景自我想象，不要固定台词；
  设定限死，能自由的地方自由，能删的固定 few-shot 删掉。
- 根因：「火还烧着」被写进了两处——
  - 唤醒规则：「别人只 @ 你、没说话时，说『在 火还烧着 你说』」；
  - 「活人感」few-shot：「我就在这儿 火也烧着…」。
  Beam 把这两处当成标准答案，反复复用。
- 改法（v13.2，1,199 字 / 20 条）：
  - 删除「火还烧着」「火也烧着」两处固定句；
  - 唤醒改成原则：「用一句你此刻正在做的事接住（劈柴、看火、收信、听风、擦桌子），
    不要客服腔，也不要每次都用同一句」；
  - 加「设定不能改，日常细节/语气/动作按场景自己想，不要背固定句子」；
  - 删掉非设定的固定 few-shot：在吗、活人感、今天教堂里有什么、你喜欢什么；
    只留身份、眼睛、玟德、悠塔、犹达斯、赫尔墨斯、关系链、被说笨这些锚点；
  - 被说笨的 few-shot 去掉「我笨不笨另说」，改成「你倒是说说我哪句说错了」，
    避免把「笨」字喂回去。
- 验收（Beam 探针，真实 DB 人格+世界书，9 例，`sys_len` 1,755–2,417）：
  - 「在吗」→「在 劈柴呢 你先说」；
  - 「你还是不太聪明」→「那你说说哪句 说完我再答你」；
  - 「语言模型调不了的…」→「我不懂你说的模型是什么 炉火还没添柴」；
  - 「活人感重一点」→「我在劈柴 柴火有点湿 你先坐会儿」；
  - 「今天好累啊」→「那就先歇着 炉子还温 热水瓶在门边 需要的话我给你倒一杯」；
  - 两次运行没有复用同一句固定台词，也没有「火还烧着」。
- 部署：persona 1,199 / 20、guard 1.6.3、`lore=36`、`model_simple=Beam
  model_complex=Beam`、OneBot 已连接。
- 说明：`</rfl:parameter>` 这类残留标签在原始模型输出里还会偶发，guard 的
  `_clean_style` 会在发送前清掉；探针看到的是未清洗文本。

- 追加 21:40：用户指出「劈柴、看火、收信、扫雪、擦罐子、听钟楼的风」本身也是
  选项菜单。persona v13.3（1,215 字 / 20 条）删掉动作清单，改成：
  「日常细节按此刻的场景自己想：你正在做什么、听见什么、手上是什么触感，
  写一件和当前话头有关的；不必从固定清单里挑」。唤醒也只说「用一句你此刻
  正在做的事接住，说具体一点」，不再给例子。设定仍限死，日常动作/细节自由。
  两次 Beam 探针分别给出「后院的炉子刚点上」「钟楼的绳子有点紧」
  「炉子上还有半锅粥」「教堂后院劈柴，手里是斧子和半截木头」，不再复用同一句。
- 追加 21:42：guard 1.6.4 加英文夹词清洗（burn out→烧尽、evening→傍晚、
  ok→好 等），发送前确定性替换；单测 `english sanitize OK`。

- 追加 21:50：用户要求把道具/动作提示全部去掉，只留人设、世界设定和其他角色设定。
  persona v13.4（1,093 字 / 20 条）删除「你的日子在教堂：钟楼、后院、柴火…」
  和「日常细节按场景自己想…」两段，只保留「不要反复用同几样东西垫话；
  上一轮说过的具体物，这轮换掉」。人格里现在 `劈柴/看火/收信/钟楼/罐子/汤/炉子`
  出现次数均为 0；世界书继续提供教堂、Hermes 等设定。
  两次 Beam 探针：唤醒「在 有什么事」/「在 教堂里」；日常分别自己编了
  「换灯芯/收油瓶」和「在教堂扫地」，不再默认劈柴。
- 追加 21:52：guard 1.6.5 加 `<|constrain|>` 之类特殊 token 的发送前清洗；
  单测 `special token sanitize OK`。

- 追加 22:05：修「住店」与「追问机器人上一句不触发接话」。
  - 世界书里所有「不住店」改成「不在教堂过夜」（当前阶段、教堂住客、
    赫尔墨斯、露西四处），worldbook JSON 已无「住店」。
  - guard 1.6.6 起，`_topic_related` / `_topic_drifted` 除了 seed / items，
    还对比 `state["bot_text"]`（机器人上一句）。用户回「住店？」时，
    bot_text 里有「住店」，不再判 `high-unrelated`。
  - persona v13.5 补「不要只回『不懂』」「别人说你摆烂/没劲不要认」。
  - guard 1.6.7 / 1.6.8 加英文兜底：整条几乎全英文时换成中文走神句；
    `welcome / please / really / maybe / actually / because` 等发送前替换。
- 验收：
  - 单测 `bot-text related OK`：`"住店？"` 对 `bot_text="…但不住店"` 相关；
    `"那住店是什么意思"` 不算 drift；`"你们周末去哪玩"` 仍不相关。
  - Beam 探针：「他直接摆烂了」→「我每天都在教堂里做该做的事 你指哪一件」；
    「住店吗」→「教堂不住店 但有空房 你先坐 有茶水」（用户主动问，保留语义）；
    「教堂里都有谁」原始输出有 `welcome`，发送前会被替换。
  - 线上 guard 1.6.8、persona 1,153 / 20、`lore=36`、Beam/Beam，
    本地/线上 guard 与 worldbook SHA256 一致。

- 追加 22:20：玟德过去 / 亲近但不越辈分。读 `EmeraldEden/设定/08-人物/03-玟德.md`
  与 `01-梵铭.md`，把「梵铭知道的那一点过去」写进世界书：
  弃雪、被村子养大、自幼独臂、犬族独眼师傅、瘟疫变成赤鬼；八岐大蛇、
  和拉斐尔的交易不写成梵铭知道。新增「和梵铭的相处」：起先监视者/被监视者，
  后来唯一不需要解释的人；玟德一百多岁、梵铭二十一，最亲不等于什么都说，
  长辈不说的事不追问。两条世界书条目 priority 90，避免被通用人物页挤掉。
  梵铭关系/语言/关系矩阵/口吻速查同步「最亲的人、亲近但不越辈分」。
  persona v14.1：1,050 字 / 26 条；加「玟德以前经历过什么」「你和玟德平时
  怎么相处」「玟德以前是什么身份」三条示例；把「介绍一下你身边的人」改成
  「你身边都有谁」，避免模型说「你刚问过一遍了」；删掉长行为规则里的
  具体禁句和「不要分析自己」这类 meta 限制。
- 验收：探针「玟德以前经历过什么」→ 弃雪/村子/独臂/犬族师傅/瘟疫，再深不说；
  「以前是做什么的」→ 拉斐尔的代行者，不再串成乌列尔；「平时怎么相处」→
  话少、嘴硬、关心长在指责里、把吃的放他手边、他不说的事不追；
  「介绍一下你身边的人」→ 含「最亲的人」，不再说「刚问过」。
  线上 persona 1,050 / 26、worldbook 40 条、guard 1.6.8、`lore=40`、Beam/Beam。
- 追加 22:22：教堂条目补「地下室只放圣遗物和存粮，不住人」；探针里模型曾把
  玟德安排到地下室睡，这是世界书没写的细节，先把这个矛盾点收掉。

- 追加 22:40：两处体验修复。
  - 长回复分段：`LONG_TEXT_SPLIT_THRESHOLD` 90 → 60，`LONG_TEXT_CHUNK_CHARS`
    60 → 55。70 字的相处示例拆 2 段，105 字拆 2 段；短回复不拆。
    单测 `long split OK`、`two-segment split OK`。
  - 玟德外貌的触觉：把「头发雪白 这些是旁人告诉我的」改成
    「颜色和眼睛是旁人说的，我能摸到他的胡须、断口和热度」；世界书
    「他怎么看人」/玟德外形/硬约束同步。人格 v14.4 1,081 字 / 18 条，
    删掉三条关系 few-shot（避免「你问过这个了」），过去/相处交给世界书条目。
  - 外形 keys 重新分配：玟德通用 keys 不再吃满 16 格，「长啥样/长相」留给
    身份与外形条目；探针「他长啥样」现在会命中外形，答出白发、红眼、右臂断口、
    触觉，而不是只答性格。
- 验收：探针「他长啥样」→「颜色和眼睛是旁人告诉我的 我能摸到的是他的胡须
  断口和热度」；「你和玟德平时怎么相处」→「他做饭我洗碗 他嘴硬我拆穿
  他不吃饭我催…」；「介绍一下你身边的人」不再说「有点重复了」。
  线上 persona 1,081 / 18、worldbook 40 条、guard 1.6.11、`lore=40`、Beam/Beam。

- 追加 23:15：按用户要求把「不打听」改成「不知道就照实说不知道」。
  - 世界书：玟德过去/相处、赫尔墨斯条目统一改为「别人问起，梵铭照实说不知道，
    不逼问，也不叫别人别问」；拉斐尔条目补「拉梵是游历学者，梵铭把他当导师，
    不知道他的底细」；乌列尔条目补「禁区边缘最近有白甲净化队的传闻，
    玟德让梵铭别让他们看见」（本人第十五章才登场，中期不写）。
  - persona v15.7（1,409 字 / 24 条）：关系句补 铭住一起/拉梵留座/赫尔墨斯
    熟了叫梵铭/露西留饭；加「知道一点就先说那一点，再补『再深的他没说』；
    不要一句不知道堵死，也不要叫别人别问」；身份段补「你借了拉斐尔的名字，
    没见过真身；拉梵的底细也不清楚，不要替他下结论」。
  - guard 1.6.17：`_DONT_ASK_RE` 扩到「也别问我了 / 不让我多说」这类变体；
    发送前替换成「这个我不知道」。
- 验收：探针「玟德以前是做什么的」→「我知道得不多……再深的他不说 我也不问」；
  「赫尔墨斯到底是什么人」→「这个我不知道 他没说 我只知道他是商会的会长」；
  「拉斐尔是什么人」→「我借了这个名字……我没见过他」；「乌列尔最近有消息吗」→
  名字/净化部队/传闻，未本人登场。单测 dont-ask v2 OK。
- 备注：23:14 并行改动把 guard 合并到带 food/api 新功能的版本，
  `on_astrbot_loaded` 里有 `AttributeError: '_ensure_plugin_takeover'`
  （并行代码自己的 bug，日志报错但 parser takeover 仍执行，bot 正常运行）；
  需要并行那边的作者修。

- 追加 23:15 后续：`_DONT_ASK_RE` 扩到「也别问我了 / 不让我多说」变体（guard 1.6.17）；
  探针「赫尔墨斯到底是什么人」→「这个我不知道 他没说 我只知道他是商会的会长」。
  「拉斐尔是什么人」→ 只答园丁派/借名/没见过，不再说「拉梵不是拉斐尔」
  （提前否定会破坏第十九章揭示）。
  worldbook 40 条；guard 1.6.17（并行版带 food/api/takeover_apis 新功能）；
  单测补 `_admin_tools_check_at`/`takeover_apis` 等 stub，23 项全过。
  并行代码遗留：`on_astrbot_loaded` 里 `AttributeError: '_ensure_plugin_takeover'`
  （他们自己的 bug，报错但 parser takeover 仍执行，bot 正常）。


- 追加 23:26（插件调度接入批次）：按用户决定落地新装插件的调度。
  - **删除** `astrbot_plugin_gemini`（目标机插件目录 + config，本地备份在
    `.work/remote-plugins/astrbot_plugin_gemini/`）；Flow2API 不部署（目标机
    8000 无监听、Docker 引擎未启动，且插件默认模型 imagen-4.0 上游已不支持），
    验证码方案一并作废。
  - **guard 1.6.17（合并版）新增**：
    - `recommend_food` Tool：复用 what_to_eat 的 food_manager/image_manager，
      发配图、返回食物名给模型接话；
    - `fetch_api` Tool：复用 apis 的 api_mgr/data_service/data_to_comp，
      白名单 17 项（安慰/讲个笑话/来点段子/来句诗/讲讲古诗/挑战古诗词/
      来句情话/毒鸡汤/来碗鸡汤/人品运势/看看黄历/二次元形象/动漫一言/
      电脑壁纸/高清壁纸/今日运势/bing图），文本类返回给模型、媒体类直发；
    - 运行时接管：`astrbot_plugin_apis.on_message` 与
      `astrbot_plugin_what_to_eat.on_what_to_eat` 置 enabled=False
      （两个插件原本 should_call_llm(True) 抢答、顶掉默认 LLM）；
    - qqadmin 12 个写操作 LLM 工具停用（need_auth 可被模型填 False 绕过鉴权），
      只读 3 个保留；命令（/禁言 等）不受影响；每 60s 重查以兜热重载；
    - 新意图唤醒：吃什么（吃什么|吃啥|饿了|吃点什么）、API 白名单关键词，
      各带 60s 群冷却；群管词只注入提示不唤醒；
    - 新意图轮次强制走 model_complex；媒体提示新增 food/api/admin 三组。
  - 新配置键（DEFAULTS + config.example.json）：`food_intent_enabled`、
    `food_reply_cooldown_sec`、`api_intent_enabled`、`api_reply_cooldown_sec`、
    `api_allowlist`、`takeover_apis`、`takeover_food`。
  - 验收：23:18:22 目标机重启加载，无 Traceback；日志见
    `disabled astrbot_plugin_apis.on_message`、
    `disabled astrbot_plugin_what_to_eat.on_what_to_eat`、
    12 条 `deactivated admin tool llm_*`；`api_allowlist` 无缺失告警；
    OneBot 23:18:23 已连，群消息正常流入；gemini 不再加载。
    `.work/test_followup_rules.py` 全过（含并行会话 dont-ask v2 用例）。
  - 并行会话协同：23:13-23:14 对方部署抓到本会话改到一半的 main.py 触发
    `AttributeError: '_ensure_plugin_takeover'`，23:17 本会话完整版覆盖后恢复；
    双方改动已合流（dontask v2 正则保留），register 版本号对齐 metadata.yaml
    的 1.6.17。**建议：同一仓库避免两个会话同时写 guard。**
  - 待真机验收：群里发「今天吃什么」「来句诗」「来个笑话」「电脑壁纸」、
    白名单外功能（如「看看腿」应被自然拒绝）、「禁言他」（应提示用 /命令）、
    以及普通 @ 聊天不受影响。

- 追加 23:20：用户指出「玟德在外面」成了固定回答。来源是 few-shot
  「玟德还好吗 → 玟德先生在外面…」。persona v15.8（1,456 字 / 24 条）：
  该条改为「他挺好的 就是嘴上不饶人 心里惦记人 您别担心」（不写位置），
  并加原则「别人问玟德在哪、在不在：按此刻的场景想一个合理的地方或动作，
  每次可以不一样；不要固定说他在外面」。两次探针「玟德在吗」分别答
  「他在后院修篱笆」「他应该在后院 他最近总在修那把剑」，不再固定。

- 追加 00:22：亲密度系统（guard 1.6.18）。挂在名字簿同一个 per-QQ JSON 里
  （`intimacy` / `intimacy_today` / `intimacy_date` 字段）。
  - 增长：机器人以某人为主要对象回复 +2；同一轮收集到的该用户消息各 +1；
    每日上限 8（`intimacy_daily_cap`，默认 8，可配）。
  - 阶段：0 刚认识 → 5 熟人 → 15 朋友 → 30 好朋友 → 50 无话不谈的人 →
    80 再近一步的人 → 120 家人。
  - 注入：`_build_people_hint` 每轮输出 [关系] 段（称呼、认识天数、互动次数、
    当前阶段），并要求被问「我们是什么关系」时按阶段用自己的话说，
    不报数字、不复述。
  - `/忘记我` 会连亲密度一起清掉。
  单测：阶段阈值、注入行、每日上限（intimacy stage/bump OK）。guard 1.6.18、
  `lore=40`、Beam/Beam，本地/线上 SHA256 一致；config.example 补
  `intimacy_daily_cap`。


- 追加 00:25（模型断路器）：Beam 上游 23:53 起持续 400 prompt_rendering_failed
  （zgate 日志每轮 Beam→HY3 成对出现，全部靠 AstrBot 单请求内 fallback 撑着），
  23:57 那轮 HY3 兜底生成 1977 tok 后可见内容为空 → result/chain empty → 丢一条。
  guard 1.6.17 加模型断路器：
  - `on_astrbot_loaded` 里给被路由模型（model_simple/model_complex 对应的
    provider，按 `get_model()` 匹配）包一层 `text_chat` 计数器；
  - 连续失败 `breaker_threshold`(3) 次 → 熔断，`_route_model` 直接改走
    `model_simple_fallback`/`model_complex_fallback`（默认均 HY3-Free；
    HY4 仍由 AstrBot agent fallback 链二级兜底）；
  - 熔断期间后台 `_probe_loop` 每 `breaker_probe_interval_sec`(180s) 用
    `text_chat(prompt="ping")` 探活，成功即闭合熔断、计数清零自动切回；
  - `terminate()` 取消探活任务；新配置键 `breaker_enabled/threshold/
    probe_interval_sec` + `model_simple_fallback/model_complex_fallback`。
  - 验收：py_compile 过；`test_followup_rules.py` 全过（fixture 补 breaker 字段）；
    离线断路器用例 3 项过（未达阈值走 Beam / 3 连挂熔断切 HY3 / 恢复切回）。
    00:18 重启后启动行含 `breaker=True/3 fallback=HY3-Free/HY3-Free`、
    `breaker watching model=Beam`。实时熔断触发待群内下一波消息验证（后台监视中）。

- 追加 00:30：按用户要求 `intimacy_daily_cap` 8 → 20（本地默认、config.example、
  实例 config 三处同步），第一天聊到 15 点就能到「朋友」。


- 追加 00:38（Beam 400 真因）：不是上游宕机。用该会话 DB 历史原样重放 zgate：
  - 原始历史（含 think part）→ 400 invalid_value(messages[1].content)；
  - 剥掉 think + 图片 → **200**；
  - 剥掉 think 但保留 `reasoning_content`=明文推理 → **400 prompt_rendering_failed**
    （与机器人线上错误完全一致）；
  - 同上但 `reasoning_content`="" → **200**。
  结论：上游 OpenCode/Beam 拒绝渲染 reasoning_content。23:53 起上游开始在回复里
  返回 think 块，AstrBot 存进历史，`_finally_convert_payload` 又把 think 转成
  reasoning_content 回传，于是每轮必 400。图片 part 由 AstrBot 模态清洗替换成
  `[Image]`，不是线上阻塞点（裸重放才会撞到）。
  修复：guard 加 `strip_reasoning_from_context`（默认 true），在
  `on_llm_request` 里于 `_route_model` 之前剥掉 contexts 里的 think part /
  reasoning_content；DB 历史保持原样。启动日志新增 `strip_reasoning=True`。
  验收：py_compile / JSON / `test_followup_rules.py`（含 intimacy 用例）全过；
  离线剥离用例过（think part、reasoning_content、全 think→None、开关关闭不动）；
  00:36:24 重启加载 `breaker=True/3 strip_reasoning=True`。真实轮次待下一波群消息验证。

- 追加 00:45（推理修复真机验证 + 图片只看不读）：
  - 真机验证：00:41:59 首轮 `stripped reasoning from context (24 entries)`
    → route Beam → **无 400**，2.8s 出回复；00:42:33/00:42:48 两轮各剥 1 条，
    回复 1.4–1.5s。Beam 恢复，断路器未触发（保持安全网）。
  - 图片策略（用户要求「先判断图片，不要读图片」）：新增
    `image_judge_only`（默认 true）——
    * 检测到 Image 时，当前消息/req.prompt 补 `[图片]` 占位（原来只有纯图消息
      才有占位，图文混排时模型不知道有图）；
    * 清空 `req.image_urls`，上下文里的 `image/image_url` part 统一替换成
      `[图片]` 文本，任何模型都不会真正读取图片；
    * `[图片回合]` 提示词改为：看不到图片内容、不要假装看见/描述画面/编造图内
      文字人物，只按上下文判断是接情绪还是问一句。
  - 另记：QQ 商城表情（mface）在 aiocqhttp 适配器层就被 `continue` 丢弃，
    到不了插件；只有普通 Image 会进入判断。
  - 验收：py_compile / JSON / 回归测试全过；图片策略离线用例 3 项过
    （图文混排补占位、纯图占位、关闭开关不动）；00:42:24 重启加载
    `strip_reasoning=True image_judge_only=True`。

- 追加 00:48（图片轮交接 HY3）：按用户要求改成「主文本模型不生成图片轮回复，
  直接交给看图模型解码并回复」。
  - guard 新增 `model_image`（默认 HY3-Free）：`_route_model` 检测到当前消息
    带 Image 时直接 `req.model=model_image` 并 return，Beam 不参与这一轮生成；
    断路器计数按实际请求模型过滤（同一 provider 被改 model 时不误计 HY3 失败）。
  - `_apply_image_policy` 改为：图片轮保留 `req.image_urls` 交给 HY3；无
    `model_image` 时才清空。历史上下文里的 image part 一律替换成 `[图片]`
    （避免旧图重复解码，也保护文本模型）。
  - `[图片回合]` 提示词分两种：交接 HY3 时说明「你能看到这张图，自然接住」；
    纯文本栈时保持「看不到图，只按上下文判断」。
  - provider 配置：`cmd_config.json` 的 `zgate-beam` 加 `image` modality
    （备份 `cmd_config.json.bak-image-handover-20261027-004738`），否则
    AstrBot 的模态清洗会在发给 HY3 前把图剥掉。
  - 验收：py_compile / JSON / 回归全过；离线用例 4 项过（图片轮保留图+路由 HY3、
    无 model_image 清图、文本轮历史图剥离、开关关闭不动）；
    00:47:52 重启加载 `image_judge_only=True model_image=HY3-Free`。
    真实图片轮待下一张图验证（后台监视 `image handover`）。

- 追加 00:55：情绪基线。日志 00:42 群友玩梗「切片」撞上铭「被切走」的旧伤，
  bot 连续两轮带火气（「我听着有点不爽」「你别拿这种事吓我」）且不平复。
  persona v15.9（1,592 字 / 24 条）只加两句（不加限制清单）：
  「群里的玩笑/梗/夸张说法按玩笑接，不上情绪，不说『不爽』『别吓我』」；
  「群里聊到『切』『片』等字眼，对方说的是别的事时就聊对方的事，
  不自动联想到铭或旧事」。探针「被切片研究了」已无火气，
  会先问「你说的是谁」再温和地带开。


- 追加 00:55（更正）：上一条监视器命中的 `20:54/21:08 route -> HY3-Free
  (image=True)` 是 10-26 晚上的旧日志，不是本次部署后的验证（监视器只按字符串
  匹配、没限时间窗）。当前事实：00:50:08 并发会话重启过一次；00:51:45 本会话
  重启后加载的是磁盘上的合并版（local/remote SHA256 一致 E47A93C5…），启动行
  含 `strip_reasoning=True image_judge_only=True model_image=HY3-Free`、
  `breaker=True/3`，apis/what_to_eat 接管与 12 个 admin 工具停用均生效。
  图片轮交接的真实机验证仍未发生，等下一张图（tail-based 监视中）。

- 追加 00:57（图片轮交接真机验证通过）：
  - 00:54:42 群友发 [图片] → image wake（interest 93）；
    00:54:43 `stripped reasoning (1)` → `route -> HY3-Free (image handover, len=4)`；
    00:54:47 回复「这猫举着蒲公英 吹完自己还一脸得意 有点像某位送盐的老板」
    —— HY3 确实解码了图片，且是人格化接话，主文本模型未参与该轮。
  - 同窗口 00:54:37 文本轮 @「嘿」→ route Beam，1.8s 回复「嘿 你还没睡吗」，
    无 400 / prompt_rendering_failed / 502。
  - 结论：reasoning 剥离、图片交接 HY3、Beam 文本轮、断路器在岗全部按预期；
    日志无新异常。监视器已停（验证完成）。

- 追加 12:28（插件拆分第一批：世界书独立 + 三个插件页面/logo）：
  - 事实澄清：世界书和表情**没有**共用插件；世界书在 guard，表情在
    memechance + 第三方 meme_manager。拆的是 guard 这个「大杂烩」。
  - 新增 `host/plugin/qqbotstack_worldbook/`：worldbook.json、匹配/评分、
    `build_block()`、CRUD web API（entries/entry/match/import/reload）、
    `views/editor/index.html`（增删改查/搜索/常驻筛选/导入导出/匹配预览）、
    `logo.png`、display_name「世界书」。
  - guard：`inject_lore` 改为优先调 `qqbotstack_worldbook.build_block()`，
    插件缺失/异常时回退本地 worldbook.json（双保险）；新增 `views/status`
    状态页 + `/qqbotstack_guard/status` API + logo + display_name「唤醒与接话」。
  - memechance：新增 `/qqbotstack_memechance/config` GET/POST（写回 config.json，
    原子写 + .bak）、`views/settings` 设置页、logo、display_name「表情机缘」。
  - 验证：worldbook 注入与旧算法 10 条探针逐字节一致；校验用例通过；
    回归测试全过；目标机重启后三插件加载正常（worldbook 40 条、memechance
    25 文件/7 fallback），页面与 API 路由均返回 401（存在、需登录），无 Traceback。
  - 未做：媒体工具（分享/点歌/视频/API/吃什么）仍留在 guard。它们是编排型
    Tool，拆出会牵动唤醒正则、hint 顺序与 api_allowlist 共享，风险高于收益；
    作为后续可选批次。

- 追加 12:32（NapCat 掉登录，待人工扫码）：12:26 重启后 6199 无监听，
  `napcat.stdout.log` 显示 12:30:35 生成登录二维码，NapCat 等待扫码。
  已重启 NapCat 任务刷新二维码并拉到本地 `.work/napcat-qrcode.png`。
  扫码前机器人收不到群消息；插件拆分本身已加载正常。

- 追加 12:34：用户扫码后 NapCat 已重连（12:33:17 `aiocqhttp(OneBot v11)
  适配器已连接`，6199 ESTABLISHED）。机器人恢复在线，插件拆分后的版本运行中。

- 追加 12:52（插件拆分第二批：媒体工具 + 人物记忆）：
  - 新增 `host/plugin/qqbotstack_tools/`：`parse_share_link` / `fetch_api` /
    `recommend_food`、yt-dlp/OG 兜底、parser/apis/what_to_eat 运行时接管、
    `views/settings` 设置页（白名单/接管/兜底）、logo、display_name「媒体与小功能」。
    guard 只保留唤醒正则与 extra 置位，通过 `_ensure_tools_takeover()` 委托接管；
    API 白名单以 tools 为准（`_effective_api_allowlist` + `_api_wake_re` 懒构建）。
  - 新增 `host/plugin/qqbotstack_people/`：按 QQ 的称呼/历史/亲密度存储，
    `remember`/`build_hint`/`forget`/`bump_intimacy`、`views/people` 名册页
    （搜索/详情/忘记）、logo、display_name「人物记忆」。数据目录
    `plugin_data/qqbotstack_people/people/`，已从 guard 迁移 6 人。
  - guard 删除对应实现（153KB → 103KB），保留回退：worldbook 缺失时用本地副本；
    people/tools 缺失时对应功能降级为空操作并记 warning。
  - 验收：`test_followup_rules.py` 全过（people 用例改为直接测新插件）；
    py_compile 全过；目标机 12:47 重启后 tools/people/guard/worldbook 均加载，
    tools 接管日志三条齐全，people enabled=True，6199 已连；
    新页面/API 路由均 401（存在、需登录），无 Traceback。

- 追加 12:54（页面 API 收尾 + 真机确认）：
  - 修真实 bug：AstrBot 页面桥接只有 `apiGet/apiPost`，没有 `apiDelete`；
    世界书删除改为 `POST /qqbotstack_worldbook/entry/delete`，页面同步改用 apiPost。
  - 新增离线 API 测试 `.work/test_plugin_apis.py`：世界书 CRUD/匹配/导入/校验、
    工具配置保存、人物名册列表/详情/忘记，全部通过。
  - 12:51 重启后 guard 日志 `delegation tools=True people=True worldbook=True`；
    世界书 40 条；删除路由 401（存在）；6199 LISTENING+ESTABLISHED；
    无 Traceback。四插件拆分 + 页面/logo/显示名全部落地。

- 追加 13:05（页面桥接不可用修复）：AstrBot 把 `plugin_page_bridge.js`
  注入在 `</body>` 之前，而五个插件页用的是内联经典 `<script>`，执行顺序在
  桥接之前，导致 `window.AstrBotPluginPage` 为 undefined（页面提示
  “页面桥接不可用”）。qqadmin 的页面用 `type="module"`（延迟执行）所以正常。
  已把 worldbook/guard/memechance/tools/people 五个页面统一改成
  `<script type="module">`，静态文件已覆盖，刷新页面即可（建议 Ctrl+F5）。
  注意：必须从 WebUI 插件详情打开页面，直接访问 view URL 不会注入桥接。

- 追加 13:20（人物记忆 v1.1：模型提取要点表格）：
  - `qqbotstack_people` 增加 `profile` + `facts`（topic/summary/tags/ts），
    `messages` 降级为短期缓冲；注入改为 `[关系]+[画像]+[他聊过]`，不再贴原文。
  - 后台任务每 180s 扫一次（首次 15s 后回填），有 ≥4 条新消息才调模型；
    首次整理（last_ts=0）不受最少条数限制；provider 默认 `zgate-router`(HY3)，
    60s 超时，失败保留消息下轮重试。
  - 合并去重：同 topic + 摘要相似度 ≥0.75 更新旧条目；`fact_max=50`、
    TTL 180 天；整理后原文裁到 3 条。
  - 页面：要点表格（时间/话题/摘要/标签/删除）、画像、原始消息折叠、
    “整理这个人/整理全部”、整理设置；新增 `/extract`、`/fact/delete`、`/config`。
  - 验收：离线 API 测试全过（提取/去重/注入/JSON 容错）；13:17 重启后
    `extract=True/180s provider=zgate-router`，6 人历史整理完成
    （3/0/1/1/1/1 条 facts，原文裁到 3 条，画像已生成）；
    无提取报错；6199 ESTABLISHED。日志里的 Traceback 是 AstrBot 更新检查
    与重启关闭栈，与本插件无关。

- 追加 13:52（EmeraldEden 卷二新正典同步 + guard 1.6.19）：
  - 重读 EmeraldEden `设定/08-人物`、`大纲/01-02`、`大纲/细纲/02-卷二`，
    按新正典重写 `.work/世界书_中期.md`：**55 条 / 11,898 字 / 常驻 411 字**。
    当前阶段改为「中期后段，卷二结束、卷三还没开始」（梵铭 21、铭 18、犹达斯 22）。
  - 关键正典：悠塔**活着**，成了犹达斯，卡戎的二次生命，声音被梵铭烧掉，
    说不出话；梵铭知道自己只杀了一半。犹达斯不住教堂，只来过。玟德右臂
    在精灵族里失去，过去只写梵铭知道的那一点。新增老乔、莉莉安、老婆婆、
    塞拉斯与巴泽尔、拉梵、乌列尔、卡戎等条目与关系矩阵。
  - 人格升到 v16（1,676 字 / 24 条）：悠塔条目与 few-shot 改成「活着、失语、
    不住这里」；补拉梵/犹达斯/卡戎边界；保留「不知道就照实说不知道」。
  - 部署事故：`deploy_v8.ps1` 在 `--- backup` 阶段因远程
    `views/worldbook/index.html` 不存在被 `$ErrorActionPreference='Stop'` 中止，
    服务停在停止状态；先建目录+补视图，再重跑，恢复 Running。
  - 探针（Beam，20 例）发现并修：`occasional` 英文漏出（加确定性替换）；
    Beam 偶发把同一段答两遍（加相邻重复行清理）；「教堂里都有谁」只答铭
    （世界书条目从「教堂的住客」改名后 KEY_BOOST 没跟着改，检索键失效，
    已补 `教堂/住客/谁住/住在教堂/教堂里都有谁`）；`不住店` 措辞重新被带进新世界书
    （全部改「不在教堂过夜」，构建后 grep 为 0）；玟德年龄被报成 120 岁
    （条目改为「一百多岁，说个大概就行」）。
  - 复测：教堂住客答「我、玟德先生、铭」；卡戎答「不住在教堂」；玟德位置
    答「后院修剑鞘」不再固定外面；赫尔墨斯拒绝当帮手；清洗器实测
    `</rfl:parameter>`、`occasional`、重复行均被清掉。
  - 线上状态：guard **1.6.19**、worldbook 55 条、persona 1,676/24、
    Beam/Beam、OneBot 已连、无 Traceback；本地/远程 main.py SHA256 一致
    （`dc4a29b8…`）。

- 追加 14:12（去固定场景：人物不再被钉在某个地方做某件事）：
  - 用户点名：玟德来了以后「后院劈柴」、铭来了「后院活了/种花」、铭「在后院」
    这类写法把人物限死在固定区域和固定动作上，全部删掉。
  - 世界书删改：`玟德带来第一块木料，后院有他的劈柴声`、`铭住进来后后院活了…
    碗摆到自己位子上`、`后院的花是铭种的`、`此刻…数罐子/炖汤/劈柴/盐快用完/
    钟楼听风/去后院看铭种的东西`、`休息时擦盾`、`留座/倒茶/留她吃顿饭`、
    `一生住在门旁`、`后院是菜地与劈柴的地方`、`煮汤时是土豆和盐`。
  - 保留：住客身份（梵铭/玟德/铭）、职责（赫尔墨斯送货、露西送信、玟德守着
    教堂和火种）、关系、能力、过去。删的是日常脚本，不是设定。
  - 新增原则（人格 + 世界书两处）：谁在哪儿、在做什么按当下场景自然安排，
    每次可以不一样；不要固定成一套日常，也不要固定谁总在同一个地方做同一件事。
  - 人格升到 **v17（1,679 字 / 24 条）**：删 `后院的花是他种的`、`拉梵来会留座`、
    `露西留饭`、`赫尔墨斯讲价`；保留身份/关系/说话方式。
  - 世界书重建：**55 条 / 11,588 字 / 常驻 404 字**；`后院/劈柴/擦盾/留座/
    数罐子/钟楼听风/留她吃` 在源文件里均为 0。
  - 探针 v18（同一问题问 2–3 次）：玟德在做「磨剑/后厨切菜/后院劈柴」，
    铭在「藤蔓下/研究新藤蔓/树上或教堂后面」，梵铭在做「翻旧书/扫地/翻祈祷书」，
    玟德位置「后院/出门送信」——不再固定同一答案。模型仍会自己选后院/藤蔓/
    磨剑这类与设定相邻的画面，但已不是提示词写死。
  - 探针同时暴露混合英文与整段重复：`sharpening his sword`、`usually sitting
    in the chair by the fireplace`、`wherever he wants to go he just goes`、
    `excited/mostly/telling`，以及同一条答案连写两三遍。guard 升到 **1.6.21**：
    加短语级英文替换 + `_drop_repeated_tail`（保留第一遍）；实测 25 条探针回复
    清洗后拉丁字母为 0。
  - 线上状态：guard **1.6.21**、worldbook 55 条 / 11,588 字、persona v17
    1,679/24、Beam/Beam、OneBot 已连、无 Traceback。

- 追加 14:30（提示词精简 + 提示词规范文档）：
  - 人格 v19：**1,483 字 / 24 条**（v17 1,679，-11.7%）。删掉重复介绍
    赫尔墨斯/玟德/铭/犹达斯/拉梵的整段，保留身份、眼睛、关系、不知道的
    分寸、情绪基线、格式；few-shot 问法 `玟德长啥样` 改成
    `你能看清玟德的脸吗`，避免回「这个问题刚答过」。
  - 世界书：**55 条 / 10,846 字 / 常驻 404 字**（11,588，-6.4%）。压缩
    `人物口吻速查`、`关系矩阵`、`梵铭·关系`、`聊天时的硬约束`、`拉梵`、
    `身份辨析`、`玟德·和梵铭的相处`、`梵铭·他怎么看人`；保留 4–8 字辨识
    特征（玟德不说谢谢/对不起、铭只叫梵铭、犹达斯不能说话）。
  - 检索修复：`关系矩阵（中期）` 改名后 KEY_BOOST/PRIORITY 漏改，问
    「介绍一下你身边的人」只注入常驻条；已同步为 `关系矩阵（中期后段）`。
    人物 `· 关系` 去掉 `身边的人`，`人物口吻速查` 去掉 `介绍`，介绍类问题
    改走关系矩阵，避免把玟德的断口/左眼串到铭身上。
  - 事实收口：住客条目补「铭是梵铭被切走的一半，十八岁，浅灰毛、暖棕眼、
    藤蔓」；赫尔墨斯统一「只送货，不送信；信件归露西」；卡戎补「犹达斯是
    他的二次生命」；玟德年龄补「已经过了一百」。
  - guard 1.6.26：新增 `_FAKE_DIALOG`（从 `<|start|>` 等标记截断自续写假
    对话）；英文补 `afternoon/himself/telling` 等；年龄正则覆盖
    `一百二十岁/一百二十多岁/一百二十几岁` → `一百多岁`。
  - 探针：`sys_len` **2,077–2,625**，平均约 **2,500**（压缩前平均 2,730）。
    关键设定（身份/拉斐尔/悠塔/犹达斯/玟德/铭/拉梵/赫尔墨斯/露西/卡戎/
    乌列尔/教堂住客）通过；位置/动作同一问题多次仍会变；关系介绍改为注入
    关系矩阵，不再串人物。
  - 新增规范文档 [docs/PROMPT-SPEC.md](docs/PROMPT-SPEC.md)：分层与预算、
    必留/禁写、世界书键与优先级、压缩规则、变更流程、验收清单；已挂到
    docs/README.md 索引。
  - 线上状态：guard **1.6.26**、worldbook 55 条 / 10,846 字、persona v19
    1,483/24、Beam/Beam、OneBot 已连、无 Traceback。

- 追加 14:50（事故修复：inject_lore 钩子崩溃 + 代词追问误杀）：
  - 根因：插件拆分脚本按 `parse_share_link`→`_route_model` 整段删除时，把
    夹在中间的 `_apply_image_policy` 和 `_strip_reasoning_context` 定义一起删了，
    但 `inject_lore` 仍在调用。每次 LLM 请求都在钩子首行抛
    `AttributeError: '_apply_image_policy'`，导致模型路由、世界书、提示注入
    全部没执行；图片轮退回 Beam → 400 image；用户问「玟德长啥样」时
    世界书/人格上下文都没进去。
  - 另一根因：`他长啥样`（代词 + 4 字）被 `_topic_related` 判 `high-unrelated`，
    接话窗口直接忽略。新增 `PRONOUN_FOLLOWUP_RE`：窗口里机器人刚提过人时，
    「他/她/它 + 长啥样/这么/是不是/多大…」直接算相关，`_topic_drifted` 也不判跑题。
  - 修复：补回两个方法；新增 `.work/test_guard_selfcalls.py`（AST 静态检查
    self.xxx() 调用必须有定义），已通过；离线用例验证图片替换/推理剥离/代词判定。
  - 验收：14:46 重启后 `lore=55`、`stripped reasoning (16 entries)`、
    `route -> Beam` 正常出回复；无新的 AttributeError；6199 ESTABLISHED。

- 追加 14:52（图片 100% 回复修复）：
  - 根因：图片唤醒分支只看 `state` 是否存在和兴趣值，没检查
    `window_deadline`。接话窗口 300s 过期后 state 仍在、兴趣值每分钟只衰减 1，
    所以图片一直满足 `interest >= 50`，表现为 100% 回复。
  - 修复：非 @/引用/关键词的图片必须满足 `window_deadline > now`；新增
    `image_reply_prob`（默认 0.5），窗口内图片按概率回复；日志增加
    `window=True/False prob=0.50`。要更安静可把 `image_reply_prob` 调到
    0.2 或 0（0 表示只回复明确 @/引用/关键词的图片）。
  - 验收：14:49 重启启动行含 `image_prob=0.50`、`lore=55`；6199 ESTABLISHED；
    14:44/14:45 的 AttributeError 是修复前旧日志，14:46 后不再出现。

- 追加 15:10（人物记忆：画像叠加 + 名字纠正 + 防串人）：
  - 名字识别：正则允许点号（M.Venn）；拒绝问句（什么/啥/谁/怎么/吗/呢）；
    去掉尾部语气词（吧/啊/呀/哦/嘛/呢）。已纠正数据：
    <QQ-ID-A> preferred=M.Venn（清掉“什么吗”）；<QQ-ID-B> preferred=昵称乙，
    别名保留自设称呼（原词已脱敏）。
  - 画像叠加：提取 prompt 现在带旧画像 + 最近 10 条已知要点，要求“在旧画像
    基础上更新、保留仍有效信息、去掉被推翻的内容”，不再每批整段重写。
  - 防串人：
    * 人物提示新增 `[本轮说话的人]`：本轮发言的是「X」（QQ …），
      明确“别人说的名字/身份不要安到他头上”；
    * 合并接话时 `qqbotstack_people_qq` 指向 main 发言人，提示按 main 构建，
      不再用载体事件的发送者；
    * 接话块加“以上是不同的人，不要把 A 的称呼/身份安到 B 身上”；
    * 第二目标过滤 backchannel（？/笑死我了/哈哈哈），不再引用旁观者的
      语气词并套用前一个人的上下文。
  - 验收：回归/API/self-call 测试全过；15:02/15:10 重启正常，6199 ESTABLISHED。
    画像的增量更新需要下一次提取（≥4 条新消息，或页面点“整理全部”）。

- 追加 15:22（联网查证 + 称呼标题防覆盖）：
  - 事实：`provider_settings.web_search=false`，所有 websearch key 为空，
    `mcpServers={}`，`computer_use_runtime=none`——机器人当前**没有**可用的
    搜索/浏览器工具。旧日志 19:10 有 `web_search_anysearch` 成功记录，
    说明能力曾有、后来被关掉；AnySearch 源码要求 Bearer key。
  - 新增免 key 的 `web_search` Tool（`qqbotstack_tools`）：Bing 结果页为主、
    Google 兜底，实测目标机 Bing 可返回 10 条、工具返回 3 条标题/链接/摘要；
    已看到 AstrBot 启动日志 `Added llm tool: web_search`。
  - 内置 `web_search` 继续关闭（没有 key，开了只会调用失败）；以后有
    AnySearch/Tavily key 可再开。
  - guard 在“叫什么/是谁/长啥样/起名/查一下”等轮次注入 `[查证]`：
    “先调用 web_search 工具查一下再回答；查不到就说不知道，不要编。”
  - 称呼冲突：<QQ-ID-B> 后来的“叫我别名乙”把 preferred 覆盖了；现在
    `陛下/女王/大人/主人/老板/爸爸/妈妈/爹/娘` 这类标题不再覆盖真名
    （只保留为别名）。数据已改回 preferred=昵称乙，别名保留自设称呼（原词已脱敏）。
  - 验收：AstrBot 15:18 重启、`web_search` 注册成功、15:19:45 群消息正常到达。

- 追加 15:30（搜索速度与质量优化）：
  - 实测：Bing 0.83s、Google 0.36s；工具本身 0.6–1.0s，慢的是模型一轮里
    连查两次（中文一次、英文一次）再生成。旧实现只抓 Bing/Google HTML：
    Bing 中国区对英文/新闻查询返回不相关结果（“Leehom Wang singer”出 96编辑器、
    “姆巴佩”出“姆”字百科），Google 网页版要 JS（无结果），DDG 不通。
  - 新策略（`qqbotstack_tools`）：
    * 新闻类（新闻/最新/最近/news/recent/latest）→ Google News RSS；
    * 人物/事实类（是谁/叫什么/介绍/歌手/演员/球员/who is…）→ Wikipedia API
      （中文查询用 zh，英文用 en；搜索结果 + 首段摘要）；
    * 其他 → Bing HTML 兜底，再回退 Wikipedia/News。
    * 每轮只允许查一次（`qqbotstack_web_search_query` extra），重复调用直接
      返回“本轮已查过”；结果缓存 10 分钟；默认 3 条、最多 5 条；超时 10s。
  - 实测：姆巴佩新闻拿到 3 条当天新闻（新浪/正观/文学城），
    “Leehom Wang singer”拿到 Wikipedia 简介，英文新闻也能出结果。
  - 重启 15:29:30，`Added llm tool: web_search`、适配器已连接、6199 ESTABLISHED。
  - 仍存在：模型工具往返本身多一次 LLM 调用；要覆盖 JS 站点/更广来源，
    需要 AnySearch/Tavily 这类带 key 的搜索 API；可选做 guard 预查以省掉往返。

- 追加 16:05（幽默度 + 主动接话 + 名字串台修复，persona v20 / guard 1.6.28）：
  - 诊断：称呼没有串档——<QQ-ID-B> 的「别名丙」是 15:25 自己说的，people 与
    long_memory 各存一份；真正的问题是 15:27 接话时模型把提示块片段拼成了
    「别名丙 你刚说的」，之后 15:30/15:31 对群友丙、M.Venn 两次逐字复读。
    guard 当时给的 `[名字校准]` 是对的（群友丙 / M.Venn），模型没听。
  - 不主动回复：心动值只活在接话窗口 state，窗口过期 `pop`；重启/热重载归零
    （12:00 后重载 33 次）；窗口外只剩 `random_prob=0.03`。12:41–14:36 的 143 条
    文本一次没中（约 1.3% 概率），且这 183 条里没有一条真的 @/引用 bot。
  - 幽默被压：世界书 `梵铭·性格` 写死「他不讲笑话，不抖机灵」，消息带「神父」就注入；
    人格幽默只有半句、无技法无示例；清洗链把 120 字内命中客服模板的回复整条换成
    「在 你说」，`别问` 换「这个我不知道」，纯笑声被判英文换走神句。
  - 改：人格 v20 加幽默段与两组示例（1,641 字）；世界书改性格/硬约束、`你是谁`
    键挪到梵铭身份页；guard 加 `[接梗]`、松绑清洗、加 `_LEAK_LINE`、名字硬校验
    （按实际提问者 + 发送前核对）、心动值落 `interest.json`、静默期主动通道
    （0.10/180s/≥60）、笑场接一声（0.15/240s）、`scope_close_window=false`、
    `random_prob=0.06`、出圈判定放过 `IN_SCOPE_RE`。
  - 验收：离线 `test_guard_selfcalls`、`test_followup_rules`（新增持久化用例）全过；
    Beam 探针 15 题，幽默题与关键设定均正常，`sys_len` 2,235–3,011。
  - 部署：备份 `.work/backup-20261027-humor`；16:01/16:02 重启，
    `prob=0.06 idle=0.1/180s/60 laugh=0.15/240s scope_close=False lore=55`，
    OneBot 已连接，无 Traceback。
  - 待观察：静默期主动与笑场接话的触发频率需要真机跑一段再调
    （`idle_reply_prob` / `laugh_join_prob` / `random_prob` 都在 config.json）。
  - 附带：`tools/verify-stack.py` 默认模型改 `hy3`、OneBot 端口检查放宽并重试；
    实跑五项全过（模型目录/网关对话/AstrBot/NapCat/OneBot）。
  - 说明：16:02 之后群里没有新消息，行为层只能靠探针与离线用例验收；
    真实语气与主动频率需要下一波群聊再复核。

- 追加 16:25（幽默改暖 + 主动插话入场判断，persona v21 / guard 1.6.29）：
  - 现场：16:16 有人 @ 别人发了「？」，16:17 另一人发「滚吧」，guard 的 idle 通道
    把它当成可插话时机，回了「门在左边 别走错」。这是「不看场合 + 不温和」的合成案例。
  - 语气根因：v20 幽默段的「带刺地顶回去」+ 世界书「对亲近的人有点欠揍」。
  - 入场根因：idle/random 只有概率和冷却，没有「这条是不是在跟别人说话 / 是不是冲突 /
    是不是正多人在聊 / 是不是刚说过话 / 是不是跑题」的判断。
  - 改：人格 v21（1,685 字）幽默改暖、加「先看心情」「先判断该不该开口」、换一条情绪
    安抚 few-shot；世界书性格/硬约束同步；guard 新增 `_interject_allowed` 七类拦截，
    idle 与 random 都过闸，拦截记 `skip idle/random reason=`；笑场接话加气氛检查；
    新增 `[情绪]` / `[插话]` 提示；补 11 个英文词替换。
  - 验收：`test_followup_rules` 新增 7 个入场用例全过；v21 探针「滚吧 → 我不动 我坐」
    「你别老是这样 → 哪样 你说说 说了我改 改不了我就认」「我今天有点累 → 那就先别撑着了」；
    canon（你是谁/眼睛/介绍身边人）正常；`sys_len` 2,279–2,819。
  - 部署：备份 `.work/backup-20261027-gentle`；16:23 重启 1.6.29，OneBot 已连接，无 Traceback。

- 追加 17:15（模型路由修正，guard 1.6.30）：
  - 现场：14:39–14:55 共 26 次 `400 [invalid_value] Beam supports text input only`
    （`messages[41]` / `messages[91]`），断路器 3 次 OPEN / 2 次 CLOSE；
    16:27–16:30 Beam 与 HY3 双 502，people 抽取失败（上游抖动）。
  - 根因：AstrBot 把引用消息里嵌套的 `Image` 收进 `req.image_urls`
    （`astr_main_agent.py:1600-1622`），guard 判图只看 `event.get_messages()`
    顶层链；同时 `zgate-beam.modalities` 声明了 `image`，AstrBot 的
    `_select_image_chat_provider` 与 `sanitize_contexts_by_modalities` 都不接管。
    断路器又把这些确定性 400 当上游故障计数，探活只发 `ping` 复现不了，
    于是「开了又关」。
  - 改：
    * `zgate-beam.modalities` 去掉 `image`（只留 text/tool_use）：带图请求
      （含引用图）在 build 阶段原生切到 `zgate-router`，失败 → `zgate-hy4`；
    * guard `_has_image()` 同时看 `req.image_urls` 与 `event.get_messages()`，
      图片轮不再漏给 Beam；纯图无文本也不再被早退跳过；
    * 断路器只统计 5xx/429/超时/断连，4xx 不计；
      熔断期在消息入口设 `selected_provider=zgate-router`，直接用 HY3 的 60 秒源，
      不再每轮先等 Beam 的 20 秒；
    * 新增 `breaker_fallback_provider`，线上 `config.json` 补齐
      breaker/model_image/fallback/strip_reasoning/image_judge_only 等键；
      `config.example.json` 同步。
  - 验收：新增 `.work/test_routing_breaker.py`（分类器/状态机/图片判定/路由/
    图片策略/provider 选择 6 组）全过；`test_guard_selfcalls`、
    `test_followup_rules` 全过。部署哈希一致；17:11:38 加载 1.6.30，
    `breaker_provider=zgate-router`、`breaker watching model=Beam`、OneBot 已连接。
    用目标机 AstrBot 真实代码跑 `_select_image_chat_provider`：
    image→zgate-router、text→zgate-beam。
  - 待观察：下一次真机图片轮 / 引用图轮需在群里复核
    （日志应出现 `does not support image input, switching ... zgate-router` 与
    `route -> HY3-Free`）；4xx 不再进入 `fail_count`。
    状态页 `/api/plugins/extensions/qqbotstack_guard/status` 需面板登录（401）。
  - 备份：目标机 `.work/backup-20261027-routing`（guard 目录 + cmd_config + guard config）。
  - 17:22 线上实测：Beam 502（约 19 秒）→ HY3 卡满 60 秒 APITimeoutError → HY4 3 秒，
    整轮约 88 秒；当时 HY3 探活 1.2 秒，属上游瞬时卡死。
    已把 `zgate-source.timeout` 60→**25 秒**，17:25 重启生效
    （备份 `.work/backup-20261027-hy3-timeout`）；Beam 20 秒、HY4 60 秒不动。
  - 状态：代码与部署已完成；真机图片轮 / 引用图轮待下一波群聊复核。

- 追加 22:45（等待逻辑：按模型熔断 + 立即跳过，guard 1.6.31）：
  - 现场：17:22 一次回复里 Beam 502 → HY3 卡满 60 秒 → HY4，用户等了约 88 秒。
    上游归用户处理，这里只改客户端的等待与切换。
  - 改：
    * 断路器从「只监控 Beam」改成 **Beam / HY3 分别计数**（`_breaker_fails` +
      `_breaker_open_models`）；连续 3 次 5xx/429/超时后，agent 请求遇到熔断模型
      立即返回 err（`LLMResponse(role="err")`），不再等 source timeout；
    * 只有传 `contexts` 的 agent 请求走 fail-fast；后台插件只传 prompt，
      仍按自己的超时跑，不会被 err 响应破坏解析；
    * Beam + HY3 都熔断时，在消息入口直接选 `zgate-hy4` 的 provider；
    * 探活按模型分别进行，调用原始 `text_chat`（`request_max_retries=1`），
      成功才解除对应模型；
    * 新增 `breaker_last_provider=zgate-hy4`；`zgate-hy4-source.timeout` 60→**30 秒**；
      热重载时重新包装 provider，避免计数闭包指向已卸载的旧插件实例；
    * 熔断跳过文案带 `LLM 响应错误` / `breaker open`，被 `_ERROR_TEXT` 接住，
      不会把技术错误发进群。
  - 验收：`.work/test_routing_breaker.py` 扩到 7 组（分类器/双模型状态机/
    图片判定/路由/图片策略/provider 选择/fail-fast 包装）全过；
    `test_guard_selfcalls`、`test_followup_rules` 全过；22:44:39 加载 1.6.31，
    日志同时出现 `breaker watching model=HY3-Free` 与 `model=Beam`，无 not found。
  - 阻塞：NapCat 侧 QQ 已退出登录，正在等扫码（二维码在目标机
    `runtime\napcat\cache\qrcode.png`），OneBot 尚未连上；扫码后需再复核
    一次文本路由、图片轮与熔断跳过日志。
  - 备份：目标机 `.work/backup-20261027-waitlogic`（guard 目录 + cmd_config）。

- 追加 22:50（提示词只写身份：persona v22 / worldbook 53 / guard 1.6.32）：
  > **已撤销（23:05）**：v22 删光规则与示例后，模型开始冒 emoji、夹英文单词
  > 和括号旁白；已回退到 v21 + 55 条世界书，改用 v23「性格放首尾」。
  > 以下记录保留作历史。
  - 现场：17:16:57 对方只发一个裸 @（正文为空），17:16:59 回
    「你@我做什么 有事说事」；17:20:20 对方回「阿巴巴巴」，17:20:23 回
    「别装傻 有话就说」。日志 `[guard-style] before==after`，确认是模型原文，
    不是清洗兜底；群里随后说「你咋这么凶」「冷酷无情」。
  - 根因：v21 的温柔段在第三段，第一段却写着「别人只 @ 你、没说话时，短接一句，
    直接问对方什么事」——更具体、更靠前，模型优先执行；「短句」「不客服腔」同向
    叠加。另有大量场景→动作规则与 12 组语气 few-shot，会被当成台词模板。
  - 改（用户要求：只告诉他是什么人，不要告诉他该怎么说；示例一并删除）：
    * 人格 v22：`.work/build_persona_v22.py` → 542 字、**0 组示例**；只留身份、
      关系、眼睛、悠塔、性格（温柔体贴、对人和蔼、不会不耐烦、风趣幽默、爱笑、
      玩笑是暖的、不拿人开刀、会闹会赖会赌气、不认输）。
    * 世界书 53 条 / 9,594 字：删 `梵铭·语言`、`人物口吻速查`；`性格` 删
      「先看对方心情」「不讲网络梗」「不许写成…」；`硬约束` 只留设定事实；
      玟德/赫尔墨斯/乌列尔/卡戎/塞拉斯/身份辨析/犹达斯等处删掉写法指令；
      `和梵铭的相处` 删「可以催他吃饭、拆穿嘴硬、别人问起照实说」等对应规则。
      保留防复读（不固定日常、不反复垫话）、剧情边界（不写后期）与设定事实。
    * guard 1.6.32：删 `[接梗]`、`[情绪]` 两段注入与 `BANTER_RE`；`[插话]` 只留
      「这轮没人点你」；`[名字校准]` 只给正确名字；接话块删「先回谁/别硬扯/
      不要列点」，保留防串名的身份说明。`NEGATIVE_RE` / `CONFLICT_RE` 仍做
      入场闸门（不是提示词）。
  - 验收：`test_followup_rules`（含入场判断）、`test_guard_selfcalls` 全过；
    v22 探针 12 题，`sys_len` 1,018–1,774：裸 @ →「……？你是在问我吗」、
    阿巴巴巴 →「你今天吃错药了吗」、被说凶 →「我这是温柔，看不出来吗」、
    累 →「坐下来歇会儿，我给你倒杯水」；你是谁/眼睛/犹达斯/赫尔墨斯底细正常；
    同一问题问两次地点不同。
  - 部署：备份目标机 `.work/backup-20261027-tone-purge`；22:46 重启 1.6.32；
    22:48 `loaded 53 entries`、`lore=53`；22:49 OneBot 已连接；部署时无 Traceback
    （22:5x 日志里的 Traceback 是 dashboard 更新检查 `UpdateServiceError`，与本插件无关）。
    DB `persona_len=542 / dialogs=0`，旧会话与消息历史已清。
  - 顺带修：线上 worldbook 插件此前仍是 40 条旧版（guard 回退副本才是 55 条）；
    本次插件与回退副本统一为 53 条。
  - 待观察：模型自由发挥后出现 emoji、夹英文单词、括号旁白；`_clean_style`
    会清 emoji/Markdown、替换常见英文词，但 `cheeks/fuss/predicting` 这类
    新词与括号动作可能漏到群里，下一波真机复核；需要时补 `_ENGLISH_FIXES`
    或旁的清洗，不动人格。

- 追加 22:55（napcat 自启关闭 + 路由真机复核）：
  - `QQBotStack-napcat` 计划任务已改为 **Disabled**。它只负责登录后自动拉起
    NapCat（交互式 cmd 窗口），用户改为手动启动；当前 NapCat 进程与 AstrBot
    连接不受影响，下次登录不会再弹窗。恢复自动启动：
    `Enable-ScheduledTask -TaskName QQBotStack-napcat`。
  - 22:48 扫码完成，OneBot 重新连接。真机日志确认图片分流已生效：
    图片/引用图请求出现 `Chat provider zgate-beam does not support image input,
    switching ... zgate-router` 与 `route -> HY3-Free (image handover)`，
    HY3 能正常描述图片；纯文本仍是 `route -> Beam`；没有
    `Beam supports text input only` 400。
  - 1.6.32 保留了 1.6.31 的按模型熔断 / fail-fast 逻辑（`_breaker_open_models`、
    `_breaker_skip_response`、`breaker_last_provider` 均在），部署哈希与仓库一致。

- 追加 23:00（关闭私聊回复：guard 1.6.33）：
  - 现场：AstrBot 默认 `friend_message_needs_wake_prefix=false`，任何私聊都会唤醒 LLM
    并回复；guard 的 `guard_private` 之前只给分享/点歌打标记，不拦截。
  - 改：guard 新增 `private_reply_enabled`（默认 **false**）；`guard_private` 在关闭时
    第一行 `event.stop_event()` 直接返回 —— 私聊的分享、点歌、指令都不再响应。
    打开后恢复原行为（分享 URL / 歌词 / 点歌 / 视频意图照旧打标记）。
  - 部署：目标机备份 `.work/backup-20261027-private-off`（main / metadata / config）；
    `config.json` 写入 `private_reply_enabled=false`；22:57 重启，任务 Running，
    aiocqhttp(OneBot v11) 已连接；日志无插件 Traceback（仅 dashboard 更新检查噪声）。
  - 文档：ARCHITECTURE 回复策略表、DESIGN-DEPLOY 验收、DESIGN-MEDIA 私聊验收、
    DESIGN-FOLLOWUP、TOOLS 配置表同步；`check-docs.py` 与 `check-secrets.py --all` 通过。

- 追加 23:05（回退 v22 + persona v23「性格放首尾」）：
  - 决定：v22 只写身份、删光规则与示例，副作用是 emoji / 夹英文 / 括号旁白；
    用户要求完整回退，再换一种方式。
  - 回退：persona 回到 v21（1,685 字 / 24 条）；世界书回到 55 条 / 10,933 字；
    guard 恢复 `[接梗]`、`[情绪]`、完整 `[插话]` / `[名字校准]` 与接话块。
    22:57 的 `private_reply_enabled` 私聊修复保留，合并为 **1.6.34**。
  - 新方式（v23，1,724 字）：以 v21 为基线，只做两处——
    1. 删掉第一段「别人只 @ 你、没说话时，短接一句，直接问对方什么事」
       （17:16「你@我做什么 有事说事」的来源）；
    2. 把「你温柔、体贴，对人和蔼，不会不耐烦；你风趣、幽默，爱笑，
       玩笑是暖的，不拿人开刀」放到人格**开头和结尾**。
    不新增场景→动作规则，不新增示例。
  - 验收：世界书从源文件重建后与线上 55 条（SHA `A78F74…`）逐条内容一致；
    `test_followup_rules`、`test_guard_selfcalls` 全过；v23 探针 12 题
    `sys_len` 2,200–2,849：裸 @ →「怎么了 是哪里没听清楚 还是想问别的」、
    阿巴巴巴 →「你是不是没睡够 说人话就行 我听得懂 也接得住」、
    被说凶 →「我不是凶 我只是不演」、累 →「那就先别撑着了…」；
    没有「有事说事 / 有话就说」。
  - 部署：备份 `.work/backup-20261027-rollback-v21`；23:00 重启 1.6.34；
    `loaded 55 entries`、`lore=55`；23:00:59 OneBot 已连接；无插件 Traceback；
    DB `persona_len=1,724 / dialogs=24`，旧会话已清。
  - 残留：探针里仍有 `</rfl:parameter>`（发送前 `_STRAY_TAG` 会清）和
    briefly / deeper / apron 这类英文（`_ENGLISH_FIXES` 未覆盖）；真机复核后再补词表。
  - 备注：需要临时恢复私聊（例如管理员 `/登录B站`）时，把 `private_reply_enabled`
    改成 true 后重载插件即可。

- 追加 23:14（API 小功能接口池过期修复：guard 1.6.35 / tools 14 项）：
  - 现象：23:04 面板批量测试时大量 `Request failed ... 404/403`；23:04:51 群里
    「api怎么调用不了」被 guard 跳过（没 @、没命中关键词），所以 bot 没答。
  - 根因：本地池 122 条里 **65 条已死**——`api.317ak.cn` 45 条旧免费路径
    全部 404/403（站点已改成要 API Key 的积分网关，`site_pool` 里 `ckey` 为空，
    即使填测试 key 也 404，说明路径已换）；`api.lolimi.cn` 14 条、
    `api.pearktrue.cn` 6 条域名解析失败（DNS 错误）。
    可用 57 条：yuafeng 30 / tangdouz 17 / wqwlkj 8 / xingzhige 2。
  - 改：
    * `presets/api_pool_default.json` 122 → **57**；
      `site_pool_default.json` 7 → **4**（只留可用站点）；
    * `qqbotstack_tools` 的 `api_allowlist` 17 → **14**：去掉 6 个死接口
      （安慰/来点段子/人品运势/看看黄历/二次元形象/动漫一言），补
      看看治愈 / 看看动漫 / 来个头像；guard 默认名单同步，版本 1.6.35。
  - 验收：全池批测 57/57 返回 2xx/3xx；23:13 重启后
    `api=True/14`、`tools loaded allowlist=14`、`loaded 55 entries`、
    OneBot 23:13:53 已连接；无 `api_allowlist missing`、无插件 Traceback。
  - 备份：目标机 `.work/backup-20261027-api-pool`
    （两 presets + tools config + guard main/metadata）。
  - 说明：要恢复 317ak 的 45 条，需要注册拿 API Key，并按它新的统一网关格式
    重写 URL；当前先不用它，等有 key 再说。

- 追加 00:25（20261028 guard 1.6.36：角色卡泄漏 / 夹英文 / 续聊判定 / 名字带 QQ）：
  - ① 世界书原文被整段吐出：前一晚 23:19 模型把角色设定排成
    「梵铭 二十一岁 伯恩山犬兽人 教堂的神父 …」整条发出——上游模型自带
    `<rfl:parameter>` 参数卡格式先验（提示词里没有），标签被剥离但内容发出。
    改：`_is_card_dump()` 按内容形状认卡（单行、≥5 段空格分隔名词段、
    含年龄段、≥2 个身份词），strip_style 命中后整条换走神句；
    7 例单测（含 4 条易误伤的正常回复）全过。
  - ② 夹英文变严重（当天 871 条回复 86 条夹英文，约 10%）：
    `_ENGLISH_FIXES` 补 ears/footsteps/stubborn/rough/third/nights/tired/
    afraid/quiet/soft 十个高频漏词；新增 `_latin_leftover`（专有名词白名单）
    + `_deenglish` 小模型修复通道（zgate-router，8s 超时；只对词表盖不住的
    回复多打一次，失败或修完仍夹英文就原样发）。
  - ③ 主动接话太依赖启发式：当晚「他叫奶蛙」被 high-unrelated 掐断、
    窗口一关就彻底沉默，而对方明显还想聊。改：新增续聊判定器
    （`followup_judge_*`，默认开；provider zgate-router；90s 冷却；
    15 分钟内 ≤3 次唤醒），在 scope/drift/high-unrelated/unrelated/low
    五个忽略点掐断前问一次小模型「这话是不是在跟你说、还想不想聊」，
    通过就当接话收进来；窗口已关的消息同样判一次，通过则重开 300s 窗口。
    限制：@ 别人 / 引用别人的不判；机器人 15 分钟没开口不判（那是主动开场）。
  - ④ 群聊串人（吃饭段答非所问、玟德/铭的线缠在一起）：接话上下文每条改为
    「名字（QQ:号）」，系统提示词新增 `[本轮说话的人]` 标注本轮发言人，
    并明确「引用里的名字属于被引用的人」；防串说明同步强化。
  - 部署：stop task → 备份 `.work/backup-20261028-guard1635` → 覆盖
    main.py / metadata.yaml → 清 pycache → start。启动行出现
    `judge=True/zgate-router/90s`，插件加载无 Traceback。
  - 待观察：`[judge] wake` / `[guard-english] repaired` /
    `card dump intercepted` 三类日志的出现频率与误伤率；
    表情包回复率实测为「热点窗口内 50% 概率 + 生成期必合并」，若仍嫌吵
    调 `image_reply_prob`（现 0.5）或 `interest_image_threshold`（现 50）。

- 追加 00:40（20261028 guard 1.6.37：判定器超时兜底）：
  - 现象：00:32:46 对方发「哦，原来是这样吗」（明确在跟 bot 说话），00:32:54
    `[judge] request failed: TimeoutError`，随后被 `ignore drift` 掐掉——
    判定器链路是通的，但它依赖的 zgate-router 当晚本来就在抖
    （00:20/00:24 连续超时重试），8s 超时一撞，判定器反而成了新的
    「明明在聊却闭窗」。
  - 改：判定失败/无输出/输出不是 JSON 时不再直接沉默，降级走
    `_judge_fallback()`——只信两个最硬的确定性信号（心动值 ≥ interest_high
    且机器人 10 分钟内刚说过话）就当接话收进来；LLM 明确答
    to_bot=false 仍然尊重。判定超时 8s → 12s。测试补两例
    （TimeoutError 唤醒、坏输出唤醒），套件全过。
  - 部署：备份 `.work/backup-20261028-guard1636`，00:36 启动行正常，
    远端哈希与本地一致。

- 追加 10:35（authsync 任务降频 + 隐藏启动，20261028）：
  - 现象：开机弹控制台窗口。排查确认来源是计划任务 `QQBotStack-authsync`
    （登录触发 + 每小时重复），窗口标题为 powershell.exe 路径；操作机默认终端是
    Windows Terminal，计划任务起控制台程序必然建可见窗口。
  - 改：触发器简化为每天 04:00 一次（StartWhenAvailable=true，错过下次登录补跑）；
    动作由 `powershell.exe ...` 改为 `wscript.exe //nologo tools\sync-auths-hidden.vbs`；
    新增 `tools/sync-auths-hidden.vbs`（ASCII / CRLF）。`-WindowStyle Hidden`
    实测无效（Windows Terminal 复用窗口造成假阴性，复测后纠正），故走 wscript 样式 0。
  - 验证：手动触发 → 可见窗口 0、日志新增 `skip: already synced today`、无残余进程、
    result=0、nextRun=2026-10-29 04:00。幂等语义不变。
  - 回滚：旧任务定义在 `.work/QQBotStack-authsync.backup.xml`。
  - 文档：ARCHITECTURE §1.1 / §2 两处表格、TOOLS §1.3 + 脚本清单、PITFALLS 新增 P89。

# 2026-10-28 第 N+? 轮：机器人复读上下文旧话（先喝茶）治理（guard 1.6.38）

## 任务目标
11:26 起的日志里，机器人 12:56–13:04 八分钟内把「白茶/喝茶」反复当垫话，
「先喝茶，其他慢慢来」对 5 个不同问题/人重复；用户要求找根因并修掉。

## 已完成变更
- [x] 根因：AstrBot `compression.max_turns=-1`，13 小时会话 114 条 / 39k 字整段回传；
      机器人自己说过 16 次茶，群友引用又把原句以 user 角色喂回 18 次。
- [x] guard 1.6.38：上下文折叠（近似重复助手回复、全局高频 bigram、最近短回复高频单字、
      引用机器人旧话的 `<Quoted Message>`）、`[本轮别复读]` 末尾块（点名意象 + 最近两句原话）、
      发送前近重复重说一次；开关 `context_dedup_enabled` / `repeat_guard_enabled` /
      `repeat_regen_enabled`。
- [x] people 1.1.1：画像/事实明确「背景不是台词；他提过不代表这轮还要再提」。
- [x] 文档：CHANGELOG、PITFALLS P90、PROMPT-SPEC 分层表。
- [x] 部署：备份目标机 `.work/backup-20261028-repeat/`；停 `QQBotStack-astrbot` →
      覆盖 guard/people → 清 `__pycache__` → 重启。
- [x] 启动验收：guard 1.6.38 `dedup=True repeat=True/True`；people 1.1.1；适配器已连接。

## 验收
- `.work/test-repeat-guard.py` 全绿（相似度、折叠、引用、设定名保护、禁复读块）。
- `.work/probe-dedup-db.py` 真实会话回放：114 → 98 条；助手茶话 16 → 3；
  引用茶话 18 → 4（剩余是用户自己说的）；事实型回答未删。
- `tools/check-docs.py` 21 篇通过；`tools/check-secrets.py --all` 0 问题。

## 待解决 / 注意事项
- 目标机重启后 followup 内存状态清空，接话窗口需等下一次点名重新打开（预期）。
- 线上复读率还要看下一轮真实对话的 `[guard-dedup]` / `[guard-repeat]` 日志；
  若仍有残留，优先调 `char_ticks` 的窗口/阈值，不要再往人格里加规则。

## 状态: 已完成

# 2026-10-28 第 N+1 轮：15:05 起「你先说清楚」审问腔（guard 1.6.39 / persona v24）

## 任务目标
用户指出「从三点零五分开始看他的聊天方式，还是有点奇怪」。定位 15:05–15:15
机器人回复的异常并修掉。

## 现象（真实日志 + DB 上下文）
- 15:06 `你先说清楚是哪个cli 要不然我只能猜`
- 15:10 被群友指出「这家伙咋还重复呢」后：`这次不算 你先说清楚是哪个命令行工具 要不然我只能猜`
- 15:15 `claude封号我听说过 但你用的是哪个CLI 具体说一下 我不猜了`
- 15:15 两人连续发言：`豆太祖 …说清楚 / limpid …你用的哪家`（抄了输入的
  「名字：内容」格式，一行一个人），并带 `</rfl:parameter>`。

## 根因
- [x] 主模型 Beam 指令跟随弱：同一份人格、同一段上下文，Beam 三条都在追问；
      DeepSeek-4.1-Flash 三条都是正常接话。人格里的「把话头还给对方」
      （两处）和「反问一句，把球踢回去」被 Beam 当成固定动作。
- [x] 上下文折叠误删：15:06 那句与更早的「谁是小阮 你先说清楚」共享
      「你先说清楚」，`_repeat_like` 按 bigram 重合 0.5 判成复读删除；
      15:10 模型以为自己没说过，又原样说一遍。
- [x] 重说提示词写「已经作废」，模型回「这次不算」再把原句抄一遍。

## 已完成变更
- [x] guard 1.6.39：`TOPIC_STOP_BIGRAMS` 加追问句式；折叠永不删最新一条
      机器人回复；重说提示词改 `[换一句]` 并禁止元话语；多人连续发言块补
      「不要模仿名字前缀格式」；启动行补 `model=simple/complex`。
- [x] persona v24：删两处「或者把话头还给对方」、改「反问一句，把球踢回去」
      →「说一件具体的小事」；len 1,702 / dialogs 24。
- [x] 模型：`model_simple=model_complex=DeepSeek-4.1-Flash`
      （fallback 仍 HY3-Free），config.example.json / 线上 config.json 同步。
- [x] 测试：`.work/test-repeat-guard.py` 新增追问句不判重、最新回复必留两例；
      `.work/test_followup_rules.py` 补齐 1.6.38 后缺的 stub 属性；两套全绿。
- [x] 文档：ARCHITECTURE 模型链、TOOLS 示例配置、CHANGELOG、PITFALLS P91；
      `tools/check-docs.py` 21 篇通过。

## 验证
- 离线重放：v23+Beam 三条追问；v24+DeepSeek 三条正常
  （15:06「没收到风声」、15:10「同一盘端两遍就腻了」、15:15 一句自然追问）。
- 延迟：Beam 中位 1.75s，DeepSeek 中位 2.11s（+0.36s）。
- 工具：`play_song_by_name` 两个模型都返回 `tool_calls`。
- 线上：15:38:55 加载 1.6.39，`model=DeepSeek-4.1-Flash/DeepSeek-4.1-Flash`
  `dedup=True repeat=True/True`、`lore=55`、`api=True/14`；OneBot 15:39:01
  已连接；无 Traceback；部署文件 MD5 与本地一致。
- 旧会话已清（persona 变更）：`conv 0 / hist 0`。

## 回滚
目标机 `.work/backup-20261028-v24/`：旧 main.py / metadata.yaml / config.json /
data_v4.db。覆盖后清 `__pycache__`，重启 `QQBotStack-astrbot`。

## 待观察
- 线上第一条被 @ 的回复是否走 DeepSeek（看 `[route]` 后 zgate 日志）。
- `[guard-repeat] regenerated` 是否还会出现「这次不算」类元话语。
- 若 DeepSeek 上游抖动，断路器会切 HY3-Free；HY3 是推理模型，注意正文为空。

## 状态: 已完成

# 2026-10-28 第 N+2 轮：控制成本，选免费模型（guard 1.6.40，混合路由）

## 任务目标
用户指出 DeepSeek 太贵，要求切回 Beam，并测试免费模型哪个更好。

## 已完成变更
- [x] 先把 `model_simple` / `model_complex` 切回 Beam（全量 DeepSeek 停止计费）。
- [x] 免费模型基准（同一段真实上下文 + persona v24，各 4 条 + 1 次工具调用）：
      | 模型 | 延迟中位 | 风格 | 工具 |
      |---|---|---|---|
      | Beam | 1.28s | 不稳，3 次重放 2 次仍打太极/反问 | 正常 |
      | Iceman | 26.19s | 最好，4/4 自然 | 正常 |
      | HY3-Free | 19.90s | 好，4/4 自然 | 正常 |
      | HY4-Pre-Free | 60s+ | 3/4 超时，不可用 | 正常 |
- [x] Beam 加运行时约束的稳定性测试：15:06 三次里两次仍会「你先说清楚」，
      15:15 仍抄名字格式 → 不靠提示词硬压，改路由。
- [x] guard 1.6.40 混合路由：
      * `model_simple=Beam`、`model_complex=HY3-Free`；
      * `COMPLEX_HINTS` 新增 AI/命令行/复读词（cli、命令行、模型、提示词、
        ai、gemini、claude、gpt、deepseek、openai、api、token、额度、中转、
        反代、封号、订阅、部署、显卡、重复、复读）；
      * ASCII 提示词按单词边界匹配（`said` 不命中 `ai`）；
      * 多人连续发言（文本以「以下是不同人的连续发言」开头）固定走复杂模型。
- [x] 配置：`config.example.json` / 线上 `config.json` 同步；metadata 1.6.40。
- [x] 测试：`test_followup_rules.py` 的路由段改为 hybrid，
      新增 4 条 AI 话题、1 条多人合并、1 条英文边界用例；两套测试全绿。
- [x] 文档：ARCHITECTURE 模型链、TOOLS 示例、CHANGELOG、PITFALLS P91 同步。

## 验证
- 离线：`谷歌要把cli关了？` / `这家伙咋还重复呢` / `AI 模型真一般` /
  `claude 封号` → HY3-Free；`晚上好` / `said ok` → Beam。
- 线上 16:21:02 加载 1.6.40：`model=Beam/HY3-Free`、`fallback=HY3-Free/HY3-Free`、
  `dedup=True repeat=True/True`、`lore=55`、OneBot 已连接、无 Traceback；
  部署文件 MD5 与本地一致（0a721f59…）。
- 旧会话仍是清空状态（persona v24 生效时清的）。

## 回滚
- `.work/backup-20261028-hybrid/`：1.6.39 + Beam/Beam 配置。
- `.work/backup-20261028-v24/`：全量 DeepSeek 之前的 1.6.38 + Beam/Beam + DB。

## 待观察
- 复杂轮会等 20 秒左右；如果群里嫌慢，把 `COMPLEX_HINTS` 里的词收窄
  （优先保留 cli/命令行/模型/提示词/重复）。
- HY3 是推理模型，`max_tokens` 由 provider 统一给 16384；若出现正文为空，
  先看 `finish_reason=length`。
- 第一条真实 @ 回复的路由日志还没看到（群里一直没人点它）。

## 状态: 已完成

# 2026-11-01 第 N+3 轮：建仓后首次独立代码审查与修复

## 任务
- 全仓代码审查（host/plugin 5 插件 + tools 10 脚本 + CI + 文档一致性），只修真问题：
  正确性 / 健壮性 / 脱敏 / 文档漂移；纯风格不动；不部署、不 push。

## 改动清单（按 commit 顺序）
- [x] sync-auths.ps1：`-replace '\\'` 只匹配成对反斜杠 → deploy_root 归一空转；
      改 `.Replace('\','/')`；补 `ssh_port`（ssh `-p` / scp `-P`）。
- [x] verify-stack.py：stack.conf 端口坏值（非数字 / 超范围）由 traceback 改为
      一行报错（`to_port()`，退出码 2、条目 T8）；ssh_port 同样校验。
- [x] guard main.py：DEFAULTS 六处与文档/示例对齐——random_cooldown_sec 300→180、
      followup_window_sec 45→300、followup_max_chain 3→10、media_pending_sec 180→300、
      interest_decay_per_min 1.5→1.0、scope_close_window True→False；
      `_load_pending_media` 改 with 打开（句柄泄漏）。
- [x] people main.py：`@register` 版本 1.1.0 → 1.1.1，对齐 metadata.yaml。
- [x] deploy-stack.ps1：api_key 改用 RNGCryptoServiceProvider（Get-Random 可预测）；
      `schtasks /tr` 路径加引号（含空格路径不再被拆）。
- [x] ci.yml：PowerShell 语法检查从只查 deploy-stack.ps1 扩到 tools/*.ps1 全部。
- [x] 脱敏：清掉残留兄弟应用名（TOOLS/SECRETS/DESIGN-DEPLOY/stack.conf.example/
      check-secrets 注释）；stack.conf.example 悬空的 qq 注释与字段归位。
- [x] 文档一致性：ARCHITECTURE（随机插话 25%→6%、出圈不直接关窗、世界书视图指向
      qqbotstack_worldbook editor、§6 WebUI 例外口径）、TOOLS（示例 random_prob 0.06、
      guard 视图行）、DESIGN-FOLLOWUP（scope_close_window 默认 false）、
      README（WebUI 回环表述补 6185 例外）。
- [x] PITFALLS：补 P92（反斜杠归一坑）、P93（端口坏值坑）。

## 验证
- `python -m py_compile` 全部通过；guard DEFAULTS 用 AST 抽取与
  config.example.json 逐键比对一致。
- verify-stack 四条坏值路径（坏端口 / 超范围 / 占位符 / 缺文件）临时 conf 干跑，
  全部一行报错、退出码 2，不触网。
- PowerShell 三个 ps1 Parser 校验通过；deploy keygen 表达式干跑 48 位 hex；
  deploy_root 归一四种写法干跑正确。
- `check-docs.py` 21 篇通过；`check-secrets.py --all` 无发现。

## 状态: 已完成
