param([Parameter(Mandatory=$true)][string]$ReleaseRoot)
$ErrorActionPreference = 'Stop'
. (Join-Path $ReleaseRoot '_lib\nsa-common.ps1')
$testId = [guid]::NewGuid().ToString('N')
$registryRoot = 'HKCU:\Software\VentaNSAInstallerTests\' + $testId
$desktop = Join-Path $env:TEMP ('Venta shortcut test ' + $testId)
New-Item -ItemType Directory -Path $desktop -Force | Out-Null
$tokens=$null; $parseErrors=$null
$ast = [Management.Automation.Language.Parser]::ParseFile((Join-Path $ReleaseRoot 'setup_noise_survey.ps1'), [ref]$tokens, [ref]$parseErrors)
if ($parseErrors) { throw 'Setup script does not parse.' }
$functions = $ast.FindAll({ param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -in @('Install-NsaSlmContextMenu','Install-NsaDashboardContextMenu','Install-NsaShortcut') }, $false)
foreach ($function in $functions) {
    # Exercise real setup functions with registry and Desktop redirected to
    # isolated fixtures. No existing shortcut or file association is changed.
    $body = $function.Extent.Text.Replace('HKCU:\Software\Classes', $registryRoot)
    $body = $body.Replace("[Environment]::GetFolderPath('Desktop')", ("'" + $desktop.Replace("'", "''") + "'"))
    $body = $body.Replace('Join-Path $PSScriptRoot', ("Join-Path '" + $ReleaseRoot.Replace("'", "''") + "'"))
    . ([scriptblock]::Create($body))
}
try {
    Install-NsaSlmContextMenu -SlmRoot (Join-Path $ReleaseRoot 'SLM Parsers') -VenvPython 'unused' -InstallRoot $desktop
    Install-NsaDashboardContextMenu -LaunchScript (Join-Path $ReleaseRoot 'launch_noise_survey.ps1')
    $command = (Get-Item -LiteralPath ($registryRoot + '\SystemFileAssociations\.cil\shell\ExtractTHData\command')).GetValue('')
    $expected = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $ReleaseRoot 'process_meter_file.ps1') + '" -InputFile "%1"'
    if ($command -cne $expected) { throw "Incorrect meter command: $command" }
    $jsonCommand = (Get-Item -LiteralPath ($registryRoot + '\SystemFileAssociations\.json\shell\OpenNoiseSurvey\command')).GetValue('')
    if ($jsonCommand -notlike '*-ConfigPath "%1"') { throw 'Incorrect config command quoting.' }
    Write-Host 'PASS: per-user meter/config menu commands, including .cil and paths containing spaces'
    Install-NsaShortcut -ShareRoot $ReleaseRoot
    $shell = New-Object -ComObject WScript.Shell
    foreach ($name in @('Noise Survey Analysis','Import SD Card','Process Meter File')) {
        $shortcut = $shell.CreateShortcut((Join-Path $desktop ($name + '.lnk')))
        if (-not (Test-Path -LiteralPath $shortcut.TargetPath) -or $shortcut.WorkingDirectory -ine $ReleaseRoot) { throw "Broken shortcut: $name" }
    }
    Write-Host 'PASS: all three desktop shortcuts resolve to existing launchers'
} finally {
    if ($registryRoot.StartsWith('HKCU:\Software\VentaNSAInstallerTests\')) {
        Remove-Item -LiteralPath $registryRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}
