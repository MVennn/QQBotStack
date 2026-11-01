<#
.SYNOPSIS
    Deploy QQBotStack: model gateway, QQ protocol side, bot framework.

.DESCRIPTION
    Idempotent, staged deployment.

      gateway  - place wb2api + config, register and start a scheduled task.
                 Fully automatic.
      napcat   - download and unpack the NapCat one-key package. Running the
                 installer and scanning the QQ login QR still need a human at
                 the machine.
      astrbot  - download, silently install the AstrBot Launcher and point its
                 data directory into the deployment root. Creating and starting
                 an instance still needs the GUI.

    Keep this file pure ASCII: Windows PowerShell 5.1 decodes a BOM-less file
    using the ANSI code page, so non-ASCII characters break parsing.

.PARAMETER Stage
    gateway | napcat | astrbot | all (default all).

.PARAMETER Root
    Deployment root. Defaults to the parent directory of this script.

.PARAMETER GatewayExe
    Path to a locally built wb2api.exe. Only needed when the binary is not
    already present under runtime\workbuddy.

.PARAMETER NapCatVersion
    NapCatQQ release tag to download.

.PARAMETER LauncherVersion
    AstrBot Launcher release tag to download.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools\deploy-stack.ps1 -Stage gateway
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [ValidateSet('gateway', 'napcat', 'astrbot', 'all')]
    [string]$Stage = 'all',

    [string]$Root = '',

    [string]$GatewayExe = '',

    [string]$NapCatVersion = '4.18.41',

    [string]$LauncherVersion = '0.3.13'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Write-Step { param([string]$m) Write-Host "[*] $m" -ForegroundColor Cyan }
function Write-Ok   { param([string]$m) Write-Host "[+] $m" -ForegroundColor Green }
function Write-Skip { param([string]$m) Write-Host "[=] $m" -ForegroundColor DarkGray }
function Write-Warn { param([string]$m) Write-Host "[!] $m" -ForegroundColor Yellow }
function Fail       { param([string]$m) Write-Host "[x] $m" -ForegroundColor Red; exit 1 }

if ([string]::IsNullOrWhiteSpace($Root)) {
    $Root = Split-Path -Parent $PSScriptRoot
}
$Root = [IO.Path]::GetFullPath($Root)
$Runtime = Join-Path $Root 'runtime'

if (-not (Test-Path -LiteralPath $Runtime)) {
    New-Item -ItemType Directory -Path $Runtime -Force | Out-Null
}
Write-Ok "Root: $Root"

[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

# ---------------------------------------------------------------------------
function Invoke-GatewayStage {
    Write-Step 'Stage: gateway'
    $wd = Join-Path $Runtime 'workbuddy'
    foreach ($d in @($wd, (Join-Path $wd 'auths'), (Join-Path $wd 'data'))) {
        if (-not (Test-Path -LiteralPath $d)) {
            New-Item -ItemType Directory -Path $d -Force | Out-Null
        }
    }

    $exe = Join-Path $wd 'wb2api.exe'
    if (Test-Path -LiteralPath $exe) {
        Write-Skip "Binary already present: $exe"
    }
    elseif (-not [string]::IsNullOrWhiteSpace($GatewayExe)) {
        if (-not (Test-Path -LiteralPath $GatewayExe)) { Fail "GatewayExe not found: $GatewayExe" }
        if ($PSCmdlet.ShouldProcess($exe, 'Copy gateway binary')) {
            Copy-Item -LiteralPath $GatewayExe -Destination $exe -Force
            Write-Ok "Copied binary to $exe"
        }
    }
    else {
        Fail ('wb2api.exe is missing. Build it from the upstream source ' +
              '(go build -o wb2api.exe ./cmd/server) and pass -GatewayExe <path>.')
    }

    $cfgPath = Join-Path $wd 'config.json'
    if (Test-Path -LiteralPath $cfgPath) {
        Write-Skip "Config kept as is: $cfgPath"
    }
    else {
        if ($PSCmdlet.ShouldProcess($cfgPath, 'Generate config.json')) {
            # api_key must not come from Get-Random (predictable PRNG); use the
            # crypto RNG. 24 bytes -> the same 48 hex chars as before.
            $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
            $rngBytes = New-Object byte[] 24
            $rng.GetBytes($rngBytes)
            $rng.Dispose()
            $key = ([System.BitConverter]::ToString($rngBytes)).Replace('-', '').ToLowerInvariant()
            $cfg = [ordered]@{
                listen     = '127.0.0.1:7863'
                api_key    = $key
                auth_dir   = './auths'
                state_file = './data/state.json'
                server     = [ordered]@{ read_timeout = '300s' }
                logging    = [ordered]@{
                    request_archive_enabled = $true
                    request_retention_days  = 7
                    request_archive_max_mb  = 100
                }
            }
            $json = $cfg | ConvertTo-Json -Depth 6
            [IO.File]::WriteAllText($cfgPath, $json, [Text.Encoding]::ASCII)
            Write-Ok "Generated config.json with a fresh api_key"
            Write-Warn "Store the api_key from config.json into host/stack.conf"
        }
    }

    $cmdPath = Join-Path $wd 'run-wb2api.cmd'
    if ($PSCmdlet.ShouldProcess($cmdPath, 'Write launcher cmd')) {
        $lines = @(
            '@echo off',
            ('cd /d "' + $wd + '"'),
            'set HTTP_PROXY=',
            'set HTTPS_PROXY=',
            'set http_proxy=',
            'set https_proxy=',
            'set NO_PROXY=*',
            ('"' + (Join-Path $wd 'wb2api.exe') + '" -config config.json >> wb2api.stdout.log 2>> wb2api.stderr.log')
        )
        [IO.File]::WriteAllText($cmdPath, (($lines -join "`r`n") + "`r`n"), [Text.Encoding]::ASCII)
        Write-Ok "Wrote $cmdPath (ASCII, CRLF)"
    }

    $taskName = 'QQBotStack-wb2api'
    if ($PSCmdlet.ShouldProcess($taskName, 'Register and start scheduled task')) {
        # Quote /tr: an unquoted path with spaces is split by schtasks into
        # command + argument, and the task then fails to start.
        $null = & schtasks.exe /create /tn $taskName /tr ('"' + $cmdPath + '"') /sc onstart /ru SYSTEM /rl HIGHEST /f 2>&1
        if ($LASTEXITCODE -ne 0) { Fail "schtasks /create failed with exit code $LASTEXITCODE" }
        $null = & schtasks.exe /end /tn $taskName 2>&1
        $null = & schtasks.exe /run /tn $taskName 2>&1
        Write-Ok "Scheduled task $taskName registered and started"
    }

    Start-Sleep -Seconds 6
    $proc = Get-Process wb2api -ErrorAction SilentlyContinue
    if ($null -eq $proc) {
        Write-Warn 'wb2api is not running yet. Check wb2api.stderr.log (docs/TROUBLESHOOTING.md T1).'
    }
    else {
        Write-Ok ("wb2api running, pid " + $proc.Id)
    }

    try {
        $r = Invoke-WebRequest -Uri 'http://127.0.0.1:7863/panel/' -UseBasicParsing -TimeoutSec 15
        Write-Ok ("Panel responds: HTTP " + $r.StatusCode)
    }
    catch {
        Write-Warn ('Panel not reachable yet: ' + $_.Exception.Message)
    }
    Write-Warn 'Manual: open http://127.0.0.1:7863/panel/ and log in a WorkBuddy account.'
}

# ---------------------------------------------------------------------------
function Invoke-NapCatStage {
    Write-Step 'Stage: napcat'
    $nd = Join-Path $Runtime 'napcat'
    if (-not (Test-Path -LiteralPath $nd)) { New-Item -ItemType Directory -Path $nd -Force | Out-Null }

    $zip = Join-Path $nd 'NapCat.Shell.Windows.OneKey.zip'
    if (Test-Path -LiteralPath $zip) {
        Write-Skip "Package already present: $zip"
    }
    else {
        $url = 'https://github.com/NapNeko/NapCatQQ/releases/download/v' + $NapCatVersion + '/NapCat.Shell.Windows.OneKey.zip'
        if ($PSCmdlet.ShouldProcess($zip, "Download $url")) {
            Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing -TimeoutSec 300
            Write-Ok "Downloaded NapCat $NapCatVersion"
        }
    }

    $dst = Join-Path $nd 'onekey'
    if ($PSCmdlet.ShouldProcess($dst, 'Expand one-key package')) {
        Expand-Archive -LiteralPath $zip -DestinationPath $dst -Force
        Write-Ok "Expanded to $dst"
    }

    Write-Warn 'Manual: run NapCatInstaller.exe from a desktop session (it is an interactive console program),'
    Write-Warn '        choose an install directory under runtime\napcat, then start napcat.bat and scan the QR code.'
    Write-Warn 'NapCat does not accept command-line arguments; it cannot be driven over SSH.'
    Write-Warn 'If the log says "move versions failed / access denied" it still prints "install complete":'
    Write-Warn '        that is a half install. Delete NapCat.XXXX.Shell and re-run the installer.'
    Write-Warn '        Details and the manual repair steps: docs/PITFALLS.md P11.'
}

# ---------------------------------------------------------------------------
function Invoke-AstrBotStage {
    Write-Step 'Stage: astrbot'
    $ad = Join-Path $Runtime 'astrbot'
    $dataDir = Join-Path $ad 'data'
    foreach ($d in @($ad, $dataDir)) {
        if (-not (Test-Path -LiteralPath $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null }
    }

    $setupName = 'AstrBot.Launcher_' + $LauncherVersion + '_x64-setup.exe'
    $setup = Join-Path $ad $setupName
    if (Test-Path -LiteralPath $setup) {
        Write-Skip "Installer already present: $setup"
    }
    else {
        $url = 'https://github.com/AstrBotDevs/astrbot-launcher/releases/download/v' + $LauncherVersion + '/' + $setupName
        if ($PSCmdlet.ShouldProcess($setup, "Download $url")) {
            Invoke-WebRequest -Uri $url -OutFile $setup -UseBasicParsing -TimeoutSec 300
            Write-Ok "Downloaded AstrBot Launcher $LauncherVersion"
        }
    }

    $installDir = Join-Path $ad 'launcher'
    $launcherExe = Join-Path $installDir 'astrbot-launcher.exe'
    if (Test-Path -LiteralPath $launcherExe) {
        Write-Skip "Launcher already installed: $launcherExe"
    }
    elseif ($PSCmdlet.ShouldProcess($installDir, 'Silent install launcher')) {
        $p = Start-Process -FilePath $setup -ArgumentList '/S', ('/D=' + $installDir) -Wait -PassThru
        if ($p.ExitCode -ne 0) { Fail "Launcher installer failed with exit code $($p.ExitCode)" }
        Write-Ok "Installed launcher to $installDir"
    }

    $cfgDir = Join-Path $env:APPDATA 'com.github.raven95676.astrbot-launcher'
    if ($PSCmdlet.ShouldProcess($cfgDir, 'Point launcher data dir into deployment root')) {
        if (-not (Test-Path -LiteralPath $cfgDir)) { New-Item -ItemType Directory -Path $cfgDir -Force | Out-Null }
        $json = [ordered]@{ data_dir = $dataDir } | ConvertTo-Json -Compress
        [IO.File]::WriteAllText((Join-Path $cfgDir '.data-dir.json'), $json, [Text.Encoding]::ASCII)
        Write-Ok "Launcher data dir -> $dataDir"
    }

    Write-Warn 'Manual: open astrbot-launcher.exe, create one instance, start it, then note the WebUI port.'
    Write-Warn 'Configure the model provider and the aiocqhttp platform afterwards (docs/TOOLS.md section 4).'
}

# ---------------------------------------------------------------------------
if ($Stage -eq 'all' -or $Stage -eq 'gateway') { Invoke-GatewayStage }
if ($Stage -eq 'all' -or $Stage -eq 'napcat')  { Invoke-NapCatStage }
if ($Stage -eq 'all' -or $Stage -eq 'astrbot') { Invoke-AstrBotStage }

Write-Host ''
Write-Step 'Done'
Write-Host '    Next: python tools/verify-stack.py --conf host/stack.conf' -ForegroundColor Cyan
exit 0
