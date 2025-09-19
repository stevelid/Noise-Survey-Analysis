[CmdletBinding()]
param(
    [string]$Destination = 'C:\Dev\NoiseSurveyAnalysis',
    [switch]$Clean
)

$repoRoot = Split-Path -Parent $PSScriptRoot
$destinationPath = [System.IO.Path]::GetFullPath($Destination)

if ($Clean -and (Test-Path -LiteralPath $destinationPath)) {
    if ($destinationPath -like 'C:\*') {
        Write-Host "Cleaning existing destination '$destinationPath'" -ForegroundColor Yellow
        Remove-Item -LiteralPath $destinationPath -Recurse -Force
    }
    else {
        throw "Refusing to clean destination outside of C:\ drive: $destinationPath"
    }
}

if (!(Test-Path -LiteralPath $destinationPath)) {
    New-Item -ItemType Directory -Path $destinationPath | Out-Null
}

$directoriesToCopy = @(
    'noise_survey_analysis',
    'tests'
)

$filesToCopy = @(
    'package.json',
    'package-lock.json',
    'vitest.config.js',
    'requirements.txt',
    '.gitattributes',
    '.gitignore',
    'README.md'
)

function Copy-Directory {
    param(
        [string]$RelativePath
    )

    $source = Join-Path $repoRoot $RelativePath
    if (!(Test-Path -LiteralPath $source)) {
        Write-Warning "Skipping missing directory '$RelativePath'"
        return
    }

    $destination = Join-Path $destinationPath $RelativePath
    if (!(Test-Path -LiteralPath $destination)) {
        New-Item -ItemType Directory -Path $destination | Out-Null
    }

    $robocopyArgs = @('/E', '/NFL', '/NDL', '/NJH', '/NJS', '/NC', '/NS')

    & robocopy "$source" "$destination" @robocopyArgs | Out-Null
    $exitCode = $LASTEXITCODE
    if ($exitCode -gt 7) {
        throw "Robocopy failed for '$RelativePath' with exit code $exitCode"
    }
}

function Copy-File {
    param(
        [string]$RelativePath
    )

    $source = Join-Path $repoRoot $RelativePath
    if (!(Test-Path -LiteralPath $source)) {
        Write-Warning "Skipping missing file '$RelativePath'"
        return
    }

    $destination = Join-Path $destinationPath $RelativePath
    $destinationDir = Split-Path -Parent $destination
    if (!(Test-Path -LiteralPath $destinationDir)) {
        New-Item -ItemType Directory -Path $destinationDir | Out-Null
    }

    Copy-Item -LiteralPath $source -Destination $destination -Force
}

Write-Host "Syncing project files to $destinationPath" -ForegroundColor Cyan

foreach ($dir in $directoriesToCopy) {
    Copy-Directory -RelativePath $dir
}

foreach ($file in $filesToCopy) {
    Copy-File -RelativePath $file
}

Write-Host "Sync complete. Run tests from '$destinationPath'" -ForegroundColor Green
