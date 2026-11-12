<div align="center">

<img src="https://raw.githubusercontent.com/MVennn/QQBotStack/main/assets/logo.png" width="128" alt="QQBotStack">

# QQBotStack

**把 QQ 机器人、QQ 协议端与模型网关装成一套**

能用系统自带的就别装第三方，能绑回环就别开端口。

![CI](https://github.com/MVennn/QQBotStack/actions/workflows/ci.yml/badge.svg) ![源码仓库](https://img.shields.io/badge/源码仓库-GitHub-181717?logo=github&logoColor=white) ![问题反馈](https://img.shields.io/badge/问题反馈-Issues-181717?logo=github&logoColor=white) ![Windows](https://img.shields.io/badge/Windows-10%20%2F%2011-0078D4?logo=windows&logoColor=white) ![AstrBot](https://img.shields.io/badge/AstrBot-4.x-6C5CE7) ![OneBot](https://img.shields.io/badge/OneBot-11-00A1D6) ![License](https://img.shields.io/badge/License-MIT-blue)

</div>

---

## 这是什么

一套 Windows 上的 QQ 机器人部署方案，三块组件拼成一条完整链路：**QQ 消息进来 → 模型生成回复 → 发回 QQ**。仓库里是部署与运维脚本、五个自研 AstrBot 插件、文档与门面资源，**不含任何上游代码或二进制** —— AstrBot / NapCat / wb2api 都在部署时从官方 Release 下载（见 [NOTICE](https://github.com/MVennn/QQBotStack/blob/main/NOTICE)）。

**AstrBot** 是大脑：接模型、跑插件、管对话。**NapCat** 是协议端：跑在 QQ NT 之上，把 QQ 消息翻译成 OneBot 11。**zgate** 是模型网关入口：AstrBot 只连 `127.0.0.1:7871`，由 zgate 按模型名分流到 `wb2api` / OpenCode 上游；**workbuddy2api** 是其托管的 WorkBuddy 账号池兼容层。zgate 不在本仓的部署脚本里 —— 它由 [ModelBus 仓](https://github.com/MVennn/ModelBus)（原 ZcodeAIModels）的 `zgate install` 安装并注册计划任务 `QQBotStack-zgate`，本仓只依赖 `127.0.0.1:7871` 与这个任务名（见 [docs/ARCHITECTURE.md](https://github.com/MVennn/QQBotStack/blob/main/docs/ARCHITECTURE.md) §5）。

三块的接线是固定的：NapCat 作为 WebSocket 客户端**主动连** AstrBot 的 `127.0.0.1:6199`，所以协议端不需要开任何入站端口；AstrBot 以 OpenAI 兼容协议请求 `127.0.0.1:7871/v1`（zgate），由它转发到 `wb2api 7863` 或 OpenCode；`7863` 仅作 wb2api 内部端口 / 探活目标。**三个服务的 WebUI 默认只绑回环**，运维通过 SSH 本地转发进入；唯一的例外是 AstrBot 面板（6185）可按[防火墙限网段](https://github.com/MVennn/QQBotStack/blob/main/docs/ARCHITECTURE.md)的口径对局域网开放，且前提是面板密码已改掉初始值。

完整边界、端口与「会改机器哪些状态」见 [docs/ARCHITECTURE.md](https://github.com/MVennn/QQBotStack/blob/main/docs/ARCHITECTURE.md)；每块组件怎么装、怎么调见 [docs/TOOLS.md](https://github.com/MVennn/QQBotStack/blob/main/docs/TOOLS.md)。每篇文档管什么、哪篇是正本，索引见 [docs/README.md](https://github.com/MVennn/QQBotStack/blob/main/docs/README.md)。

## 仓库里有什么

| 脚本 | 干什么 |
|---|---|
| `tools/deploy-stack.ps1` | 分阶段幂等部署：`-Stage gateway` / `napcat` / `astrbot` / `all` |
| `tools/verify-stack.py` | 五项验收，经 SSH 在目标机本地发起探测 |
| `tools/start-stack.ps1` | 一键查看 / 拉起四块组件（网关、zgate、AstrBot、NapCat）；`-Status` 只读报状态（服务、端口、QQ 登录），`-Restart` 支持 `gateway` / `zgate` / `astrbot` / `all` |
| `tools/stack-menu.cmd` | 双击式数字菜单：状态 / 启动 / 重启 / 面板 / 扫码 / SSH，地址全从 `stack.conf` 读 |
| `tools/get-qr.ps1` | 把目标机的最新 NapCat 二维码拉到本机并打开 |
| `tools/sync-auths.ps1` | 把操作机的 `auths/` 推到目标机并重启网关，当天已同步过就跳过 |

另有文档自检（`check-docs.py`）、脱敏扫描（`check-secrets.py`）、世界书切分（`build-worldbook.py`）与门面资源渲染（`make_social_preview.py`）；参数与退出码统一见 [docs/TOOLS.md](https://github.com/MVennn/QQBotStack/blob/main/docs/TOOLS.md) §1。

五个自研插件在 `host/plugin/`，装法是复制到实例的 `core\data\plugins\` 下再重启 AstrBot：

| 插件 | 干什么 |
|---|---|
| `qqbotstack_guard` | 唤醒与接话：指定群按 @ / 关键词 / 随机插话才开口，分享、点歌、聊视频走 LLM 工具 |
| `qqbotstack_people` | 人物记忆：按 QQ 号记称呼与亲密度，后台把聊天整理成画像与要点表 |
| `qqbotstack_worldbook` | 世界书：关键词匹配、常驻条目、优先级，带 WebUI 编辑器 |
| `qqbotstack_tools` | 媒体与小功能：分享解析、吃什么、API 小工具，运行时接管 parser / apis / what_to_eat |
| `qqbotstack_memechance` | 表情机缘：给 LLM 回复随机附加一张本地表情包图片 |

插件配置用各自目录的 `config.example.json`（guard / people / tools / memechance 四份，worldbook 在 WebUI 编辑器里配）：复制成同目录的 `config.json` 再填群号与关键词，`config.json` 不入库。细节见 [docs/TOOLS.md](https://github.com/MVennn/QQBotStack/blob/main/docs/TOOLS.md) §1.5、[docs/ARCHITECTURE.md](https://github.com/MVennn/QQBotStack/blob/main/docs/ARCHITECTURE.md) §1.2。

## 环境要求

| 项 | 要求 |
|---|---|
| 系统 | Windows 10 1809+ / Windows 11（x64）；需要管理员权限 |
| 磁盘 | 建议 ≥ 5 GB 可用（QQ + AstrBot 运行时 + 模型网关） |
| 运行时 | Python 3.10–3.13（Launcher 会自带隔离环境）、Node.js 20+、Go 1.21+（仅从源码构建网关时需要） |
| 网络 | 能访问 GitHub 与腾讯服务；局域网内另一台机器可用 SSH 连入做运维 |
| 账号 | 一个 QQ 号（建议小号）、一个 WorkBuddy 账号 |

## 使用

1. 克隆仓库到目标机（或先在本机准备再同步过去），目录约定见 [docs/ARCHITECTURE.md](https://github.com/MVennn/QQBotStack/blob/main/docs/ARCHITECTURE.md) §3。操作机上再把 `host/stack.conf.example` 复制成 `host/stack.conf`，填目标机地址、SSH 账号与网关 `api_key`（这个文件不入库）。
2. 跑部署脚本，它会把网关、协议端与机器人三块按顺序铺到 `runtime/` 下（zgate 与插件另行安装，见「仓库里有什么」）：

   ```powershell
   powershell -ExecutionPolicy Bypass -File tools\deploy-stack.ps1 -Stage all
   ```

   分阶段跑用 `-Stage gateway` / `-Stage napcat` / `-Stage astrbot`，可重复执行。
3. 需要人工的两步（脚本会打印提示）：NapCat 安装器是交互式控制台程序，要**到桌面会话**里跑、自己选安装目录（它不接受命令行参数，SSH 里跑不了）；QQ 首次登录要扫码。
4. 全部就位后跑验收：

   ```sh
   python tools/verify-stack.py --conf host/stack.conf
   ```

   它会依次验模型目录、网关对话、AstrBot 面板、NapCat 面板与 OneBot 端口（五项全自动，经 SSH 在目标机本地探测）；端到端问答要在 QQ 里发一条消息人工确认。失败项会指向 [docs/TROUBLESHOOTING.md](https://github.com/MVennn/QQBotStack/blob/main/docs/TROUBLESHOOTING.md) 的条目号。
5. 日常运维在**操作机**上跑同一支脚本：

   ```powershell
   powershell -ExecutionPolicy Bypass -File tools\start-stack.ps1 -Status   # 只看
   powershell -ExecutionPolicy Bypass -File tools\start-stack.ps1           # 缺什么起什么
   powershell -ExecutionPolicy Bypass -File tools\start-stack.ps1 -Restart astrbot
   ```

   它会经 SSH 驱动目标机的计划任务；第一次跑会顺手把 NapCat 的登录自启任务建好，
   之后不用再远程登录进 `runtime\napcat\onekey\NapCat.*.Shell` 双击 `napcat.bat`。
   参数与退出码见 [docs/TOOLS.md](https://github.com/MVennn/QQBotStack/blob/main/docs/TOOLS.md) §1.4。

   NapCat 连 AstrBot 的反连配置是 `onebot11_<QQ-ID>.json`：**WebSocket 客户端**指 `ws://127.0.0.1:6199/ws`，带 token，与 AstrBot 的 aiocqhttp 适配器一致。账号写在 `runtime\napcat\quicklogin.txt`（一行一个号），换号 = 改这个文件 + 重启 `QQBotStack-napcat` 任务；新号第一次登录前，先把旧号的 `onebot11_*.json` 复制改名，否则登录成功也收不到事件（见 [docs/ARCHITECTURE.md](https://github.com/MVennn/QQBotStack/blob/main/docs/ARCHITECTURE.md) §5）。

   操作机的 `tools\` 下还有两个日常入口：`tools\stack-menu.cmd`（双击数字菜单：状态 / 启动 / 重启 / 面板 / 扫码 / SSH）与 `tools\get-qr.ps1`（把二维码文件拉到本机打开，不用远程碰桌面）。操作机上的 `tools\sync-auths.ps1` 负责把 `auths/` 推到目标机并重启网关，计划任务 `QQBotStack-authsync` 每天 04:00 跑一次、当天成功过就跳过。

## 反馈

装不上、验收项对不上、想要新的运维能力，到 [Issues](https://github.com/MVennn/QQBotStack/issues) 反馈。请带上：

- 目标机的 Windows 版本（`winver`）
- 出问题的是哪一块（网关 / 协议端 / 机器人）
- 执行的完整命令与输出原文（贴前先抹掉 QQ 号、账号与 token）

踩过的坑见 [docs/PITFALLS.md](https://github.com/MVennn/QQBotStack/blob/main/docs/PITFALLS.md)，按现象查见 [docs/TROUBLESHOOTING.md](https://github.com/MVennn/QQBotStack/blob/main/docs/TROUBLESHOOTING.md)。想参与贡献见 [CONTRIBUTING](https://github.com/MVennn/QQBotStack/blob/main/CONTRIBUTING.md)，安全问题按 [SECURITY](https://github.com/MVennn/QQBotStack/blob/main/SECURITY.md) 报告。

## 免责声明

本项目仅供学习与个人使用。

- 部署脚本**会改目标机的系统状态**（安装 QQ 与 AstrBot、创建计划任务、写配置）。执行前请看清它每一步做什么。
- **QQ 协议端登录存在账号风险**。请使用小号，不要用主号；因使用本项目导致的账号异常由使用者自行承担。
- 本仓库**不保存任何凭据** —— WorkBuddy token、网关 API key、QQ 登录态都在 `runtime/` 下且不入库，位置见 [docs/SECRETS.md](https://github.com/MVennn/QQBotStack/blob/main/docs/SECRETS.md)。
- 所有结论都是在特定版本与网络环境下实测的，换环境后**必须重新验证**。
- 本项目与腾讯、AstrBot、NapCat 的维护者均无隶属或合作关系。

「QQ」「AstrBot」「NapCat」等名称与标识的权利均归其各自权利人所有。

## 开源鸣谢

本仓库建立在这些项目之上（详见 [NOTICE](https://github.com/MVennn/QQBotStack/blob/main/NOTICE)）：

| 项目 | 用途 | 许可 |
|---|---|---|
| [**AstrBot**](https://github.com/AstrBotDevs/AstrBot) | bot 框架：模型、插件、平台适配 | AGPL-3.0 |
| [**AstrBot Launcher**](https://github.com/AstrBotDevs/astrbot-launcher) | 隔离安装与多实例管理 | MIT |
| [**NapCatQQ**](https://github.com/NapNeko/NapCatQQ) | QQ 协议端，提供 OneBot 11 | 自定义（限再分发、非商业） |
| [**workbuddy2api**](https://github.com/linguo2625469/workbuddy2api-panel) | WorkBuddy 账号池 → OpenAI 兼容网关 | MIT |
| [**astrbot_plugin_parser**](https://github.com/Zhalslar/astrbot_plugin_parser) | 媒体解析：B站 / 抖音 / 快手 / 小红书链接与 QQ 小程序卡片 | MIT |
| [**astrbot_plugin_music**](https://github.com/Zhalslar/astrbot_plugin_music) | 点歌：搜源并发送 QQ 音乐卡片 | GPL-3.0 |
| [**FFmpeg**](https://ffmpeg.org/) | 可选：合并 B 站 DASH 音视频流、转码 | 视构建而定（LGPL / GPL） |

## 许可证

本仓库以 [MIT License](https://github.com/MVennn/QQBotStack/blob/main/LICENSE) 发布；上游组件的版权与许可证声明见 [NOTICE](https://github.com/MVennn/QQBotStack/blob/main/NOTICE)。
