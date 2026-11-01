# 排错手册

> **一句话**：排错手册（**正本**）：按「现象 → 排查步骤 → 原因 / 解法」组织，标题即检索词。

`tools/verify-stack.py` 失败时会打印对应的条目号（`T1`…`T8`）。

---

## T1 面板 / 接口连不上（连接被拒或超时）

**排查**（在目标机上）：

```powershell
Get-Process wb2api -ErrorAction SilentlyContinue | Select-Object Id,StartTime
& netstat -ano | Select-String ':7863'
& schtasks /query /tn QQBotStack-wb2api /fo LIST
Get-Content "<部署根>\runtime\workbuddy\wb2api.stderr.log" -Tail 20
```

**原因 / 解法**：按可能性排序 ——
① 进程没起（计划任务没运行，见 [PITFALLS.md](PITFALLS.md) P1）；
② `config.json` 的 `listen` 写错（比如写成了别的端口）；
③ 启动即崩溃（看 stderr，常见是 `config.json` 语法错误或端口被占）。
**注意**：`Get-NetTCPConnection` 在某些会话里会漏报，用 `netstat -ano` 更可靠。

## T2 `/v1/models` 返回 0 条

**排查**：

```powershell
Get-ChildItem "<部署根>\runtime\workbuddy\auths" | Measure-Object
```

**原因 / 解法**：账号目录为空。模型目录由已登录账号聚合而来 ——
先在 `http://127.0.0.1:7863/panel/` 登录一个 WorkBuddy 账号，再查一次。
这是预期行为，不是故障（[PITFALLS.md](PITFALLS.md) P2）。

## T3 模型有响应但回复是空的

**排查**：看响应的 `usage`：

```text
usage.completion_tokens_details.reasoning_tokens
```

**原因 / 解法**：如果 `reasoning_tokens` 几乎等于 `completion_tokens`，
说明 token 预算全被思考过程吃掉 —— `max_tokens` 给小了。
把 AstrBot 的 `max_tokens` 提到 2048 以上（[PITFALLS.md](PITFALLS.md) P4）。

## T4 AstrBot 连不上 NapCat

**排查**：

1. NapCat WebUI（6099）里看那条「WebSocket 客户端」的状态；
2. AstrBot 平台页看 aiocqhttp 适配器是否显示已连接；
3. 两端 token 是否完全一致（含大小写）。

**原因 / 解法**：最常见是**地址或角色配反**。正确形态是：
NapCat 作为 **WebSocket 客户端**连 `ws://127.0.0.1:6199/ws`；
AstrBot 作为**服务端**监听 `127.0.0.1:6199`。若配成 NapCat 当服务端，
AstrBot 永远等不到连接。其次是 token 不一致、端口被别的程序占了。

## T5 QQ 掉线 / 提示需要重新扫码

**排查**：NapCat 控制台窗口或 WebUI 的登录状态。

**原因 / 解法**：QQ 登录态会过期或被风控踢下线。到目标机前重新扫码即可。
**不要**为了「自动重登」去改 QQ 客户端的登录逻辑 —— 那既违反许可，也容易触发风控。
若频繁掉线，检查是否同一账号在别处登录（手机端顶号）。

## T6 重启机器后 bot 不回消息

**排查**：分别确认三块 ——

```powershell
& schtasks /query /tn QQBotStack-wb2api /fo LIST      # 网关（不依赖登录）
Get-Process QQ, NapCatWinBootMain -ErrorAction SilentlyContinue
Get-Process astrbot-launcher -ErrorAction SilentlyContinue
```

**原因 / 解法**：wb2api 是 SYSTEM 计划任务，重启后应该自动起来；
**NapCat 与 AstrBot 依赖桌面会话**，没人登录就不跑。
开「自动登录」，或改用服务化部署（[PITFALLS.md](PITFALLS.md) P8）。

## T7 部署脚本报「拒绝访问」/ `OS error 5` / 文件被占用

**原因 / 解法**：目标文件正被进程占用。先停对应组件再重跑：

```powershell
Get-Process wb2api -ErrorAction SilentlyContinue | Stop-Process -Force
& schtasks /end /tn QQBotStack-wb2api
```

杀完再执行 `deploy-stack.ps1`。另外确认当前是**管理员** PowerShell ——
装 QQ、建 SYSTEM 计划任务都需要提权。

## T8 `verify-stack.py` 报配置缺失

**现象**：退出码 2，提示读不到 `host/stack.conf`。

**原因 / 解法**：样例是 `host/stack.conf.example`，必须先复制成 `host/stack.conf` 再填值。
该文件被 `.gitignore` 排除，`git clone` 之后不存在是正常的。字段说明见
[SECRETS.md](SECRETS.md) §3。
