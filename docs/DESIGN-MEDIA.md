# 媒体分享解析与自然点歌 —— 踩点与设计

> **一句话**：用上游「万能解析器」做 B站/抖音/快手/小红书媒体，用上游「点歌」做音乐卡片，
> 只魔改 `qqbotstack_guard` 把它们接进人格对话；不碰上游源码，不把 GPL 代码并进本仓。

状态：**已确认并实施**（2026-10-26）。用户选择：方案 A（上游插件 + 魔改 guard）、
B2（yt-dlp 兜底）、网易云 + 卡片优先、安装 ffmpeg。

---

## 0. 结论

**可行。** 推荐路线：

1. 安装两个上游插件（AstrBot 插件市场里都有）：
   - `astrbot_plugin_parser` 1.6.1（MIT）—— 解析 B站/抖音/快手/小红书/QQ 小程序卡片，
     下载视频/图集并发送。
   - `astrbot_plugin_music` 3.3.1（GPL-3.0，**外部安装、不 vendor**）—— 搜歌、发 QQ 音乐卡片、
     自带 LLM Tool `play_song_by_name`。
2. 魔改本仓的 `qqbotstack_guard`（MIT）：
   - 让「分享链接 / QQ 小程序 JSON 卡片 / 想听歌」三类消息能唤醒 LLM；
   - 注册一个 LLM Tool `parse_share_link`，**复用解析器插件的 parser 实例**发送媒体；
   - 在 `on_llm_request` 里注入「这是分享 / 这是点歌」的提示，让模型用梵铭人格接一两句；
   - 运行时接管解析器插件的自动解析（把它 whitelist 置空），避免「插件先发媒体 → 默认 LLM
     被 `_has_send_oper` 跳过 → 没有人格接话」。
3. 可选安装 ffmpeg：B站 DASH 视频需要合并音视频；抖音/快手直链 MP4 不需要。

这样消息流是：

```text
群友发 B站小程序/抖音链接
  → guard 识别链接或 Json 卡片，唤醒 LLM
  → LLM 调 parse_share_link
      → 复用 parser 插件的 parser.parse()
      → parser 插件发送媒体/卡片
      → 工具把标题/作者/简介返回给 LLM
  → LLM 用梵铭人格接一两句（“这个我看了…”“你居然会刷到这个”）

群友说“我想听晴天”
  → guard 识别音乐意图，唤醒 LLM
  → LLM 调点歌插件的 play_song_by_name
      → 插件搜网易云、发 QQ 音乐卡片
      → 工具返回“已发送《晴天 - 周杰伦》”
  → LLM 接一句（“是这首吗？嗯…品味不错”）
```

---

## 1. 现状与实测

### 1.1 机器人侧

| 项 | 实测 |
|---|---|
| AstrBot | **4.29.3**，实例 `<INSTANCE>` 正常运行 |
| Provider | `zgate-router` / `HY3-Free`，`modalities=["text","image","tool_use"]` |
| 函数调用 | 经 zgate 实测 `tool_calls` 正常（`Beam`、`HY3-Free` 都返回） |
| 现有插件 | `qqbotstack_guard`、`astrbot_plugin_meme_manager` |
| 插件市场 | 可访问，已有 `astrbot_plugin_parser` 1.6.1、`astrbot_plugin_music` 3.3.1 |
| NapCat | 4.18.41，OneBot 11 反向 WS 正常 |
| ffmpeg | **未安装**（`Get-Command ffmpeg` 为空） |
| 磁盘 | F: 剩余约 200 GB |

### 1.2 平台接口实测（目标机网络）

| 平台/能力 | 结果 | 说明 |
|---|---|---|
| B站网页 | ✅ 200 | `window.__INITIAL_STATE__` 可读标题/UP/封面 |
| B站旧 API | ⚠️ 412 | `x/web-interface/view` 触发风控，带 buvid 仍 412 |
| B站 yt-dlp | ✅ | 标题/UP/封面/格式列表正常，可绕开 412 |
| B站 DASH | ⚠️ 需 ffmpeg | 视频流/音频流分离，合并要 ffmpeg |
| 抖音 ttwid | ✅ 200 | 匿名注册 `ttwid` 成功 |
| 抖音分享页 | ✅ 200 | `window._ROUTER_DATA` 可读标题/作者/视频直链 |
| 抖音视频直链 | ✅ 200 `video/mp4` | 实测约 21 MB，带音轨 |
| 快手短链 | ✅ 200 | 跳 `chenzhongtech.com`，`window.INIT_STATE` 可读 |
| 快手视频直链 | ✅ 200 `video/mp4` | 实测约 4.8 MB，带音轨 |
| 小红书 | ⚠️ 未完整实测 | 需要 Cookie；本次样本已失效，页面返回 404 |
| 网易云搜索 | ✅ 200 | `POST /api/search/get/web` 正常 |
| 网易云音频 | ⚠️ 部分可用 | 免费歌 `api.qijieya.cn` 返回 `audio/mpeg`；VIP 歌返回空 HTML |
| NapCat 音乐签名 | ✅ 200 | 自定义卡片签名返回 `com.tencent.music.lua` |
| NapCat 原生 163/QQ 卡片 | ⚠️ | 只传 `type+id` 时签名服务要求 `title`；补 `title` 会退化成图文卡，不建议 |
| QQ 小程序卡片 | ✅ 解析器支持 | `Json` 段里的 `meta.miniapp` / `meta.detail_1.qqdocurl` 都能提 URL |

### 1.3 关键机制（决定方案）

1. **QQ 小程序卡片到达 AstrBot 后是 `Json` 组件**，`event.message_str` 为空。
   解析器插件会扫描 `Json.data` 提取 URL；`qqbotstack_guard` 现在会因为「无文本、非 @、非关键词」直接
   `stop_event()`，所以卡片既不会被解析，也不会有人格回复。
2. **AstrBot 默认 LLM 请求有一个门槛**：
   `process_stage` 只在 `not event._has_send_oper` 时才走默认 LLM。
   任何插件先 `event.send()` 过，默认 LLM 就不跑了。
   所以「解析器插件自动发媒体 + 期望默认 LLM 再补一句」**行不通**。
3. **LLM Tool 内部发送不受这个门槛影响**：工具在 agent 循环里 `event.send()` 之后，
   agent 仍会拿到工具返回值并继续生成最终回复。点歌插件的 `play_song_by_name` 就是这么工作的。
4. **handler 顺序**：`star_handlers_registry` 按 `priority` 降序执行。
   给 guard 的 handler 设高优先级（如 `priority=100`），它就能先于解析器插件决定放行/拦截。

---

## 2. 方案对比

| 方案 | 做法 | 优点 | 缺点 | 结论 |
|---|---|---|---|---|
| **A. 上游插件 + 魔改 guard**（推荐） | 装 parser/music；guard 注册 `parse_share_link` 工具，复用 parser 实例；运行时关掉 parser 自动解析 | 平台覆盖全、代码少、上游持续维护；人格回复由默认 agent 生成 | 依赖上游内部属性（`parser_map`/`sender`），需锁版本；音乐插件 GPL 只能外部装 | **推荐** |
| B. 全部自研 | 自己写 B站/抖音/快手/小红书解析 + 点歌 + 卡片 | 完全可控、无 GPL | 四个平台的签名/风控/下载都要自己维护，工作量大、易失效 | 不推荐 |
| C. 只装插件不改 guard | 装 parser/music，保持现状 | 最省事 | 小程序卡片被 guard 拦掉；链接解析后没有人格接话；点歌只有命令式 | 不满足需求 |

---

## 3. 详细设计（方案 A）

### 3.1 组件职责

| 组件 | 职责 | 是否改 |
|---|---|---|
| `astrbot_plugin_parser` | 平台解析、媒体下载、卡片渲染、发送 | 不改源码；运行时把 `cfg.whitelist` 置为哨兵值，关闭它的自动解析 |
| `astrbot_plugin_music` | 搜歌、发卡片/语音/文件/文本、LLM Tool | 不改源码；只改插件配置 |
| `qqbotstack_guard` | 唤醒判定、分享/点歌提示注入、`parse_share_link` 工具、B站兜底 | **改** |
| NapCat | 把 `music` 段签名成 QQ 卡片 | 不改；可选配置 `musicSignUrl` |
| ffmpeg（可选） | B站 DASH 合并、AAC-LC 转码 | 系统安装 |

### 3.2 `qqbotstack_guard` 改动

#### 3.2.1 唤醒判定

在现有 `guard()` 里增加三步，顺序在「关键词」之前：

1. **命令前缀**：保持现状，`/` 开头交给默认管线。
2. **分享链接/卡片**：
   - 扫描 `event.get_messages()` 里的 `Json`，提取 URL；
   - 扫描 `event.message_str`，匹配支持平台的 URL 正则；
   - 命中则 `event.set_extra("qqbotstack_share_url", url)`，
     `event.is_at_or_wake_command = True`，`return`。
3. **音乐意图**：
   - 正则：`想听|要听|听一下|放一首|来一首|点歌|有没有.*歌|推荐.*歌`；
   - 命中则 `event.set_extra("qqbotstack_music_intent", True)`，
     `event.is_at_or_wake_command = True`，`return`。
4. 后面保持关键词 / @ / 引用 / 随机插话逻辑。

`guard` handler 加 `priority=100`，保证它先于解析器插件执行，非允许群直接 `stop_event()`。

#### 3.2.2 注册 LLM Tool `parse_share_link`

```python
@filter.llm_tool(name="parse_share_link")
async def parse_share_link(self, event: AstrMessageEvent, url: str = "") -> str:
    """解析并发送用户分享的 B站/抖音/快手/小红书 链接或 QQ 卡片。

    发送媒体/卡片后，返回作品标题、作者和简介，供你用一两句话自然接住。

    Args:
        url(string): 要解析的分享链接；留空时从当前消息的文本或卡片中提取
    """
```

实现要点：

- `url` 为空时，从 `event.message_str` 或 `Json` 组件提取；
- 从 `star_map` 找到 `astrbot_plugin_parser` 实例，使用它的
  `key_pattern_list` 找匹配、`parser_map[keyword].parse()` 拿 `ParseResult`、
  `sender.send_parse_result(event, result)` 发送；
- 发送成功后返回：
  `平台：B站；标题：…；作者：…；简介：…；链接：…`（标题 80 字、简介 160 字以内）；
- 解析/发送异常时走兜底：
  - B站优先用 `yt_dlp` 提取标题/UP/封面，发「封面图 + 标题/作者/链接」；
  - 其他平台尝试 OpenGraph 封面/标题；
  - 都不行就返回「这个链接我打不开，可能要登录」。
- 工具 docstring 里明确要求模型：发送后用一两句话接住，不复述标题、不列点、不解释工具调用。

#### 3.2.3 `on_llm_request` 注入提示

在现有世界书注入之后追加（用 marker 防止工具循环里重复注入）：

- 分享：
  ```
  [本轮用户分享了一条内容。请调用 parse_share_link 工具解析并发送；
   发送后用一两句话自然接住，不要复述标题、不要列点、不要解释工具调用。]
  分享链接：<url>
  ```
- 点歌：
  ```
  [本轮用户想听歌。请调用 play_song_by_name 工具点歌；
   发送后用一两句话自然接住，比如确认是不是这首、夸一下对方的品味。
   不要复述歌名列表，不要解释工具调用。]
  ```
- 分享/点歌轮次强制走 `model_complex`（`HY3-Free`），避免短文本被路由到 `Beam` 后工具调用不稳。

#### 3.2.4 运行时接管解析器

```python
parser_plugin = _find_plugin("astrbot_plugin_parser")
if parser_plugin and self.takeover_parser:
    parser_plugin.cfg.whitelist = ["__qqbotstack_tool_only__"]
```

- **三个时机都调**：`on_astrbot_loaded` 先关一次；每条群/私聊消息进入 guard 时再关一次；
  `on_llm_request` / `parse_share_link` 里再兜一次。只靠 LLM 请求时懒加载不够 ——
  第一条分享会被 parser 的 `on_message` 先发掉，默认 LLM 就被 `_has_send_oper` 跳过了。
- 解析器插件的 `on_message` 会因为 whitelist 不匹配而直接返回，不再自动发送；
- `parser_map` / `sender` 仍然可用，供我们的工具调用；
- 如果用户不想接管，配置 `takeover_parser=false`，但那样就只能得到媒体、没有人格接话。

> parser 1.6.1 自己也注册了 `parse_media_url` LLM Tool。分享提示里明确写
> 「只调用 `parse_share_link`，不要调用 `parse_media_url`」，避免两个工具都发一遍。

### 3.3 点歌链路

不自己写点歌，直接用 `astrbot_plugin_music`：

- 它的 `play_song_by_name` 工具就是「搜歌 → 发卡片 → 返回结果」；
- 工具在 agent 循环里发送，最终 LLM 会继续生成人格回复；
- 需要把插件配置改成：
  - 音源：网易云（`netease`）启用；
  - 发歌顺序：`card` → `record_link` → `record_local` → `text`；
  - `enable_comments=false`（否则工具返回 None，LLM 不会接话）；
  - `enable_lyrics=false`；
  - `return_play_song_result=true`；
  - `select_modes=["single(单曲模式)"]`（命令式点歌也直接发第一首，不弹候选菜单）；
  - `ark_key` 留空（签名卡片模式会跳过）。

### 3.4 B站策略

三档，按用户选择：

| 档 | 做法 | 视频 | 需要登录 | 说明 |
|---|---|---|---|---|
| B1 | parser + `登录B站` 扫码 | ✅ | 是 | 最完整；cookie 过期需重扫 |
| **B2（已选）** | parser 失败时 yt-dlp 兜底 | ❌（需 ffmpeg 才能下 DASH） | 否 | 只发封面+标题+链接，稳定绕 412 |
| B3 | 只发预览卡 | ❌ | 否 | 最轻量，不下载视频 |

默认实现 B2 兜底；B1 作为可选增强（用户扫码后 parser 优先成功）。

### 3.5 ffmpeg

- 不装：抖音/快手/小红书直链 MP4 正常；B站 DASH 合并失败，只能走 B2/B3。
- 装：B站视频可下载；解析器的 AAC-LC 转码也正常。
- 本仓采用**便携版 + 启动脚本前置 PATH**，不动系统环境变量：
  ```powershell
  # 解压到 runtime/ffmpeg，确保 bin/ffmpeg.exe、bin/ffprobe.exe 存在
  # run-astrbot.cmd 里加一行（%PATH% 前面，<部署根> 换成实际路径）
  set PATH=<部署根>\runtime\ffmpeg\bin;%PATH%
  ```
  这样只有 AstrBot 进程能看到 ffmpeg，回退时删目录 + 删这一行即可。
  `winget install --id Gyan.FFmpeg -e` 也可用，但会改系统 PATH，不如便携版好撤。

### 3.6 触发词与接话策略

触发词分三类，正则在 `qqbotstack_guard/main.py` 顶部：

| 类别 | 触发示例 | 行为 |
|---|---|---|
| 点歌/聊歌 | 想听、要听、听一下、放一首、来一首、点歌、这首歌、这首、那首歌、单曲循环、在听、我听的是、我在听、最近在听、推荐…歌、有没有…歌、什么歌、歌名、BGM、背景音乐、歌…好听、好听…歌、`《歌名》` | 有明确歌名 → `play_song_by_name` 点歌；没有 → 接话/反问，不拿整句搜 |
| 聊视频 | 这个视频、这段视频、视频好看/不错、刷到…视频、看了…视频、这个剪辑/片段/短片/直播、这个番/剧/电影/综艺/纪录片、这个UP/博主/主播 | 只接话，不假装看过；按群 60 秒冷却 |
| 分享 | B站/抖音/快手/小红书链接、短链、QQ 小程序 `Json` 卡片 | `parse_share_link` 解析并发送媒体/卡片 |

两个边界：

- **「这个视频里的 BGM 是什么歌」** 同时命中音乐和视频。此时走“视频里的音乐”提示：
  已明确歌名才点歌，只问 BGM 就让模型反问，不猜歌名。
- **不要用裸「好听」「视频」当触发词**。它们会误伤普通聊天；用「这首歌 / 视频好看 /
  刷到…视频」这类组合短语，聊视频再加冷却（见 PITFALLS P31）。

---

## 4. 改动清单

### 4.1 代码/配置（本仓）

| 文件 | 改动 |
|---|---|
| `host/plugin/qqbotstack_guard/main.py` | 加 `Json` 导入；分享 URL/卡片识别；点歌/聊歌/聊视频触发词；handler `priority=100`；`parse_share_link` 工具；`on_llm_request` 提示注入；运行时接管 parser；B站 yt-dlp/OG 兜底（辅助函数内联） |
| `host/plugin/qqbotstack_guard/config.example.json` | 新增 `share_wake_enabled`、`music_intent_enabled`、`video_intent_enabled`、`video_reply_cooldown_sec`、`takeover_parser`、`share_fallback_enabled`、`share_reply_cooldown_sec` 等 |
| `docs/DESIGN-MEDIA.md`（新增） | 本文定稿 |
| `docs/ARCHITECTURE.md` §1.2 | 行为矩阵加「分享解析 / 点歌」两行 |
| `docs/TOOLS.md` §1.4 | guard 新配置与 `parse_share_link` 工具说明 |
| `docs/PITFALLS.md` | 新增：AstrBot `_has_send_oper` 门槛、B站 412、音乐签名服务、XHS Cookie、无 ffmpeg |
| `NOTICE` | 记录 `astrbot_plugin_parser`（MIT）与 `astrbot_plugin_music`（GPL-3.0，外部依赖） |

### 4.2 目标机（人工/WebUI）

| 项 | 操作 |
|---|---|
| 安装解析器 | AstrBot WebUI → 插件市场 → 搜 `astrbot_plugin_parser` → 安装 → 重载 |
| 安装点歌 | 搜 `astrbot_plugin_music` → 安装 → 重载 |
| 解析器配置 | 启用 bilibili/douyin/kuaishou/xhs；`whitelist` 留空（由 guard 运行时接管）；`source_max_size=50`、`source_max_minute=5`、`single_heavy_render_card=true`、`forward_threshold=6`、`arbiter=false`（单 bot） |
| 点歌配置 | 见 §3.3 |
| B站登录（可选） | 管理员私聊发 `/登录B站` 扫码（需临时把 guard 的 `private_reply_enabled` 设为 true）；cookie 写入插件配置 |
| 小红书（可选） | 插件配置里填浏览器 Cookie；不填则部分链接失败 |
| ffmpeg（已选） | 便携版解压到 `runtime/ffmpeg`，在 `run-astrbot.cmd` 里前置 `bin` 到 PATH |

> 本次实测走的是插件市场 zip（parser 1.6.1 / music 3.3.1）手动解压到实例
> `core/data/plugins/`，再用实例 venv `pip install -r requirements.txt`；
> 与 WebUI 插件市场安装等价。插件配置预写在 `core/data/config/`，AstrBot 启动时直接读取。

> 所有 cookie、群号、QQ 号只留在目标机 `runtime/` 与插件配置里，**不进仓库、不进文档**。

---

## 5. 风险与回退

| 风险 | 影响 | 回退/缓解 |
|---|---|---|
| AstrBot 升级后 `_has_send_oper`/工具机制变化 | 人格接话失效 | 锁 AstrBot 4.29.3；升级前跑验收 |
| 解析器插件内部属性变化 | `parse_share_link` 失效 | 锁 `astrbot_plugin_parser==1.6.1`；工具里 try/except + 日志；失败时走 yt-dlp/OG 兜底 |
| B站 412 / cookie 过期 | B站解析失败 | 扫码重登；或 yt-dlp 兜底（B2）；或只发预览卡（B3） |
| 小红书 Cookie 失效 | XHS 解析失败 | 重新填 Cookie；失败时返回「打不开」并附链接 |
| 音乐签名服务不可用 | 卡片发不出 | 点歌插件自动降级语音/文件/文本；可在 NapCat 配 `musicSignUrl` |
| VIP 歌音频为空 | 卡片能显示但不能播 | 卡片仍展示；或换免费音源；或走语音/文本 |
| 没有 ffmpeg | B站视频下载失败 | 装 ffmpeg，或 B2/B3 |
| 视频过大/超时 | 工具调用超时 | `source_max_size`/`source_max_minute` 限流；先发预览卡；失败提示 |
| 分享刷屏 | 群里每条链接都接话 | guard 按 URL 做冷却（`share_reply_cooldown_sec`，默认 60s）；只允许群生效 |
| GPL 污染 | 本仓 MIT 与 GPL 混用 | 点歌插件只外部安装，不复制源码；NOTICE 标注 |
| 隐私 | 音乐签名服务会收到歌名/封面/音频 URL | 文档说明；可自建签名服务或改用文本/语音 |

---

## 6. 验收方式

1. **加载**：装完两个插件重启 AstrBot，日志无 import/依赖错误；`/插件列表` 能看到两个插件。
2. **B站小程序**：在允许群发一个 B站小程序卡片 → 先出媒体/预览卡，再出一两句人格回复；其他群同样操作无反应。
3. **抖音/快手**：发 `v.douyin.com/...`、`v.kuaishou.com/...` → 出视频/卡片 + 人格回复。
4. **小红书**：发一条有效笔记链接（带 Cookie）→ 出图集/视频 + 人格回复；无 Cookie 时给出可读失败提示。
5. **自然点歌**：发「我想听起风了」→ 出 QQ 音乐卡片，随后一句「是这首吗…品味不错」风格回复；不出现候选菜单、不重复发两条。
6. **命令点歌**：发「点歌 起风了」→ 直接发第一首卡片；确认与自然语言链路不冲突。
7. **私聊**：默认不回复（`private_reply_enabled=false`）；临时打开后才验收链接/点歌。
8. **稳定性**：连续发 5 条链接，确认防抖/冷却生效；查看 `astrbot.stdout.log` 无异常堆栈；磁盘缓存可清理。
9. **脱敏**：`python tools/check-docs.py`、`python tools/check-secrets.py --all` 通过。

---

## 7. 已确认决策（2026-10-26）

| # | 选项 | 决定 |
|---|---|---|
| 1 | 接入方式 | **A：上游插件 + 魔改 guard** |
| 2 | B站策略 | **B2：parser 失败时 yt-dlp 兜底**；B1 扫码登录作为可选增强 |
| 3 | 音乐音源 | **网易云 + 卡片优先**（失败降级语音/文本） |
| 4 | ffmpeg | **安装**（便携版 + `run-astrbot.cmd` 前置 PATH） |
| 5 | 分享回复范围 | 只允许指定群（私聊默认关闭，需手动打开 `private_reply_enabled`） |
| 6 | 点歌命令模式 | 单曲直发 |

按以上选择实施，并按 §6 验收。
