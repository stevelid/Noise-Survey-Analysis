<#
Noise Survey Analysis - Generate a survey config
================================================

Scans a job's Surveys folder and writes noise_survey_config_<job>.json next to
the data, then offers to open it in the dashboard.

Usage: double-click generate_config.bat, or
       generate_config.ps1 -JobNumber 6306
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)][string]$JobNumber,
    [Parameter(Mandatory = $false)][string]$JobsFolder,
    [Parameter(Mandatory = $false)][string]$ScanDir
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '_lib\nsa-common.ps1')

try {
    $paths = Get-NsaPaths -ShareRoot $PSScriptRoot
    $log = Start-NsaLog -Name 'generate-config'

    Write-NsaSection 'Generate a survey config'

    $result = Invoke-NsaEnsureReady -Paths $paths -Quiet
    if (-not $result.Ready) {
        Write-NsaFail 'The installation is not usable. Run setup_noise_survey.bat first.'
        Wait-NsaForUser
        exit 1
    }

    if (-not $JobNumber) {
        $JobNumber = (Read-Host 'Job number (for example 6306)').Trim()
    }
    if (-not $JobNumber) { Write-NsaFail 'No job number given.'; Wait-NsaForUser; exit 1 }

    $script = Join-Path $paths.App 'generate_job_config.py'
    if (-not (Test-Path $script)) { throw "generate_job_config.py not found at $script" }

    $scriptArgs = @($script, $JobNumber)
    if ($JobsFolder) { $scriptArgs += $JobsFolder }
    if ($ScanDir)    { $scriptArgs += @('--scan-dir', $ScanDir) }

    Write-NsaInfo "Scanning survey data for job $JobNumber ..."
    Push-Location $paths.App
    try {
        & $paths.VenvPython @scriptArgs 2>&1 | ForEach-Object { Write-NsaLine "  $_" }
        $code = $LASTEXITCODE
    } finally {
        Pop-Location
    }

    if ($code -ne 0) {
        Write-NsaFail "The config could not be generated (exit code $code)."
        Write-NsaInfo 'If the job folder could not be found, run this again and give the Jobs folder explicitly:'
        Write-NsaInfo '  generate_config.ps1 -JobNumber 6306 -JobsFolder "G:\Shared drives\Venta\Jobs"'
        Wait-NsaForUser
        exit 1
    }

    Write-NsaOk 'Config written. Right-click the .json file and choose "Open in Noise Survey Analysis" to load it.'

} catch {
    Write-NsaLine ''
    Write-NsaFail $_.Exception.Message
    if (Get-NsaLogFile) { Write-NsaInfo "Log file: $(Get-NsaLogFile)" }
    Wait-NsaForUser
    exit 1
}

Wait-NsaForUser
