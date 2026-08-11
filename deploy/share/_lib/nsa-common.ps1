<#
Noise Survey Analysis - shared helper library
=============================================

Dot-sourced by setup / launch / diagnose / uninstall. Written for Windows
PowerShell 5.1 (the version that ships with Windows) so it runs on every team
machine without installing PowerShell 7.

Design notes
------------
* The application itself runs straight from the shared drive, which is synced
  (not streamed) to every machine, so it is always present locally and a new
  deployment reaches everyone without a copy step.
* Only the machine-specific parts live locally, under:
      %LOCALAPPDATA%\NoiseSurveyAnalysis\
        venv\     private Python virtual environment
        pycache\  bytecode cache, kept out of the synced folder
        logs\     setup / launch logs, for when something goes wrong
        install.json   record of what is installed, used to detect staleness
* Dependencies install from a wheelhouse on the shared drive (--no-index), so no
  internet, PyPI access or corporate proxy is required. PyPI is only a fallback.
#>

Set-StrictMode -Version 2.0

$script:NsaAppName = 'Noise Survey Analysis'

# ---------------------------------------------------------------------------
# Console output
# ---------------------------------------------------------------------------

$script:NsaLogFile = $null

function Write-NsaLine {
    param([string]$Text, [string]$Colour = 'Gray')
    Write-Host $Text -ForegroundColor $Colour
    if ($script:NsaLogFile) {
        try { Add-Content -Path $script:NsaLogFile -Value $Text -Encoding UTF8 -ErrorAction SilentlyContinue } catch { }
    }
}

function Write-NsaSection { param([string]$Text)
    Write-NsaLine ''
    Write-NsaLine $Text 'Cyan'
    Write-NsaLine ('-' * $Text.Length) 'Cyan'
}
function Write-NsaInfo { param([string]$Text) Write-NsaLine "  $Text" 'Gray' }
function Write-NsaOk   { param([string]$Text) Write-NsaLine "  [ok] $Text" 'Green' }
function Write-NsaWarn { param([string]$Text) Write-NsaLine "  [!]  $Text" 'Yellow' }
function Write-NsaFail { param([string]$Text) Write-NsaLine "  [X]  $Text" 'Red' }

function Start-NsaLog {
    param([string]$Name)
    $paths = Get-NsaPaths
    if (-not (Test-Path $paths.Logs)) { New-Item -ItemType Directory -Path $paths.Logs -Force | Out-Null }
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $script:NsaLogFile = Join-Path $paths.Logs ("{0}_{1}.log" -f $Name, $stamp)
    Add-Content -Path $script:NsaLogFile -Value "$Name started $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') on $env:COMPUTERNAME as $env:USERNAME" -Encoding UTF8
    # Keep only the 15 most recent logs so this never grows without bound.
    Get-ChildItem -Path $paths.Logs -Filter '*.log' -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -Skip 15 |
        Remove-Item -Force -ErrorAction SilentlyContinue
    return $script:NsaLogFile
}

function Get-NsaLogFile { return $script:NsaLogFile }

function Wait-NsaForUser {
    param([string]$Message = 'Press Enter to close this window')
    if ($Host.Name -eq 'ConsoleHost') {
        Write-Host ''
        Read-Host $Message | Out-Null
    }
}

# ---------------------------------------------------------------------------
# Paths and manifest
# ---------------------------------------------------------------------------

function Get-NsaPaths {
    <#
      .SYNOPSIS
      Resolves every path the tooling uses. $ShareRoot defaults to the folder
      holding the calling script's parent (_lib lives one level down).
    #>
    param([string]$ShareRoot)

    if (-not $ShareRoot) {
        $ShareRoot = Split-Path -Parent $PSScriptRoot   # _lib -> share root
    }

    $installRoot = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'NoiseSurveyAnalysis'

    $payload = Join-Path $ShareRoot 'Noise Survey Analysis'

    return [pscustomobject]@{
        ShareRoot    = $ShareRoot
        SharePayload = $payload
        ShareSlm     = Join-Path $ShareRoot 'SLM Parsers'
        Wheelhouse   = Join-Path $ShareRoot 'runtime\wheelhouse'
        Manifest     = Join-Path $ShareRoot 'runtime\manifest.json'
        # The application runs in place on the synced shared drive.
        App          = $payload
        AppPackage   = Join-Path $payload 'noise_survey_analysis'
        InstallRoot  = $installRoot
        Venv         = Join-Path $installRoot 'venv'
        VenvPython   = Join-Path $installRoot 'venv\Scripts\python.exe'
        PyCache      = Join-Path $installRoot 'pycache'
        Logs         = Join-Path $installRoot 'logs'
        Stamp        = Join-Path $installRoot 'install.json'
        PidFile      = Join-Path $installRoot 'bokeh_server.pid'
    }
}

function Get-NsaManifest {
    param([string]$ManifestPath)
    if (-not (Test-Path $ManifestPath)) { return $null }
    try {
        return Get-Content -Path $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        Write-NsaWarn "Could not read the deployment manifest: $($_.Exception.Message)"
        return $null
    }
}

function Get-NsaStamp {
    param([string]$StampPath)
    if (-not (Test-Path $StampPath)) { return $null }
    try { return Get-Content -Path $StampPath -Raw -Encoding UTF8 | ConvertFrom-Json } catch { return $null }
}

function Set-NsaStamp {
    param([string]$StampPath, [hashtable]$Data)
    $json = $Data | ConvertTo-Json -Depth 5
    Set-Content -Path $StampPath -Value $json -Encoding UTF8
}

function Get-NsaFileHashSafe {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return '' }
    try { return (Get-FileHash -Path $Path -Algorithm SHA256).Hash } catch { return '' }
}

# ---------------------------------------------------------------------------
# Python discovery
# ---------------------------------------------------------------------------

function Get-NsaPythonVersion {
    <# Returns [Version] for a python.exe, or $null if it will not run. #>
    param([string]$Exe)
    if (-not (Test-Path $Exe)) { return $null }
    try {
        $out = & $Exe -c "import sys;print('%d.%d.%d' % sys.version_info[:3])" 2>&1
        if ($LASTEXITCODE -ne 0) { return $null }
        $text = ($out | Out-String).Trim()
        if ($text -match '^(\d+\.\d+\.\d+)') { return [Version]$Matches[1] }
    } catch { }
    return $null
}

function Test-NsaPython64Bit {
    param([string]$Exe)
    try {
        $out = & $Exe -c "import struct;print(struct.calcsize('P')*8)" 2>&1
        return (($out | Out-String).Trim() -eq '64')
    } catch { return $false }
}

function Find-NsaPythonInterpreters {
    <#
      .SYNOPSIS
      Finds every usable python.exe on the machine.

      Deliberately does NOT rely on PATH alone. After a winget install, PATH is
      not refreshed in the running process, so a PATH-only search reports "no
      Python" on a machine that has just installed it. That was a real failure
      mode of the previous setup script.
    #>
    param([Version]$MinimumVersion = [Version]'3.10')

    $found = @{}

    function Add-Candidate([string]$exe, [string]$source) {
        if (-not $exe) { return }
        try { $exe = (Resolve-Path -LiteralPath $exe -ErrorAction Stop).ProviderPath } catch { return }
        $key = $exe.ToLowerInvariant()
        if ($found.ContainsKey($key)) { return }
        $ver = Get-NsaPythonVersion -Exe $exe
        if (-not $ver) { return }
        if ($ver -lt $MinimumVersion) { return }
        $found[$key] = [pscustomobject]@{
            Path    = $exe
            Version = $ver
            Tag     = ('cp{0}{1}' -f $ver.Major, $ver.Minor)
            Is64Bit = Test-NsaPython64Bit -Exe $exe
            Source  = $source
        }
    }

    # 1. The py launcher knows about every registered install.
    $py = Get-Command 'py.exe' -ErrorAction SilentlyContinue
    if ($py) {
        try {
            $listing = & $py.Source -0p 2>&1
            foreach ($line in ($listing -split "`r?`n")) {
                if ($line -match '([A-Za-z]:\\[^\r\n]*python\.exe)') { Add-Candidate $Matches[1] 'py launcher' }
            }
        } catch { }
    }

    # 2. Anything on PATH. This includes the Microsoft Store app-execution
    #    alias in WindowsApps, which may be either a real Store Python or the
    #    "not installed" stub. Both are probed the same way: the stub cannot
    #    report a version, so it is filtered out by Get-NsaPythonVersion.
    foreach ($cmd in @(Get-Command 'python.exe' -All -ErrorAction SilentlyContinue)) {
        $label = if ($cmd.Source -like '*\WindowsApps\*') { 'Microsoft Store' } else { 'PATH' }
        Add-Candidate $cmd.Source $label
    }

    # 3. Standard install locations, in case PATH is not set up.
    $roots = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Python'),
        'C:\Program Files\Python313', 'C:\Program Files\Python312',
        'C:\Program Files\Python311', 'C:\Program Files\Python310',
        'C:\Python313', 'C:\Python312', 'C:\Python311', 'C:\Python310'
    )
    foreach ($root in $roots) {
        if (-not (Test-Path $root)) { continue }
        foreach ($exe in @(Get-ChildItem -Path $root -Filter 'python.exe' -Recurse -Depth 2 -ErrorAction SilentlyContinue)) {
            Add-Candidate $exe.FullName 'filesystem scan'
        }
    }

    # The leading comma stops PowerShell unrolling a single result to a scalar,
    # so callers can always rely on .Count.
    return ,@($found.Values)
}

function Select-NsaPython {
    <#
      .SYNOPSIS
      Picks the best interpreter. Preference order:
        1. 64-bit, and matching a wheelhouse ABI tag (fully offline install)
        2. 64-bit, matching the manifest's preferred version list
        3. Any 64-bit
        4. Anything at all
      Within a tier, newest wins.
    #>
    param(
        [array]$Interpreters,
        [string[]]$WheelhouseTags = @(),
        [string[]]$PreferredVersions = @()
    )

    if (-not $Interpreters -or $Interpreters.Count -eq 0) { return $null }

    $scored = foreach ($i in $Interpreters) {
        $score = 0
        if ($i.Is64Bit) { $score += 100 }
        if ($WheelhouseTags -contains $i.Tag) { $score += 50 }
        $shortVersion = '{0}.{1}' -f $i.Version.Major, $i.Version.Minor
        if ($PreferredVersions -contains $shortVersion) { $score += 25 }
        # A normally installed Python is preferred over the Store alias, which
        # sandboxes its file access and is more awkward to support.
        if ($i.Source -ne 'Microsoft Store') { $score += 10 }
        [pscustomobject]@{ Interp = $i; Score = $score }
    }

    return (@($scored) | Sort-Object -Property @{Expression = 'Score'; Descending = $true},
                                               @{Expression = { $_.Interp.Version }; Descending = $true} |
            Select-Object -First 1).Interp
}

function Install-NsaPython {
    <#
      .SYNOPSIS
      Installs Python for the current user via winget. Returns $true if a usable
      interpreter exists afterwards.
    #>
    param([string]$Version = '3.13', [Version]$MinimumVersion = [Version]'3.10')

    $winget = Get-Command 'winget.exe' -ErrorAction SilentlyContinue
    if (-not $winget) {
        Write-NsaFail 'Python is not installed and winget is not available to install it automatically.'
        Write-NsaInfo "Install Python $Version manually from https://www.python.org/downloads/windows/"
        Write-NsaInfo 'Tick "Add python.exe to PATH" during the install, then run Setup again.'
        return $false
    }

    $packageId = "Python.Python.$Version"
    Write-NsaInfo "Installing $packageId for the current user (this can take a few minutes)..."
    try {
        $wingetArgs = @('install', '-e', '--id', $packageId, '--scope', 'user', '--silent',
                        '--accept-package-agreements', '--accept-source-agreements')
        $proc = Start-Process -FilePath $winget.Source -ArgumentList $wingetArgs -Wait -PassThru -NoNewWindow
        if ($proc.ExitCode -ne 0) {
            Write-NsaWarn "winget exited with code $($proc.ExitCode)."
        }
    } catch {
        Write-NsaWarn "winget install failed: $($_.Exception.Message)"
    }

    # Re-scan the filesystem, NOT just PATH - PATH is stale in this process.
    $interpreters = Find-NsaPythonInterpreters -MinimumVersion $MinimumVersion
    if ($interpreters.Count -gt 0) {
        Write-NsaOk "Python is now available ($($interpreters.Count) interpreter(s) detected)."
        return $true
    }

    Write-NsaFail 'Python still could not be found after the install attempt.'
    Write-NsaInfo 'Restart the computer and run Setup again, or install Python manually.'
    return $false
}

# ---------------------------------------------------------------------------
# Application availability
# ---------------------------------------------------------------------------

function Test-NsaAppAvailable {
    <#
      .SYNOPSIS
      Confirms the shared-drive application is readable. Drive syncs the folder
      to every machine, so the only realistic failures are Drive not running,
      the Venta shared drive not being added, or the sync still catching up.
    #>
    param([string]$AppPackage)

    $entry = Join-Path $AppPackage 'main.py'
    if (Test-Path $entry) { return [pscustomobject]@{ Available = $true; Message = '' } }

    if (-not (Test-Path $AppPackage)) {
        return [pscustomobject]@{ Available = $false
            Message = "Application folder not found: $AppPackage" }
    }
    return [pscustomobject]@{ Available = $false
        Message = "Application folder found but main.py is missing from $AppPackage - Google Drive may still be syncing." }
}

# ---------------------------------------------------------------------------
# Virtual environment and dependencies
# ---------------------------------------------------------------------------

# xlrd is here because the "Extract TH data" parsers need it and share this
# environment - a dashboard that runs while the parsers fail is still broken.
$script:NsaImportCheck = 'import bokeh, pandas, numpy, scipy, soundfile, openpyxl, pytz, xlrd'

function Test-NsaVenvHealthy {
    <#
      .SYNOPSIS
      Confirms the venv exists AND can actually import every required package.
      A venv folder that exists but has a broken/partial install is the single
      most common cause of "it worked yesterday" - checking for the folder is
      not enough.
    #>
    param([string]$VenvPython)
    if (-not (Test-Path $VenvPython)) { return $false }
    try {
        & $VenvPython -c $script:NsaImportCheck 2>&1 | Out-Null
        return ($LASTEXITCODE -eq 0)
    } catch { return $false }
}

function New-NsaVenv {
    param([string]$PythonExe, [string]$VenvPath)
    if (Test-Path $VenvPath) {
        Write-NsaInfo 'Removing the previous environment...'
        Remove-Item -Path $VenvPath -Recurse -Force -ErrorAction SilentlyContinue
    }
    & $PythonExe -m venv $VenvPath
    if ($LASTEXITCODE -ne 0) { throw "Failed to create the virtual environment at $VenvPath (exit code $LASTEXITCODE)." }
}

function Install-NsaDependencies {
    <#
      .SYNOPSIS
      Installs the pinned dependencies, preferring the offline wheelhouse.

      Order:
        1. Wheelhouse matching this interpreter's ABI tag, with --no-index.
           Deterministic and needs no network.
        2. Wheelhouse as an extra index, allowing PyPI to fill gaps.
        3. Plain PyPI.
      Each fallback is reported so the log shows which path was used.
    #>
    param(
        [string]$VenvPython,
        [string]$RequirementsFile,
        [string]$WheelhouseRoot,
        [string]$Tag
    )

    if (-not (Test-Path $RequirementsFile)) { throw "Requirements file not found: $RequirementsFile" }

    $tagDir = Join-Path $WheelhouseRoot $Tag
    $haveWheelhouse = (Test-Path $tagDir) -and
                      (@(Get-ChildItem -Path $tagDir -Filter '*.whl' -ErrorAction SilentlyContinue).Count -gt 0)

    # pip is bundled by ensurepip, so this is only a nice-to-have. Never let a
    # missing network connection stop the install here.
    & $VenvPython -m pip install --upgrade pip --disable-pip-version-check --quiet 2>&1 | Out-Null

    $attempts = @()
    if ($haveWheelhouse) {
        $attempts += ,@{ Label = "offline wheelhouse ($Tag)"
                         Args  = @('--no-index', '--find-links', $tagDir) }
        $attempts += ,@{ Label = 'wheelhouse plus PyPI'
                         Args  = @('--find-links', $tagDir) }
    } else {
        Write-NsaWarn "No wheelhouse for $Tag on the shared drive - falling back to downloading from PyPI."
    }
    $attempts += ,@{ Label = 'PyPI'; Args = @() }

    foreach ($attempt in $attempts) {
        Write-NsaInfo "Installing packages from $($attempt.Label)..."
        $pipArgs = @('-m', 'pip', 'install', '--disable-pip-version-check', '-r', $RequirementsFile) + $attempt.Args
        $output = & $VenvPython @pipArgs 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-NsaOk "Packages installed from $($attempt.Label)."
            return $true
        }
        Write-NsaWarn "Install from $($attempt.Label) did not succeed."
        if ($script:NsaLogFile) {
            Add-Content -Path $script:NsaLogFile -Value ($output | Out-String) -Encoding UTF8 -ErrorAction SilentlyContinue
        }
    }

    Write-NsaFail 'Could not install the Python packages by any route.'
    Write-NsaInfo "Full pip output is in the log: $script:NsaLogFile"
    return $false
}

# ---------------------------------------------------------------------------
# VLC (audio playback only)
# ---------------------------------------------------------------------------

function Get-NsaVlcStatus {
    <#
      .SYNOPSIS
      Audio playback needs the 64-bit VLC runtime (libvlc.dll). Everything else
      in the dashboard works without it, so this is a warning, never an error.
      A 32-bit-only VLC alongside 64-bit Python is a silent failure worth naming.
    #>
    $paths64 = @(
        (Join-Path $env:ProgramFiles 'VideoLAN\VLC\libvlc.dll'),
        'C:\Program Files\VideoLAN\VLC\libvlc.dll'
    )
    $paths32 = @(
        (Join-Path ${env:ProgramFiles(x86)} 'VideoLAN\VLC\libvlc.dll'),
        'C:\Program Files (x86)\VideoLAN\VLC\libvlc.dll'
    )

    foreach ($p in $paths64) { if ($p -and (Test-Path $p)) {
        return [pscustomobject]@{ Installed = $true; Bitness = '64-bit'; Path = $p }
    } }
    foreach ($p in $paths32) { if ($p -and (Test-Path $p)) {
        return [pscustomobject]@{ Installed = $true; Bitness = '32-bit'; Path = $p }
    } }
    return [pscustomobject]@{ Installed = $false; Bitness = $null; Path = $null }
}

function Install-NsaVlc {
    $winget = Get-Command 'winget.exe' -ErrorAction SilentlyContinue
    if (-not $winget) { return $false }
    Write-NsaInfo 'Installing VLC media player (needed for audio playback)...'
    try {
        $wingetArgs = @('install', '-e', '--id', 'VideoLAN.VLC', '--silent',
                        '--accept-package-agreements', '--accept-source-agreements')
        $proc = Start-Process -FilePath $winget.Source -ArgumentList $wingetArgs -Wait -PassThru -NoNewWindow
        return ($proc.ExitCode -eq 0)
    } catch {
        Write-NsaWarn "VLC install failed: $($_.Exception.Message)"
        return $false
    }
}

# ---------------------------------------------------------------------------
# The one function that makes everything ready
# ---------------------------------------------------------------------------

function Invoke-NsaEnsureReady {
    <#
      .SYNOPSIS
      Brings the local install up to date with the shared drive, repairing
      anything that is missing or broken. Safe to call on every launch.

      .PARAMETER Force
      Rebuild the environment even if it looks healthy.

      .PARAMETER Quiet
      Skip work and messages when nothing has changed (used by the launcher).

      Returns an object with Ready (bool) and the resolved paths.
    #>
    param(
        [Parameter(Mandatory = $true)] $Paths,
        [switch]$Force,
        [switch]$Quiet,
        [switch]$AllowVlcInstall
    )

    $manifest = Get-NsaManifest -ManifestPath $Paths.Manifest
    $minPython = [Version]'3.10'
    $wheelTags = @()
    $preferred = @('3.13', '3.12', '3.11')
    $requirementsName = 'requirements-lock.txt'
    $deployedVersion = 'unknown'

    if ($manifest) {
        if ($manifest.PSObject.Properties['min_python'] -and $manifest.min_python) { $minPython = [Version]$manifest.min_python }
        if ($manifest.PSObject.Properties['wheelhouse_tags']) { $wheelTags = @($manifest.wheelhouse_tags) }
        if ($manifest.PSObject.Properties['preferred_python']) { $preferred = @($manifest.preferred_python) }
        if ($manifest.PSObject.Properties['requirements_file'] -and $manifest.requirements_file) { $requirementsName = $manifest.requirements_file }
        if ($manifest.PSObject.Properties['version'] -and $manifest.version) { $deployedVersion = $manifest.version }
    }

    # --- 1. Check the shared application is reachable ------------------------
    $app = Test-NsaAppAvailable -AppPackage $Paths.AppPackage
    if (-not $app.Available) {
        Write-NsaFail $app.Message
        Write-NsaInfo 'Check that Google Drive is running and that you can open this folder in Explorer:'
        Write-NsaInfo "  $($Paths.SharePayload)"
        return [pscustomobject]@{ Ready = $false; Manifest = $manifest }
    }
    if (-not $Quiet) { Write-NsaOk "Application found on the shared drive (version $deployedVersion)." }

    # Keep Python's bytecode cache off the synced drive. Without this, every run
    # writes __pycache__ folders that Drive then syncs to everyone else.
    if (-not (Test-Path $Paths.PyCache)) { New-Item -ItemType Directory -Path $Paths.PyCache -Force | Out-Null }
    $env:PYTHONPYCACHEPREFIX = $Paths.PyCache

    $requirementsFile = Join-Path $Paths.App $requirementsName
    if (-not (Test-Path $requirementsFile)) {
        $requirementsFile = Join-Path $Paths.App 'requirements.txt'
    }
    $requirementsHash = Get-NsaFileHashSafe -Path $requirementsFile

    # --- 2. Decide whether the environment needs rebuilding ------------------
    $stamp = Get-NsaStamp -StampPath $Paths.Stamp
    $venvHealthy = Test-NsaVenvHealthy -VenvPython $Paths.VenvPython

    $reasons = @()
    if ($Force)                                          { $reasons += 'a rebuild was requested' }
    if (-not $venvHealthy)                               { $reasons += 'the Python environment is missing or incomplete' }
    if (-not $stamp)                                     { $reasons += 'no previous install was recorded' }
    elseif ($stamp.PSObject.Properties['requirements_hash'] -and
            $stamp.requirements_hash -ne $requirementsHash) { $reasons += 'the required packages have changed' }

    if ($reasons.Count -eq 0) {
        if (-not $Quiet) { Write-NsaOk 'Python environment is healthy and up to date.' }
        return [pscustomobject]@{ Ready = $true; Manifest = $manifest; Rebuilt = $false }
    }

    Write-NsaSection 'Preparing the Python environment'
    foreach ($r in $reasons) { Write-NsaInfo "Reason: $r." }

    # --- 3. Find (or install) Python ----------------------------------------
    $interpreters = Find-NsaPythonInterpreters -MinimumVersion $minPython
    if ($interpreters.Count -eq 0) {
        Write-NsaWarn "Python $minPython or newer was not found on this computer."
        $targetVersion = if ($preferred.Count -gt 0) { $preferred[0] } else { '3.13' }
        if (-not (Install-NsaPython -Version $targetVersion -MinimumVersion $minPython)) {
            return [pscustomobject]@{ Ready = $false; Manifest = $manifest }
        }
        $interpreters = Find-NsaPythonInterpreters -MinimumVersion $minPython
    }

    $python = Select-NsaPython -Interpreters $interpreters -WheelhouseTags $wheelTags -PreferredVersions $preferred
    if (-not $python) {
        Write-NsaFail 'No usable Python interpreter could be selected.'
        return [pscustomobject]@{ Ready = $false; Manifest = $manifest }
    }

    Write-NsaOk "Using Python $($python.Version) ($(if ($python.Is64Bit) { '64-bit' } else { '32-bit' })) from $($python.Path)"
    if (-not $python.Is64Bit) {
        Write-NsaWarn 'This is a 32-bit Python. Large surveys may run out of memory. A 64-bit Python is strongly preferred.'
    }
    if ($wheelTags.Count -gt 0 -and ($wheelTags -notcontains $python.Tag)) {
        Write-NsaWarn "The offline package store on the shared drive is built for $($wheelTags -join ', '), not $($python.Tag)."
        Write-NsaInfo 'Packages will be downloaded from the internet instead. This still works, it is just slower.'
    }

    # --- 4. Build the environment and install packages -----------------------
    Write-NsaInfo "Creating the environment at $($Paths.Venv)"
    New-NsaVenv -PythonExe $python.Path -VenvPath $Paths.Venv

    $installed = Install-NsaDependencies -VenvPython $Paths.VenvPython `
                                         -RequirementsFile $requirementsFile `
                                         -WheelhouseRoot $Paths.Wheelhouse `
                                         -Tag $python.Tag
    if (-not $installed) { return [pscustomobject]@{ Ready = $false; Manifest = $manifest } }

    if (-not (Test-NsaVenvHealthy -VenvPython $Paths.VenvPython)) {
        Write-NsaFail 'The packages installed but could not be imported. The environment is not usable.'
        Write-NsaInfo "Send this log to Steve: $script:NsaLogFile"
        return [pscustomobject]@{ Ready = $false; Manifest = $manifest }
    }
    Write-NsaOk 'All required packages import correctly.'

    # --- 5. VLC (audio only) -------------------------------------------------
    $vlc = Get-NsaVlcStatus
    if (-not $vlc.Installed) {
        Write-NsaWarn 'VLC media player is not installed. Charts and data work fine, but audio playback will be unavailable.'
        if ($AllowVlcInstall) {
            if (Install-NsaVlc) {
                Write-NsaOk 'VLC installed.'
            } else {
                Write-NsaInfo 'Install VLC (64-bit) from https://www.videolan.org/vlc/ if you need audio playback.'
            }
        }
    } elseif ($vlc.Bitness -eq '32-bit' -and $python.Is64Bit) {
        Write-NsaWarn 'Only a 32-bit VLC was found, but Python is 64-bit. Audio playback will not work.'
        Write-NsaInfo 'Install the 64-bit VLC from https://www.videolan.org/vlc/ to enable audio.'
    } else {
        Write-NsaOk "VLC $($vlc.Bitness) detected - audio playback available."
    }

    # --- 6. Record what we installed ----------------------------------------
    Set-NsaStamp -StampPath $Paths.Stamp -Data @{
        installed_at      = (Get-Date -Format 'o')
        app_version       = $deployedVersion
        share_root        = $Paths.ShareRoot
        python_path       = $python.Path
        python_version    = $python.Version.ToString()
        python_tag        = $python.Tag
        requirements_file = $requirementsFile
        requirements_hash = $requirementsHash
        vlc               = $vlc.Bitness
    }

    return [pscustomobject]@{ Ready = $true; Manifest = $manifest; Rebuilt = $true }
}
