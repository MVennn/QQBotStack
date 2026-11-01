<#
.SYNOPSIS
    Push WorkBuddy auth files to the bot host, at most once per day.

.DESCRIPTION
    The operator machine is the account owner: it is the only side that runs the
    gateway keepalive, so it is the only side whose auth files are authoritative.
    The bot host keeps a copy. This script copies that copy once per day and then
    restarts the gateway there so the new accounts are loaded.

    Idempotent per day: the date is written to a state file after a successful
    copy, and every later run on the same day exits immediately.

    Keep this file pure ASCII (Windows PowerShell 5.1 decodes BOM-less files with
    the ANSI code page).

.PARAMETER Conf
    host/stack.conf path. Defaults to <repo>\host\stack.conf.

.PARAMETER Source
    Local auths directory. Defaults to the ZcodeAIModels upstream path.

.PARAMETER StateFile
    Where the last successful sync date is recorded.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools\sync-auths.ps1
#>
[CmdletBinding()]
param(
    [string]$Conf = '',
    [string]$Source = '',
    [string]$StateFile = ''
)

$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($Conf)) { $Conf = Join-Path $RepoRoot 'host\stack.conf' }
if ([string]::IsNullOrWhiteSpace($Source)) { $Source = 'F:\Project\ZcodeAIModels\gateways\upstream\workbuddy\auths' }
if ([string]::IsNullOrWhiteSpace($StateFile)) {
    $StateFile = Join-Path $env:LOCALAPPDATA 'QQBotStack\authsync.state'
}

function Write-Log {
    param([string]$Message)
    $dir = Split-Path -Parent $StateFile
    if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    $line = (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + '  ' + $Message
    Add-Content -LiteralPath (Join-Path $dir 'authsync.log') -Value $line -Encoding ASCII
}

$today = Get-Date -Format 'yyyy-MM-dd'
if (Test-Path -LiteralPath $StateFile) {
    $last = (Get-Content -LiteralPath $StateFile -Raw).Trim()
    if ($last -eq $today) { Write-Log 'skip: already synced today'; exit 0 }
}

if (-not (Test-Path -LiteralPath $Conf)) { Write-Log "fail: conf not found: $Conf"; exit 2 }
$confMap = @{}
foreach ($line in Get-Content -LiteralPath $Conf) {
    $t = $line.Trim()
    if ($t -eq '' -or $t.StartsWith('#')) { continue }
    $i = $t.IndexOf('=')
    if ($i -lt 1) { continue }
    $confMap[$t.Substring(0, $i).Trim().ToLower()] = $t.Substring($i + 1).Trim()
}
$hostName = $confMap['host']
$userName = $confMap['user']
if ([string]::IsNullOrWhiteSpace($hostName) -or [string]::IsNullOrWhiteSpace($userName)) {
    Write-Log 'fail: host/user missing in stack.conf'
    exit 2
}
$remoteDir = 'F:/Tools/AITool/QQBotStack/runtime/workbuddy/auths'
$target = $userName + '@' + $hostName + ':' + $remoteDir + '/'

if (-not (Test-Path -LiteralPath $Source)) { Write-Log "fail: source not found: $Source"; exit 1 }
$files = @(Get-ChildItem -LiteralPath $Source -Filter '*.json' -File)
if ($files.Count -eq 0) { Write-Log 'fail: no auth files to push'; exit 1 }

$scpArgs = @('-q', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=accept-new')
$scpArgs += $files.FullName
$scpArgs += $target
& scp @scpArgs
if ($LASTEXITCODE -ne 0) {
    Write-Log ("fail: scp exit " + $LASTEXITCODE)
    exit 1
}
Write-Log ("copied " + $files.Count + " auth file(s)")

$sshOpts = @('-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15')
& ssh @sshOpts ($userName + '@' + $hostName) 'schtasks /end /tn QQBotStack-wb2api'
Start-Sleep -Seconds 2
& ssh @sshOpts ($userName + '@' + $hostName) 'schtasks /run /tn QQBotStack-wb2api'
if ($LASTEXITCODE -ne 0) {
    Write-Log ("warn: gateway restart exit " + $LASTEXITCODE + " (files already copied)")
}

$dir = Split-Path -Parent $StateFile
if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
Set-Content -LiteralPath $StateFile -Value $today -Encoding ASCII
Write-Log 'done: marked synced for today'
exit 0
