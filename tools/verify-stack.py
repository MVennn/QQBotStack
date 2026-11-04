#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验收 QQBotStack：模型目录 / 网关对话 / AstrBot 面板 / NapCat 面板 / OneBot 端口。

用法：
    python tools/verify-stack.py --conf host/stack.conf
    python tools/verify-stack.py --host <HOST-IP> --user <HOST-USER> --key <API-KEY>

退出码：0 全通过 / 1 有项目失败 / 2 配置缺失或不可读。

为什么通过 SSH 跑：三个服务全部只绑 127.0.0.1，操作机上直接访问不到。
这里用 `ssh ... powershell -EncodedCommand` 在目标机本地发起探测，
既不用改绑定，也不用开隧道。
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

CONF_DEFAULT = os.path.join("host", "stack.conf")
DEFAULTS = {
    "ssh_port": "22",
    "gateway_port": "7863",
    "astrbot_port": "6185",
    "napcat_port": "6099",
    "onebot_port": "6199",
}


class ConfError(Exception):
    pass


def read_conf(path: str) -> dict:
    if not os.path.isfile(path):
        raise ConfError(
            "找不到 %s —— 先复制样例：cp host/stack.conf.example host/stack.conf" % path
        )
    conf = {}
    with open(path, encoding="utf-8", errors="replace") as fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                raise ConfError("%s:%d 不是 key=value 形式：%s" % (path, lineno, line))
            key, _, value = line.partition("=")
            conf[key.strip().lower()] = value.strip()
    return conf


def is_placeholder(value: str) -> bool:
    return not value or (value.startswith("<") and value.endswith(">"))


def remote_ps(args, script: str) -> tuple:
    """在目标机上跑一段 PowerShell，返回 (ok, stdout, stderr)。"""
    # Windows PowerShell writes redirected output in the OEM code page (GBK on a
    # Chinese system). Force UTF-8 or every non-ASCII error message arrives as
    # mojibake. See docs/PITFALLS.md P10.
    preamble = (
        "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8\n"
        "$OutputEncoding = [System.Text.Encoding]::UTF8\n"
    )
    encoded = base64.b64encode((preamble + script).encode("utf-16-le")).decode("ascii")
    cmd = [
        "ssh",
        "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "ConnectTimeout=10",
        "-p", str(args.ssh_port),
        "%s@%s" % (args.user, args.host),
        "powershell", "-NoProfile", "-EncodedCommand", encoded,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=90,
                              encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return False, "", "timeout"
    except FileNotFoundError:
        return False, "", "找不到 ssh 命令"
    if proc.returncode != 0:
        return False, proc.stdout, proc.stderr
    return True, proc.stdout, proc.stderr


def parse_json_result(stdout: str) -> dict:
    """从 ssh 输出里挑出最后一行 JSON（PowerShell 可能夹带 CLIXML 噪声）。"""
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            return json.loads(line)
        except ValueError:
            continue
    return {"ok": False, "err": "无法解析目标机返回：%s" % stdout.strip()[:200]}


def ps_models(port: int, key: str) -> str:
    return r'''
try {
  $r = Invoke-RestMethod -Uri 'http://127.0.0.1:%d/v1/models' -Headers @{ Authorization = 'Bearer %s' } -TimeoutSec 25
  $ids = @($r.data | ForEach-Object { $_.id })
  $hy3 = @($ids | Where-Object { $_ -match 'hy3' })
  @{ ok = $true; count = $ids.Count; hy3 = ($hy3 -join ',') } | ConvertTo-Json -Compress
} catch {
  @{ ok = $false; err = $_.Exception.Message } | ConvertTo-Json -Compress
}
''' % (port, key)


def ps_chat(port: int, key: str, model: str) -> str:
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
        "max_tokens": 256,
        "stream": False,
    }, ensure_ascii=True)
    return r'''
try {
  $body = '%s'
  $r = Invoke-RestMethod -Uri 'http://127.0.0.1:%d/v1/chat/completions' -Method Post `
        -Headers @{ Authorization = 'Bearer %s' } -ContentType 'application/json' `
        -Body $body -TimeoutSec 90
  $msg = $r.choices[0].message
  $reasoning = 0
  if ($r.usage -and $r.usage.completion_tokens_details) { $reasoning = $r.usage.completion_tokens_details.reasoning_tokens }
  @{ ok = $true; content = [string]$msg.content; model = [string]$r.model; reasoning_tokens = $reasoning } | ConvertTo-Json -Compress
} catch {
  @{ ok = $false; err = $_.Exception.Message } | ConvertTo-Json -Compress
}
''' % (body.replace("'", "''"), port, key)


def ps_http(port: int, path: str) -> str:
    return r'''
try {
  $r = Invoke-WebRequest -Uri 'http://127.0.0.1:%d%s' -UseBasicParsing -TimeoutSec 15
  @{ ok = $true; status = [int]$r.StatusCode } | ConvertTo-Json -Compress
} catch {
  $code = 0
  if ($_.Exception.Response) { $code = [int]$_.Exception.Response.StatusCode }
  @{ ok = $false; status = $code; err = $_.Exception.Message } | ConvertTo-Json -Compress
}
''' % (port, path)


def ps_port(port: int) -> str:
    return r'''
# OneBot 的监听 socket 偶尔会短暂处于 FIN_WAIT/CLOSED，但已有 websocket 仍可用；
# 只要看到 LISTENING 或 ESTABLISHED 就算通，并且失败后隔 2 秒再试一次。
for ($i = 0; $i -lt 2; $i++) {
  $hit = (& netstat.exe -ano | Select-String ':%d\s' | Select-String 'LISTENING|ESTABLISHED')
  if ($hit) { @{ ok = $true } | ConvertTo-Json -Compress; exit 0 }
  Start-Sleep -Seconds 2
}
@{ ok = $false; err = 'port %d is not listening' } | ConvertTo-Json -Compress
''' % (port, port)


def main() -> int:
    parser = argparse.ArgumentParser(description="验收 QQBotStack")
    parser.add_argument("--conf", default=CONF_DEFAULT, help="配置路径（默认 host/stack.conf）")
    parser.add_argument("--host", help="覆盖 host")
    parser.add_argument("--user", help="覆盖 user")
    parser.add_argument("--ssh-port", help="覆盖 ssh_port")
    parser.add_argument("--key", help="覆盖 api_key")
    parser.add_argument("--model", default="hy3", help="对话测试用的模型（默认 hy3）")
    args = parser.parse_args()

    need_conf = not (args.host and args.user and args.key)

    def to_port(key: str, raw) -> int:
        """端口配置必须是 1-65535 的纯数字，坏值给一行人话，不甩 traceback。"""
        text = str(raw or "").strip()
        try:
            port = int(text)
        except ValueError:
            raise ConfError(
                "%s 里的 %s 不是数字：%s —— 端口必须是纯数字（如 7863）"
                % (args.conf, key, text or "(空)")
            )
        if not 1 <= port <= 65535:
            raise ConfError(
                "%s 里的 %s 超出 1-65535：%d" % (args.conf, key, port)
            )
        return port

    try:
        conf = read_conf(args.conf) if (need_conf or os.path.isfile(args.conf)) else {}
        args.host = args.host or conf.get("host", "")
        args.user = args.user or conf.get("user", "")
        args.key = args.key or conf.get("api_key", "")
        args.ssh_port = to_port(
            "ssh_port", args.ssh_port or conf.get("ssh_port", DEFAULTS["ssh_port"])
        )
        gw_port = to_port("gateway_port", conf.get("gateway_port") or DEFAULTS["gateway_port"])
        ab_port = to_port("astrbot_port", conf.get("astrbot_port") or DEFAULTS["astrbot_port"])
        nc_port = to_port("napcat_port", conf.get("napcat_port") or DEFAULTS["napcat_port"])
        ob_port = to_port("onebot_port", conf.get("onebot_port") or DEFAULTS["onebot_port"])
    except ConfError as exc:
        print("[FAIL] %s" % exc, file=sys.stderr)
        print("  条目：T8", file=sys.stderr)
        return 2

    missing = [name for name, val in
               (("host", args.host), ("user", args.user), ("api_key", args.key))
               if is_placeholder(val)]
    if missing:
        print("[FAIL] 以下字段仍是占位符或缺失：%s" % "、".join(missing), file=sys.stderr)
        print("  在 %s 里填真值，或用命令行覆盖。条目：T8" % args.conf, file=sys.stderr)
        return 2

    print("目标：%s@%s  网关 %d / AstrBot %d / NapCat %d / OneBot %d"
          % (args.user, args.host, gw_port, ab_port, nc_port, ob_port))
    print("-" * 64)

    failed = []

    def run(label, script, hint, judge=None):
        ok, out, err = remote_ps(args, script)
        if not ok:
            print("[FAIL] %s：无法在目标机执行（%s）" % (label, (err or out).strip()[:160]))
            print("  条目：T1")
            failed.append(label)
            return None
        result = parse_json_result(out)
        if judge is not None:
            good, detail = judge(result)
        else:
            good = bool(result.get("ok"))
            detail = result.get("err") or "ok"
        if good:
            print("[OK] %s：%s" % (label, detail))
        else:
            print("[FAIL] %s：%s" % (label, detail))
            print("  条目：%s" % hint)
            failed.append(label)
        return result

    run("模型目录", ps_models(gw_port, args.key), "T2",
        lambda r: (bool(r.get("ok")) and int(r.get("count") or 0) > 0,
                   ("%s 个模型，hy3: %s" % (r.get("count"), r.get("hy3")))
                   if r.get("ok") else r.get("err")))

    def judge_chat(r):
        if not r.get("ok"):
            return False, r.get("err")
        content = (r.get("content") or "").strip()
        if content:
            return True, "模型 %s 返回 %r" % (r.get("model"), content[:40])
        return False, ("有响应但正文为空（reasoning_tokens=%s）—— max_tokens 给小了"
                       % r.get("reasoning_tokens"))

    run("网关对话", ps_chat(gw_port, args.key, args.model), "T3", judge_chat)

    run("AstrBot 面板", ps_http(ab_port, "/"), "T1",
        lambda r: (r.get("status") in (200, 302, 401), "HTTP %s" % r.get("status")))

    run("NapCat 面板", ps_http(nc_port, "/"), "T1",
        lambda r: (r.get("status") in (200, 302, 401), "HTTP %s" % r.get("status")))

    run("OneBot 端口", ps_port(ob_port), "T4",
        lambda r: (bool(r.get("ok")), "监听中" if r.get("ok") else r.get("err")))

    print("-" * 64)
    if failed:
        print("[FAIL] %d 项失败：%s" % (len(failed), "、".join(failed)))
        print("  端到端问答（QQ 发消息）无法自动验证，请人工确认。")
        return 1
    print("[OK] 五项全部通过。")
    print("  还剩一步人工验收：在 QQ 里给 bot 发一条消息，确认能收到回复。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
