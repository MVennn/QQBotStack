# 工具与组件清单

> **一句话**：工具清单（**正本**）：每个脚本干什么、三块组件从哪来、版本与许可、
> 目录结构、参数与退出码。

---

## 1. 脚本

| 脚本 | 跑在哪 | 干什么 | 会改状态吗 |
|---|---|---|---|
| `tools/deploy-stack.ps1` | 目标机（管理员 PowerShell） | 分阶段幂等部署：网关 / 协议端 / 机器人 | **会** —— 见 [ARCHITECTURE.md](ARCHITECTURE.md) §2 |
| `tools/verify-stack.py` | 操作机 | 五步验收：模型目录 / 网关对话 / AstrBot 面板 / NapCat 连接 / 端到端问答 | 不改；会消耗少量模型额度 |
| `tools/sync-auths.ps1` | 操作机 | 把 `auths/` 推到目标机并重启网关；**每天最多一次**（日期记在 `%LOCALAPPDATA%\QQBotStack\authsync.state`） | 改目标机的账号文件与网关进程 |
| `tools/sync-auths-hidden.vbs` | 操作机 | `sync-auths.ps1` 的隐藏启动器，供计划任务调用（`WScript.Shell.Run(..., 0, True)`） | 不改；只是启动器 |
| `tools/start-stack.ps1` | 操作机 | 一键查看/拉起四块组件；`-Restart` 重启网关 / zgate / AstrBot | **会** —— 在目标机起进程、首次运行会建 NapCat 计划任务 |
| `tools/build-worldbook.py` | 任意 | 把 Markdown 设定集切成世界书条目（按二级标题切、标题与加粗术语作关键词） | 只写输出 JSON |
| `tools/check-docs.py` | 任意 | 文档自检：断链、失效锚点、缺引言块、孤儿文档 | 不改 |
| `tools/check-secrets.py` | 任意 | 脱敏扫描：token、本机绝对路径、真实邮箱 | 不改 |
| `tools/make_social_preview.py` | 任意 | 从 `assets/icon.svg` 渲染 logo 与社交预览 | 只写 `assets/` |

### 1.1 `deploy-stack.ps1`

```powershell
powershell -ExecutionPolicy Bypass -File tools\deploy-stack.ps1 -Stage all
```

| 参数 | 说明 |
|---|---|
| `-Stage` | `gateway` / `napcat` / `astrbot` / `all`，默认 `all` |
| `-Root` | 部署根目录，默认脚本所在目录的上一级 |
| `-WhatIf` | 只打印将要做什么 |

每个阶段可重复执行。`gateway` 阶段会覆盖 `wb2api.exe` 与 `run-wb2api.cmd`，
但**不会覆盖已存在的 `config.json`**（里面有你生成的 api_key 与已登录账号的关联）。

### 1.2 `verify-stack.py`

```sh
python tools/verify-stack.py --conf host/stack.conf
python tools/verify-stack.py --host <HOST-IP> --user <HOST-USER> --key <API-KEY>
```

退出码：`0` 全通过 / `1` 有项目失败 / `2` 配置缺失。失败项打印
[TROUBLESHOOTING.md](TROUBLESHOOTING.md) 的条目号。

### 1.3 `sync-auths.ps1`

```powershell
powershell -ExecutionPolicy Bypass -File tools\sync-auths.ps1
```

| 参数 | 默认 | 说明 |
|---|---|---|
| `-Conf` | `<repo>\host\stack.conf` | 从这里读目标机的 host / user |
| `-Source` | ZcodeAIModels 的 `gateways/upstream/workbuddy/auths` | 账号文件来源 |
| `-StateFile` | `%LOCALAPPDATA%\QQBotStack\authsync.state` | 记录最后一次成功同步的日期 |

**幂等**：当天已同步过就直接退出（退出码 0），不会重复推送。
推送成功后会重启目标机的 `QQBotStack-wb2api` 任务，让新账号生效。
日志在 `%LOCALAPPDATA%\QQBotStack\authsync.log`。

计划任务 `QQBotStack-authsync` 就是它的定时包装：**每天 04:00 触发**（错过则在下次
登录后补跑），注册需要管理员权限。它通过 `tools/sync-auths-hidden.vbs` 以隐藏窗口
拉起 PowerShell —— 操作机的默认终端是 Windows Terminal，直接起控制台程序会弹一个
可见窗口，`-WindowStyle Hidden` 也压不住（见 [PITFALLS.md](PITFALLS.md) P89）。
账号归属的设计理由见 [ARCHITECTURE.md](ARCHITECTURE.md) §1.1。

### 1.4 `start-stack.ps1`

```powershell
powershell -ExecutionPolicy Bypass -File tools\start-stack.ps1 -Status
powershell -ExecutionPolicy Bypass -File tools\start-stack.ps1              # 缺什么起什么
powershell -ExecutionPolicy Bypass -File tools\start-stack.ps1 -Restart astrbot
```

| 参数 | 说明 |
|---|---|
| `-Status` | 只报告四块组件的任务状态与进程，不启动、不改状态 |
| `-Restart` | `astrbot` / `gateway` / `zgate` / `all`；重启后面板能应答（6185）才算完 |
| `-Wait` | 起完后等几秒再取一次状态，默认 8 |
| `-Conf` | 默认 `<repo>\host\stack.conf` |

**首次运行**会在目标机上落两个东西：`runtime\napcat\run-napcat.cmd`（找最新的
`NapCat.*.Shell` 目录、已在跑就直接退出）与计划任务 `QQBotStack-napcat`
（**登录后延迟 20 秒**触发，可随时 `schtasks /run`，以交互令牌跑，QQ 才会出现在
桌面会话里）。之后 NapCat 不再需要远程登录、进目录双击 `napcat.bat`。

脚本不存主机值：host / user / ssh_port 全部从 `host/stack.conf` 读，部署根
（`<部署根>\runtime\...`）从目标机上 `QQBotStack-wb2api` 任务的动作路径反推，
换机器不用改脚本。`tools\start-stack.cmd` 是双击入口；仓库根目录的
`启动QQBotStack.lnk` 指向它（快捷方式不入库，换机器重新建一个即可）。

退出码：`0` 四块都在 / `1` 有组件没起来 / `2` 配置或 SSH 出问题。

### 1.5 `host/plugin/qqbotstack_guard/`

AstrBot 插件，决定机器人在群里什么时候开口。部署位置：
`<实例>\core\data\plugins\qqbotstack_guard\`。

| 文件 | 作用 |
|---|---|
| `main.py` | 插件本体：放行 / `stop_event()` 的判定；分享与点歌的 LLM Tool；B站兜底 |
| `config.json` | **实例配置，不入库**（含群号与关键词）；模板见 `config.example.json` |
| `worldbook.json` | **世界书产物，不入库**；当前中期版由 `.work/build_midworldbook.py` 从 `.work/世界书_中期.md` 编排，底层仍调用 `tools/build-worldbook.py` |
| `views/worldbook/index.html` | WebUI 浏览页（数据内联）：搜索条目、看关键词与正文 |

```json
{
  "allowed_group": "<GROUP-ID>",
  "keywords": ["<KEYWORD-1>", "<KEYWORD-2>"],
  "random_prob": 0.25,
  "random_cooldown_sec": 180,
  "wake_prefix": "/",
  "routing_enabled": true,
  "model_simple": "Beam",
  "model_complex": "HY3-Free",
  "simple_max_len": 14,
  "private_reply_enabled": false,
  "share_wake_enabled": true,
  "music_intent_enabled": true,
  "video_intent_enabled": true,
  "video_reply_cooldown_sec": 60,
  "takeover_parser": true,
  "share_fallback_enabled": true,
  "share_reply_cooldown_sec": 60,
  "share_meta_timeout": 10
}
```

新增的分享/点歌能力：

| 配置/接口 | 作用 |
|---|---|
| `private_reply_enabled` | 是否回复私聊（默认 false；关闭时私聊直接停事件，分享/点歌/指令都不响应） |
| `share_wake_enabled` | 群/私聊里出现 B站/抖音/快手/小红书链接或 QQ 小程序卡片时唤醒 LLM |
| `music_intent_enabled` | 点歌/聊歌触发词唤醒 LLM（见下方触发词表） |
| `video_intent_enabled` | 「这个视频 / 视频好看 / 刷到一个视频」等聊视频短语唤醒 LLM |
| `video_reply_cooldown_sec` | 同一群聊视频接话冷却（默认 60 秒） |
| `takeover_parser` | 运行时关闭 `astrbot_plugin_parser` 的自动解析，改由 `parse_share_link` 工具发送 |
| `share_fallback_enabled` | parser 失败时用 yt-dlp / OpenGraph 发封面+标题+链接 |
| `share_reply_cooldown_sec` | 同一 URL 的接话冷却（默认 60 秒） |
| `parse_share_link` | LLM Tool：解析并发送分享内容，返回标题/作者/简介给模型接话 |

触发词分三类（正则在 `main.py` 顶部）：

| 类别 | 触发示例 |
|---|---|
| 点歌/聊歌 | 想听、要听、听一下、放一首、来一首、点歌、这首歌、这首、那首歌、单曲循环、在听、我听的是、我在听、最近在听、推荐…歌、有没有…歌、什么歌、歌名、BGM、背景音乐、歌…好听、好听…歌、`《歌名》` |
| 聊视频 | 这个视频、这段视频、视频好看/不错、刷到…视频、看了…视频、这个剪辑/片段/短片/直播、这个番/剧/电影/综艺/纪录片、这个UP/博主/主播 |
| 分享 | B站/抖音/快手/小红书链接、`b23.tv` / `v.douyin.com` / `v.kuaishou.com` / `xhslink.com` 短链、QQ 小程序 `Json` 卡片 |

聊歌时如果没提具体歌名（如「这首歌叫什么」），提示词会让模型接话/反问，不拿整句去搜；
「这个视频里的 BGM 是什么歌」同时命中两类，会走“视频里的音乐”提示，不猜歌名。
聊视频按群 60 秒冷却，避免连续接话刷屏。

改完 `config.json` 需要重启 AstrBot 才生效。行为矩阵见
[ARCHITECTURE.md](ARCHITECTURE.md) §1.2 与 §1.5，完整设计见
[DESIGN-MEDIA.md](DESIGN-MEDIA.md)，实现原理见 [PITFALLS.md](PITFALLS.md) P19 / P24。

### 1.6 `host/plugin/qqbotstack_memechance/`

AstrBot 插件，负责「表情标记」的最后一段提示和发送前清理。部署位置：
`<实例>\core\data\plugins\qqbotstack_memechance\`。

| 文件 | 作用 |
|---|---|
| `main.py` | 在 `on_llm_request` 末尾追加 `&&名字&&` 提醒 + 示例；发送前清理泄漏的 XML 标签；随机配图备用 |
| `config.json` | **实例配置，不入库**；模板见 `config.example.json` |

```json
{
  "enabled": true,
  "pack_id": "qq-fav-001",
  "probability": 0.2,
  "cooldown_sec": 60,
  "marker_reminder_enabled": true,
  "leak_sanitize_enabled": true,
  "context_keep": -1,
  "fallback_names": ["抱小鸡", "猫狗贴", "哭哭狗", "哭脸狗", "冒汗狗", "趴问号", "毛巾狗"]
}
```

当前正式模式是**模型单轮选图**：meme_manager 把 25 个名字写进 system prompt，
本插件在所有 hook 之后（priority `-100`）再补一段提醒和真实示例，模型在回复末尾
输出 `&&名字&&`；meme_manager 剥掉标记并按 `generation.emotion.probability`
（当前 50）决定是否发图。`enabled=true` 的随机兜底只在模型没选中或门控没中时生效，
从 `fallback_names` 列的安慰/难过类里抽，`probability` 是 0.2、`cooldown_sec` 60 秒。
`leak_sanitize_enabled` 清理工具回合漏出的 `</rfl:parameter>` 一类标签。
`context_keep=-1` 表示不改动上下文；正数表示只保留最近 N 条（调试用）。
改完 `config.json` 需要重启 AstrBot 才生效。设计见
[DESIGN-MEME-EXPORT.md](DESIGN-MEME-EXPORT.md) §3。

## 2. 组件来源与版本

| 组件 | 来源 | 本仓记录的版本 | 许可 |
|---|---|---|---|
| AstrBot | `AstrBotDevs/AstrBot` 官方 Release | 4.29.x | AGPL-3.0 |
| AstrBot Launcher | `AstrBotDevs/astrbot-launcher` 官方 Release（`*_x64-setup.exe`） | 0.3.13 | MIT |
| NapCatQQ | `NapNeko/NapCatQQ` 官方 Release（`NapCat.Shell.Windows.OneKey.zip`） | 4.18.41 | 自定义（限再分发、非商业） |
| workbuddy2api | `linguo2625469/workbuddy2api-panel`，`go build -o wb2api.exe ./cmd/server` | 见上游 | MIT |
| astrbot_plugin_parser | AstrBot 插件市场（`Zhalslar/astrbot_plugin_parser`） | 1.6.1 | MIT |
| astrbot_plugin_music | AstrBot 插件市场（`Zhalslar/astrbot_plugin_music`） | 3.3.1 | GPL-3.0（**外部安装，不 vendor**） |

> **本仓不分发任何上游二进制。** 部署脚本从官方 Release 下载，落到 `runtime/`（不入库）。
> NapCat 的许可禁止公开再分发修改版，AstrBot 是 AGPL —— 两者都只下载、不打包、不修改。

## 3. 目录结构

```text
QQBotStack/
├── host/
│   └── stack.conf.example       主机与账号配置模板（只有占位符）
├── tools/
│   ├── deploy-stack.ps1         分阶段部署（纯 ASCII）
│   ├── verify-stack.py          五步验收
│   ├── check-docs.py            文档自检
│   ├── check-secrets.py         脱敏扫描
│   └── make_social_preview.py   门面资源渲染
├── docs/                        文档（索引见 docs/README.md）
├── assets/                      门面资源（icon.svg 是正本）
├── runtime/                     部署后生成（不入库）
└── .github/                     Issue 表单与 CI
```

## 4. 三块组件怎么配（要点）

| 组件 | 关键配置 | 值 |
|---|---|---|
| wb2api | `config.json` 的 `listen` | `127.0.0.1:7863`（**不要** `:7863`，那会绑所有网卡） |
| wb2api | `config.json` 的 `api_key` | 每个部署点重新生成，别复用别处的 |
| NapCat | OneBot 网络配置 | **WebSocket 客户端** → `ws://127.0.0.1:6199/ws`，带 token |
| AstrBot | 服务提供商 | OpenAI 兼容，`http://127.0.0.1:7863/v1`，模型 `global:hy3` |
| AstrBot | `max_tokens` | **≥ 2048** —— hy3 是推理模型，给少了正文为空（[PITFALLS.md](PITFALLS.md) P4） |
| AstrBot | 平台适配 | aiocqhttp，`ws_reverse_host=127.0.0.1`、`port=6199`、token 与 NapCat 一致 |

## 5. 模型侧速查

| 项 | 值 |
|---|---|
| 可用模型数 | 55（6 个账号都在时） |
| hy3 系列 | `cn:hy3`、`cn:hy3-x`、`global:hy3` |
| hy4 系列 | `global:hy4-preview`（付费，积分不足时 503）、`global:hy4-preview-f`（免费档） |
| 响应特征 | 同时返回 `content` 与 `reasoning_content`（推理模型，`max_tokens` 要给足） |
| 无账号时 | `/v1/models` 返回 0 条 —— 目录由账号聚合，不是故障 |

**能力边界**（决定 provider 的 `modalities` 怎么填）：

| 能力 | 支持 | 说明 |
|---|---|---|
| 文本 | ✅ | — |
| 图片 | ✅ | hy3 / hy4 都能读图，实测可读出图内文字 |
| 音频 | ❌ | `input_audio` 返回 400 |
| 函数调用 | ✅ 经 zgate | 直连 wb2api 会被剥掉 `tools`；经 zgate 正常，实测两模型都返回 `tool_calls` |

**按模型分**（能力不按家族统一，加新模型必须逐个测）：

| 模型 | 文本 | 图片 | 工具调用 |
|---|---|---|---|
| `Beam`（OpenCode） | ✅ 1.7s | ❌ 图片请求直接 400 | ✅ |
| `HY3-Free`（WorkBuddy） | ✅ 2.1s | ✅ 4.2s 可读出图内文字 | ✅ |

路由据此把带图的消息固定交给 `HY3-Free`（见插件 `_route_model`）。

因此 provider 的 `modalities` 是 `["text", "image", "tool_use"]`（前提：走 zgate）。
填错会让 AstrBot 误判能力（填少了丢图片、填多了浪费 token），详见
[PITFALLS.md](PITFALLS.md) P20。
