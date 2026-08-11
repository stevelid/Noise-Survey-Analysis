<#
Noise Survey Analysis - Uninstall
=================================

Removes everything this tool put on the computer:
  * the local application copy and Python environment
  * the desktop shortcut
  * the Explorer right-click menus

Nothing on the shared drive and no survey data is touched. Python and VLC are
left installed, because other things may depend on them.
#>

[CmdletBinding()]
param([switch]$KeepLogs, [switch]$Quiet)

$ErrorActionPreference = 'Continue'
. (Join-Path $PSScriptRoot '_lib\nsa-common.ps1')

$paths = Get-NsaPaths -ShareRoot $PSScriptRoot

Write-NsaSection 'Noise Survey Analysis - Uninstall'
Write-NsaInfo "This will remove $($paths.InstallRoot), the desktop shortcut and the right-click menus."
Write-NsaInfo 'Survey data and the shared drive are not affected.'

if (-not $Quiet) {
    Write-Host ''
    $answer = Read-Host 'Continue? (y/N)'
    if ($answer -notmatch '^(y|yes)$') { Write-NsaInfo 'Cancelled.'; Wait-NsaForUser; exit 0 }
}

# --- Stop a running server ---------------------------------------------------
if (Test-Path $paths.PidFile) {
    $pidText = try { Get-Content -Path $paths.PidFile -ErrorAction Stop | Select-Object -First 1 } catch { $null }
    if ($pidText -match '^\d+$') {
        try { Stop-Process -Id ([int]$pidText) -Force -ErrorAction SilentlyContinue } catch { }
    }
}

# --- Registry ----------------------------------------------------------------
$keys = @(
    'HKCU\Software\Classes\SystemFileAssociations\.svl\shell\ExtractTHData',
    'HKCU\Software\Classes\SystemFileAssociations\.svn\shell\ExtractTHData',
    'HKCU\Software\Classes\SystemFileAssociations\.csv\shell\ExtractTHData',
    'HKCU\Software\Classes\SystemFileAssociations\.xls\shell\ExtractTHData',
    'HKCU\Software\Classes\SystemFileAssociations\.xlsx\shell\ExtractTHData',
    'HKCU\Software\Classes\SystemFileAssociations\.json\shell\OpenNoiseSurvey',
    'HKCR\Directory\Background\shell\ExtractTHData',
    'HKCR\Svan.File\shell\ExtractTHData',
    'HKCR\*\shell\ExtractTHData',
    'HKCR\SystemFileAssociations\.svl\shell\ExtractTHData',
    'HKCR\SystemFileAssociations\.svn\shell\ExtractTHData',
    'HKCR\SystemFileAssociations\.csv\shell\ExtractTHData',
    'HKCR\SystemFileAssociations\.xls\shell\ExtractTHData',
    'HKCR\SystemFileAssociations\.xlsx\shell\ExtractTHData'
)
foreach ($key in $keys) { try { & reg.exe delete $key /f 2>$null | Out-Null } catch { } }
Write-NsaOk 'Right-click menus removed.'

# --- Desktop shortcut --------------------------------------------------------
$shortcut = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Noise Survey Analysis.lnk'
if (Test-Path $shortcut) { Remove-Item -Path $shortcut -Force -ErrorAction SilentlyContinue }
Write-NsaOk 'Desktop shortcut removed.'

# --- Local files -------------------------------------------------------------
$savedLogs = $null
if ($KeepLogs -and (Test-Path $paths.Logs)) {
    $savedLogs = Join-Path $env:TEMP ("NoiseSurveyAnalysis_logs_{0}" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
    Copy-Item -Path $paths.Logs -Destination $savedLogs -Recurse -Force -ErrorAction SilentlyContinue
}

if (Test-Path $paths.InstallRoot) {
    Remove-Item -Path $paths.InstallRoot -Recurse -Force -ErrorAction SilentlyContinue
}
if (Test-Path $paths.InstallRoot) {
    Write-NsaWarn "Some files could not be removed from $($paths.InstallRoot) - close the dashboard and run this again."
} else {
    Write-NsaOk 'Local application and Python environment removed.'
}

if ($savedLogs) { Write-NsaInfo "Logs kept at $savedLogs" }

Write-NsaSection 'Uninstall complete'
Write-NsaInfo 'Run setup_noise_survey.bat from the shared drive to reinstall at any time.'
Wait-NsaForUser
