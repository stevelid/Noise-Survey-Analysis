<#
Noise Survey Analysis - deploy to the shared drive
==================================================

Publishes the current development tree to the team's shared-drive copy.

What it does
------------
1. Mirrors the application payload (Python package, entry scripts, docs) into
   "…\Software\Noise Survey Analysis\Noise Survey Analysis", excluding dev-only
   files, caches and junk.
2. Copies the team launcher scripts from deploy\share into the shared root.
3. Optionally rebuilds the offline wheelhouse (pip download of the pinned
   requirements) so team machines can install with no internet access.
4. Writes runtime\manifest.json recording the version and what the wheelhouse
   supports. The team launcher compares against this and self-repairs.

Usage
-----
    .\deploy\deploy_to_shared.ps1                     # code + scripts
    .\deploy\deploy_to_shared.ps1 -RebuildWheelhouse  # also refresh the wheels
    .\deploy\deploy_to_shared.ps1 -WhatIf             # show what would happen

Rebuild the wheelhouse whenever requirements-lock.txt changes, or when you want
to add support for another Python version (run it once per Python version, each
run adds a folder for that version's tag).
#>

[CmdletBinding()]
param(
    [string]$Destination = 'G:\Shared drives\Venta\Software\Noise Survey Analysis',
    [switch]$RebuildWheelhouse,
    [switch]$SkipGitCheck,
    [switch]$RemoveLegacyGit,
    [switch]$WhatIf
)

$ErrorActionPreference = 'Stop'

$RepoRoot  = Split-Path -Parent $PSScriptRoot
$ShareDir  = Join-Path $PSScriptRoot 'share'
$PayloadDest = Join-Path $Destination 'Noise Survey Analysis'
$RuntimeDest = Join-Path $Destination 'runtime'
$WheelDest   = Join-Path $RuntimeDest 'wheelhouse'

function Write-Step { param([string]$T) Write-Host "`n$T" -ForegroundColor Cyan; Write-Host ('-' * $T.Length) -ForegroundColor Cyan }
function Write-Ok   { param([string]$T) Write-Host "  [ok] $T" -ForegroundColor Green }
function Write-Warn2{ param([string]$T) Write-Host "  [!]  $T" -ForegroundColor Yellow }
function Write-Info2{ param([string]$T) Write-Host "  $T" -ForegroundColor Gray }

# Files copied to the payload root alongside the Python package.
$PayloadFiles = @(
    'requirements.txt',
    'requirements-lock.txt',
    'generate_job_config.py',
    'combine_nti_reports.py',
    'truncate_csv_by_date.py',
    'USER_GUIDE.txt',
    'QUICKSTART.md',
    'CONTROL_API.md'
)

# Junk that has crept into the package directory and must never ship.
$PackageExcludeFiles = @('*.pyc', 'nul', 'repomix-output.xml')
$PackageExcludeDirs  = @('__pycache__', '.git', '.pytest_cache')

Write-Step 'Noise Survey Analysis - deployment'
Write-Info2 "Source      : $RepoRoot"
Write-Info2 "Destination : $Destination"
if ($WhatIf) { Write-Warn2 'WhatIf mode - nothing will be written.' }

# --- Preconditions -----------------------------------------------------------

if (-not (Test-Path $Destination)) {
    throw "Destination not found: $Destination. Check that Google Drive is running and you can reach the Venta shared drive."
}
if (-not (Test-Path $ShareDir)) {
    throw "Launcher source folder not found: $ShareDir"
}
foreach ($f in @('requirements-lock.txt')) {
    if (-not (Test-Path (Join-Path $RepoRoot $f))) { throw "Required file missing from the repo: $f" }
}

if (-not $SkipGitCheck) {
    Push-Location $RepoRoot
    try {
        $dirty = & git status --porcelain 2>$null
        if ($LASTEXITCODE -eq 0 -and $dirty) {
            Write-Warn2 'You have uncommitted changes:'
            $dirty | Select-Object -First 20 | ForEach-Object { Write-Info2 $_ }
            if (-not $WhatIf) {
                $answer = Read-Host '  Deploy anyway? (y/N)'
                if ($answer -notmatch '^(y|yes)$') { Write-Info2 'Cancelled.'; exit 1 }
            }
        }
        $script:GitCommit = (& git rev-parse --short HEAD 2>$null)
        if ($LASTEXITCODE -ne 0) { $script:GitCommit = 'unknown' }
    } finally { Pop-Location }
} else {
    $script:GitCommit = 'skipped'
}

# --- 1. Application payload ---------------------------------------------------

Write-Step '1. Application code'

$roboCommon = @('/R:2', '/W:5', '/NFL', '/NDL', '/NJH', '/NJS', '/NP')
if ($WhatIf) { $roboCommon += '/L' }

$pkgArgs = @((Join-Path $RepoRoot 'noise_survey_analysis'), (Join-Path $PayloadDest 'noise_survey_analysis'), '/MIR')
$pkgArgs += @('/XD') + $PackageExcludeDirs
$pkgArgs += @('/XF') + $PackageExcludeFiles
$pkgArgs += $roboCommon

& robocopy.exe @pkgArgs | Out-Null
if ($LASTEXITCODE -ge 8) { throw "Failed to copy the Python package (robocopy exit code $LASTEXITCODE)." }
Write-Ok 'noise_survey_analysis package synced.'

foreach ($file in $PayloadFiles) {
    $src = Join-Path $RepoRoot $file
    if (-not (Test-Path $src)) { Write-Warn2 "$file not found in the repo - skipped."; continue }
    $fileArgs = @($RepoRoot, $PayloadDest, $file) + $roboCommon
    & robocopy.exe @fileArgs | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "Failed to copy $file (robocopy exit code $LASTEXITCODE)." }
}
Write-Ok "Support files synced ($($PayloadFiles.Count) candidates)."

# The old deployment left stale copies of files that have since been renamed or
# removed. Clear anything at the payload root that is no longer part of the set.
if (-not $WhatIf) {
    $keep = $PayloadFiles + @('config.json')      # config.json is the site's own, never touched
    foreach ($existing in @(Get-ChildItem -Path $PayloadDest -File -ErrorAction SilentlyContinue)) {
        if ($keep -notcontains $existing.Name) {
            Write-Warn2 "Removing stale file from the share: $($existing.Name)"
            Remove-Item -Path $existing.FullName -Force -ErrorAction SilentlyContinue
        }
    }
}

# Robocopy's /XD excludes a directory from the mirror in BOTH directions, so
# caches left by an earlier deployment are never cleaned up by /MIR. They have
# to be removed explicitly, otherwise every team machine syncs stale bytecode.
if (-not $WhatIf) {
    $purged = 0
    foreach ($name in @('__pycache__', '.pytest_cache')) {
        foreach ($dir in @(Get-ChildItem -Path $PayloadDest -Directory -Recurse -Force -Filter $name -ErrorAction SilentlyContinue)) {
            Remove-Item -Path $dir.FullName -Recurse -Force -ErrorAction SilentlyContinue
            $purged++
        }
    }
    if ($purged -gt 0) { Write-Ok "Removed $purged stale cache folder(s) from the share." }
}

# A previous deployment kept a git repository on the shared drive. It is around
# 190 MB of history that every team member now syncs for nothing, and rollback
# is done from the development repo instead. Deleting it is not reversible from
# here, so it needs an explicit switch.
$legacyGit = Join-Path $PayloadDest '.git'
if (Test-Path $legacyGit) {
    $size = [math]::Round((Get-ChildItem -Path $legacyGit -Recurse -File -Force -ErrorAction SilentlyContinue |
                           Measure-Object Length -Sum).Sum / 1MB)
    if ($RemoveLegacyGit -and -not $WhatIf) {
        Remove-Item -Path $legacyGit -Recurse -Force -ErrorAction SilentlyContinue
        if (Test-Path $legacyGit) { Write-Warn2 'Could not fully remove the legacy .git folder.' }
        else { Write-Ok "Removed the legacy git repository from the share (${size} MB reclaimed)." }
    } else {
        Write-Warn2 "The share still holds a legacy git repository (~${size} MB) that every team member syncs."
        Write-Info2 'Re-run with -RemoveLegacyGit to delete it. Rollback is done from the dev repo (see DEPLOYMENT.md).'
    }
}

# --- 2. Team launcher scripts -------------------------------------------------

Write-Step '2. Launcher and setup scripts'

$libArgs = @((Join-Path $ShareDir '_lib'), (Join-Path $Destination '_lib'), '/MIR') + $roboCommon
& robocopy.exe @libArgs | Out-Null
if ($LASTEXITCODE -ge 8) { throw "Failed to copy _lib (robocopy exit code $LASTEXITCODE)." }

$scriptArgs = @($ShareDir, $Destination, '*.ps1', '*.bat', '*.txt') + $roboCommon
& robocopy.exe @scriptArgs | Out-Null
if ($LASTEXITCODE -ge 8) { throw "Failed to copy the launcher scripts (robocopy exit code $LASTEXITCODE)." }
Write-Ok 'Setup, launch, diagnose, uninstall and config scripts synced.'

# Retire the superseded scripts from the previous deployment so nobody runs them.
$obsolete = @('fix_extract_th_context_menu.bat', 'fix_extract_th_context_menu.ps1', 'README.md')
if (-not $WhatIf) {
    foreach ($name in $obsolete) {
        $p = Join-Path $Destination $name
        if (Test-Path $p) { Remove-Item -Path $p -Force -ErrorAction SilentlyContinue; Write-Info2 "Removed obsolete $name" }
    }
}

# --- 3. Wheelhouse ------------------------------------------------------------

Write-Step '3. Offline package store (wheelhouse)'

$lockFile = Join-Path $RepoRoot 'requirements-lock.txt'
$pythonTag = & python -c "import sys;print('cp%d%d' % sys.version_info[:2])"
if ($LASTEXITCODE -ne 0) { throw 'Could not run python to determine the ABI tag.' }
$pythonTag = $pythonTag.Trim()

$tagDir = Join-Path $WheelDest $pythonTag
$existingWheels = 0
if (Test-Path $tagDir) { $existingWheels = @(Get-ChildItem -Path $tagDir -Filter '*.whl' -ErrorAction SilentlyContinue).Count }

if ($RebuildWheelhouse) {
    if ($WhatIf) {
        Write-Info2 "Would download wheels for $pythonTag into $tagDir"
    } else {
        # Stage locally first. Writing hundreds of MB of wheels straight onto a
        # File Stream drive is slow and half-finished downloads there are worse
        # than none at all.
        $staging = Join-Path $env:TEMP ("nsa_wheels_{0}" -f $pythonTag)
        if (Test-Path $staging) { Remove-Item -Path $staging -Recurse -Force }
        New-Item -ItemType Directory -Path $staging -Force | Out-Null

        Write-Info2 "Downloading wheels for $pythonTag (this takes a few minutes)..."
        & python -m pip download -r $lockFile -d $staging --only-binary=:all:
        if ($LASTEXITCODE -ne 0) {
            Write-Warn2 'Binary-only download failed; retrying and allowing source distributions.'
            & python -m pip download -r $lockFile -d $staging
            if ($LASTEXITCODE -ne 0) { throw 'pip download failed. The wheelhouse was not updated.' }
        }

        if (-not (Test-Path $tagDir)) { New-Item -ItemType Directory -Path $tagDir -Force | Out-Null }
        $wheelArgs = @($staging, $tagDir, '/MIR') + $roboCommon
        & robocopy.exe @wheelArgs | Out-Null
        if ($LASTEXITCODE -ge 8) { throw "Failed to copy the wheelhouse to the shared drive (exit code $LASTEXITCODE)." }
        Remove-Item -Path $staging -Recurse -Force -ErrorAction SilentlyContinue

        $existingWheels = @(Get-ChildItem -Path $tagDir -Filter '*.whl' -ErrorAction SilentlyContinue).Count
        Write-Ok "$existingWheels package files published for $pythonTag."
    }
} elseif ($existingWheels -gt 0) {
    Write-Info2 "Keeping the existing wheelhouse ($existingWheels files for $pythonTag). Use -RebuildWheelhouse to refresh."
} else {
    Write-Warn2 "No wheelhouse exists yet. Team machines will download from the internet instead."
    Write-Info2 'Run this again with -RebuildWheelhouse to make installs work offline.'
}

# --- 4. Manifest --------------------------------------------------------------

Write-Step '4. Manifest'

$tags = @()
if (Test-Path $WheelDest) {
    $tags = @(Get-ChildItem -Path $WheelDest -Directory -ErrorAction SilentlyContinue |
              Where-Object { @(Get-ChildItem -Path $_.FullName -Filter '*.whl' -ErrorAction SilentlyContinue).Count -gt 0 } |
              ForEach-Object { $_.Name })
}

# Preferred Python versions, newest first, derived from what the wheelhouse can
# actually serve. Setup uses this to choose (or install) an interpreter.
$preferred = @($tags | ForEach-Object {
    if ($_ -match '^cp(\d)(\d+)$') { "$($Matches[1]).$($Matches[2])" }
} | Sort-Object { [Version]$_ } -Descending)
if ($preferred.Count -eq 0) { $preferred = @('3.13', '3.12', '3.11') }

$version = '{0}.{1}' -f (Get-Date -Format 'yyyy.MM.dd'), (Get-Date -Format 'HHmm')

$manifest = [ordered]@{
    app_name          = 'Noise Survey Analysis'
    version           = $version
    deployed_at       = (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
    deployed_by       = $env:USERNAME
    git_commit        = $script:GitCommit
    payload_dir       = 'Noise Survey Analysis'
    requirements_file = 'requirements-lock.txt'
    min_python        = '3.10'
    preferred_python  = $preferred
    wheelhouse_tags   = $tags
}

if ($WhatIf) {
    Write-Info2 'Would write manifest:'
    Write-Info2 (($manifest | ConvertTo-Json -Depth 5) -replace "`r`n", "`n  ")
} else {
    if (-not (Test-Path $RuntimeDest)) { New-Item -ItemType Directory -Path $RuntimeDest -Force | Out-Null }
    $manifest | ConvertTo-Json -Depth 5 | Set-Content -Path (Join-Path $RuntimeDest 'manifest.json') -Encoding UTF8
    Write-Ok "Version $version published."
    if ($tags.Count -gt 0) { Write-Ok "Offline installs supported for: $($tags -join ', ')" }
    else { Write-Warn2 'No offline package store - team machines will need internet access.' }
}

# --- Done ---------------------------------------------------------------------

Write-Step 'Deployment complete'
Write-Info2 'Team members do not need to do anything - the next time they open the'
Write-Info2 'dashboard from their desktop shortcut it updates itself.'
Write-Info2 ''
Write-Info2 'A new team member runs, once:'
Write-Info2 "  $Destination\setup_noise_survey.bat"
Write-Host ''
