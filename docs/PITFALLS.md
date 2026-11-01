# 踩坑总汇

> **一句话**：踩坑总汇（**正本**）：每条写清「现象 → 根因 → 怎么避」，现象那一行即搜索词。

按现象搜索本文，或先看 [TROUBLESHOOTING.md](TROUBLESHOOTING.md) 的排查树。

---

## P1 SSH 会话里启动的进程，会话一断就没了

**现象**：通过 SSH 在目标机上 `Start-Process` 起 `wb2api.exe`，当场能访问 `127.0.0.1:7863`；
断开 SSH 再连，进程消失、端口没了、面板连不上。日志里却写着启动成功。

**根因（2026-10-26 真机确认）**：Windows OpenSSH 会把每个会话放进一个作业对象（job object），
会话结束时作业被终止，**会话内派生的所有子进程一并被杀**。`Start-Process` 看起来是「独立进程」，
但它仍在作业里。

**怎么避**：常驻服务不要从 SSH 会话直接起，交给**计划任务**（或 Windows 服务）：

```powershell
schtasks /create /tn QQBotStack-wb2api /tr "<部署根>\runtime\workbuddy\run-wb2api.cmd" `
  /sc onstart /ru SYSTEM /rl HIGHEST /f
schtasks /run /tn QQBotStack-wb2api
```

计划任务由任务计划程序服务承载，与你的 SSH 会话无关，开机也会自动跑。

## P2 没有账号时 `/v1/models` 返回 0 条

**现象**：网关起来了、面板 200、`/v1/models` 返回 `{"data":[]}`，以为网关坏了。

**根因**：wb2api 的模型目录是**从已登录账号聚合**出来的。`auths/` 为空时它没有任何上游模型可列。

**怎么避**：这不是故障。判定网关活着看两件事 —— 面板 `/panel/` 返回 200、
日志里有 `listening on 127.0.0.1:7863 (api_key=true)`。模型列表要等登录账号后再看。

## P3 NapCat 一键安装器是控制台交互程序，SSH 里跑不了

**现象**：在 SSH 会话里执行 `NapCatInstaller.exe`，没有任何输出就返回，或直接卡住。

**根因**：它是 **console 子系统**程序（PE subsystem = 3），靠交互提示选择安装目录，
没有任何命令行参数（二进制里查不到 usage/argv 相关字符串）。SSH 的非交互 stdin 喂不了它。

**怎么避**：在目标机的**桌面会话**里跑（双击，或在普通 cmd/PowerShell 窗口里执行）。
把它放在 `runtime/napcat/onekey` 下运行，产物会落在同目录的 `NapCat.XXXX.Shell/`。

## P4 hy3 是推理模型，`max_tokens` 给小了会返回空正文

**现象**：AstrBot 里模型测试「通过」了，但回复是空的；或 curl 拿到 200 且 `usage` 有数，
`choices[0].message.content` 却是 `''`。

**根因（2026-10-26 实测）**：hy3 会先产出思考内容，响应里同时有
`reasoning_content` 与 `content`。`max_tokens` 太小时 token 全花在思考上，
`content` 没机会生成。实测 `max_tokens=16` → 正文空、`completion_thinking_tokens=16`；
`max_tokens=300` → 正常返回 `OK`。

**怎么避**：AstrBot 侧 `max_tokens` 设 **≥ 2048**。排错时先看响应的
`usage.completion_tokens_details.reasoning_tokens` 占了多少 —— 如果几乎等于总输出，
就是预算不够，不是模型坏了。

## P5 `listen: ":7863"` 会把面板暴露到整个局域网

**现象**：以为网关只在本机可用，实际同网段任何人访问 `http://<目标机>:7863/panel/` 都能打开管理面板。

**根因**：Go 的监听地址写法里 `":7863"` 等价于 `0.0.0.0:7863`（所有网卡），
而不是 `127.0.0.1:7863`。上游的示例配置就是这种写法。

**怎么避**：把 `config.json` 的 `listen` 显式写成 `127.0.0.1:7863`。
本仓的部署脚本会强制改成回环地址。运维要访问面板就走 SSH 本地转发。

## P6 计划任务里的 `.cmd` 必须纯 ASCII、CRLF，且要自己 `cd`

**现象**：计划任务显示「正在运行」，但进程没起来、日志空；或者脚本内容里出现乱码。

**根因**：三个叠加问题 ——
① `schtasks` **不设置工作目录**，`.cmd` 里用相对路径（`-config config.json`）会解析到 `C:\Windows\System32`；
② cmd 对 UTF-8 中文不友好，中文注释可能让整行失效；
③ 用 LF 结尾的 `.cmd` 在部分场景下会被 cmd 解析错位。

**怎么避**：`.cmd` 里第一件事 `cd /d "<绝对路径>"`；内容保持纯 ASCII；
用 CRLF 落盘（`tools/deploy-stack.ps1` 自己按 CRLF 写，不依赖文本编辑器）。

## P7 AstrBot Launcher 的数据目录默认在家目录，不指走就散落

**现象**：想让整套东西都在一个目录里，结果 AstrBot 的实例、Python 运行时、插件全跑到
`C:\Users\<你>\.astrbot_launcher` 去了。

**根因**：Launcher 默认数据目录是 `~/.astrbot_launcher`。

**怎么避**：写覆盖文件（源码支持，路径必须是绝对路径）：

```text
%APPDATA%\com.github.raven95676.astrbot-launcher\.data-dir.json
{"data_dir":"<部署根>\\runtime\\astrbot\\data"}
```

本仓部署脚本的 `astrbot` 阶段会写好它。

## P8 启动器与 QQ 都依赖桌面会话

**现象**：机器重启后没人登录桌面，bot 不回消息；或者一注销，AstrBot 就停了。

**根因**：AstrBot Launcher 是 Tauri 桌面程序（托盘驻留），QQ 也是桌面程序。
两者都活在你的登录会话里。只有 wb2api 是以 SYSTEM 计划任务跑的，不受影响。

**怎么避**：开「自动登录」让机器重启后自动进桌面；或改用服务化部署
（[DESIGN-DEPLOY.md](DESIGN-DEPLOY.md) §八.1 选项 B）。这是本栈已知的可用性缺口，不是 bug。

## P9 NapCat 的许可不允许再分发修改版

**现象**：想省事，把 NapCat 的二进制或改过的 `bootmain` 提交进仓库。

**根因**：NapCatQQ 用的是自定义「Limited Redistribution License」——
再分发必须带完整许可与出处，**修改后的代码不得公开发布**，且限非商业用途。
AstrBot 是 AGPL-3.0，分发二进制要连带提供源码。

**怎么避**：仓库里**不放任何上游二进制或源码**，`.gitignore` 已排除 `*.exe` / `*.zip`。
部署脚本从官方 Release 下载到 `runtime/`。要改上游行为，改配置，不改代码。

## P10 远程 PowerShell 的输出按 GBK 编码，解析出来是乱码

**现象**：用 `ssh <HOST> powershell -EncodedCommand ...` 取回来的错误信息是一串乱码，
`(503) �����������á` 这种；自己写的探测脚本读不懂返回值。

**根因**：Windows PowerShell 5.1 在输出被重定向时，按**系统 OEM 代码页**（中文系统是 GBK/936）
编码，而调用方通常按 UTF-8 解码。错误文本几乎必然含中文，于是全乱。

**怎么避**：在被执行的脚本开头强制 UTF-8：

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
```

`tools/verify-stack.py` 的 `remote_ps()` 会把这 preamble 拼到每段远程脚本前面。
另外，**结果不要靠文本匹配** —— 让远程脚本输出一行 JSON，本地按 JSON 解析，能少踩很多编码坑。

## P11 NapCat 一键安装器「移动 versions 失败」但照样报安装完成

**现象**：安装日志里出现

```text
[错误] 移动versions目录失败: rename: 拒绝访问。:
       "NapCat.52230.Shell\Files\versions", "NapCat.52230.Shell\versions"
```

紧接着仍然打印 `[成功] ...`、`===== 安装完成 =====`。目录建出来了、`napcat.bat` 也在，
但双击启动 QQ 起不来。

**根因（2026-10-26 真机确认）**：目标 `versions` 目录**已存在**（之前跑过一次，或解压先建了它），
安装器用的 `rename` 在目标已存在时直接返回「拒绝访问」。它**不检查这个错误**，继续往下走，
于是 QQ 本体的 `versions` 留在 `Files\versions` 里没并过去，而 `versions\` 下只有后来解压的 NapCat。

**怎么避**：

- **首选**：删掉整个 `NapCat.XXXX.Shell` 目录，重新跑安装器（`versions` 不存在时 rename 会成功）。
- **手工补救**（不重装）：按顺序两次 robocopy，只补缺失、不覆盖 NapCat 那边：

  ```powershell
  robocopy "NapCat.XXXX.Shell\Files\versions" "NapCat.XXXX.Shell\versions" /E /XC /XN /XO
  robocopy "NapCat.XXXX.Shell\Files" "NapCat.XXXX.Shell" /E /XC /XN /XO /XD versions
  ```

- **判断是否真的装好**（三条都要满足）：
  1. `versions\<版本>\resources\app\package.json` 的 `main` 是 `./napcat/napcat.mjs`；
  2. `versions\<版本>\` 下有 `chrome_100_qq.pak`、`ffmpeg.dll` 这类 QQ 文件（不只是 `resources\app\napcat`）；
  3. 根目录有 `QQ.exe`、`msvcp140.dll`、`extension\`、`napcat.bat`。

> 日志里那句 `在package.json中未找到需要替换的路径` 通常是**误报** ——
> 该文件往往已经是 `./napcat/napcat.mjs`。别急着按它去改。

## P12 AstrBot 首次启动卡死：进程活着、CPU 不动、6185 不监听

**现象**（2026-10-26 真机确认）：实例建好后启动，`python.exe` 两个进程都在（父进程 5 MB / 子进程
260 MB），CPU 停在十几秒不再增长，`6185` 始终没有 `LISTENING`，面板打不开。
看起来像「卡住了」但进程不退出。

**根因**：AstrBot 启动流程里 `check_dashboard_files()` → `AstrBotUpdater().ensure_dashboard()`
会校验并**按需准备面板静态文件**。首次运行这一步会做下载/整理，期间主协程被占住，
HTTP 服务还没开始监听，于是表现成「进程活着但不响应」。

**怎么避**：**等它自己走完，然后重启一次实例**。重启时面板文件已就绪，
日志会直接出现 `AstrBot started` + `WebUI is ready`。
排查手段：拿同样的命令手动跑一次并重定向输出，能看到卡在哪一步：

```powershell
$inst = "<部署根>\runtime\astrbot\data\instances\<实例 id>"
$env:PYTHONIOENCODING = 'utf-8'
Start-Process -FilePath "$inst\venv\Scripts\python.exe" -ArgumentList 'main.py' `
  -WorkingDirectory "$inst\core" -RedirectStandardOutput "$inst\diag.out.log" `
  -RedirectStandardError "$inst\diag.err.log" -WindowStyle Hidden
```

**不要**因为「没反应」就反复重启 —— 第一次的准备过程会被打断，反而更慢。

## P13 AstrBot 面板默认绑 `0.0.0.0`，等于把管理面暴露到局域网

**现象**：AstrBot 启动日志里自己就写了
`WebUI listens on all interfaces. Check security.`，从同网段任何机器都能打开 `:6185`。

**根因**：AstrBot 的 `cmd_config.json` 默认 `dashboard.host = "0.0.0.0"`。

**怎么避**：改成回环，运维走 SSH 转发：

```json
"dashboard": { "enable": true, "host": "127.0.0.1", "port": 6185 }
```

改完重启实例。本仓的口径是**所有 WebUI 只绑 127.0.0.1**（[ARCHITECTURE.md](ARCHITECTURE.md) §3）。
注意 NapCat 与 wb2api 也要同样处理。

## P14 首次登录密码只在启动日志里，且容易被编码吃掉

**现象**：启动日志里那行 `Initial password: xxxx` 显示成 `?` 或整行缺失，
拿不到初始密码；面板进不去。

**根因**：那行前面带 emoji，控制台代码页不是 UTF-8 时整行会被替换成 `?`；
如果日志只是被临时抓取过、没落盘，密码就丢了（`cmd_config.json` 里存的是 pbkdf2 哈希，不可逆）。

**怎么避**：用内置开关重新生成一个**会打印在日志里**的密码：

```powershell
& "<实例>\venv\Scripts\python.exe" main.py --reset-password
```

前提是抓取时设 `$env:PYTHONIOENCODING = 'utf-8'` 并重定向到文件。
拿到后立刻在 WebUI 里改成自己的密码（首登也会强制要求改）。

## P15 NapCat WebUI 的 API 有一堆反直觉细节，写自动化脚本时会连踩四个

**现象**（2026-10-26 真机确认）：想用 HTTP 直接改 OneBot 配置、不重启 NapCat，
结果依次撞上「token is empty」「Unauthorized」「GET 返回空」「SetConfig 报错」。

**根因**：四个点都和直觉不符：

1. **登录字段叫 `hash`，不叫 `token`**，且值不是明文 token，而是
   `sha256(token + ".napcat")` 的十六进制。
2. **`Credential` 本身就是 base64 字符串**，直接 `Authorization: Bearer <Credential>`；
   再对它做一次 base64/JSON 序列化就会 `Unauthorized`（服务端拿它 base64 解码后校验 HMAC）。
3. **`GetConfig` / `SetConfig` 都是 `POST`**，不是 GET。用 GET 会拿到一个没有 `code` 字段的响应。
4. **`SetConfig` 的 body 是 `{"config": "<OneBot 配置的 JSON 字符串>"}`** ——
   内层是整个 OneBot 配置的**字符串**，不是对象。

**怎么避**：照着这四步写，并注意 `SetConfig` 是**热生效**的（不需要重启 NapCat，
所以不用重新扫码）：

```powershell
$t   = (Get-Content webui.json -Raw | ConvertFrom-Json).token
$sha = [Security.Cryptography.SHA256]::Create()
$hash = (($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($t + '.napcat'))) |
         ForEach-Object { $_.ToString('x2') }) -join ''
$login = Invoke-RestMethod "http://127.0.0.1:6099/api/auth/login" -Method Post `
           -Body (@{hash=$hash} | ConvertTo-Json -Compress) -ContentType 'application/json'
$h = @{ Authorization = 'Bearer ' + $login.data.Credential }
$cur = Invoke-RestMethod "http://127.0.0.1:6099/api/OB11Config/GetConfig" -Method Post `
         -Headers $h -ContentType 'application/json' -Body '{}'
# 改 $cur.data.network.websocketClients，然后：
$body = @{ config = ($cur.data | ConvertTo-Json -Depth 20 -Compress) } | ConvertTo-Json -Compress
Invoke-RestMethod "http://127.0.0.1:6099/api/OB11Config/SetConfig" -Method Post `
  -Headers $h -ContentType 'application/json' -Body $body
```

> `webui.json` 里的 `host` 默认是 `::`，实际用 `127.0.0.1` 连即可。

## P16 PowerShell 5.1 的 `-Encoding UTF8` 会写 BOM，直接把 Go 的配置解析打挂

**现象**（2026-10-26 真机确认）：用 `Set-Content -Encoding UTF8` 改完 wb2api 的
`config.json`，网关起不来，日志只有一行：

```text
load config: parse config: invalid character '?' looking for beginning of value
```

**根因**：Windows PowerShell 5.1 的 `-Encoding UTF8` 写的是 **带 BOM 的 UTF-8**（前三个字节
`EF BB BF`）。Go 的 `encoding/json` 不接受 BOM，直接把第一个字节当成非法字符。
文件内容本身完全正确，肉眼看不出问题。

**怎么避**：改 JSON 配置一律用无 BOM 写：

```powershell
$enc = New-Object System.Text.UTF8Encoding($false)
[IO.File]::WriteAllText($path, ($obj | ConvertTo-Json -Depth 40), $enc)
```

改完顺手验一下前三个字节：`([IO.File]::ReadAllBytes($path))[0..2]` 应该是 `123,13,10`
（`{` + CRLF），不是 `239,187,191`。

> 反过来，AstrBot 那份配置**能容忍** BOM（它按 `utf-8-sig` 读），所以同一个错误在它身上
> 不报错 —— 别因此以为 BOM 无害。

## P17 PowerShell 变量名大小写不敏感，`$conf` 会覆盖参数 `$Conf`

**现象**：脚本里 `param([string]$Conf)` 之后写 `$conf = @{}`，接着
`Get-Content -LiteralPath $Conf` 报
`找不到路径"System.Collections.Hashtable"`。

**根因**：PowerShell 的变量名**大小写不敏感**，`$conf` 与 `$Conf` 是同一个变量。
赋哈希表给 `$conf` 等于把路径参数覆盖掉了。

**怎么避**：参数与局部变量别只靠大小写区分。本仓 `tools/sync-auths.ps1` 里把哈希表命名成
`$confMap`。同类坑还有 `$Host`（PowerShell 内置只读变量，赋值直接报错）。

## P18 用 PowerShell 的 `ConvertFrom-Json` 读 AstrBot 的配置不可靠

**现象**：改完 AstrBot 的 `cmd_config.json`，`ConvertFrom-Json` 读回来
`provider` 只剩 1 条、`provider_id` 全是空 —— 但 AstrBot 自己启动时明明正确加载了两个 provider。

**根因**：AstrBot 启动后会重写这份配置（4 空格缩进的规范化输出），其结构在 PS 5.1 的
`ConvertFrom-Json` 下会出现取值异常（含重复键时甚至会直接抛错）。**别把它当作配置真的写坏了**
—— 先用 AstrBot 的日志和它自己的 Python 确认。

**怎么避**：验证这类配置用目标机上那个实例自带的 Python：

```powershell
$py = "<实例>\venv\Scripts\python.exe"
& $py -c "import json;d=json.load(open(r'<配置路径>',encoding='utf-8-sig'));print(d['provider'])"
```

`utf-8-sig` 能吃掉 BOM（见 P16）。改配置时用无 BOM 写，读回来验证时用 Python ——
两头都稳。

## P19 「关键词触发」不能靠 `wake_prefix`，也不能靠插件 filter 直接放行

**现象**（2026-10-26 真机确认）：想实现「群里消息**包含**关键词就回复」。
先试 `wake_prefix = ["神父", ...]` —— 只有消息**以**关键词开头才触发，句子中间出现不算。
改用插件 + `@filter.event_message_type(GROUP_MESSAGE)` 匹配，日志显示 handler 被激活了，
但机器人**仍然不回复**。

**根因**：三个独立事实叠在一起：

1. `wake_prefix` 的判定是 `message_str.startswith(prefix)`（**前缀**，不是包含）。
2. 会话白名单 `id_whitelist` 是**精确匹配**（完整 UMO 或群号），所以表达不出
   「所有私聊 + 某一个群」—— 白名单里只放一个群号会把私聊一起挡掉。
3. 唤醒阶段对**插件 handler filter 命中**只置 `event.is_wake = True`，
   **不置** `event.is_at_or_wake_command`；而 `ProcessStage` 触发默认 LLM 回复的条件是
   `event.is_at_or_wake_command`。所以事件被「唤醒」了，但没有「被召唤」的标记，
   默认管线不会回。

**怎么避**：用插件做，并在放行分支手动置位：

```python
if 命中关键词 or 被 @ or 引用机器人:
    event.is_at_or_wake_command = True   # 让消息继续走完整默认管线（人格 / 上下文 / 插件）
    return
event.stop_event()                        # 不满足条件就丢掉
```

**不要**用 `yield event.request_llm(prompt=...)` 代替 —— 那条路会绕过人格与上下文组装，
角色 bot 会突然「失忆」。

> `is_at_or_wake_command` 属于半内部属性，升级 AstrBot 大版本后若出现
> 「群里 @ 能回、关键词不回」，先回来确认这个名字没变。
> 参考实现：`host/plugin/qqbotstack_guard/`。

## P20 「模型不支持图片」多半是 provider 的 `modalities` 没声明，不是模型不能看

**现象**（2026-10-26 真机确认）：群里发图片，日志出现

```text
[WARN] Chat provider wb2api-hy4f does not support image input and no image-capable
       fallback provider is available.
```

机器人于是回一句「我看不到这张图片」。但同一个模型直接打网关却能正确读出图里的文字。

**根因**：AstrBot 判断一个模型能不能看图，看的是 **provider 配置里的 `modalities` 字段**，
它不会去探测模型真实能力。手工写 provider 时只写了 `["text","tool_use"]`，
AstrBot 就按纯文本模型处理，图片在进模型之前就被丢掉。

**怎么避**：

1. 先实测模型到底行不行 —— 直接向网关发一条带 `image_url` 的请求（`data:image/png;base64,...`
   就够），问它图里写了什么。能读出字就说明支持。
2. 确认支持后，把 `"image"` 加进 provider 的 `modalities`：

```json
"modalities": ["text", "image", "tool_use"]
```

3. 回退模型也要加 —— 否则主模型失败、回退到另一个 provider 时图片又会丢。

> 顺带一条：**随机插话不要对图片消息触发**。主模型就算能看图，
> 对一张没有配文的图凭空接话也容易答非所问；`qqbotstack_guard` 已排除
> 「含图片」和「空文本」的消息，只对纯文本随机。

### P20 附录：hy3 / hy4 在 wb2api 下的真实能力（2026-10-26 实测）

| 能力 | 结论 | 怎么验的 |
|---|---|---|
| 文本 | ✅ | 常规对话 |
| 图片 | ✅ | 造一张写着 `CAT` 的图，模型正确读出 |
| 音频 | ❌ | `input_audio` 内容段直接返回 **400** |
| 函数调用（tool_use） | ✅ **经 zgate 正常** | 直连 wb2api 时 `tools` 会被剥掉（`data/request-logs` 里没有该字段）；经 zgate 转发时正常 —— `Beam` 与 `HY3-Free` 在 `tool_choice=required` 下都返回了 `tool_calls` |

所以 provider 的 `modalities` 要写 `["text", "image", "tool_use"]` —— **前提是走 zgate**。
如果哪天改回直连 wb2api，工具调用会失效，届时要把 `tool_use` 去掉，否则 AstrBot 会把
工具定义塞进永远到不了模型的请求里，白烧 token。

> 由此推论：依赖 LLM 函数调用的能力（网页搜索、子代理 `transfer_to_*`、
> 表情包的 `search_memes`）**只有走 zgate 才可用**。这也是本仓不直连 wb2api 的原因之一。

## P21 思考压不下去，且流式默认是关的

**现象**（2026-10-26 实测）：回复慢，而且是「憋一大段、然后整段一起出来」，没有打字机感。

**根因一：思考长度不可控。** 试着传 `reasoning_effort: "low"`、`enable_thinking: false`、
`thinking: {"type":"disabled"}`，表面上耗时从 16.1s 降到 8.7–10.9s，但**这是波动** ——
查网关的 `data/request-logs`，三个字段**一个都没出现在上游请求里**。
wb2api 会把所有非标准字段剥掉（和 P20 的 `tools` 同一个行为）。

**根因二：`provider_settings.streaming_response` 默认 `False`。** 不打开它，
AstrBot 会等整段生成完再发一次。

**怎么避**：

```json
"provider_settings": {
  "streaming_response": true,
  "unsupported_streaming_strategy": "realtime_segmenting"
}
```

网关**是支持流式的**（实测 `text/event-stream`，首字节 ~1.2s）。aiocqhttp 不支持原生流式，
走 `realtime_segmenting` 兜底：**按 `。？！~…` 切句，每句一到就发**，句间硬编码 1.5s 间隔。

**想再快只能换模型** —— 同一句提示词实测：

| 模型 | 耗时 | 首字节 | reasoning tokens |
|---|---|---|---|
| `global:hy4-preview-f` | **16.1s** | 1.2s | 309 |
| `global:hy3` | **3.4s** | 1.1s | 154 |

两个都是免费档，hy3 快约 5 倍。要换就把 `agent_runner.config.model.provider_id`
改成 `wb2api-hy3`、把 `wb2api-hy4f` 放进 `fallback_provider_ids`（一行改动，可逆）。

## P22 模型会输出 Markdown 和 emoji，在 QQ 上非常假

**现象**：回复里出现 `**加粗**`、`# 标题`、`1. 2. 3.` 列表、`> 引用`，以及大量 emoji。
QQ 的 OneBot 通道**不渲染 Markdown**，所以星号是原样显示出来的 —— 一眼就看出不是人打的。

**根因**：模型默认按「助手」风格输出，Markdown 是它的默认排版习惯。
AstrBot 对 aiocqhttp 没有内置的 Markdown 清理（`use_markdown` 只存在于 QQ 官方机器人模板）。

**怎么避**：两道防线，缺一不可。

1. **人格提示词**里明确禁用（模型会遵守，但不是 100%）；
2. **发送前正则兜底** —— 插件 `on_decorating_result` 钩子把 `Plain` 组件里的
   `**` / `__` / `~~` / 反引号 / `#` 标题 / `- ` 列表 / `> ` 引用 / emoji 全部剥掉：

```python
@filter.on_decorating_result()
async def strip_style(self, event):
    result = event.get_result()
    for comp in (result.chain if result else []):
        if isinstance(comp, Plain):
            comp.text = _clean_style(comp.text)
```

> `platform_settings.segmented_reply.content_cleanup_rule` 也能做同样的事，
> 但它**只在分段路径里执行** —— 短回复不触发分段就不会被清理，不可靠。别指望它。

**关于断句**：流式的 `realtime_segmenting` 是按 `。？！~…` 切句的。
如果人格要求「不打句号」（真人 QQ 聊天确实很少打句号），那就几乎没有切分点，
流式等于失效。所以本仓的选择是：**关掉流式**，用 `segmented_reply` 的
`words_count_threshold=100000`，让所有回复都进入分段；但 guard 只给长文插换行，
短回复没有换行，仍然整条发。
想快就换 hy3（见 P21），而不是靠流式。

## P23 世界书的关键词是效果生死线，自动切出来的必须过一遍

**现象**：把设定集按小节自动切成世界书后，问「世界律是什么」注入的却是别的条目，
或者随便一句闲聊就注入三四条设定，把人格的声音盖掉了。

**根因**：自动生成关键词容易犯两个错。

1. **通用词当 key**：`绿海` / `世界律` / `界膜` 这类词几乎每个小节都出现，
   一旦进 key，任何提到它们的消息都会命中一片条目。本仓的生成器有 `GENERIC_KEYS` 黑名单。
2. **整句加粗当 key**：设定集里加粗的常常是**强调句**（`同样的动作，结果不一致。`），
   不是术语。这类 key 永远不会被命中，还占位。生成器用 `KEY_SHAPE`
   （只允许 2–10 个中英文数字字符、不含标点空格）过滤。

**怎么避**：

- 自动生成后**一定要人工扫一遍 key**，通用词删掉、整句删掉；
- **别名要手工补**：设定里写的是正名，群里叫的是别名（本仓用
  `--aliases 拉贵尔=梵铭,神父=梵铭` 把别名并进同一条目），不补就永远命不中；
- 单轮注入要设上限（本仓：常驻 + 最多 3 条命中、合计 ≤ 2200 字），
  否则一次命中十条会把上下文塞满，回复变慢也变呆；
- 常驻条目只放**世界骨架**（几百字），不要放细节。

**本仓 2026-10-26 又补了四条**（v6 世界书踩出来的）：

- **长节必须先拆再截断**：人物条目动辄两三千字，700 字截断会正好把「语言 / 性格」切掉。
  生成器现在把超过 700 字的 `##` 节按 `###` 拆成子条目，并把「语言 / 性格」
  排在同人物其他条目前。
- **同命中数要有优先级**：`梵铭` 在别的章节里被加粗一次，就会和人物条目同分；
  没有 `priority` 时稳定排序会把人物条目挤掉。现在人物 80 / 剧情 70 / 世界观 50 / 附录 10。
- **人物条目的 key 只收本人与别名**：正文里顺带提到的其他人物（玟德的语言条目里提了一句蒂米）
  会把「蒂米」的条目抢走。
- **常驻条目别取「编纂说明」**：那是「这本书怎么用」，不是世界观。生成器跳过说明类小节。

## P24 插件先发消息，默认 LLM 就不回复了

**现象**：装了解析器插件后，群里发链接，机器人只发媒体/卡片，不再说话；
日志里 parser 发送成功，但看不到默认 LLM 请求。

**根因**：AstrBot `process_stage` 的默认 LLM 请求条件是 `not event._has_send_oper`。
任何插件只要 `event.send()` 过一次，`_has_send_oper=True`，默认 LLM 直接被跳过。
所以「插件自动发媒体 + 期望默认 LLM 再补一句」在结构上不成立。

**怎么避**：把「解析 + 发送」放进 LLM Tool 内部（`@filter.llm_tool`）。
工具在 agent 循环里 `event.send()` 后返回字符串，agent 仍会继续生成最终回复。
本仓的 `qqbotstack_guard.parse_share_link` 与点歌插件的 `play_song_by_name` 都是这个模式；
不要在普通 handler 里先发再等默认 LLM。

## P25 B站 API 412，但网页和 yt-dlp 能读

**现象**：B站链接解析失败，日志里 `412`；浏览器打开同一个视频页正常。

**根因**：`api.bilibili.com/x/web-interface/view` 触发 B站风控，带 `buvid3` 仍 412；
`bilibili-api` 也走这个端点。网页 HTML 的 `__INITIAL_STATE__` 与 yt-dlp 不受影响。

**怎么避**：

- parser 配置里用 `登录B站` 扫码拿 Cookie（最完整，能下视频）；
- 或者让 `parse_share_link` 走 yt-dlp 兜底（无需登录，只发封面+标题+链接）；
- 只发预览卡也可以；
- 不要对 412 反复重试，会加重风控。

## P26 NapCat 音乐卡片要签名，VIP 歌可能只有卡片

**现象**：点歌插件发卡片失败；或卡片能显示，但点播放没声音。

**根因**：

- NapCat 的 `music` 段会请求第三方签名服务（内置首选 + 备选），服务不可用就发不出；
- 网易云 VIP 歌的音频解析服务可能返回空 HTML，卡片能显示但播不了；
- 只传 `type+id` 时签名服务要求 `title`，补 `title` 会退化成图文卡，不是音乐卡。

**怎么避**：

- 发歌顺序用 `card → record_link → record_local → text`，失败自动降级；
- `enable_comments=false`，让点歌工具返回结果给 LLM 接话；
- 接受 VIP 歌“只显示卡片”，或换免费音源；
- 签名服务不稳时在 NapCat 配 `musicSignUrl`，或直接走文本/语音。

## P27 小红书必须带 Cookie

**现象**：小红书链接解析失败，或只能拿到带水印图。

**根因**：XHS 需要登录态 Cookie；短链跳转后的 `__INITIAL_STATE__` 才带 note 数据，
匿名访问经常被重定向到 404/登录页。

**怎么避**：在 parser 插件的 `xhs.cookies` 填浏览器 Cookie；失败时回退“标题+链接”；
Cookie 只放目标机插件配置，不进仓库、不进日志。

## P28 没有 ffmpeg 时 B站视频合不出来

**现象**：B站视频下载失败，日志里 `ffmpeg` / `ffprobe` 找不到；抖音/快手正常。

**根因**：B站是 DASH，视频流和音频流分离，合并要 ffmpeg；
抖音/快手返回的是带音轨的 MP4 直链，不需要合并。

**怎么避**：便携版 ffmpeg 解压到 `runtime/ffmpeg`，在 `run-astrbot.cmd` 里把
`runtime\ffmpeg\bin` 前置到 `PATH`；或 B站只发预览卡。
`transcode_video_audio_to_lc` 找不到 ffmpeg 会跳过转码，不会崩，但视频可能没声音。

## P29 改人格后旧对话历史会把新人设盖回去

**现象**：数据库 `personas.default` 已经换成新人格，AstrBot 也重启了，但群里问「你是谁」，
模型仍按旧人格回答。本仓实测：新人格已经写入 754 字，模型却回答「小鲸鱼」，
`think` 里写着「按照人设，梵铭是蓝头发小姑娘，自称小鲸鱼，最爱吃大白饭」。

**根因**：`conversations.content` 里存着旧人格生成的 assistant 消息。模型在上下文里
看到这些消息，会优先模仿旧人设；系统提示词是新的，但旧上下文的权重更大。
只改 `personas` 表、只重启，都清不掉这层污染。

**怎么避**：

- 改人格后**必须重置会话**：QQ 里发 `/reset`，或删掉 `conversations` 里对应行；
- 群聊上下文还要清 `platform_message_history`，否则旧的 bot 发言仍会被带进请求；
- `preferences` 里的 `sel_conv_id` 指向旧会话，一并删掉，让 AstrBot 新建会话；
- 排查时直接看 `conversations.content` 里 assistant 的 `think`，它通常会写出
  「按照人设，我是……」——那句话就是模型实际看到的人格。

## P30 PowerShell 的 Stop 偏好会把 pip 的 stderr 当成致命错误

**现象**：部署脚本在 `pip install -r requirements.txt` 处中断，报
`NativeCommandError` / `RemoteException`，但 pip 其实只是往 stderr 打了一条
`WARNING: ... does not provide the extra ...`；插件依赖只装了一半。

**根因**：PowerShell 在 `$ErrorActionPreference = 'Stop'` 下，会把原生命令写到
stderr 的任何内容包装成 terminating error，`2>&1 | Tee-Object` 也救不了。
pip 的警告、进度条、下载信息都可能走 stderr。

**怎么避**：不要直接 `& $python -m pip ... 2>&1`。用 `Start-Process` 分别重定向
stdout/stderr 到文件，等进程退出后只看 `$proc.ExitCode`：

```powershell
$proc = Start-Process -FilePath $py `
  -ArgumentList @('-m','pip','install','-r',$req) `
  -Wait -NoNewWindow -PassThru `
  -RedirectStandardOutput $out -RedirectStandardError $err
if ($proc.ExitCode -ne 0) { throw "pip failed: $($proc.ExitCode)" }
```

同类问题也适用于 `ffmpeg -version` 这类把版本写到 stderr 的命令。

## P31 触发词别用裸「好听」「视频」，会误伤普通聊天

**现象**：给机器人加了「好听」「视频」这类触发词后，普通聊天也被当成点歌/聊视频：
「这个名字真好听」「会议视频发我」都会把机器人叫出来，接得莫名其妙。

**根因**：中文短词歧义大。「好听」可以夸名字、声音、音乐；「视频」可以指会议、
文件、监控。裸词没有足够的上下文判断意图。

**怎么避**：

- 用**组合短语**：`这首歌` / `这首歌很好听` / `视频好看` / `刷到一个视频` /
  `这个剪辑` / `这个电影`，不要用裸「好听」「视频」；
- 聊视频这种低置信度触发要加**冷却**（本仓按群 60 秒），避免连续接话刷屏；
- 聊歌时让模型先判断**有没有明确歌名**：有就点歌，没有（「这首歌叫什么」）就反问，
  不要把整句丢给搜索接口；
- 同时命中音乐和视频（「这个视频的 BGM 是什么歌」）时走合并提示，不猜歌名。

## P32 QQ 小程序卡片只有 `Json` 段，会被 LLM 阶段当成空消息跳过

**现象**：群里发 B站小程序卡片，guard 日志已经出现 `share wake: b23.tv/...`，
但之后既没有 `Agent 使用工具`，也没有任何回复——看起来像卡片完全没被处理。

**根因**：小程序卡片在 AstrBot 里是一个 `Json` 组件，`event.message_str` 为空。
`pipeline/process_stage/method/agent_sub_stages/internal.py` 在请求 LLM 前有一道判断：

```python
has_valid_message = bool(event.message_str and event.message_str.strip())
has_media_content = any(isinstance(comp, (Image, File, Record, Video)) ...)
has_reply = any(isinstance(comp, Reply) ...)
if not has_provider_request and not has_valid_message and not has_media_content and not has_reply:
    return  # skip llm request: empty message and no provider_request
```

`Json` 不在 `Image/File/Record/Video` 里，于是整条事件在唤醒后又被静默丢弃。
guard 设置的 `is_at_or_wake_command` 只能保证「该唤醒」，管不到这道「消息是否为空」的门槛。

**怎么避**：

- 识别到分享卡片后，若 `event.message_str` 为空，就把提取出的链接写回
  `event.message_str`（见 `qqbotstack_guard` 1.2.1），让 LLM 阶段有文本可读；
- 链接同时已放进 `qqbotstack_share_url` extra，并在 `on_llm_request` 注入提示，
  所以即使模型侧不读 `message_str`，也能拿到 URL 调 `parse_share_link`；
- 排查这类「日志有唤醒、后面全空」的问题，先看 `internal.py` 的空消息判断，
  不要只盯着 guard 的唤醒分支。

## P31 接话窗口：handler 里 sleep 再置位可行，但必须做防抖

**现象**：想在机器人回复后收集几条接话再统一回，直接在 `guard` 里 `await sleep`
再置 `is_at_or_wake_command`，结果每条接话都触发一次，或者干脆不触发。

**根因**：

- AstrBot 的 process stage 在插件 handler **返回后**才检查
  `is_at_or_wake_command`，所以 handler 内 `await sleep` 再置位是可行的；
- 多条消息并发时，每个 handler 都会 sleep，必须用 generation 计数器只让最后一条触发；
- 先 `stop_event()` 的 handler 不能再置位，只有最后一条不要 stop。

**怎么避**：

- 每条接话 append 后 `generation += 1`，sleep 后检查 generation 是否仍等于自己的；
- 不是最新的 `stop_event()`；最新的不 stop，置 `is_at_or_wake_command=True`；
- 触发后设 `generating=True`，机器人回复的 `after_message_sent` 再开新窗口；
- `generating` 要有超时（60s），避免模型/发送失败后永久卡住。

**引用第二个人**：`Reply(id=对方 message_id, sender_id=..., sender_nickname=...,
message_str=...)` + `Plain(text)`，用
`context.send_message(event.unified_msg_origin, MessageChain(chain))` 发。
`event.send` 依赖当前执行上下文，延迟发送用 `context` 更稳。

## P33 上游全挂时，技术错误会被 AstrBot 当正文发进群

**现象**：群里突然出现一整条
`LLM 响应错误: All chat models failed: InternalServerError: Error code: 502 - {...}`，
既突兀，也把网关、模型、账号细节漏给群友。

**根因**：zgate 的所有上游都返回 429（免费池 `global:hy3` / `cn:hy3` 同时被限流）后，
zgate 返回 502；AstrBot 把「所有 chat model 都失败」渲染成一条 `Plain` 消息，
`respond.stage` 原样发送。guard 的 `on_decorating_result` 当时只清 Markdown/emoji，
不识别错误文案。

**怎么避**：

- guard 1.3.1 起，`on_decorating_result` 先匹配
  `LLM 响应错误|All chat models failed|all upstreams failed|proxy_error|Error code: 4xx/5xx`
  等签名，命中就把整段替换成 `error_reply_lines` 里的一条人格化台词；
- 台词准备多条并记录上一条，连续两次不重复，避免一眼看出是模板；
- 原始错误只写日志（`[guard-error] provider error intercepted`），不发给用户；
- 降低触发概率：短消息走 `Beam`（OC 上游，独立额度），`HY3-Free` 配
  `fallback_provider_ids=[zgate-beam]`，两条上游不在同一个账号池里。

## P32 反问后的歌名会被 guard 当普通消息丢掉

**现象**：机器人问「想听什么歌？」，用户过了一会儿只回「晴天」，Bot 不回，
也不发点歌卡片。

**根因**：`guard` 只放行 @/关键词/随机；裸歌名不在其中，30 秒接话窗口又已经过期。
即使模型在接话窗口内看到「晴天」会主动调 `play_song_by_name`，窗口外这句根本到不了 LLM。

**怎么避**：

- `after_message_sent` 检测机器人刚发的那句：命中
  `MEDIA_MUSIC_ASK_RE` / `MEDIA_VIDEO_ASK_RE` 就记一个 `group_id:sender_id` 的待答意图，
  默认 180 秒；
- 接话窗口内：follow-up 触发时消费待答意图，给本轮加
  `qqbotstack_music_intent` / `qqbotstack_video_intent`；
- 接话窗口外：`guard` 在普通消息前查待答意图；命中就置同样 extra +
  `is_at_or_wake_command=True`，让默认管线接这一句；
- 指令 / 分享 / 点歌 / 视频意图命中时清掉待答意图，走原链路。

**实测**：给模型「你刚才说：想听什么歌？ / 有人说：晴天」的接话上下文，
`HY3-Free` 直接返回 `tool_calls: play_song_by_name({"song_name":"晴天"})`。

**线上实测（2026-10-26 16:14）**：

- 16:13:56 `[media-pending] set kind=music`；16:14:04 `collect`；16:14:08 `trigger`
  —— 待答意图与接话都正常。
- 16:14:19 模型对「慢歌1」选择直接反问「你说个真名儿我放」，**没调**
  `play_song_by_name`。提示词必须写死「像歌名就先搜一次，搜不到再问」。
- 16:14:52 的接话是机器人回复后 **33 秒**，被 30 秒窗口挡掉；窗口调到 45 秒。
- 16:14:28 有一次正常重启（无 traceback），内存待答状态会丢；
  已落盘插件目录的 `pending_media.json`，180 秒内重启不丢。

## P33 统一回复/点歌卡片后接话窗口不重开

**现象**：接话窗口触发过一次统一回复后，机器人再说话就不再收集后续接话；
点歌卡片发出来后，卡片下面也没有接话窗口。

**根因**：

- `after_message_sent` 在「手动置 `is_at_or_wake_command`」的统一回复路径上
  不一定触发；只在普通唤醒路径上稳定。
- 点歌/分享是工具直接 `event.send` 发卡片。如果最终文字回复为空，
  respond stage 直接返回，不触发 `after_message_sent`。

**怎么避**：

- `on_decorating_result` 里也调用 `_open_followup_window`，普通回复和统一回复都重开；
- 点歌/分享/视频回合在 `on_llm_request` 先开一个 provisional window，
  卡片没有最终文字也仍有接话窗口；
- 窗口和待答意图都按群隔离，重启后 `pending_media.json` 仍能恢复。

**超时别先怪插件**：zgate 日志里 `model=Beam -> OC:beam-free` 后
`context canceled` 要等 50–120 秒，是 OpenCode 免费上游不返回；
`DeepSeek-4.1-Flash` 是 `rate_limit_exceeded` / `no_healthy_account`。
`HY3-Free` 是唯一稳定的，但 `global:hy3` 经常 `Too Many Requests` 后回退
`cn:hy3`，这才是 9–11 秒的主因，不是插件循环卡住。

## P34 AstrBot 重启窗口里 NapCat 反向 WS 会 ECONNREFUSED

**现象**：群里发消息机器人不回；NapCat 日志反复出现
`反向WebSocket (ws://127.0.0.1:6199/ws) 连接意外关闭`、
`connect ECONNREFUSED 127.0.0.1:6199`，但它自己的进程一直在。

**根因**：AstrBot 重启的几秒里 6199 没有监听；NapCat 每 5 秒重连，
**重连失败期间收到的群消息直接丢失**。这不是 NapCat 掉线，也不是 guard 挡消息。
本仓 16:36–16:51 的「不回复」就是连续部署/诊断重启造成的。

**怎么避**：

- 部署/改插件不要连续重启；一次改完再重启，重启后等 10 秒再发消息；
- 计划任务不要配重复触发器；`QQBotStack-astrbot` 只保留 boot 触发；
- 不要在机器上同时跑多个诊断脚本（例如 `probe_emotion_beam.py`），
  它们会占用模型上游、制造额外 Beam 超时；
- 判断依据看 AstrBot 日志有没有 `event_bus` 收到消息，而不是只看机器人有没有回。

## P35 Beam 本身很快，但别把它配成 180 秒超时的 fallback

**现象**：`Beam` 单次 2–6 秒就返回（思考 36–143 tokens），但偶尔一次冷启动
45 秒甚至更久；HY3 限流时 AstrBot 回退到 `zgate-beam`，用户要等 45–180 秒。

**根因**：`zgate-beam` 和 `zgate-router` 共用同一个 provider source，
`timeout=180`；`agent_runner.model.fallback_provider_ids=["zgate-beam"]`。
Beam 的 OpenCode `beam-free` 上游冷启动会挂起，不是 Beam 的思考慢。

**怎么避**：

- 给 Beam 单独一个 provider source，`timeout` 设 8–10 秒，再 fallback 到 HY3；
- 或者在 Beam 上游稳定前，先把 `zgate-beam` 从 `fallback_provider_ids` 移除，
  让 HY3 失败时走 `error_reply`，而不是卡 45–180 秒；
- 不要因为一次测速 Beam 2.2s 就把所有短消息切过去，先看它冷启动是否稳定。

**本仓落地（2026-10-27）**：`zgate-beam` 单独 **20 秒** source timeout（快速失败，
把时间留给 fallback），`zgate-router`（HY3-Free）**25 秒**，`zgate-hy4`
（HY4-Pre-Free）**30 秒**；`agent_runner` 主 provider 是 `zgate-beam`，fallback 是
`["zgate-router","zgate-hy4"]`；guard 的 `routing_enabled=true`，但
`model_simple=model_complex=Beam`。图片不走 `req.model` 硬切，而是靠
`zgate-beam.modalities` 不含 `image`，让 AstrBot 原生把带图请求切到 HY3
（见 P88）。实测文本回复 2 秒（zgate `model=Beam`）。

**为什么 HY3 只给 25 秒**：WB 的 `cn:hy3` 偶尔整分钟不返回（2026-10-27 17:22
实测一次 60 秒 APITimeoutError）。原来的 60 秒超时会让「Beam 502 → HY3 卡满 →
HY4」的一轮拖到 88 秒。HY3 健康时简单回复 1–4 秒、带工具 9–15 秒，25 秒既够用，
又能把最坏等待压到 20 + 25 + 几秒。

**HY3 也单独熔断（guard 1.6.31）**：Beam 和 HY3 各自计数，连续 3 次超时/5xx 后，
agent 请求遇到熔断模型会**立即返回 err**，不再等 source timeout，直接由 fallback
链切下一个；Beam 和 HY3 都熔断时直接选 `zgate-hy4`。HY4 的 source timeout 也压到
30 秒，避免最后一层再拖满一分钟。后台插件（只传 prompt、不传 contexts）不受
fail-fast 影响，仍按自己的超时跑。

## P36 歌词工具只发图、不返回文本，模型没得评论

**现象**：用户查歌词，机器人只发一张歌词图，没有一句评论。
日志：`query_lyrics_by_name 没有返回值，或者已将结果直接发送给用户。`

**根因**：音乐插件的 `query_lyrics_by_name` 成功后没有 return；工具只把图
`event.send` 出去，agent 循环拿不到任何歌词文本，自然无法评论。

**怎么避**：

- 工具发图后返回一段歌词摘录（本仓运行时补丁：去 LRC 时间戳，截 220 字）；
- guard 增加歌词意图和提示：先调 `query_lyrics_by_name`，拿到摘录后用一两句话
  说歌词/感受，不要只发图、不要复述全文；
- 第三方插件升级会覆盖运行时补丁，升级后要重新打；补丁只改
  `astrbot_plugin_music/main.py`，不改仓库。

## P37 分段回复的正则不认换行

**现象**：模型回复里有一个大回车/空行，但机器人整段发一条，没有一句一句发。

**根因**：`platform_settings.segmented_reply.regex` 默认只匹配
`。？！~…`，不包含 `\n`；模型不打句号时，整个回复被 `.+$` 一次吞掉。
另外 `words_count_threshold` 的语义是「超过阈值就不分段」：设 100 时
超过 100 字的长文根本不进分段；设 100000 才让长文进入正则。
但模型常用空格断句、不打标点，正则仍然抓不到切分点。

**怎么避**：

- regex 改为 `.*?[。？！~…\n]+|.+$`，让换行也成为切分点；
- `content_cleanup_rule` 设为 `[\s。]+$`，去掉每条末尾的换行和句号；
- `words_count_threshold` 设 **100**，不要设 100000；
- 实测「第一句\n第二句。第三句」→ 三条消息。

## P38 世界书把「拉斐尔」和「拉贵尔」写串

**现象**：机器人说自己是拉斐尔，甚至把「玟德是拉斐尔的代行者」说成「玟德是我代行者」；
群里问「你是不是拉斐尔」，它顺着认了。

**根因**：世界书里有大量拉斐尔条目（神体、人间体、权柄、羽翼），人物页只写
「外人叫他拉斐尔神父」，没有一条**优先级足够高**的身份辨析。模型把「借名」当成「本人」，
再把拉斐尔和玟德的关系挪到自己身上。

**怎么避**：

- 新增 `## 身份辨析`，`priority=95`，写死：梵铭不是拉斐尔；拉贵尔是梵铭的别名；
  拉斐尔是另一位神之裔，是另一个人；凯把「拉贵尔」听成「拉斐尔」，梵铭没有纠正；
  玟德是拉斐尔的代行者（不是梵铭的），也是梵铭的长辈，不是下属；
- 新增 `## 人物口吻速查`，`priority=85`，把七个人的语气一屏列完；
- 两条的 `keys` 必须包含 `拉斐尔`、`拉贵尔`、`玟德`，否则问「你是不是拉斐尔」时注入不到；
- 人格首段再重复一遍身份，不能只靠世界书；
- 只写「他是拉斐尔神父」不够，模型会默认「神父 = 本人」。

## P39 对长辈不敬、语气放荡

**现象**：说玟德「皮糙肉厚」「我代行者」，对长辈贫嘴拆台；回复像网络乐子人，
没有神父的稳重。

**根因**：人设里「对亲近的人欠揍」被泛化到所有关系；口吻表只写「短句不客套」，
没写「对玟德要称先生、语气敬重」；模型把「不客套」理解成「可以不尊重」。

**怎么避**：

- 人格里把「欠揍」限定为同龄熟人、只在不正经的场合；对长辈用「您」「先生」，
  不贫嘴、不拆台、不拿他们开玩笑；
- 写死「玟德是长辈，也是救过你的人，不是你的下属；不要用我的人 / 我代行者」；
- 口吻表单独补「他不是你的下属」；加 few-shot「玟德还好吗」→
  「玟德先生在外面 有消息会告诉我 您别担心」；
- 加「不夹英文单词」「别人说网络梗不跟着说」；实测模型会在「你好犟」里夹 `stubborn`，
  用 few-shot 钉住比只写规则有效。

## P40 所有回复都变短

**现象**：问关系链、问过去也只回一句；模型 think 里反复说「按 persona 简短回应」；
长回复被拆成好几条短句。

**根因**：两处叠加：人格里「短」的权重过高；`words_count_threshold=100000`
让所有回复都走分段，长文也被拆碎。另有旧版人设硬性限 30 字。

**怎么避**：

- 人格加长度规则：日常闲聊一两句；对方认真问设定、关系、过去，或需要安慰、解释、
  讲故事时，必须三四句以上；对方说「讲讲」「介绍一下」「说说看」就是要长文；
- `begin_dialogs` 加长文示例（关系链 127 字、悠塔 144 字、蒂米 103 字），
  只写规则不够，few-shot 才拉得动；
- `words_count_threshold` 改 100000 + guard 长文切段：短回复整条发，长文按小段拆；
- 保留「不要每次都写小作文」，避免从「全短」摆到「全长」。

## P41 生成期间到达的接话被吞

**现象**：两个人隔 1 秒发问，第二条在 `[followup] trigger` 之后到达；日志里没有
`collect`，消息直接被丢掉（17:11 的「还没适配好吧」）。

**根因**：`guard` 开头 `if state["generating"]: event.stop_event(); return`，
没有排队；同时 3 秒防抖太短，第一个人已经触发统一回复。

**怎么避**：

- `followup_debounce_sec` 3 → 6 秒，等第二个人把话打完；
- 生成期间到达的接话不立即回、也不丢：handler 每 0.4 秒查 `generating`，
  等当前回复发完再 `is_at_or_wake_command=True`，作为下一条单独接住；
- 最多等 45 秒，避免模型/发送异常时事件永久挂住；
- 日志留 `[followup] defer late` / `late release`，下次看日志能直接判断；
- 纯图片、自己、`ignore_ids`、空文本仍然不接。

## P42 模型把内部标签和大回车漏进正文

**现象**：回复里出现 `</rfl:parameter>`；段落之间有两个以上连续换行，QQ 里看起来
是一个大空行。

**根因**：模型把工具参数标签漏进正文；`_clean_style` 只压到 `

`，没有压到单换行；
AstrBot 的分段清理只在分段路径执行，长回复不走分段就不会被清。

**怎么避**：

- `_STRAY_TAG` 正则删掉 `</?tag>` 这类残留标签；
- `
` 统一成 `
`；`
{2,}` 压成 `
`；行首行尾空格清掉；
- `_clean_style` 在 `on_decorating_result` 对每个 `Plain` 执行，和 Markdown/emoji 同一条路径；
- 这条是确定性兜底，人格里仍然要求不用括号、不写旁白。

## P43 接话太勤，变成水群

**现象**：机器人在 45/300 秒窗口里对每一条群聊都回，5 分钟回了 10 条；
用户问「只要说话就会被回复吗」。随后 `chain` 到 10 又突然不说话了。

**根因**：`_followup_candidate` 只要求文本长度 ≥2，不判断和当前话题有没有关系；
`random_prob=0.25` 又额外制造随机插话。`followup_max_chain` 是硬上限，
到 10 就停，所以表现成「先刷屏、后装死」。

**怎么避**：

- 每群加**心动值**（初始 70，每分钟 -1.0；点名 +25，相关 +6，回复 -2，无关 -8）；
  低于 20 只接 @/引用/叫名字；
- 窗口内先过相关性：问句与当前话题的 bigram 重叠 ≥0.1，陈述句 ≥0.2；
  无关消息不收、不回，只降心动值；
- 心动值 ≥60 时不再无条件接；只把门槛压低（问句 0.05 / 陈述 0.1），仍需沾边；
  出圈话题 / 话题漂移会扣 12 分并关窗（见 P50）；
- 直接 @ / 叫名字的那条永远当主目标，不能被更相关的第二个人顶掉；
- 直接点名把 `chain` 清零，避免硬上限造成永久沉默；
- `random_prob` 0.25 → 0.03；
- 日志留 `[interest] value=...`，能看出它为什么回/不回。

## P44 纯图 / 表情包一来，机器人直接不说话

**现象**：群里发表情包，机器人毫无反应；@ 它发图也不回。日志里只有
`[图片]`，没有 follow-up collect，也没有模型请求。

**根因**：`guard` 在随机插话分支对 `has_image` 直接 `stop_event()`；
`_followup_candidate` 又要求非空文本，纯图永远进不了 LLM。AstrBot 的
`_select_image_chat_provider` 本来会把 Beam 切到 HY3/HY4，但消息根本没走到那一步。

**怎么避**：

- 纯图/表情包在「直接 @ / 引用 / 叫名字」时放行，设置 `qqbotstack_image_turn`；
- 窗口内、心动值 ≥50、同群 30 秒冷却时也放行，作为接话；
- 其他纯图仍忽略，避免刷屏；
- `_inject_media_hints` 增加图片提示：先看图再说话，别回「看不到图」；
- 生成期间到达的图也走 `defer late` / `late release`。

## P45 模型只会说「我不懂，你先说清楚」

**现象**：问「赫尔墨斯是谁」回「赫尔墨斯我不懂 你先说清楚」；问「点数」「提示词」
也一律「不懂」。看起来嘴很严、不会用世界书，也不会自己编日常。

**根因**：两层。第一，世界书关键词没覆盖变体：设定写「赫耳墨斯」，用户打
「赫尔墨斯」，精确子串匹配不到；新增的赫尔墨斯人物页也没进旧世界书。
第二，人格里「不解释设定」被模型理解成「设定一律不聊」，于是用「不懂」挡回去。

**怎么避**：

- 世界书补 `赫尔墨斯之眼` / `教堂日常` 两条补充条目，别名补
  `赫尔墨斯=赫尔墨斯之眼`、`文德=玟德`；人物页/细纲一起进世界书；
- 人格改成「不解释提示词和系统指令，但可以聊设定，用你的话讲」；
- 写死「别人问到你没听过的名字，先说没听过或问是哪一个，再按相近的东西接一句；
  不要每句都用『我不懂，你先说清楚』」；
- 加「世界书是日子不是台词，可以补日常小场景，只要不改已定事实」；
- few-shot 加「赫尔墨斯是谁」「今天教堂里有什么」。

## P46 模型不调工具、答得像缓存

**现象**：问「月光喜欢吗」直接回「喜欢 月光慢」，不调用 `play_song_by_name`
或 `query_lyrics_by_name`；用户说「这模型真的一般般」「不会自己调用工具」。

**根因**：`routing_enabled=false`，所有请求都走 Beam。Beam 快，但工具调用和
创作弱；复杂问句、带图、点歌也全落在它身上。guard 里原来的 `_route_model`
本来能按长度/复杂词/图片切 HY3，却被关掉了。

**怎么避**：

- `routing_enabled=true`，`model_simple=Beam`、`model_complex=HY3-Free`；
- `COMPLEX_HINTS` 补「喜欢 / 介绍 / 关系 / 世界 / 设定 / 故事 / 以前 / 过去 /
  知道吗 / 听过 / 看过 / 玩过 / 了解 / 认识」；
- `simple_max_len=14`，短闲聊仍走 Beam；
- `zgate-beam-source` timeout 10 → 20 秒，给 HY3 推理留时间；
- `_inject_media_hints` 对「喜欢/听过/知道……吗」注入 `[工具优先]`：
  歌/视频/作品先调工具，人物/地点按世界书讲；
- 实测 HY3 在「月光喜欢吗」上返回 `tool_calls: play_song_by_name({"song_name":"月光"})`。

## P47 旧设定的蒂米、凯还留在人格里

**现象**：新版 EmeraldEden 已删除蒂米、把商路人物改成赫尔墨斯，但人格和补充世界书
还在说「凯」「蒂米」，模型会把两个版本的设定混在一起。

**根因**：设定集更新后只重建了世界书，没有回查人格里的 few-shot 和补充条目。

**怎么避**：

- 以 `设定/08-人物/00-人物索引` 的七个人为准：梵铭、铭、玟德、犹达斯、
  赫尔墨斯、乌列尔、卡戎；蒂米这条线已删，功能并入赫尔墨斯；
- 人格里的「凯」全部改「赫尔墨斯」，「蒂米」改成「多出来的一副碗 / 铭 / 炉子」；
- 世界书补充的身份辨析、赫尔墨斯之眼、教堂日常同步改；
- 重建后搜一遍 `蒂米|凯`，确认人格和补充条目里不再出现旧名字。

## P48 中期 RP 的世界书混进后期剧情

**现象**：机器人提前说「赫尔墨斯是乌列尔的代行者」「犹达斯以前叫悠塔，现在说不了话」
「火种是钥匙，绿海是一艘船」；问「犹达斯是谁」时把它和卡戎认错；
问「拉梵是谁」时夹出 `occasional`，问「火种是什么」时夹出 `faces`。

**根因**：世界书直接拼全本设定 + 粗纲/细纲，人物页和剧情页把第十三章以后的事
和作者级真相一起注入；人格 few-shot 也留着后期事实（「说不了话」「乌列尔的代行者」）。
世界书本身没错，错在给中期 RP 用了全本。另有两次关键词事故：
`铭` 这个单字 key 会命中「梵铭」，让关系矩阵一次算两票；
`犹达斯` 同时挂在「悠塔」和「此刻不在场的人」两条上，模型会在两个名字里挑错。

**怎么避**：

- 世界书按**当前阶段**手工编排：只收梵铭此刻知道的世界、四个核心人物
  （梵铭、铭、玟德、拉梵）和熟悉的来客（赫尔墨斯、露西）；后期人物只留
  「没见过 / 没听过」的边界条目；
- 不写章节号、不写结局、不写静默协议 / 双核 / 方舟；作者级真相
  （拉梵=拉斐尔人间体、赫尔墨斯=乌列尔代行者）不写进注入正文，
  最多写「梵铭不知道他的底细」；
- 「犹达斯」只留悠塔一条，并写死「不要提卡戎，也不要把两个人混在一起」；
  不要再把「犹达斯」加进「此刻不在场」的 keys；
- 单字人名 `铭` 保留在人物页，但不要加进 `关系矩阵` 的 keys；
- 人格 few-shot 同步删后期事实；改完清 `conversations`；
- 英文夹词不要只靠禁用词表，优先加中文 few-shot 钉住
  （本次加「火种是什么」「拉梵是谁」两条）；
- 探针至少覆盖：你是谁 / 是不是拉斐尔 / 玟德还好吗 / 介绍身边的人 /
  悠塔以前是不是话很多 / 拉梵是谁 / 赫尔墨斯是谁 / 犹达斯是谁 /
  火种是什么 / 结局是什么。

## P49 音乐卡片发出来了，但没有封面图

**现象**：点歌后 QQ 里能看到音乐卡片，标题、歌手都正常，封面是空的；换歌也一样。

**根因**：`netease` 搜索接口本身不带封面，`BaseMusicPlayer.fetch_extra` 从
`https://api.qijieya.cn/meting/?type=song&id=...` 补到的 `pic` 是**重定向地址**。
NapCat 的 `card` 模式把封面交给音乐签名服务（默认
`http://106.55.0.102:10087/`，失败回退 `https://ss.xingzhige.com/music_card/card`）；
签名服务对重定向地址会返回 `qq.ugcimg.cn` 的 `preview`，实测 **404**，
所以卡片没有图。

**怎么避**：

- 发卡前先把封面按 `allow_redirects=True` 解析成最终 CDN 直链，再交给 NapCat；
  本次在 `astrbot_plugin_music` 的 `BaseMusicPlayer` 补了 `resolve_cover_url()`，
  `_send_card` 调用它；
- 直链示例：`https://p3.music.126.net/...jpg?param=300y300`；
  主签名服务会原样把它作为 `preview` 返回，GET 200 / `image/jpg`；
- 备选签名服务 `ss.xingzhige.com` 目前也会返回 404 的 `qq.ugcimg.cn` 地址，
  不能当可靠兜底；主签名服务挂了才会走到它；
- 插件升级会覆盖本次补丁，升级后要用 `.work/music-plugin-src/` 里的版本重打，
  备份在目标机 `.work/backup-20261026-music-cover/`；
- 探针顺序：搜歌 → `fetch_extra` 取 `pic` → 解析重定向 → 签名服务 →
  GET `preview`；四步都过才叫修好。

## P50 群里聊到 AI / 游戏，机器人还硬接

**现象**：机器人刚回完一句，群里转去聊 AI、游戏、显卡、动漫、明星，它还在接；
接的内容空泛、云里雾里。心动值越高越明显。

**根因**：`interest_high`（≥60）时 `_followup_candidate` 直接 `return True`，
完全不看话题；话题相关又是拿「滚动拼接的最后 240 字」算 bigram，
新话题只要沾上旧词就能混过去；没有「这个话题不适合我」的判断。

**怎么避**：

- 出圈闸门：`OUT_OF_SCOPE_RE` 命中 AI / 游戏 / 技术 / 娱乐圈，且不是直接点名 → 不接；
- 漂移闸门：开窗时记 `topic_seed`（点名消息 + 机器人回复），消息和 seed、
  上一条接话都没有实际内容重合 → 视为换话题；
- 用 `TOPIC_STOP_BIGRAMS` 过滤「今天 / 你们 / 觉得 / 就是」这类通用词，
  别让一个「今天」假装还在聊原话题；
- 命中人设领域词（汤 / 盐 / 罐子 / 雪 / 教堂 / 玟德 / 铭 / 拉梵 / 累 / 难受…）
  直接算相关，避免短句被 bigram 误杀；
- 出圈 / 漂移扣 `scope_loss`（默认 12）并 `scope_close_window` 直接关窗，
  让群里自己聊；
- 高心动值只降门槛（问句 0.05 / 陈述 0.1），不再无条件放行；
- 直接 @ / 引用 / 叫名字仍然一定回；不懂就照实说没听过。

## P51 few-shot 里的「具体细节」会变成复读模板

**现象**：角色扮演 15 分钟内 7 次提罐子、5 次提汤；用户调侃「他真的很爱数罐子」
之后还继续数；「你喜欢什么」「今天教堂里有什么」都回到同两样东西。

**根因**：人格一边要求「每次回答尽量带一个新的具体细节」，一边只给罐子/汤/
草球/雪/盐/碗这几个例子；begin_dialogs 里又有四条在示范同样的物。小模型会把
「范例」当成「必须复用的模板」，越被提醒越容易复读。

**怎么避**：

- 具体细节要给**可轮换的池子**，不要只给两三个词；写明「上一轮用过的物、
  句子结构、口头禅，这一轮换掉」；
- 加一条反模板硬规则：最近反复出现的几样东西，除非对方先提起，否则不要主动写；
  对方点名调侃时，承认、收住、换话题，不要顺着再演一遍；
- few-shot 不要只写「模板答案」，要写「被用户指出重复时怎么收」；
- 验收不要只问一次，跑一条 6 轮连续对话，统计每个意象的出现次数；单轮探针
  看不出复读。

## P52 角色扮演 bot 不该拿到主机 shell / grep / 文件工具

**现象**：问「玟德长啥样」时，模型连续调用 `web_search_anysearch` /
`astrbot_grep_tool` / `astrbot_execute_shell` / `astrbot_shell_session`，
在目标机上翻目录找角色设定，最后仍是编的；既慢，又能读到主机文件。

**根因**：实例 `cmd_config.json` 开着 `provider_settings.web_search=true` 和
`provider_settings.computer_use_runtime=local`。AstrBot 会因此把 web_search、
shell、python、file read/write/edit、grep 一起塞进请求，模型在群聊里也能调。

**怎么避**：

- 角色扮演实例固定 `web_search=false`、`computer_use_runtime=none`、
  `add_cron_tools=false`；
- `computer_use_local_permissions` 的 admin/member 都关 `allow_execution` /
  `allow_network`，不要把「管理员」当成可信边界；
- 只保留业务插件工具（点歌、解析、表情检索）；启动日志应只剩
  `play_song_by_name / query_lyrics_by_name / parse_media_url / parse_share_link /
  search_memes`；
- 需要真实世界资料时，单独开一个只读搜索工具，不要用 shell/grep 代替。

## P53 角色的死亡/创伤写成「出了事」会被模型轻演

**现象**：问悠塔时答「他从前话最多……后来那夜的事我不常提」，像在讲一段可爱
童年；用户明确说「他小时候就死了，应该是怀念」，机器人的表现完全不对。

**根因**：世界书只写「梵铭以为他死了 / 不知道他还活着」，人格只写「后来出了事，
不要把这件事当谈资」。模型拿不到「他已经死了、梵铭觉得是自己害死的」这两个
硬事实，就会按「久别的朋友」演。

**怎么避**：

- 在中期视角里写死「悠塔死在十岁那夜」和「梵铭一直觉得是自己害死的」；
  作者级真相（他其实还活着）不要写进中期注入，避免模型两边摇摆；
- 给表演规则：先停、句子变短、可以讲一件很短的小事，但讲完落回沉默或自责；
  不要用罐子/汤/天气岔开，不要马上反问对方听歌，不要主动提；
- few-shot 写一条「悠塔以前是不是话很多」，最后必须落到那夜和他的死；
- 区分「梵铭知道的版本」和「作者知道的真相」，不要把后者写进当前阶段的世界书。
## P54 代词追问不带人名，世界书会漏命中

**现象**：先问「玟德是什么性格」，再问「他长啥样」，机器人没有拿到玟德的外貌
条目，转而去翻主机文件，最后自己编了一段。

**根因**：世界书取词只看当前消息（`event.message_str`）和接话上下文；「他长啥样」
里没有「玟德」，人物页的 keys 一个都命中不了。

**怎么避**：

- 当前消息含代词（他 / 她 / 它 / 这人 / 那人 / 这个 / 那个 / 其）时，把上一轮
  机器人回复的末 240 字一起拿来取词；只在代词追问时生效，避免每轮都把上一轮
  设定拖进来；
- 取词范围不要扩到整段历史或 begin_dialogs，否则所有人物页都会命中；
- 单测至少覆盖「他长啥样」+ 上一轮含「玟德」→ 命中玟德人物页；
- 这类漏命中会诱使模型调用 shell/grep 自己找设定，所以还要同时关掉角色扮演
  实例的主机工具（见 P52）。
## P55 旧「近全盲 / 认人全靠声音」口径会和新内视设定打架

**现象**：设定已改成「不是看不见，是不用眼睛看；闭眼更清楚；认人靠脉络」，
但人格和世界书还留着「近全盲」「我眼睛不好，认人全靠声音」，模型会两头说。

**根因**：类似这种「同一事实换了说法」的设定更新，只改了源头文件，没有回查
prompt / few-shot / 世界书里的旧口径。小模型会优先复述训练中更熟的那句。

**怎么避**：

- 设定改口径时，搜一遍旧词：`近全盲 / 全盲 / 眼睛不好 / 认人全靠声音`；
- 人格里把新口径写成可执行规则：`不是看不见 是不用眼睛看`；`看得见热度、流速、
  断点`；`看不见脸，也读不了心`；并补一条 few-shot；
- 世界书里给能力单开一个条目（这次是「梵铭 · 他怎么『看』人」），keys 放
  `眼睛 / 内视 / 光网 / 脉络 / 断点 / 读心`，不要只把它塞在长人物页里；
- 验收要同时问「你眼睛怎么了」「你看得见吗」「你能读心吗」「他长啥样」，
  只看一个「你是谁」发现不了旧口径。

## P56 begin_dialogs 末尾放同题 few-shot，模型会以为「刚答过」

**现象**：给「你眼睛怎么了」「赫尔墨斯长啥样」补了 few-shot 后，用户再问同样的话，
模型回「刚才答过啦」「我刚同您说过他的模样了」。

**根因**：`begin_dialogs` 是作为「之前的对话」注入的；放在列表末尾的 few-shot
就是离当前问题最近的一轮。当前问题与它同题时，模型会把示例当成真实历史。

**怎么避**：

- 新 few-shot 放在 `begin_dialogs` 开头，不要放末尾；
- 问法不要和用户最可能问的原句完全一致（「你眼睛怎么了」→「眼睛对你来说算什么」，
  「赫尔墨斯长啥样」→「赫尔墨斯是猫吗」）；
- 如果只需要一条口径，优先写进 system prompt 的规则段，不一定要加 few-shot；
- 验收时用探针问同题，专门看有没有「刚才答过」「刚说过」。
## P57 drift 只比字面重合，会误杀「短回答接住机器人自己的邀请」

**现象**：机器人说「你要是方便，就来教堂坐坐」，用户回「可以，就你一个人吗」，
guard 记 `reason=drift`、`ignore drift`，不回复；同一时段其他消息照常回。

**根因**：`_topic_drifted` 只拿 `topic_seed` 和 `items[-1]` 做 bigram 重合，没看
机器人自己上一句。短回答和最早话题的字面重合天然很低，「可以」「一个」又在停用
bigram 里，于是被判成换话题。

**怎么避**：

- 漂移判定除了 seed / 上一条接话，还要看 `state["bot_text"]`（机器人上一句）；
- 机器人上一句含邀请/问句线索（来 / 去 / 吃 / 喝 / 坐 / 方便 / 吗 / 睡 / 聊 / 一起），
  用户用「可以 / 好 / 行 / 那 / 我 / 没 / 不 / 吃 / 喝 / 坐 / 来 / 去」开头的短句
  接住时，直接放行，不要只靠 bigram；
- 放行前仍先过 `OUT_OF_SCOPE_RE`，别让「可以 原神启动」借短回答混进来；
- 单测要覆盖真实句子，不要只测「那盐还够吗」这种和 seed 有字面重合的例子。

## P52 用户记忆写进 DB / 日志，改人设或清会话就没了

**现象**：机器人刚认识的人，改一次人格、清一次 `conversations` 就又不记得了；
或者想在日志里翻「他以前说过什么」，只翻到零碎句子。

**根因**：把用户记忆塞进 AstrBot 的 `conversations` / `platform_message_history`
或 `logger`。改人格时必须清旧会话（见 P29），日志会轮转/被清；
这些地方都不是记忆库。

**怎么避**：

- 稳定偏好 → `plugin_data/astrbot_plugin_long_memory/memory/<QQ>.json`
  （long_memory 1.2.0，按 QQ 号一人一份）；
- 群昵称 / 每人历史发言 → `plugin_data/qqbotstack_guard/people/<QQ>.json`
  （guard 1.6.1，每条群消息记录，单条 200 字 / 每人 80 条 / 180 天）；
- 日志只留 `len=`、结果、错误类型，不留消息正文和称呼；
- 删除入口：guard `/忘记我`、long_memory `/忘记`；
- 改人格/清 `conversations` 前先备份这两个 `plugin_data` 目录；
  它们和 `data_v4.db`、`astrbot.log` 是分开的。
## P58 「先接住」不是「顺着认」；自嘲不能用来接贬低

**现象**：别人说「你还是不太聪明」，机器人回「是啊 不太聪明 你多教教我」；
别人说「去调教一下他的语言模型」，它回「我这调调跟旧木头似的 磨不出光来」；
同样的话连续两轮几乎原样复读。

**根因**：人格写「别人呛你、指出你的问题，先接住，再解释」+「对自己是自嘲的」，
模型把「接住」执行成「认同标签」，把「自嘲」当成万能接话。Beam 更严重：短吐槽
没有触发复杂词，直接被当成指令顺着答。

**怎么避**：

- 把「接住」写清楚：先听清对方指哪件事，再按自己的判断回；可以不认这个说法，
  也可以轻轻顶一句；不要人身攻击，也不要用「是啊 我不太聪明 你多教教我」把
  自己放低；
- 给角色一个可用的「反击素材」：他记得脚步声、数东西没数错过、能看见热度/断点；
  用具体事实挡回去，比空泛自嘲更像活人；
- 自嘲只在自己人面前偶尔用，明确写「不用它接别人的贬低」；
- 加「接住不是复读」：不要照抄对方上一句，同一个理由/自嘲不要连续两轮用；
- few-shot 用「有人说你不太聪明」这类不完全同题的句子，放 `begin_dialogs` 开头；
- 验收看实际回复里有没有「是啊/我不太聪明/旧木头/交出去」这些认输词，不要只看
  「有没有回复」。

## P59 短吐槽走 Beam，会把「吐槽」当「寒暄」

**现象**：「你还是不太聪明」「活人感重一点」这种 6–8 字的短句走 Beam，回复
要么顺着认标签，要么回一句「外面天快黑了 你吃了吗」，完全没有接住 meta 反馈。

**根因**：`_route_model` 只在长度 >14、带图、或命中 `COMPLEX_HINTS` 时走 HY3；
短吐槽没有命中，落到 Beam。Beam 快，但缺少人物判断和 meta 识别。

**怎么避**：

- 把「被评价 / meta 话题」的词补进 `COMPLEX_HINTS`：笨、傻、聪明、调教、模型、
  语言模型、提示词、人设、人格、语气、口吻、说话、活人感、AI味、不像、顺着、
  幽默、太假、好假；
- 只让这些词触发 HY3，正常短闲聊（「晚上好」「吃了吗」）仍走 Beam，别为了质量
  把所有短句都拖慢；
- 单测同时断言「你还是不太聪明」→ HY3、「晚上好」→ Beam，避免一刀切；
- 如果某个新吐槽词仍被 Beam 顺着接，先补词，不要继续加长人格。
## P60 late-release 逐条放行，会让一次回答变成一串回复

**现象**：机器人在生成一条长回答时，群里又来了 `[at]`、一句短话、一张图；当前
回答发完后，机器人连着回三次，用户体感是「突然回一堆、每条都回、同一个人的话
不整合」。

**根因**：late-release 路径是「每条消息各自等生成结束，然后单独
`is_at_or_wake_command=True` 放行」。没有批量缓存，三条 late 就是三次 LLM 调用。

**怎么避**：

- 生成期间到达的消息先写 per-group `late_buffer`，不要立刻放行；
- 当前回复发完后再等一个短 debounce（本次 2 秒），把同一批合并成一条；
- 合并文本带发言人前缀，同一个人只写一次名字，不同人分行；
- 图片优先做 carrier（保证图片本身不被丢），其他事件 stand down；
- 日志只应出现一次 `late release items=N`；如果还是多次，先查 carrier 选择和
  debounce，不要先改人格；
- 单测要覆盖 async 并发：3 条 late 同时到，只有一个 carrier 获得
  `is_at_or_wake_command`。

## P61 只 @ 不说话时，别用客服腔「想聊点什么」

**现象**：有人只 @ 机器人、没输入内容，机器人回
「在呢～想聊点什么，或者有什么需要帮忙的吗？」，像客服，不像梵铭。

**根因**：唤醒提示里「友好地询问想聊什么」被模型照搬；人格里没有针对
「只 @ 不说话」的具体口径。

**怎么避**：

- 人格加一条：只 @ 不说话时，说短招呼，比如「在 火还烧着 你说」；
- 明确禁止「想聊点什么」「有什么需要帮忙」这类客服句；
- 禁用波浪号～，它会让语气更像客服/助手；
- 验收时单独测一次裸 @，不要只测有内容的问句。
## P62 提示词堆到 1 万字符，Beam 会开始评价自己/摆烂

**现象**：机器人说「在的呢～想聊点什么」「端着说话的几句都透着一股念稿味」
「反正我这儿能干的活儿也不多」；日志 `sp_len=10445`。

**根因**：人格 3,919 字 + 66 条 few-shot + 世界书 2,200 字 + 表情提醒 +
接话块 + 长期记忆。小模型被长提示压住，注意力从「接话」转到「满足规则」，
于是开始评价自己的说话方式，并把「不卖惨」执行成摆烂。

**怎么避**：

- 每次改人格先看 `sp_len`；目标 3,000–5,000 字符，不要无限加规则；
- 人格只留核心：身份、感知、口吻、反模板、被调侃、meta、关键关系；
  具体场景用少量 few-shot，不要每个坑都加一条；
- 世界书注入设硬上限（本次 2 条 / 1,400 字）；
- 接话块、表情提醒也要算进总长度，不要只算人格；
- 验收用**实际模型**（本次 Beam）跑，不要只看 HY3 的效果；
- 如果模型开始说「念稿味 / 活人感 / 我干不了什么」，先减 prompt，不要继续加
  「不要念稿」「不要摆烂」这类 meta 规则——它们会加重症状。

## P63 世界书是按键注入的 RAG，不是群消息，也不是模型自选

**现象**：用户问「世界书不应该是可选读取吗，为什么是直接发出去的」。

**实际**：

- 群友看不到世界书。Guard 在 `on_llm_request` 里把命中的条目追加到
  `req.system_prompt`，只给模型看；
- 命中的是关键词（`keys`），不是全部；常驻条目（当前阶段/世界观总览）每轮都在；
- 本轮把上限从 3 条 / 2,200 字降到 2 条 / 1,400 字；简单闲聊通常只带常驻 366 字。

**如果要做「模型自选读取」**：

- 需要给模型一个 `read_worldbook` 工具 + 一段很短的索引，模型自己决定调不调；
- 代价是多一次工具往返，Beam 对工具调用的稳定性一般；当前 RP 场景不划算；
- 所以保留关键词 RAG，但严格限条数和字数。要改工具式，先确认模型愿意/能够
  稳定调用，再动。
## P64 把「场景自想」写成固定句，会立刻变成新的口头禅

**现象**：想让机器人接话自然，在唤醒规则里写了「说『在 火还烧着 你说』」，
又在「活人感」few-shot 里写「我就在这儿 火也烧着」；结果 Beam 把这两句当成
标准答案，反复复用。

**根因**：小模型会把 few-shot 和规则里的**原句**当模板；越具体的固定句，越容易
被复制。提示词里写死的「自然台词」反而最不自然。

**怎么避**：

- 唤醒/日常接话只写原则：用此刻正在做的事接住（劈柴、看火、收信、听风、
  擦桌子），每次换一样；不要写唯一答案；
- few-shot 只留给**设定/边界**（身份、眼睛、悠塔、赫尔墨斯、关系、被贬低时
  怎么接），日常细节不要给固定答案；
- 明确区分「设定不能改」和「日常可以自由」，让模型知道哪里能发挥；
- 验收至少跑两次同一问题，看是否复用同一句；只跑一次发现不了口头禅。
## P65 把「自由发挥」写成选项清单，还是限定答案

**现象**：为了不让机器人说「火还烧着」，人格改成「此刻在劈柴、看火、收信、
扫雪、擦罐子、听钟楼的风，挑一件合理的写」；结果它还是照菜单挑，只是菜单变长了。

**根因**：小模型会把列表当成候选集，逐项挑。只要 prompt 里出现枚举，它就会
优先复用这些词，而不是按场景想象。

**怎么避**：

- 自由发挥的地方不要写枚举；写**感官提问**：你正在做什么、听见什么、
  手上是什么触感、屋里什么味道；
- 只要求「写一件和当前话头有关的」，不规定是哪几件；
- 设定（身份、能力、死亡、关系）继续写死；日常动作/细节放开；
- 验收至少跑两次同一问题，看是否给出不同场景；只跑一次发现不了菜单复用。
## P66 人格里写「道具/动作」，模型会把它当成启动动作

**现象**：为了让机器人有生活感，人格写「钟楼、后院、柴火、炉子…」或
「此刻在劈柴、看火、收信…」；结果它每轮都从这些词起手，反复劈柴/看火。

**根因**：小模型会把人格里的具体名物当成默认场景；列举越多，越容易复用。
即使写成「按场景自己想」，括号里的选项也会被当成候选集。

**怎么避**：

- 人设只写身份、感知、口吻、行为边界、关系；**日常道具和动作不要写进人格**；
- 世界设定、地点、其他角色放在世界书里，按键注入；需要时自然会出现；
- 如果必须防止复读，只写一句「不要反复用同几样东西垫话；上一轮的具体物换掉」，
  不要列例子；
- 验收至少跑两次同一问题，看是否还从同一个道具起手。

## P67 Beam 会漏 `<|constrain|>` 这类特殊 token

**现象**：探针原始输出出现「在 教堂里<|constrain|>」，如果不清洗会直接进群。

**根因**：特殊 token 不是普通 XML 标签，`_STRAY_TAG`（要求 `<` 后是字母）
匹配不到；Beam 在受约束/截断时会漏出来。

**怎么避**：

- 在 `_clean_style` 里加 `_SPECIAL_TOKEN = re.compile(r"<\|[^>]*\|>")`，
  发送前先清；
- 单测覆盖 `<|constrain|>`，断言清洗后既不残留 token，也保留前面的正文；
- 这类 token 可能截断句子，清洗后如果只剩半句，按实际语义接受，不要硬补。
## P68 世界书原文会被模型原样搬进群

**现象**：问「就你一个人吗」，机器人回「玟德在里间 铭也住这里 赫尔墨斯和露西
常来 但不住店」——直接把世界书「不住店」搬进闲聊，像在念设定。

**根因**：世界书条目里的行业词/书面语（住店、住客、补给点）被模型原样引用；
世界书是设定，不是台词。

**怎么避**：

- 世界书用自然口语，不写行业词；本次「不住店」全部改成「不在教堂过夜」；
- 人物页写「平时住哪、谁常来」，不要写「住店/退房/前台」这类词；
- 模型引用设定时要求「用自己的话讲」，但更可靠的是从源头改掉不自然的词；
- 验收时问「就你一个人吗」「教堂里都有谁」，看会不会搬出书面语。

## P69 接话关联只看 seed/topic，不看机器人自己的上一句

**现象**：机器人刚说「……但不住店」，用户回「住店？」；guard 判
`high-unrelated`，不触发自动接话。用户觉得「明明和它上一句有关」。

**根因**：`_topic_related` / `_topic_drifted` 只对比 `topic_seed`、`topic`、
`items[-1]`；接话轮的 `topic_seed` 没有更新，机器人上一句只存在 `bot_text`，
而 `bot_text` 没参与关联判断。

**怎么避**：

- 关联/漂移判断必须同时看 `state["bot_text"]`；
- 短追问（「住店？」「为什么呢」）如果命中 bot_text 里的内容 bigram，直接算相关；
- 单测用真实句子：bot_text 含「不住店」，用户「住店？」要 related、
  「那住店是什么意思」不能 drift；
- 不要只靠 `answer-to-bot` 的固定前缀，那只覆盖「可以/好/那/我」这类回答。

## P70 Beam 会整句英文，也会夹常见英文词

**现象**：机器人整句回 `He doesn't explain much. I don't push.`；中文回复里
夹 `welcome`。

**根因**：Beam 偶发英文输出；`_ENGLISH_FIXES` 只覆盖少数词，整句英文没有兜底。

**怎么避**：

- 整条回复 Latin 字符 >= 8 且 CJK 为 0（或 Latin > CJK*2）时，发送前换成
  中文走神句，不让英文进群；
- 常见夹词做确定性替换：welcome/please/really/maybe/actually/because 等；
- 单测同时覆盖整句英文和单词夹词；
- 这是发送前兜底，不改变模型路由；用户要求继续用 Beam 时尤其需要。
## P71 亲近不等于全盘托出：角色知道多少要按性格和辈分写

**现象**：为了表现梵铭和玟德很熟，把玟德的完整过去（八岐大蛇、和拉斐尔的交易）
都写成「梵铭知道」；模型就会在闲聊里把这些深层秘密当谈资倒出来。

**根因**：把「最亲的人」误解成「什么都说」。玟德话少、说正事先卡壳、不说谢谢
也不说对不起，一百多岁；梵铭二十一，辈分差在那儿。他只会从日常里攒到一部分。

**怎么避**：

- 世界书写「梵铭知道的那一点过去」，只写表层：弃雪、村子、独臂、师傅、瘟疫；
- 深层真相留在作者设定，不写进中期「梵铭知道」的条目；
- 明确写「他不太讲；有些是喝多了漏一句，第二天不认；梵铭不追问」；
- 亲近写成动作：催吃饭、拆穿嘴硬、把吃的放他手边，而不是交换全部秘密；
- 验收要问「以前经历过什么」「以前是什么身份」，看会不会倒深层设定。

## P72 人物页拆成多条时，通用条目会挤掉具体条目

**现象**：玟德的人物页拆成「性格 / 语言与关系 / 梵铭知道的以前 / 和梵铭的相处」；
问「玟德以前是做什么的」时，注入的是「性格 + 语言与关系」，过去条目没进来，
模型就自己编成「镇狱官派/乌列尔」。

**根因**：所有玟德子条目共享同一组 keys，命中数和 priority 相同；排序稳定，
靠前的通用条目先占满 2 个注入名额。

**怎么避**：

- 具体的过去/关系条目单独提 priority（本次 90），高于通用人物页（84）；
- 条目名带上用户会说的词（「以前」「相处」），命中时多一票；
- keys 里加「以前/过去/师傅/相处」，但不要只靠通用人物名「玟德」；
- 验收要覆盖「以前是做什么的」这种会触发具体条目的问法。
## P73 长回复不拆/拆太碎：阈值和块大小要按真实句子调

**现象**：一段 70 字的相处回答整条发出去，用户觉得该拆成两段；把阈值降太低，
短回复又被拆碎。

**根因**：`_split_long_for_qq` 的阈值 90 太高（70 字不拆），块 60 又会让
105 字变成 60+45 两段但比例不自然；分段策略没有按实际句子长度校准。

**怎么避**：

- 用用户实际给出的句子做基准：本次 70 字和 105 字都目标 2 段；
- `LONG_TEXT_SPLIT_THRESHOLD=60`、`LONG_TEXT_CHUNK_CHARS=55`；
- 单测分别断言 70 字 → 2 段、105 字 → 2 段、短句 → 1 段；
- 不要把阈值降到 40 以下，否则日常短回复会被拆成多条。

## P74 把五官全推给旁人，会写死可触摸的感知

**现象**：问「玟德长啥样」，机器人说「头发雪白……这些是旁人告诉我的」；
把轮廓、断口、热度这些它能摸到的信息也推给了旁人。

**根因**：few-shot 里写死了「这些是旁人告诉我的」，模型把它当模板。

**怎么避**：

- 分清视觉和触觉：颜色、眼睛、文字是旁人/看不见；轮廓、胡须、断口、热度
  是它可以摸到的；
- few-shot 写「颜色和眼睛是旁人说的，我能摸到的是……」而不是全盘推给旁人；
- 世界书的「怎么看人」和人物外形条目同步这条边界；
- 验收要问「他长啥样」，看回答里有没有触觉，而不只是视觉描述。

## P75 关系 few-shot 与用户问句完全同题，会回「你问过这个了」

**现象**：用户问「你和玟德平时怎么相处」，模型答完加一句
「你问过这个了 有新的想问的吗」。

**根因**：`begin_dialogs` 里有一条完全同题的 few-shot，模型把它当成刚发生的
对话；关系信息其实已经写在世界书里。

**怎么避**：

- 关系/过去这类可由世界书回答的内容，不要再放完全同题的 few-shot；
- 需要 few-shot 时换问法（「你身边都有谁」而不是「介绍一下你身边的人」）；
- 世界书条目给具体 priority/keys，靠注入而不是靠背示例；
- 验收要问用户最可能说的原句，看会不会回「刚才答过」。
## P76 角色的位置/近况写进 few-shot，会变成固定回答

**现象**：每次问玟德，机器人都说「玟德在外面」；few-shot「玟德还好吗」的
固定答案正是这一句。

**根因**：位置/近况属于"按场景自想"的部分，却写进了 few-shot 的固定答案；
Beam 把它当模板复用。

**怎么避**：

- few-shot 只锚定身份、关系、行为边界；位置、近况、动作按场景自想；
- 人格里写原则：「按此刻的场景想一个合理的地方或动作，每次可以不一样；
  不要固定说他在外面」；
- 验收跑两次同一问题，确认场景不同；只跑一次发现不了。

## P77 部署脚本备份缺失文件会整段中止，服务停在停止状态

**现象**：`deploy_v8.ps1` 跑到 `--- backup` 就退出，机器人一直是停止状态；
原因是远程 `views/worldbook/index.html` 不存在，`Copy-Item` 抛错，而脚本
开头是 `$ErrorActionPreference='Stop'`。

**根因**：备份步骤默认目标文件一定存在，没有 `Test-Path`；停止任务和启动
任务之间没有 `try/finally`，任何一步失败都会把服务留在停止状态。

**怎么避**：

- 备份前逐个 `Test-Path`，缺失的跳过并打印，不要让整段中止；
- 停任务后把「启动任务」放进 `finally`，或失败时显式重启；
- 部署脚本先补目录/视图（`New-Item -Force` + `Copy-Item`），再跑备份；
- 每次部署后都查 `Get-ScheduledTask` 状态和 `aiocqhttp` 连接日志。

## P78 世界书条目改名后 KEY_BOOST/PRIORITY 静默失效

**现象**：问「教堂里都有谁」，模型只答「铭十八岁 住在这里 后院的花是他种的」，
漏掉梵铭和玟德。

**根因**：源文件标题从「教堂的住客（中期）」改成「住客与来客（中期）」，
但 `build_midworldbook.py` 的 `KEY_BOOST`/`PRIORITY` 还挂在旧名上；构建
不报错，条目只剩「住客与来客」两个自名键，`教堂/都有谁` 匹配不到。

**怎么避**：

- 改条目标题时同步改 `KEY_BOOST`、`PRIORITY`、`SUBKEY_BOOST`；
- 构建后打印目标条目的 `keys`，别只看条数；
- 用用户的原句做检索测试（「教堂里都有谁」「谁住在教堂里」）；
- 住客类条目至少挂 `教堂/住客/来客/谁住/住在教堂/教堂里都有谁`；不要用 `都有谁/谁在` 这种过宽的键。

## P79 重写世界书会把已清理的措辞带回来

**现象**：新世界书里又出现「不住店」，模型把它原样搬进回复；问玟德年龄，
模型报「一百二十岁」，被条目里的「别报具体岁数」带成「你别逼我猜」。

**根因**：重写时从设定原文抄写，P68 已经清理过的行业词没有同步；否定式
指令（「别报具体数字」）会被模型转成对用户说的「你别…」。

**怎么避**：

- 构建后 grep 禁用词：`住店/住客/退房/前台/补给点`，命中就改；
- 世界书用自然口语：「不在教堂过夜」而不是「不住店」；
- 年龄写「一百多岁，说个大概就行」，不要写「别报具体数字」；
- 探针要问「玟德多大了」，看会不会报具体数或怼用户。

## P80 Beam 偶发重复整段，英文词表要持续补

**现象**：同一条回复里同一段答两遍，中间只隔一个 `</rfl:parameter>`；
另外夹出 `occasional` 这种没进替换表的英文词。

**根因**：Beam 在长上下文/受约束时会把候选答案拼在一起；`_clean_style`
只清标签和已知英文词，不处理相邻重复行，也不处理同一行内连写两三遍。

**怎么避**：

- 发送前清 `_STRAY_TAG`/`_SPECIAL_TOKEN`；
- 加 `_drop_adjacent_duplicate_lines`，只删紧邻的完全相同行，不动正常重复；
- 加 `_drop_repeated_tail`：同一行里从开头起有 ≥16 字的整段重复时，只留第一遍；
- 英文先做短语级替换（`sharpening his sword`、`usually sitting in the chair
  by the fireplace`、`wherever he wants to go he just goes`），再做单词级；
- 探针里出现的新英文词补进 `_ENGLISH_FIXES`（本次 `occasional(ly)`、
  `excited/mostly/usually/telling`）；
- 探针直接调模型、不过 guard，看到标签/英文/重复先确认线上清洗器是否覆盖；
- 实测：25 条探针回复经 `_clean_style` 后拉丁字母为 0。

## P81 人物日常被写死成「某地做某事」

**现象**：玟德一出现就是「后院劈柴」，铭一出现就是「后院/藤蔓/花」，梵铭
日常固定成数罐子、炖汤、劈柴、上钟楼、去后院。用户问「他为什么每次都在
外面/后院」。

**根因**：世界书把「住客/关系」写成了日常脚本（「玟德带来第一块木料，后院
有他的劈柴声」「铭住进来后后院活了」），模型把设定当台词复用；few-shot 里
的固定画面也会被当模板。

**怎么避**：

- 只写住客身份、职责、关系、能力、过去；日常动作和地点交给当下场景；
- 世界书写「谁在哪儿、在做什么，按当下场景自然安排」，不要写「他总在…」；
- 人格里加一句原则即可，不要列「不要在后院/不要劈柴」这种禁句清单；
- 验收同一问题问 2–3 次，看回答分布，不要用单次回答判断。

## P82 关系细节写成固定动作，会变成服务脚本

**现象**：拉梵来必留座倒茶，露西来必留饭，犹达斯休息必擦盾，玟德必带
第一块木料。关系是暖的，但每次都用同一个动作表达，像执行脚本。

**根因**：用具体动作表达关系最省事，模型会把它当「这个角色的固定行为」；
写得越具体，复用率越高。

**怎么避**：

- 关系写感受和分寸（亲近、敬重、警惕、欠他的），不写「每次他来就…」；
- 必须给动作时用「可以/有时/偶尔」，不要用「总是/每次/一到…就」；
- 同一关系不要在多条条目里重复同一个动作（关系矩阵、口吻速查、人物页
  各写一遍，模型会当成三次强调）；
- 验收问「他来的时候你们做什么」，看是否只有一套答案。

## P83 去掉写死后，模型仍会自己发明固定爱好

**现象**：世界书已经删掉「后院劈柴/种花」，探针里玟德还是常被安排磨剑、
擦剑，铭还是常在后院/藤蔓边。

**根因**：设定里的相邻词（剑、藤蔓、教堂）会吸引模型；提示词只能去掉
写死的脚本，不能保证模型每次都不选同一个画面。

**怎么避**：

- 验收看多次分布：同一问题问 3 次，至少有 2 种不同地点/动作就算合格；
- 某个画面占比过高时，先检查是不是世界书里还有相邻词反复出现；
- 需要时只加一句「换一个场景」的轻提示，不要列禁句；
- 不要把模型自发的画面误判成提示词写死；先 grep 源文件确认。


## P84 「介绍身边人」被人物·关系页抢走，答成单向关系

**现象**：问「介绍一下你身边的人」，模型只讲铭对悠塔的痛，或者把玟德的断口/左眼串到铭身上，没有把玟德、铭、拉梵、赫尔墨斯、露西都介绍一遍。

**根因**：`SUBKEY_BOOST["· 关系"]` 给每个人物关系页都挂了 `身边的人`，人物页 priority 84 高于关系矩阵 78，检索时抢在关系矩阵前面；`人物口吻速查` 也挂了 `介绍`，进一步挤掉关系矩阵。

**怎么避**：

- 人物关系页的键只留 `关系`、`怎么看他`，不要挂 `身边的人`；
- `人物口吻速查` 去掉 `介绍`，介绍类问题交给 `关系矩阵`；
- 关系矩阵补最小身份（玟德是精灵族、铭十八岁/被切走的一半），避免模型自己编；
- 验收看 lore 里有没有 `关系矩阵（中期后段）`，没有就是键又没命中。

## P85 压缩速查表会把人物特征串在一起

**现象**：口吻速查压缩后，模型把「断口/左眼瞎」安到铭身上，把「送货」和「送信」都安到赫尔墨斯身上。

**根因**：速查表是密集的人物列表，压缩后每条只剩几个词，模型容易跨行混用；关系类问题又恰好注入了这张表。

**怎么避**：

- 介绍/关系类问题走关系矩阵，速查只用于「他怎么说话/什么语气」；
- 速查里保留最短的身份锚点（玟德精灵族、赫尔墨斯只送货/信件归露西、卡戎是摆渡人/犹达斯是他的二次生命）；
- 压缩时保留 4–8 字的辨识特征（不说谢谢/对不起、只叫梵铭、不能说话），不要为了字数全删；
- 验收问「介绍一下你身边的人」和「赫尔墨斯帮你劈柴」，看会不会串。

## P86 负例会被复述，假对话会自续写

**现象**：提示词写「不要让他抄歌词、修机关、带话」，模型回「别找他抄歌词」；模型还会在答案后面自续写 `<|start|>user<|message|>铭是谁`。

**根因**：负例把不该出现的词放进了上下文，模型原样复用；内部标记被当成新一轮对话的起点。

**怎么避**：

- 用职责句替代负例：`他只送货；信件归露西`，不写「不要让他抄歌词」；
- 在 `_clean_style` 里加 `_FAKE_DIALOG`，从第一个 `<|start|>/<|message|>/<|channel|>/<|constrain|>` 起整段截断；
- 单测用真实假对话样本，断言只保留第一段正文；
- 发送前再清 `_STRAY_TAG`/`_SPECIAL_TOKEN`。

## P87 年龄和英文残留要按真实输出补规则

**现象**：模型说「一百二十岁」「一百二十多岁」「一百二十几岁」；夹 `afternoon`、`himself`、`telling`。

**根因**：年龄正则只覆盖「一百二十岁」，没覆盖「多/几」；英文词表只覆盖已见过的词。

**怎么避**：

- 年龄正则写成 `一百[一二三四五六七八九十百几]+多?岁` → `一百多岁`；
- 新漏出的英文词/短语补进 `_ENGLISH_FIXES`，短语级先于单词级；
- 单测覆盖 `一百二十岁/一百二十多岁/一百二十几岁`、`afternoon`、`himself`；
- 探针直接调模型、不过 guard，看到残留先确认清洗器是否覆盖，不要误判成提示词没写。

## P88 引用消息里的图片不走 `get_messages()`，会漏给 Beam 并 400

**现象**：引用一张图再发一句话，Beam 返回
`400 [invalid_value] Beam supports text input only`；报错位置在
`messages[41]` / `messages[91]`（最后一条）。连续几次后 guard 断路器 OPEN，
图片修好后探活又立刻 CLOSE，看起来像「上游抖动」。

**根因**：AstrBot 把引用消息里嵌套的 `Image` 收进 `req.image_urls`
（`astr_main_agent.py:1600-1622`），而 guard 判图只看
`event.get_messages()`（返回顶层消息链，Reply 里的图不算 `Image`）。
再加上 `zgate-beam.modalities` 里声明了 `image`，AstrBot 的
`_select_image_chat_provider` 不会切 provider，`sanitize_contexts_by_modalities`
也不会剥图——图片就直接送到 Beam。断路器又把这些 400 当上游故障计数，
探活只发纯 `ping`，永远复现不了，于是「开了又关」。

**怎么避**：

- `zgate-beam.modalities` 只留 `text/tool_use`，**不要加 `image`**；
  图片分流交给 AstrBot 原生：`req.image_urls` 非空 → `zgate-router`（HY3，60s），
  失败 → `zgate-hy4`；
- guard 的 `has_image` 同时看 `req.image_urls` 和 `event.get_messages()`，
  作为模型名层面的双保险；
- 断路器只统计 5xx/429/超时/断连，4xx（内容/参数错误）不计；
- 回归用例必须包含「引用一张图 + 一句话」，只测纯图片消息会漏掉这条路径。

## P89 计划任务弹控制台窗口，`-WindowStyle Hidden` 压不住

**现象**：每次开机（任务每小时重试时也一样）弹出一个黑色/Terminal 窗口，标题是
`C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe`，一闪就关；
任务本身执行成功，日志里能看到记录。

**根因（2026-10-28 真机确认）**：操作机的默认终端是 Windows Terminal
（`HKCU\Console\%%Startup` 的 `DelegationTerminal` 指向 Terminal）。计划任务以交互身份
起控制台程序时，Windows 先把控制台托管给 Terminal 并**建好窗口**，而 `powershell.exe
-WindowStyle Hidden` 的隐藏标志是 PowerShell 起来之后才生效的 —— 窗口已经可见了。
实测：任务动作直接写 `powershell.exe -WindowStyle Hidden ...`，窗口照样以 VISIBLE 的
`CASCADIA_HOSTING_WINDOW_CLASS` 出现。

**怎么避**：别让任务直接跑控制台程序，套一层 `wscript` 用窗口样式 0 启动
（`tools/sync-auths-hidden.vbs`），控制台在创建时就带 `SW_HIDE`：

```vbs
sh.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -File ""...\sync-auths.ps1""", 0, True
```

任务动作写成 `wscript.exe //nologo "<repo>\tools\sync-auths-hidden.vbs"`。实测：无可见窗口、
脚本正常执行、跑完 wscript 与 powershell 都不留残余进程。附三条：

- 任务设置里的 `Hidden` 勾选框只影响任务列表显示，**不隐藏窗口**；
- 火绒的「隐藏执行PowerShell」敏感动作防护会把 `-WindowStyle Hidden` 的计划任务拦下来，
  必须在火绒放行；`wscript` 样式 0 不触发这条规则（2026-10-28 实测）；
- 验证时别只数「有没有新窗口」：Windows Terminal 会复用已有窗口/进程，
  容易把无效的隐藏方式误判成有效（本仓踩过：先判有效，复测才纠正）。

## P90 整段会话全量回传，bot 会把自己说过的垫话当模板

**现象（2026-10-28）**：8 分钟里「白茶/喝茶」出现 8 次；「先喝茶，其他慢慢来」
对 5 个不同的问题和人对答 5 次。用户说「不准喝茶了」，下一轮先答「好，不喝就不喝」，
再问一句又回到茶。人格里明明写着「上一轮说过的具体物，这轮换掉」。

**根因不是人格，是上下文自己喂出来的**：

- AstrBot 这个群的 `agent_runner.compression.max_turns = -1`，13 小时会话
  （114 条 / 39k 字）整段发给模型，里面机器人自己说过 **16 次茶**；
- 群友回复时引用机器人上一句，AstrBot 又把被引用原句以 **user 角色**塞回去
  （同一时段 18 条含茶引用）——模型在「用户回合」里也反复读到自己的旧话；
- Beam 这类小模型天然会接着上下文里的句式写，提示词里一句「不要复读」压不过
  十几次同款示范。few-shot/池子的复读（P51）是另一个来源，本质相同：**看见什么
  就会写什么**。

**怎么避**：

- 请求前折叠上下文（只改本次请求，不动 DB）：近似重复的旧助手回复删到只剩最新；
  全局高频 bigram（≥5 次）和最近短回复里的高频单字（≥3 次）再收一轮；
  世界书人物名/关键词对应的 token 受保护，设定问答不能删；
- 用户消息里引用机器人旧话的 `<Quoted Message>` 块去掉，用户自己的话保留；
- system 末尾追加**指名**的禁复读块：最近反复出现的意象（如「茶」）+ 最近两句原话，
  要求对具体问题先正面回答，禁止「先……再说 / 慢慢来」这类回避句；
- 发送前近重复兜底：纯文字回复与最近实际发出的 8 句近重复时，用同一份
  人格/上下文中重说一次（最多一次，失败保留原稿）；
- 别为此改人格——用户明确要求人格只写「他是什么人」（见
  [PROMPT-SPEC.md](PROMPT-SPEC.md) §5）；这类运行期规则放 guard。

**验证**：真实会话离线回放 114 → 98 条，助手茶话 16 → 3，引用茶话 18 → 4
（剩余 4 条是用户自己说的）；方大同/薛之谦等事实型回答全部保留。
线上验收看 `[guard-dedup]` / `[guard-repeat]` 日志和连续 6 轮同一问题的意象计数。

## P91 小模型把「把话头还给对方」执行成审问，还会抄输入格式

**现象**：2026-10-28 15:05 起，群里聊 AI/命令行，机器人连续回
「你先说清楚是哪个cli 要不然我只能猜」→（被指出重复后）
「这次不算 你先说清楚是哪个命令行工具 要不然我只能猜」→
「claude封号我听说过 但你用的是哪个CLI 具体说一下 我不猜了」。
15:15 两个人先后发言时，它把输入里的「名字：内容」格式原样抄回来，
用一行一个人的方式回复；同一条回复里还带着 `</rfl:parameter>`。

**根因**：两层。
1. 主模型 Beam 的指令跟随弱。人格里「接一句自己的话，或者把话头还给对方」
   和「也可以反问一句，把球踢回去」被它当成固定动作，于是每个听不懂的话题
   都变成要求对方先解释；「不要只回不懂」又堵掉了直说的出口。
   同一份人格、同一段上下文换 DeepSeek-4.1-Flash，三条全部是正常接话。
2. 上下文折叠误删。15:06 那句「你先说清楚是哪个cli…」和更早的
   「谁是小阮 你先说清楚」共享「你先说清楚」，被 `_repeat_like` 按
   bigram 重合 0.5 判成复读删掉；模型在 15:10 以为自己没说过，又原样说了一遍。

**怎么避**：

- 混合路由（guard 1.6.40）：`model_simple=Beam`、`model_complex=HY3-Free`。
  AI/命令行/复读抱怨这类易翻车话题，以及多人连续发言（输入以
  「以下是不同人的连续发言」开头）走 HY3-Free（约 20s），其余短句仍走
  Beam（约 1.3s）。免费模型实测：Iceman 风格最好但 26s，HY4 频繁 60s 超时，
  都不适合当主模型；全量 DeepSeek-4.1-Flash 只要 2.1s 但要花钱。
- 人格里删掉「或者把话头还给对方」（两处）和「也可以反问一句，把球踢回去」，
  换成「接一句自己的话」「说一件具体的小事」——只删指令，不加场景规则。
- `TOPIC_STOP_BIGRAMS` 加入追问句式（你先/先说/说清/清楚/具体/哪个/哪家/哪位），
  别让两个不同的追问句互相判重。
- 上下文折叠永不删**最新一条**机器人回复；真复读只删旧句。
- 多人连续发言的输入块末尾补一句「名字：内容只是记录格式，回复不要带名字前缀、
  不要按人分行」。
- 重说提示词别用「已经作废」这类措辞——模型会回一句「这次不算」再把原句抄一遍。

**验证**：同一段真实上下文（15:06/15:10/15:15）离线重放，
v23+Beam 三条都在追问；v24+DeepSeek 三条是正常接话；
工具调用 `play_song_by_name` 两个模型都正常返回 `tool_calls`。
