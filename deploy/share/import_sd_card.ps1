[CmdletBinding()]
param([string]$JobNumber, [string]$DriveRoot, [string]$JobsFolder)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '_lib\nsa-common.ps1')
try {
    $paths = Get-NsaPaths -ShareRoot $PSScriptRoot
    $null = Start-NsaLog -Name 'sd-import'
    Assert-NsaReleaseComplete $paths
    if (-not $JobsFolder) { $JobsFolder = Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) 'Jobs' }
    if (-not (Test-Path -LiteralPath $JobsFolder)) {
        Add-Type -AssemblyName System.Windows.Forms
        $picker = New-Object Windows.Forms.FolderBrowserDialog
        $picker.Description = 'Choose the Venta Jobs folder (the folder containing the numbered jobs)'
        if ($picker.ShowDialog() -ne 'OK') { exit 0 }
        $JobsFolder = $picker.SelectedPath
        $picker.Dispose()
    }
    if (-not (Test-Path -LiteralPath $paths.SdImporter)) { throw 'SD importer is missing. Wait for Google Drive to finish syncing.' }
    & $paths.SdImporter -JobNumber $JobNumber -DriveRoot $DriveRoot -JobsBasePath $JobsFolder -KeepCardFiles
} catch {
    Write-NsaFail $_.Exception.Message
    Write-NsaInfo "Send this log to Steve: $(Get-NsaLogFile)"
    Wait-NsaForUser
    exit 1
}
