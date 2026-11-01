<#
.SYNOPSIS
    Fetch the newest NapCat QR code from the bot host and open it locally,
    so the operator can scan it without touching the host desktop.

.DESCRIPTION
    Resolves the deploy root from the QQBotStack-astrbot task action (works for
    both the legacy direct-cmd action and the hidden-run.vbs wrapper), copies
    the newest qrcode.png to a fixed temp path on the host, pulls it over scp
    and opens it with the local image viewer. Pure ASCII by house rule.
#>
$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$conf = Join-Path $RepoRoot 'host\stack.conf'
if (-not (Test-Path -LiteralPath $conf)) {
    Write-Host ('[x] conf not found: ' + $conf) -ForegroundColor Red
    exit 2
}
$map = @{}
foreach ($line in Get-Content -LiteralPath $conf) {
    $t = $line.Trim()
    if ($t -eq '' -or $t.StartsWith('#')) { continue }
    $i = $t.IndexOf('=')
    if ($i -lt 1) { continue }
    $map[$t.Substring(0, $i).Trim().ToLower()] = $t.Substring($i + 1).Trim()
}
$h = $map['host']; $u = $map['user']; $port = $map['ssh_port']
if (-not $port) { $port = '22' }
if (-not $h -or -not $u) { Write-Host '[x] host/user missing in stack.conf' -ForegroundColor Red; exit 2 }
$Target = "$u@$h"
$SshBase = @('-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10')
$ScpBase = @('-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10')
if ($port -ne '22') { $SshBase += @('-p', $port); $ScpBase += @('-P', $port) }

function Invoke-Remote {
    param([string]$Script)
    $b64 = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($Script))
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $raw = & ssh @SshBase $Target ('powershell -NoProfile -ExecutionPolicy Bypass -OutputFormat Text -EncodedCommand ' + $b64) 2>&1
    } finally {
        $ErrorActionPreference = $prevEap
    }
    $lines = @()
    foreach ($l in $raw) {
        $s = [string]$l
        if ($s.StartsWith('**') -or $s.StartsWith('#< CLIXML') -or $s.StartsWith('<Objs')) { continue }
        $lines += $s
    }
    return $lines
}

# 1) deploy root from the astrbot task action
$probe = @'
$t = @(Get-ScheduledTask -TaskName 'QQBotStack-astrbot' -ErrorAction SilentlyContinue)[0]
$ex = [string](@($t.Actions)[0].Execute)
$ar = [string](@($t.Actions)[0].Arguments)
$p = ''
if ($ar -match '"([^"]+run-astrbot\.cmd)"') { $p = $Matches[1] }
elseif ($ex -like '*run-astrbot.cmd') { $p = $ex.Trim() }
if ($p) {
    $root = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $p))
    Write-Output ('ROOT:' + $root)
} else {
    Write-Output 'ROOT:'
}
'@
$root = ''
foreach ($l in (Invoke-Remote $probe)) {
    if ($l.StartsWith('ROOT:')) { $root = $l.Substring(5).Trim() }
}
if (-not $root) {
    Write-Host '[x] could not resolve deploy root on target' -ForegroundColor Red
    exit 2
}

# 2) newest qrcode.png -> fixed temp path on the host
$copyScript = @"
`$ErrorActionPreference = 'SilentlyContinue'
`$src = Get-ChildItem '$root\runtime\napcat\onekey\NapCat.*.Shell\versions\*\resources\app\napcat\cache\qrcode.png' |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not `$src) { Write-Output 'QR:none'; exit 0 }
Copy-Item `$src.FullName 'C:\Windows\Temp\qbs-qr.png' -Force
Write-Output ('QR:' + `$src.LastWriteTime.ToString('HH:mm:ss'))
"@
$qrLine = $null
foreach ($l in (Invoke-Remote $copyScript)) {
    if ($l.StartsWith('QR:')) { $qrLine = $l.Substring(3) }
}
if (-not $qrLine -or $qrLine -eq 'none') {
    Write-Host '[!] no QR code on the host right now - QQ is not waiting for a scan (maybe already logged in)' -ForegroundColor Yellow
    exit 1
}
Write-Host ('  QR generated at ' + $qrLine + ' on the host, pulling it over...')

# 3) pull it back and open locally
$local = Join-Path $env:TEMP 'qbs-qr.png'
$prevEap = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
try {
    & scp @ScpBase -q ($Target + ':C:/Windows/Temp/qbs-qr.png') $local | Out-Null
    $code = $LASTEXITCODE
} finally {
    $ErrorActionPreference = $prevEap
}
if ($code -ne 0) {
    Write-Host ('[x] scp failed (exit ' + $code + ')') -ForegroundColor Red
    exit 2
}
Invoke-Item -LiteralPath $local
Write-Host '[ok] QR opened locally - scan it with the phone of the QQ account you want to log in.' -ForegroundColor Green
