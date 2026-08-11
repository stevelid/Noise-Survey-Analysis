<#
Noise Survey Analysis - Diagnostics
===================================

Produces a single report file describing this computer's installation, and
opens it. When something will not work, running this and sending Steve the
report is faster than describing the symptoms.

Nothing is changed by this script.
#>

[CmdletBinding()]
param([switch]$NoOpen)

$ErrorActionPreference = 'Continue'
. (Join-Path $PSScriptRoot '_lib\nsa-common.ps1')

$lines = New-Object System.Collections.Generic.List[string]
function Add-Line { param([string]$Text = '') $lines.Add($Text) | Out-Null }
function Add-Heading { param([string]$Text) Add-Line ''; Add-Line $Text; Add-Line ('-' * $Text.Length) }

try {
    $paths = Get-NsaPaths -ShareRoot $PSScriptRoot

    Add-Line 'Noise Survey Analysis - diagnostic report'
    Add-Line '========================================='
    Add-Line "Generated : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
    Add-Line "Computer  : $env:COMPUTERNAME"
    Add-Line "User      : $env:USERNAME"
    Add-Line "Windows   : $([Environment]::OSVersion.VersionString)"
    Add-Line "PowerShell: $($PSVersionTable.PSVersion)"

    # --- Shared drive --------------------------------------------------------
    Add-Heading 'Shared drive'
    Add-Line "Share root      : $($paths.ShareRoot)"
    Add-Line "Application     : $($paths.SharePayload)  [$(if (Test-Path $paths.SharePayload) { 'found' } else { 'MISSING' })]"
    Add-Line "SLM Parsers     : $($paths.ShareSlm)  [$(if (Test-Path $paths.ShareSlm) { 'found' } else { 'missing' })]"
    Add-Line "Wheelhouse      : $($paths.Wheelhouse)  [$(if (Test-Path $paths.Wheelhouse) { 'found' } else { 'MISSING' })]"
    if (Test-Path $paths.Wheelhouse) {
        foreach ($dir in @(Get-ChildItem -Path $paths.Wheelhouse -Directory -ErrorAction SilentlyContinue)) {
            $count = @(Get-ChildItem -Path $dir.FullName -Filter '*.whl' -ErrorAction SilentlyContinue).Count
            Add-Line "  $($dir.Name): $count wheel file(s)"
        }
    }

    $manifest = Get-NsaManifest -ManifestPath $paths.Manifest
    if ($manifest) {
        Add-Line "Deployed version: $($manifest.version)  (deployed $($manifest.deployed_at))"
    } else {
        Add-Line 'Deployed version: MANIFEST NOT FOUND - the shared drive may not be fully synced.'
    }

    Add-Line "Entry point     : $(Join-Path $paths.AppPackage 'main.py')  [$(if (Test-Path (Join-Path $paths.AppPackage 'main.py')) { 'found' } else { 'MISSING' })]"

    # --- Local install -------------------------------------------------------
    Add-Heading 'Local installation (this computer only)'
    Add-Line "Install root : $($paths.InstallRoot)"
    Add-Line "Environment  : $(if (Test-Path $paths.VenvPython) { $paths.VenvPython } else { 'MISSING' })"

    $stamp = Get-NsaStamp -StampPath $paths.Stamp
    if ($stamp) {
        Add-Line "Installed at : $($stamp.installed_at)"
        Add-Line "Built for    : version $($stamp.app_version)"
        Add-Line "Python used  : $($stamp.python_version) at $($stamp.python_path)"
    } else {
        Add-Line 'Install record: NONE - setup has not completed successfully on this machine.'
    }

    # --- Python --------------------------------------------------------------
    Add-Heading 'Python interpreters found on this computer'
    $interpreters = Find-NsaPythonInterpreters -MinimumVersion ([Version]'3.6')
    if ($interpreters.Count -eq 0) {
        Add-Line 'None. Python needs to be installed - run setup_noise_survey.bat.'
    } else {
        foreach ($i in ($interpreters | Sort-Object Version -Descending)) {
            Add-Line ("{0,-9} {1,-8} {2,-16} {3}" -f $i.Version, $(if ($i.Is64Bit) { '64-bit' } else { '32-bit' }), $i.Source, $i.Path)
        }
    }

    # --- Packages ------------------------------------------------------------
    Add-Heading 'Installed packages in the dashboard environment'
    if (Test-Path $paths.VenvPython) {
        $probe = @'
import importlib, sys
print("python", sys.version.split()[0], "64-bit" if sys.maxsize > 2**32 else "32-bit")
for name, dist in [("bokeh","bokeh"),("pandas","pandas"),("numpy","numpy"),("scipy","scipy"),
                   ("soundfile","soundfile"),("openpyxl","openpyxl"),("pytz","pytz"),
                   ("xlrd","xlrd"),("vlc","python-vlc")]:
    try:
        m = importlib.import_module(name)
        v = getattr(m, "__version__", "")
        print("  OK      %-12s %s" % (dist, v))
    except Exception as exc:
        print("  FAILED  %-12s %s: %s" % (dist, type(exc).__name__, exc))
'@
        $probeFile = Join-Path $env:TEMP 'nsa_probe.py'
        Set-Content -Path $probeFile -Value $probe -Encoding UTF8
        $out = & $paths.VenvPython $probeFile 2>&1
        foreach ($line in ($out | Out-String -Stream)) { Add-Line $line }
        Remove-Item -Path $probeFile -Force -ErrorAction SilentlyContinue
    } else {
        Add-Line 'No environment to check.'
    }

    # --- VLC -----------------------------------------------------------------
    Add-Heading 'VLC (needed only for audio playback)'
    $vlc = Get-NsaVlcStatus
    if ($vlc.Installed) {
        Add-Line "$($vlc.Bitness) VLC found at $($vlc.Path)"
        if ($vlc.Bitness -eq '32-bit') {
            Add-Line 'WARNING: a 64-bit VLC is required for audio playback with 64-bit Python.'
        }
    } else {
        Add-Line 'Not installed. Charts and data still work; audio playback will not.'
    }

    # --- Explorer integration ------------------------------------------------
    Add-Heading 'Explorer right-click menus'
    foreach ($key in @(
        'HKCU:\Software\Classes\SystemFileAssociations\.svl\shell\ExtractTHData\command',
        'HKCU:\Software\Classes\SystemFileAssociations\.json\shell\OpenNoiseSurvey\command')) {
        if (Test-Path $key) {
            $value = (Get-ItemProperty -Path $key -Name '(Default)' -ErrorAction SilentlyContinue).'(default)'
            Add-Line "$key"
            Add-Line "  $value"
        } else {
            Add-Line "$key  [not registered]"
        }
    }

    # --- Recent logs ---------------------------------------------------------
    Add-Heading 'Most recent log'
    $recent = Get-ChildItem -Path $paths.Logs -Filter '*.log' -ErrorAction SilentlyContinue |
              Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($recent) {
        Add-Line "From $($recent.FullName)"
        Add-Line ''
        foreach ($line in (Get-Content -Path $recent.FullName -Tail 120 -ErrorAction SilentlyContinue)) { Add-Line $line }
    } else {
        Add-Line 'No logs yet.'
    }

    Add-Line ''
    Add-Line '--- end of report ---'

} catch {
    Add-Line ''
    Add-Line "The diagnostic script itself failed: $($_.Exception.Message)"
}

$reportDir = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'NoiseSurveyAnalysis\logs'
if (-not (Test-Path $reportDir)) { New-Item -ItemType Directory -Path $reportDir -Force | Out-Null }
$reportPath = Join-Path $reportDir ("diagnostic_{0}_{1}.txt" -f $env:COMPUTERNAME, (Get-Date -Format 'yyyyMMdd-HHmmss'))
Set-Content -Path $reportPath -Value $lines -Encoding UTF8

Write-Host ''
Write-Host 'Diagnostic report written to:' -ForegroundColor Cyan
Write-Host "  $reportPath" -ForegroundColor White
Write-Host ''
Write-Host 'Send that file to Steve.' -ForegroundColor Green

if (-not $NoOpen) { try { Start-Process notepad.exe $reportPath } catch { } }

Wait-NsaForUser
