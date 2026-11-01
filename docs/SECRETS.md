# 凭据与账号配置

> **一句话**：凭据与账号的位置索引（**正本**，只写位置不写值）：
> 本仓存什么、不存什么、真值在哪、怎么扫。

---

## 1. 本仓存什么

| 内容 | 存不存 | 位置 |
|---|---|---|
| 部署脚本、验证脚本、文档 | ✅ 存 | 仓库内，**只有占位符** |
| WorkBuddy accessToken | ❌ 不存 | `runtime/workbuddy/auths/*.json` |
| 网关 api_key | ❌ 不存 | `runtime/workbuddy/config.json` |
| OneBot token | ❌ 不存 | AstrBot 与 NapCat 各自的配置 |
| QQ 号 / 群号 | ❌ 不存 | `host/stack.conf`（不入库） |
| QQ 登录态 | ❌ 不存 | QQ NT 自身 |
| 真机实测记录、面板截图 | ❌ 不存 | `.work/`（不入库） |

## 2. 真值在哪

| 值 | 真值位置 |
|---|---|
| 目标机地址与登录用户 | `host/stack.conf`（本地，`.gitignore` 已排除） |
| 网关 api_key | `runtime/workbuddy/config.json` → `api_key` |
| WorkBuddy 账号凭据 | `runtime/workbuddy/auths/*.json` |
| 网关面板 | `http://127.0.0.1:7863/panel/`（运维走 SSH 转发） |
| AstrBot 面板 | `http://127.0.0.1:6185`（同上） |
| NapCat 面板 | `http://127.0.0.1:6099`（同上） |

> `runtime/` 整个目录被 `.gitignore` 排除。**不要在仓库里放它的副本，也不要贴进 Issue。**

## 3. `host/stack.conf` 字段

```ini
host=<HOST-IP>          # 目标机地址
user=<HOST-USER>        # 登录用户名
ssh_port=22             # 可选，默认 22
gateway_port=7863       # 可选，默认 7863
astrbot_port=6185       # 可选，默认 6185
napcat_port=6099        # 可选，默认 6099
onebot_port=6199        # 可选，默认 6199
api_key=<REDACTED-TOKEN>  # 网关 api_key；也可用 --key 传
qq=<QQ-ID>              # 可选，bot 的 QQ 号（只用于自检展示，不参与连接）
```

## 4. 占位符口径

| 占位符 | 代替什么 |
|---|---|
| `<HOST-IP>` | 目标机地址 |
| `<HOST-USER>` | 登录用户名 |
| `<QQ-ID>` / `<GROUP-ID>` | QQ 号 / 群号 |
| `<WB-ACCOUNT>` | WorkBuddy 账号邮箱或 uid |
| `<REDACTED-TOKEN>` | accessToken / api_key / OneBot token |
| `<REDACTED-MAC>` | MAC 地址 |
| `<REPLACE-...>` | 需要使用者自己填的值 |

## 5. 推送前脱敏

`tools/check-secrets.py` 是本节的可执行版本，扫描三类命中：

1. **凭据形态**：私钥块、GitHub token、云厂商 AK、各类 `sk-` key、订阅链接里的 token
2. **本机绝对路径**：`C:\Users\<真实用户名>`、`/home/<真实用户名>`
3. **真实邮箱**：`@qq.com` / `@163.com` / `@gmail.com` 等（GitHub noreply 不在其中）

放行口径：命中片段本身含 `REDACTED` / `REPLACE-` / `<...>` 占位符，或路径呈截断形式。
**同一行里并排写下的完整真值仍会被报出来** —— 占位符只豁免它自己那一段。

```sh
python tools/check-secrets.py          # 只扫已跟踪文件（需要 git）
python tools/check-secrets.py --all    # 扫工作树（跳过 .git/.work/runtime）
```
