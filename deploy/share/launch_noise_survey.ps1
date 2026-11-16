<#
Noise Survey Analysis - Launcher
================================

Starts the dashboard. The application itself runs from the synced shared drive,
so it is always the current version. Before starting, this checks that the local
Python environment is present, healthy and matches the deployed requirements,
and rebuilds it if not. That means a user never has to know that "setup" exists
after the first run - new releases and broken environments are handled here.

Usage:
    launch_noise_survey.bat
    launch_noise_survey.ps1 -ConfigPath "…\noise_survey_config_1234.json"
    launch_noise_survey.ps1 -Repair          (force a rebuild, then start)
    launch_noise_survey.bat 6645             (open job 6645: finds the job folder, generates the
                                              config if missing, reuses a running dashboard for
                                              that config, opens the browser at it)
    launch_noise_survey.ps1 -JobNumber 6645 [-Restart] [-Fresh] [-JobsFolder "G:\Shared drives\Venta\Jobs"]

Annotations are autosaved beside the config (<config>.workspace.json) and restored on the next
open; -Fresh opens without restoring them. -Restart stops a running dashboard and starts a new one
(the default is to leave a healthy one running and just open the config in it).
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $false, Position = 0)][string]$JobNumber,
    [Parameter(Mandatory = $false)][string]$JobsFolder = 'G:\Shared drives\Venta\Jobs',
    [Parameter(Mandatory = $false)][string]$ConfigPath,
    [Parameter(Mandatory = $false)][string]$StatePath,
    [Parameter(Mandatory = $false)][int]$ControlPort = 0,
    [switch]$Repair,
    [switch]$Restart,
    [switch]$Fresh,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '_lib\nsa-common.ps1')

# Large surveys can take minutes to load. Without this, Bokeh discards the
# session before the first render finishes and the page silently reloads.
$script:UnusedSessionLifetimeMs = 300000

function Stop-NsaExistingServer {
    param([string]$PidFile, [string]$PythonExe)

    if (-not (Test-Path $PidFile)) { return }

    $pidText = try { Get-Content -Path $PidFile -ErrorAction Stop | Select-Object -First 1 } catch { $null }
    if (-not ($pidText -match '^\d+$')) {
        Remove-Item -Path $PidFile -Force -ErrorAction SilentlyContinue
        return
    }

    $processId = [int]$pidText
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$processId" -ErrorAction SilentlyContinue
    if (-not $process) {
        Remove-Item -Path $PidFile -Force -ErrorAction SilentlyContinue
        return
    }

    # Only ever kill our own python.exe - the PID may have been recycled.
    if ($process.ExecutablePath -and ($process.ExecutablePath -ieq $PythonExe)) {
        Write-NsaInfo "Stopping the previous dashboard server (PID $processId)..."
        try {
            Stop-Process -Id $processId -Force -ErrorAction Stop
            Start-Sleep -Seconds 1
        } catch {
            Write-NsaWarn "Could not stop process ${processId}: $($_.Exception.Message)"
        }
    } else {
        Write-NsaWarn "PID $processId now belongs to another program - leaving it alone."
    }
    Remove-Item -Path $PidFile -Force -ErrorAction SilentlyContinue
}

function Get-NsaFreePort {
    <#
      Finds a port Bokeh can actually bind to.

      A test bind on 127.0.0.1 is not enough on its own: a server already
      listening on another local address (0.0.0.0, ::, or a specific NIC) does
      not always block a loopback bind, so the port looks free and Bokeh then
      fails with "port is already in use". Checking the machine's active
      listener list first catches that case.
    #>
    param([int]$Preferred = 5006, [int]$Attempts = 20)

    $inUse = @{}
    try {
        $props = [System.Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties()
        foreach ($endpoint in $props.GetActiveTcpListeners()) { $inUse[$endpoint.Port] = $true }
    } catch { }

    for ($port = $Preferred; $port -lt ($Preferred + $Attempts); $port++) {
        if ($inUse.ContainsKey($port)) { continue }
        $listener = $null
        try {
            $listener = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Any, $port)
            $listener.Start()
            return $port
        } catch {
            continue
        } finally {
            if ($listener) { try { $listener.Stop() } catch { } }
        }
    }
    return $Preferred
}

function Find-NsaJobSurveyFolder {
    <# Job folder under $Root whose name starts with the job number; prefers "<job> Surveys" inside it. #>
    param([string]$Root, [string]$Job)
    if (-not (Test-Path -LiteralPath $Root)) { throw "Jobs folder not found: $Root" }
    $jobDir = Get-ChildItem -LiteralPath $Root -Directory -Filter "$Job*" -ErrorAction SilentlyContinue |
        Sort-Object Name | Select-Object -First 1
    if (-not $jobDir) { throw "No job folder starting with '$Job' under $Root" }
    $surveys = Get-ChildItem -LiteralPath $jobDir.FullName -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -ieq "$Job surveys" } | Select-Object -First 1
    if ($surveys) { return $surveys.FullName }
    return $jobDir.FullName
}

function Get-NsaRunningServer {
    <# Port of a healthy dashboard started by this launcher, or 0. Never touches foreign processes. #>
    param([string]$PidFile, [string]$PortFile, [string]$PythonExe)
    if (-not ((Test-Path $PidFile) -and (Test-Path $PortFile))) { return 0 }
    $pidText = try { Get-Content -Path $PidFile -ErrorAction Stop | Select-Object -First 1 } catch { $null }
    $portText = try { Get-Content -Path $PortFile -ErrorAction Stop | Select-Object -First 1 } catch { $null }
    if (-not (($pidText -match '^\d+$') -and ($portText -match '^\d+$'))) { return 0 }
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$([int]$pidText)" -ErrorAction SilentlyContinue
    if (-not $process -or -not $process.ExecutablePath -or ($process.ExecutablePath -ine $PythonExe)) { return 0 }
    try {
        $null = Invoke-WebRequest -Uri "http://127.0.0.1:$portText/noise_survey_analysis" -UseBasicParsing -TimeoutSec 8
        return [int]$portText
    } catch { return 0 }
}

function Format-NsaArgument {
    param([string]$Value)
    if ($Value -match '[\s"]') { return '"' + ($Value -replace '"', '""') + '"' }
    return $Value
}

try {
    $paths = Get-NsaPaths -ShareRoot $PSScriptRoot
    $log = Start-NsaLog -Name 'launch'

    Write-NsaSection 'Noise Survey Analysis'

    # --- Make sure the install is present, healthy and current ---------------
    $result = Invoke-NsaEnsureReady -Paths $paths -Force:$Repair -Quiet:(-not $Repair)
    if (-not $result.Ready) {
        Write-NsaLine ''
        Write-NsaFail 'The dashboard could not be started because the installation is not usable.'
        Write-NsaInfo 'Run setup_noise_survey.bat, or diagnose_noise_survey.bat to produce a report for Steve.'
        Write-NsaInfo "Log file: $log"
        Wait-NsaForUser
        exit 1
    }

    $appDir = $paths.AppPackage
    if (-not (Test-Path (Join-Path $appDir 'main.py'))) {
        throw "The application files are missing from $appDir. Check that Google Drive has finished syncing."
    }

    # --- "Open job 6645": find the folder, make the config if it is missing ----
    if ($JobNumber -and (($JobNumber -match '\.json$') -or (Test-Path -LiteralPath $JobNumber -PathType Leaf))) {
        # A config path given positionally (drag and drop onto the .bat).
        $ConfigPath = $JobNumber
        $JobNumber = $null
    }
    if ($JobNumber -and -not $ConfigPath) {
        $JobNumber = $JobNumber.Trim()
        if ($JobNumber -notmatch '^\d{3,6}$') { throw "'$JobNumber' is not a job number (expected digits, for example 6645)." }
        $scanDir = Find-NsaJobSurveyFolder -Root $JobsFolder -Job $JobNumber
        $jobConfig = Join-Path $scanDir "noise_survey_config_$JobNumber.json"
        if (Test-Path -LiteralPath $jobConfig) {
            Write-NsaInfo "Using existing config: $jobConfig"
        } else {
            Write-NsaInfo "No config for job $JobNumber yet - scanning $scanDir ..."
            $generator = Join-Path $paths.App 'generate_job_config.py'
            if (-not (Test-Path $generator)) { throw "generate_job_config.py not found at $generator" }
            Push-Location $paths.App
            try {
                & $paths.VenvPython $generator $JobNumber $JobsFolder 2>&1 | ForEach-Object { Write-NsaLine "  $_" }
                $generatorCode = $LASTEXITCODE
            } finally { Pop-Location }
            if ($generatorCode -ne 0 -or -not (Test-Path -LiteralPath $jobConfig)) {
                throw "Could not generate a config for job $JobNumber in $scanDir (no recognised survey files?)."
            }
        }
        $ConfigPath = $jobConfig
    }

    # --- Reuse a healthy dashboard instead of killing it ------------------------
    $portFile = $paths.PidFile + '.port'
    if (-not $Restart -and -not $Repair) {
        $livePort = Get-NsaRunningServer -PidFile $paths.PidFile -PortFile $portFile -PythonExe $paths.VenvPython
        if ($livePort -gt 0) {
            $url = "http://localhost:$livePort/noise_survey_analysis"
            $query = @()
            if ($ConfigPath) {
                $resolvedForUrl = (Resolve-Path -LiteralPath $ConfigPath -ErrorAction Stop).ProviderPath
                $query += 'config=' + [uri]::EscapeDataString($resolvedForUrl)
            }
            if ($StatePath) { $query += 'state=' + [uri]::EscapeDataString((Resolve-Path -LiteralPath $StatePath).ProviderPath) }
            if ($Fresh) { $query += 'fresh=1' }
            if ($query.Count) { $url += '?' + ($query -join '&') }
            Write-NsaOk "A dashboard is already running on port $livePort - opening this config in it."
            Write-NsaInfo $url
            Write-NsaInfo 'Use -Restart to stop it and start a new one instead.'
            if (-not $NoBrowser) { Start-Process $url }
            exit 0
        }
    }

    # --- Build the Bokeh command line ---------------------------------------
    Stop-NsaExistingServer -PidFile $paths.PidFile -PythonExe $paths.VenvPython
    Remove-Item -Path $portFile -Force -ErrorAction SilentlyContinue
    $port = Get-NsaFreePort -Preferred 5006
    if ($port -ne 5006) {
        Write-NsaInfo "Port 5006 is in use by something else, so this dashboard will use port $port."
    }

    $serveArgs = @('-m', 'bokeh', 'serve', $appDir,
                   '--address', '127.0.0.1',
                   '--port', "$port",
                   '--allow-websocket-origin', "localhost:$port",
                   '--allow-websocket-origin', "127.0.0.1:$port",
                   '--unused-session-lifetime', "$script:UnusedSessionLifetimeMs")
    if (-not $NoBrowser) { $serveArgs += '--show' }

    $appArgs = @()
    if ($ConfigPath) {
        try { $resolved = (Resolve-Path -LiteralPath $ConfigPath -ErrorAction Stop).ProviderPath }
        catch { throw "Config file not found: $ConfigPath" }
        $appArgs += @('--config', $resolved)
        Write-NsaInfo "Config: $resolved"
    }
    if ($StatePath) {
        try { $resolvedState = (Resolve-Path -LiteralPath $StatePath -ErrorAction Stop).ProviderPath }
        catch { throw "Workspace file not found: $StatePath" }
        $appArgs += @('--state', $resolvedState)
        Write-NsaInfo "Workspace: $resolvedState"
    }
    if ($Fresh) { $appArgs += '--no-restore' }
    if ($ControlPort -gt 0) { $appArgs += @('--control-port', "$ControlPort") }
    if ($appArgs.Count -gt 0) { $serveArgs += @('--args') + $appArgs }

    Write-NsaLine ''
    Write-NsaLine "  Starting the dashboard on http://localhost:$port/noise_survey_analysis" 'Cyan'
    Write-NsaLine '  Keep this window open. Closing it stops the dashboard.' 'DarkCyan'
    Write-NsaLine '  A large survey can take a couple of minutes to appear the first time.' 'DarkGray'
    Write-NsaLine ''

    $argumentString = ($serveArgs | ForEach-Object { Format-NsaArgument $_ }) -join ' '
    Add-Content -Path $log -Value "command: $($paths.VenvPython) $argumentString" -Encoding UTF8

    $serverLog = Join-Path $paths.Logs ('server_' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.log')
    $serverErrors = $serverLog + '.errors.log'
    Write-NsaInfo "Dashboard log: $serverLog"
    $process = Start-Process -FilePath $paths.VenvPython -ArgumentList $argumentString -WorkingDirectory $paths.InstallRoot -NoNewWindow -PassThru -RedirectStandardOutput $serverLog -RedirectStandardError $serverErrors
    if (-not $process) { throw 'Failed to start the Bokeh server process.' }

    # Touching .Handle makes .NET cache the process handle. Without it,
    # .ExitCode comes back empty once the process has gone.
    $null = $process.Handle

    $exitCode = 0
    try {
        Set-Content -Path $paths.PidFile -Value $process.Id -Encoding ASCII
        Set-Content -Path $portFile -Value $port -Encoding ASCII
        $process.WaitForExit()
        $exitCode = $process.ExitCode
    } finally {
        Remove-Item -Path $paths.PidFile -Force -ErrorAction SilentlyContinue
        Remove-Item -Path $portFile -Force -ErrorAction SilentlyContinue
    }

    if ($exitCode -ne 0) {
        Write-NsaLine ''
        Write-NsaWarn "The dashboard stopped unexpectedly (exit code $exitCode)."
        Write-NsaInfo 'If this keeps happening, run diagnose_noise_survey.bat and send Steve the report.'
        Write-NsaInfo "Log file: $log"
        Wait-NsaForUser
    }

} catch {
    Write-NsaLine ''
    Write-NsaFail $_.Exception.Message
    if (Get-NsaLogFile) { Write-NsaInfo "Log file: $(Get-NsaLogFile)" }
    Wait-NsaForUser
    exit 1
}
