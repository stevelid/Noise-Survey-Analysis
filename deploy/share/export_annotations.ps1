<# Drop a workspace JSON onto export_annotations.bat for a full-resolution CSV. #>
[CmdletBinding()]
param(
    [Parameter(Position = 0)][string]$InputPath,
    [string]$Config,
    [string]$Output,
    [switch]$IncludeAllResolutions,
    [ValidateRange(0.001, 86400)][double]$BackgroundWindowSeconds = 300,
    [ValidateRange(0, 172800)][double]$MinimumContextSeconds = 60
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '_lib\nsa-common.ps1')
try {
    if (-not $InputPath) {
        Add-Type -AssemblyName System.Windows.Forms
        $picker = New-Object System.Windows.Forms.OpenFileDialog
        $picker.Filter = 'Workspace or annotation file|*.json;*.csv'
        $picker.Title = 'Choose a workspace or annotation export'
        if ($picker.ShowDialog() -ne 'OK') { exit 0 }
        $InputPath = $picker.FileName
    }
    $InputPath = (Resolve-Path -LiteralPath $InputPath).Path
    if ($Config) { $Config = (Resolve-Path -LiteralPath $Config).Path }
    if ($Output) { $Output = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Output) }
    $paths = Get-NsaPaths -ShareRoot $PSScriptRoot
    $ready = Invoke-NsaEnsureReady -Paths $paths -Quiet
    if (-not $ready.Ready) { throw 'Run setup_noise_survey.bat to repair the Python environment.' }
    $repository = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
    $application = if (Test-Path -LiteralPath (Join-Path $repository 'noise_survey_analysis')) { $repository } else { $paths.App }
    Push-Location $application
    try {
        if ([IO.Path]::GetExtension($InputPath) -eq '.csv' -and -not $Config) {
            # Pass the path as an argument, never interpolate it into Python code.
            # A self-contained v2 CSV needs no extra configuration picker.
            $probeArguments = @('-c', 'import sys; from noise_survey_analysis.export.annotations import load_annotation_input; sys.exit(0 if load_annotation_input(sys.argv[1]).get(''sourceConfigs'') else 2)', $InputPath)
            $probeOutput = @(& $paths.VenvPython @probeArguments 2>&1)
            $probeCode = $LASTEXITCODE
            if ($probeCode -eq 2) {
                Add-Type -AssemblyName System.Windows.Forms
                $picker = New-Object System.Windows.Forms.OpenFileDialog
                $picker.Filter = 'Survey source configuration|*.json'
                $picker.Title = 'Choose source data config for this annotation CSV'
                if ($picker.ShowDialog() -ne 'OK') { exit 0 }
                $Config = $picker.FileName
            } elseif ($probeCode -ne 0) {
                throw ('Could not read annotation CSV: ' + ($probeOutput -join [Environment]::NewLine))
            }
        }
    } finally { Pop-Location }
    $arguments = @('-m', 'noise_survey_analysis.export.annotations', $InputPath)
    if ($Config) { $arguments += @('--config', $Config) }
    if ($Output) { $arguments += @('--output', $Output) }
    if ($IncludeAllResolutions) { $arguments += '--include-all-resolutions' }
    $culture = [Globalization.CultureInfo]::InvariantCulture
    $arguments += @('--background-window-s', $BackgroundWindowSeconds.ToString($culture), '--min-context-s', $MinimumContextSeconds.ToString($culture))
    Push-Location $application
    try { & $paths.VenvPython @arguments; $resultCode = $LASTEXITCODE }
    finally { Pop-Location }
    if ($resultCode -ne 0) { throw "Export failed (exit $resultCode)." }
    Write-NsaOk 'Export complete. The CSV is beside the workspace unless an output path was supplied.'
} catch {
    Write-NsaFail $_.Exception.Message
    Wait-NsaForUser
    exit 1
}
Wait-NsaForUser
