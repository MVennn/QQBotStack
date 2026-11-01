# 参与贡献

> **一句话**：怎么把栈跑起来、改脚本守什么规矩、提交前跑什么。

## 跑起来

```sh
# 主机配置：复制样例后按自己的环境改（该文件不入库）
cp host/stack.conf.example host/stack.conf

# 分阶段部署（可重复执行）
powershell -ExecutionPolicy Bypass -File tools\deploy-stack.ps1 -Stage gateway
powershell -ExecutionPolicy Bypass -File tools\deploy-stack.ps1 -Stage napcat
powershell -ExecutionPolicy Bypass -File tools\deploy-stack.ps1 -Stage astrbot

# 验收
python tools/verify-stack.py --conf host/stack.conf
```

> `tools/deploy-stack.ps1` **会改目标机状态**（装 QQ、装 AstrBot、建计划任务）。
> 执行前先读 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) 的「会改什么」一节。

## 硬规矩

### 1. 主机与账号相关的值一律外置（脱敏红线）

**不许**把下面这些写进源码、文档、示例、日志、提交信息：

| 类别 | 例子 | 该放哪 |
|---|---|---|
| 主机地址 | 局域网 IP、DDNS 名 | `host/stack.conf` |
| 主机标识 | 计算机名、MAC、SSID | 哪都不该放 |
| QQ 号 | bot 号、管理员号、群号 | `host/stack.conf` |
| WorkBuddy 账号 | 邮箱、uid、昵称 | `runtime/workbuddy/auths/` |
| 凭据 | accessToken、api_key、OneBot token | 运行时目录，不入库 |
| 本机绝对路径 | 你的家目录 | 相对路径或 `~` 推导 |

提交前跑 `python tools/check-secrets.py --all` —— 这是红线的可执行版本。

### 2. 不分发上游

AstrBot 是 AGPL-3.0、NapCat 是「限再分发 + 非商业」自定义许可。
**不要把它们的源码、补丁或二进制放进本仓**。部署脚本只从官方 Release 下载，
校验版本号后落到 `runtime/`（`.gitignore` 已排除）。

### 3. 格式

- `tools/*.ps1` **必须纯 ASCII**（注释用英文）—— PowerShell 5.1 会按 ANSI 解码无 BOM 文件。
- 计划任务用的 `.cmd`：纯 ASCII、无多行 if、CRLF 落盘。
- Python 只用标准库（`tools/make_social_preview.py` 例外，需要 numpy + Pillow）。
- 所有文本文件 LF 换行（`.gitattributes` 已锁）。

## 文档

规则见 [docs/DOC-RULES.md](docs/DOC-RULES.md)（单一正本、每篇开头一句话引言块、
索引唯一、孤儿零容忍）。改完跑：

```bash
python tools/check-docs.py
```

## 提交前自检

```bash
# Python 语法
python -c "import ast,glob; [ast.parse(open(f,encoding='utf-8').read(), f) for f in glob.glob('**/*.py', recursive=True)]"

# PowerShell 纯 ASCII + 语法
python -c "import glob,sys; bad=[p for p in glob.glob('tools/*.ps1') if any(b>127 for b in open(p,'rb').read())]; sys.exit(1 if bad else 0)"
pwsh -NoProfile -Command '$e=$null; [System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path "tools/deploy-stack.ps1").Path,[ref]$null,[ref]$e)|Out-Null; if($e.Count){$e; exit 1}'

# 文档 + 脱敏
python tools/check-docs.py
python tools/check-secrets.py --all
```

CI（`.github/workflows/ci.yml`）跑的就是这几样。

## 提交信息

Conventional Commits：`feat:` `fix:` `docs:` `chore:` `refactor:` `test:` `perf:`。
多个改动**按对象拆行**（一行一个对象）。
