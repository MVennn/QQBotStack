<#
.SYNOPSIS
    Start (or inspect) the QQBotStack services on the bot host, over SSH.

.DESCRIPTION
    Operator-side helper. It does not run on the target: it drives the target's
    scheduled tasks, so nothing dies when the ssh session ends (PITFALLS P1).

    Three of the four components already start at boot through scheduled tasks:

        QQBotStack-wb2api    onstart / SYSTEM
        QQBotStack-zgate     onstart / SYSTEM
        QQBotStack-astrbot   onstart / SYSTEM   (run-astrbot.cmd)

    NapCat is the exception: it is a QQ NT process and needs a desktop session,
    so it cannot be a boot task. This script creates (once, idempotent) a task
    QQBotStack-napcat that runs as the interactive user, plus a small wrapper
    <runtime>\napcat\run-napcat.cmd. After that NapCat starts at logon on its
    own and can be kicked on demand with a single command.

    Idempotent: re-running only re-writes the wrapper and leaves a healthy
    stack alone. Keep this file pure ASCII (Windows PowerShell 5.1 decodes
    BOM-less files with the ANSI code page).

.PARAMETER Conf
    host/stack.conf path. Defaults to <repo>\host\stack.conf.

.PARAMETER Status
    Only report what is running. Starts nothing and changes nothing.

.PARAMETER Restart
    Restart a component instead of just starting what is down. One of:
    astrbot / gateway / zgate / all. NapCat is not restarted here on purpose:
    it may need a fresh QQ login, so stop it by hand if that is what you want.

.PARAMETER Wait
    Seconds to wait before the closing status snapshot. Default 8.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools\start-stack.ps1 -Status

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools\start-stack.ps1
#>
[CmdletBinding()]
param(
    [string]$Conf = '',
    [switch]$Status,
    [string]$Restart = '',
    [int]$Wait = 8
)

$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($Conf)) { $Conf = Join-Path $RepoRoot 'host\stack.conf' }

function Fail {
    param([string]$Message, [int]$Code = 1)
    Write-Host ('[x] ' + $Message) -ForegroundColor Red
    exit $Code
}

# --- target from host/stack.conf (host values never live in this file) ---
if (-not (Test-Path -LiteralPath $Conf)) {
    Fail ("conf not found: " + $Conf + "  (copy host\stack.conf.example to host\stack.conf)") 2
}
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
$port = $confMap['ssh_port']
if ([string]::IsNullOrWhiteSpace($port)) { $port = '22' }
if ([string]::IsNullOrWhiteSpace($hostName) -or [string]::IsNullOrWhiteSpace($userName)) {
    Fail 'host/user missing in stack.conf' 2
}
$Target = $userName + '@' + $hostName

$SshBase = @('-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', '-o', 'StrictHostKeyChecking=accept-new')
if ($port -ne '22') { $SshBase = $SshBase + @('-p', $port) }

function Invoke-Remote {
    param([string]$Script)
    $b64 = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($Script))
    $cmd = 'powershell -NoProfile -ExecutionPolicy Bypass -OutputFormat Text -EncodedCommand ' + $b64
    $sshArgs = $SshBase + @($Target, $cmd)
    # ssh writes its post-quantum notice to stderr; under 'Stop' that would become
    # a terminating NativeCommandError, so relax the preference for this call only.
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $raw = & ssh @sshArgs 2>&1
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $prevEap
    }
    $lines = @()
    foreach ($l in $raw) {
        $s = [string]$l
        # ssh prints its post-quantum notice on stderr; drop it so parsing stays simple
        if ($s.StartsWith('**')) { continue }
        # -EncodedCommand can leak CLIXML progress noise on stderr
        if ($s.StartsWith('#< CLIXML') -or $s.StartsWith('<Objs')) { continue }
        $lines += $s
    }
    return [pscustomobject]@{ Code = $code; Lines = $lines }
}

$StatusScript = @'
$ErrorActionPreference = 'SilentlyContinue'
$ProgressPreference = 'SilentlyContinue'
$names = @('QQBotStack-wb2api', 'QQBotStack-zgate', 'QQBotStack-astrbot', 'QQBotStack-napcat')
$tasks = [ordered]@{}
foreach ($n in $names) {
    $t = @(Get-ScheduledTask -TaskName $n -ErrorAction SilentlyContinue)[0]
    if ($t) { $tasks[$n] = [string]$t.State } else { $tasks[$n] = 'Absent' }
}
$explorer = @(Get-Process explorer -ErrorAction SilentlyContinue)[0]
$session = 'none'
if ($explorer) { $session = 'session ' + $explorer.SessionId }
$procs = [ordered]@{
    napcat  = [bool](@(Get-Process NapCatWinBootMain -ErrorAction SilentlyContinue)[0])
    astrbot = [bool](@(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -match 'main\.py' })[0])
    wb2api  = [bool](@(Get-Process wb2api -ErrorAction SilentlyContinue)[0])
    zgate   = [bool](@(Get-Process zgate -ErrorAction SilentlyContinue)[0])
}
$root = ''
$t = @(Get-ScheduledTask -TaskName 'QQBotStack-wb2api' -ErrorAction SilentlyContinue)[0]
if ($t) {
    $exe = [string](@($t.Actions)[0].Execute)
    if ($exe) { $root = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $exe)) }
}
$out = [ordered]@{ tasks = $tasks; procs = $procs; session = $session; root = $root }
Write-Output ('QBS_JSON:' + ($out | ConvertTo-Json -Depth 4 -Compress))
'@

function Get-RemoteStatus {
    $r = Invoke-Remote $StatusScript
    if ($r.Code -ne 0) {
        Fail ('ssh failed (exit ' + $r.Code + '). Output: ' + ($r.Lines -join ' | ')) 2
    }
    $json = $null
    foreach ($l in $r.Lines) {
        if ($l.StartsWith('QBS_JSON:')) { $json = $l.Substring(9); break }
    }
    if (-not $json) { Fail ('unexpected remote output: ' + ($r.Lines -join ' | ')) 2 }
    return ($json | ConvertFrom-Json)
}

function Write-Status {
    param($Snapshot)
    Write-Host ''
    Write-Host ('== QQBotStack on ' + $hostName + ' ==') -ForegroundColor Cyan
    $rows = @(
        @{ Name = 'gateway (wb2api)'; Task = 'QQBotStack-wb2api'; Proc = 'wb2api' },
        @{ Name = 'zgate';            Task = 'QQBotStack-zgate';  Proc = 'zgate' },
        @{ Name = 'bot (AstrBot)';    Task = 'QQBotStack-astrbot'; Proc = 'astrbot' },
        @{ Name = 'protocol (NapCat)'; Task = 'QQBotStack-napcat'; Proc = 'napcat' }
    )
    foreach ($row in $rows) {
        $state = [string]$Snapshot.tasks.($row.Task)
        $proc = [bool]$Snapshot.procs.($row.Proc)
        $line = '  {0,-18} task={1,-9} process={2}' -f $row.Name, $state, $(if ($proc) { 'yes' } else { 'no' })
        if ($proc) { Write-Host $line -ForegroundColor Green }
        elseif ($state -eq 'Running') { Write-Host $line -ForegroundColor Yellow }
        else { Write-Host $line -ForegroundColor DarkYellow }
    }
    Write-Host ('  desktop         ' + $Snapshot.session) -ForegroundColor DarkGray
    Write-Host ''
}

# --- 1) report only ---
$before = Get-RemoteStatus
if ($Status) {
    Write-Status $before
    exit 0
}

if ([string]::IsNullOrWhiteSpace([string]$before.root)) {
    Fail 'could not locate the deploy root on the target (is the gateway task registered?)'
}

# --- 1b) restart one component (the usual move after a plugin/config change) ---
if ($Restart) {
    $allowed = @('astrbot', 'gateway', 'zgate', 'all')
    if ($allowed -notcontains $Restart) {
        Fail ('-Restart accepts: ' + ($allowed -join ' / ')) 2
    }
    $sel = $Restart
    $RestartScript = @"
`$ErrorActionPreference = 'SilentlyContinue'
`$ProgressPreference = 'SilentlyContinue'
`$sel = '$sel'
`$targets = @()
if (`$sel -eq 'all' -or `$sel -eq 'gateway') { `$targets += 'QQBotStack-wb2api' }
if (`$sel -eq 'all' -or `$sel -eq 'zgate')   { `$targets += 'QQBotStack-zgate' }
if (`$sel -eq 'all' -or `$sel -eq 'astrbot') { `$targets += 'QQBotStack-astrbot' }
foreach (`$n in `$targets) { schtasks /end /tn `$n | Out-Null }
if (`$sel -eq 'all' -or `$sel -eq 'astrbot') {
    # /end only kills the cmd wrapper; the python tree has to go too, and the new
    # instance must not start before the old one released 6185 / 6199.
    for (`$i = 0; `$i -lt 15; `$i++) {
        `$p = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
            Where-Object { `$_.CommandLine -match 'runtime\\astrbot\\data' -and `$_.CommandLine -match 'main\.py' })
        if (`$p.Count -eq 0) { break }
        `$p | ForEach-Object { Stop-Process -Id `$_.ProcessId -Force }
        Start-Sleep -Seconds 2
    }
}
Start-Sleep -Seconds 2
foreach (`$n in `$targets) {
    schtasks /run /tn `$n | Out-Null
    Write-Output ('restarted: ' + `$n)
}
if (`$sel -eq 'all' -or `$sel -eq 'astrbot') {
    `$deadline = (Get-Date).AddSeconds(150)
    `$ready = `$false
    while ((Get-Date) -lt `$deadline) {
        try {
            `$r = Invoke-WebRequest -Uri 'http://127.0.0.1:6185/' -UseBasicParsing -TimeoutSec 3
            if (`$r.StatusCode -ge 200) { `$ready = `$true; break }
        } catch { }
        Start-Sleep -Seconds 3
    }
    if (`$ready) { Write-Output 'astrbot: webui is answering on 6185' }
    else { Write-Output 'astrbot: webui did not answer within 150s, check the log' }
}
"@
    Write-Host ('Restarting: ' + $Restart) -ForegroundColor Cyan
    $restartResult = Invoke-Remote $RestartScript
    foreach ($l in $restartResult.Lines) {
        if ($l -eq '') { continue }
        Write-Host ('  ' + $l) -ForegroundColor DarkGray
    }
    $afterRestart = Get-RemoteStatus
    Write-Status $afterRestart
    if ([bool]$afterRestart.procs.astrbot -and [bool]$afterRestart.procs.wb2api -and [bool]$afterRestart.procs.zgate) {
        Write-Host 'Restart done.' -ForegroundColor Green
        exit 0
    }
    Write-Host 'Restart issued, but a component is still down; see the table above.' -ForegroundColor Yellow
    exit 1
}

# --- 2) make sure the NapCat wrapper and its task exist (idempotent) ---
$WrapperText = @'
@echo off
rem Start NapCat inside the logged-on desktop session.
rem Called by scheduled task QQBotStack-napcat; safe to run when already up.
setlocal
set "SCRIPTDIR=%~dp0"
set "SHELLDIR="
for /d %%D in ("%SCRIPTDIR%onekey\NapCat.*.Shell") do set "SHELLDIR=%%~fD"

if not exist "%SCRIPTDIR%onekey" goto no_onekey
if not defined SHELLDIR goto no_shell
if not exist "%SHELLDIR%\NapCatWinBootMain.exe" goto no_boot

tasklist /fi "imagename eq NapCatWinBootMain.exe" 2>nul | find /i "NapCatWinBootMain.exe" >nul
if not errorlevel 1 (
    echo [run-napcat] already running, nothing to do
    if /i "%~1"=="/check" echo [run-napcat] shell=%SHELLDIR%
    exit /b 0
)

if /i "%~1"=="/check" (
    echo [run-napcat] not running, would start: %SHELLDIR%\NapCatWinBootMain.exe
    exit /b 0
)

cd /d "%SHELLDIR%"
echo [run-napcat] starting NapCat from %SHELLDIR%
"NapCatWinBootMain.exe" >> "%SCRIPTDIR%napcat.stdout.log" 2>> "%SCRIPTDIR%napcat.stderr.log"
exit /b %ERRORLEVEL%

:no_onekey
echo [run-napcat] missing folder: %SCRIPTDIR%onekey 1>&2
exit /b 2
:no_shell
echo [run-napcat] no NapCat.*.Shell under %SCRIPTDIR%onekey 1>&2
exit /b 3
:no_boot
echo [run-napcat] NapCatWinBootMain.exe missing under %SHELLDIR% 1>&2
exit /b 4
'@
$WrapperBytes = [Text.Encoding]::ASCII.GetBytes(($WrapperText -replace "`r?`n", "`r`n") + "`r`n")

# The wrapper is uploaded, not embedded in the remote command: an -EncodedCommand
# carrying it would exceed the Windows command line limit.
$LocalWrapper = Join-Path $env:TEMP ('qqb-run-napcat-' + [Guid]::NewGuid().ToString('N') + '.cmd')
[IO.File]::WriteAllBytes($LocalWrapper, $WrapperBytes)
$RemoteTemp = 'C:/Windows/Temp/qqb-run-napcat.cmd'
$scpArgs = @('-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=accept-new')
if ($port -ne '22') { $scpArgs = $scpArgs + @('-P', $port) }
$scpArgs = $scpArgs + @($LocalWrapper, ($Target + ':' + $RemoteTemp))
& scp @scpArgs | Out-Null
$scpCode = $LASTEXITCODE
Remove-Item -LiteralPath $LocalWrapper -Force -ErrorAction SilentlyContinue
if ($scpCode -ne 0) { Fail ('could not upload the NapCat wrapper (scp exit ' + $scpCode + ')') }

$EnsureScript = @"
`$ErrorActionPreference = 'Stop'
`$ProgressPreference = 'SilentlyContinue'
`$root = '$($before.root)'
`$napDir = Join-Path `$root 'runtime\napcat'
if (-not (Test-Path -LiteralPath `$napDir)) { Write-Output ('ERR:missing ' + `$napDir); exit 3 }
`$src = '$($RemoteTemp -replace '/', '\')'
if (-not (Test-Path -LiteralPath `$src)) { Write-Output 'ERR:upload missing'; exit 3 }
`$wrapper = Join-Path `$napDir 'run-napcat.cmd'
Copy-Item -LiteralPath `$src -Destination `$wrapper -Force
Remove-Item -LiteralPath `$src -Force
Write-Output ('wrapper: ' + `$wrapper)
`$me = [Security.Principal.WindowsIdentity]::GetCurrent().Name
`$t = @(Get-ScheduledTask -TaskName 'QQBotStack-napcat' -ErrorAction SilentlyContinue)[0]
if (-not `$t) {
    `$action = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument ('/c "' + `$wrapper + '"') -WorkingDirectory `$napDir
    `$trigger = New-ScheduledTaskTrigger -AtLogOn -User `$me
    `$trigger.Delay = 'PT20S'
    `$principal = New-ScheduledTaskPrincipal -UserId `$me -LogonType Interactive -RunLevel Highest
    `$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew
    Register-ScheduledTask -TaskName 'QQBotStack-napcat' -Action `$action -Trigger `$trigger -Principal `$principal -Settings `$settings | Out-Null
    Write-Output 'task: created QQBotStack-napcat (at logon +20s, interactive)'
} else {
    # QQ needs the desktop to be up; give Explorer a moment after logon.
    `$trig = @(`$t.Triggers)[0]
    if (`$trig -and -not `$trig.Delay) {
        `$trig.Delay = 'PT20S'
        Set-ScheduledTask -TaskName 'QQBotStack-napcat' -Trigger `$trig | Out-Null
        Write-Output 'task: QQBotStack-napcat exists, added 20s logon delay'
    } else {
        Write-Output 'task: QQBotStack-napcat already registered'
    }
}
"@
$ensure = Invoke-Remote $EnsureScript
foreach ($l in $ensure.Lines) {
    if ($l.StartsWith('ERR:')) { Fail $l 2 }
    Write-Host ('  ' + $l) -ForegroundColor DarkGray
}
if ($ensure.Code -ne 0) {
    Fail ('remote ensure failed (exit ' + $ensure.Code + '): ' + ($ensure.Lines -join ' | '))
}

# --- 3) start whatever is down ---
$StartScript = @'
$ErrorActionPreference = 'SilentlyContinue'
$ProgressPreference = 'SilentlyContinue'
foreach ($n in @('QQBotStack-wb2api', 'QQBotStack-zgate', 'QQBotStack-astrbot')) {
    $t = @(Get-ScheduledTask -TaskName $n -ErrorAction SilentlyContinue)[0]
    if ($t -and ([string]$t.State -ne 'Running')) {
        schtasks /run /tn $n | Out-Null
        Write-Output ('started: ' + $n)
    }
}
if (-not @(Get-Process NapCatWinBootMain -ErrorAction SilentlyContinue)[0]) {
    if (-not @(Get-Process explorer -ErrorAction SilentlyContinue)[0]) {
        Write-Output 'napcat: no desktop session on host, cannot start it (log in on the host first)'
    } else {
        schtasks /run /tn QQBotStack-napcat | Out-Null
        Write-Output 'started: QQBotStack-napcat'
    }
}
'@
$started = Invoke-Remote $StartScript
foreach ($l in $started.Lines) {
    if ($l -eq '') { continue }
    if ($l.StartsWith('napcat: no desktop')) { Write-Host ('  [!] ' + $l) -ForegroundColor Yellow }
    else { Write-Host ('  ' + $l) -ForegroundColor DarkGray }
}
if ($started.Lines.Count -eq 0) { Write-Host '  all services were already up' -ForegroundColor DarkGray }

# --- 4) closing snapshot ---
if ($Wait -gt 0) { Start-Sleep -Seconds $Wait }
$after = Get-RemoteStatus
Write-Status $after

$allUp = $true
foreach ($p in 'napcat', 'astrbot', 'wb2api', 'zgate') {
    if (-not [bool]$after.procs.$p) { $allUp = $false }
}
if ($allUp) {
    Write-Host 'All four components are up.' -ForegroundColor Green
    exit 0
}
Write-Host 'Something is still down; see the table above.' -ForegroundColor Yellow
exit 1
