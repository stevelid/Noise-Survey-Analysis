[CmdletBinding()]
param([string]$InputFile)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '_lib\nsa-common.ps1')
try {
    $paths = Get-NsaPaths -ShareRoot $PSScriptRoot
    $null = Start-NsaLog -Name 'meter-file'
    if (-not $InputFile) {
        Add-Type -AssemblyName System.Windows.Forms
        $picker = New-Object Windows.Forms.OpenFileDialog
        $picker.Title = 'Choose a meter file'
        $picker.Filter = 'Meter files|*.svl;*.svn;*.cil;*.csv;*.xls;*.xlsx;*.txt|All files|*.*'
        if ($picker.ShowDialog() -ne 'OK') { exit 0 }
        $InputFile = $picker.FileName
        $picker.Dispose()
    }
    $InputFile = (Resolve-Path -LiteralPath $InputFile -ErrorAction Stop).ProviderPath
    $result = Invoke-NsaEnsureReady -Paths $paths -Quiet
    if (-not $result.Ready) { throw 'The installation could not be prepared. Run setup_noise_survey.bat.' }
    if ([IO.Path]::GetExtension($InputFile) -ieq '.txt') {
        Write-NsaInfo 'NTi reports are read directly by the dashboard.'
        Write-NsaInfo 'In the dashboard, scan the folder containing this report and its matching log/spectrum files.'
        & (Join-Path $PSScriptRoot 'launch_noise_survey.ps1')
        exit $LASTEXITCODE
    }
    $parser = Join-Path $paths.ShareSlm 'src\process_files.py'
    # Only --no-pause: preserve the Noise Sentry install/retrieval trim prompts.
    & $paths.VenvPython $parser $InputFile --no-pause
    $code = $LASTEXITCODE
    if ($code -ne 0) { throw "The meter file could not be processed (code $code). Keep the original and send Steve the log." }
    Write-NsaOk 'Processed successfully. The log and summary CSV files are beside the original.'
} catch {
    Write-NsaFail $_.Exception.Message
    Write-NsaInfo "Send this log to Steve: $(Get-NsaLogFile)"
    Wait-NsaForUser
    exit 1
}
Wait-NsaForUser
