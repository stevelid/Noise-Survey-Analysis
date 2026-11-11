[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$ReleaseRoot, [Parameter(Mandatory=$true)][string]$InstallRoot)
$ErrorActionPreference = 'Stop'
$env:NSA_INSTALL_ROOT = $InstallRoot
$env:NSA_NONINTERACTIVE = '1'
. (Join-Path $ReleaseRoot '_lib\nsa-common.ps1')
$paths = Get-NsaPaths -ShareRoot $ReleaseRoot
$initialVlc = Get-NsaVlcStatus
if ($initialVlc.Installed) {
    $env:PYTHON_VLC_LIB_PATH = $initialVlc.Path
    $env:PYTHON_VLC_MODULE_PATH = Split-Path -Parent $initialVlc.Path
    $env:PATH = $env:PYTHON_VLC_MODULE_PATH + ';' + $env:PATH
}
$lock = Join-Path $paths.App 'requirements-lock.txt'
if (-not (Test-NsaVenvHealthy $paths.VenvPython $lock)) { throw 'Fresh environment is unhealthy.' }
Write-Host 'PASS: native imports and all pinned versions'
$fakeLock = Join-Path $InstallRoot 'test-wrong-lock.txt'
Set-Content -LiteralPath $fakeLock -Value 'numpy==0.0.1' -Encoding ASCII
if (Test-NsaVenvHealthy $paths.VenvPython $fakeLock) { throw 'Wrong package version was accepted.' }
Remove-Item -LiteralPath $fakeLock -Force
Write-Host 'PASS: wrong package version detected'
$refused = $false
try { Assert-NsaLocalPath 'C:\Windows' } catch { $refused = $true }
if (-not $refused) { throw 'Outside-install mutation path was accepted.' }
Write-Host 'PASS: outside-install path refused'
$ready = Invoke-NsaEnsureReady -Paths $paths -Quiet
if (-not $ready.Ready -or $ready.Rebuilt) { throw 'Repeat setup unnecessarily rebuilt the environment.' }
Write-Host 'PASS: repeat setup keeps the healthy environment'
# Explicitly exercise the portable audio route even on a PC with VLC installed.
if (-not (Install-NsaVlc)) { throw 'Portable audio install failed.' }
$vlc = Get-NsaVlcStatus
$env:PYTHON_VLC_LIB_PATH = $vlc.Path
$env:PYTHON_VLC_MODULE_PATH = Split-Path -Parent $vlc.Path
$env:VLC_PLUGIN_PATH = Join-Path $env:PYTHON_VLC_MODULE_PATH 'plugins'
$env:PATH = $env:PYTHON_VLC_MODULE_PATH + ';' + $env:PATH
$audioProbe = Join-Path $InstallRoot 'test-audio.py'
@'
import vlc
instance = vlc.Instance('--no-video')
assert instance is not None
print('PASS: portable libVLC loads and creates a player', vlc.libvlc_get_version())
instance.release()
'@ | Set-Content -LiteralPath $audioProbe -Encoding ASCII
& $paths.VenvPython $audioProbe
if ($LASTEXITCODE -ne 0) { throw 'Portable audio runtime cannot load.' }
Remove-Item -LiteralPath $audioProbe -Force
Write-Host 'Installer integration checks passed.'
