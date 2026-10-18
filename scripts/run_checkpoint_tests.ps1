# Run verification against an immutable local snapshot; never sync source back.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidatePattern('^[a-zA-Z0-9_-]+$')][string]$Stage,
    [string]$Repository = (Split-Path -Parent $PSScriptRoot),
    [string]$Python = 'python',
    [string]$LocalRoot = (Join-Path $env:TEMP 'nsa-annotation-tests'),
    [ValidateSet('vitest', 'python', 'playwright')][string[]]$Suites = @('vitest', 'python', 'playwright'),
    [string[]]$PythonTests = @('tests/'),
    [switch]$CopyOnly
)

$ErrorActionPreference = 'Stop'
$Repository = (Resolve-Path -LiteralPath $Repository).Path
$runName = '{0}-{1}-{2}' -f $Stage, (Get-Date -Format 'yyyyMMdd-HHmmss'), ([guid]::NewGuid().ToString('N').Substring(0, 8))
$runRoot = Join-Path $LocalRoot $runName
$copyRoot = Join-Path $runRoot 'repo'
$evidenceRoot = Join-Path $runRoot 'evidence'
$driveEvidence = Join-Path $Repository ('docs/evaluation/{0}/{1}' -f $Stage, $runName)
New-Item -ItemType Directory -Path $copyRoot, $evidenceRoot -Force | Out-Null

function Get-SnapshotManifest([string]$Base, [string[]]$Paths) {
    $manifest = [ordered]@{}
    foreach ($relative in $Paths) {
        $absolute = Join-Path $Base $relative
        if (Test-Path -LiteralPath $absolute -PathType Leaf) {
            $manifest[$relative] = (Get-FileHash -LiteralPath $absolute -Algorithm SHA256).Hash
        }
    }
    return $manifest
}

function Invoke-Logged([string]$Name, [string]$Executable, [string[]]$Arguments) {
    Write-Host "[$Name] running; log: $(Join-Path $evidenceRoot ($Name + '.log'))"
    $started = Get-Date
    # Native output is captured in full, while the caller receives a bounded tail.
    $savedPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & $Executable @Arguments *> (Join-Path $evidenceRoot ($Name + '.log'))
    $code = $LASTEXITCODE
    $ErrorActionPreference = $savedPreference
    $entry = [ordered]@{ command = (@($Executable) + $Arguments); exitCode = $code; durationSeconds = [math]::Round(((Get-Date) - $started).TotalSeconds, 3) }
    $results[$Name] = $entry
    Write-Host "[$Name] exit $code after $($entry.durationSeconds)s"
    Get-Content -LiteralPath (Join-Path $evidenceRoot ($Name + '.log')) -Tail 14 | Write-Host
    return $code
}

$paths = @(& git -C $Repository ls-files --cached --others --exclude-standard)
if ($LASTEXITCODE -ne 0) { throw 'Cannot enumerate original repository snapshot.' }
# Evidence and generated data are intentionally not part of the source snapshot.
$paths = @($paths | Where-Object { $_ -notmatch '^(docs/evaluation/|output/|node_modules/|\.playwright-cli/|\.playwright-mcp/|tools/.+/(results|data|tfhub_cache)/)' })
$sourceBefore = Get-SnapshotManifest $Repository $paths
$metadata = [ordered]@{
    stage = $Stage; run = $runName; startedUtc = (Get-Date).ToUniversalTime().ToString('o')
    originalRepository = $Repository; localCopy = $copyRoot; localEvidence = $evidenceRoot
    evidenceDestination = $driveEvidence; head = (& git -C $Repository rev-parse HEAD).Trim()
    sourceStatus = @(& git -C $Repository status --short); sourceFileCount = $sourceBefore.Count
    results = [ordered]@{}
}
$results = $metadata.results
$sourceBefore | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $evidenceRoot 'source-manifest.json') -Encoding utf8

$excluded = @('.git', 'node_modules', '__pycache__', '.pytest_cache', '.venv', 'venv', 'output', 'test-results', 'playwright-report', '.playwright-mcp', '.playwright-cli', $driveEvidence, (Join-Path $Repository 'docs/evaluation'))
foreach ($tool in @('music_detection_benchmark', 'panns_benchmark', 'yamnet_benchmark')) {
    foreach ($leaf in @('results', 'data', 'tfhub_cache')) { $excluded += Join-Path $Repository "tools/$tool/$leaf" }
}
& robocopy $Repository $copyRoot /E /XJ /R:1 /W:1 /NFL /NDL /NP /XD @excluded /XF nul '*.pyc' '.coverage*' 'repomix-output.xml' *> (Join-Path $evidenceRoot 'copy.log')
$metadata.copyExitCode = $LASTEXITCODE
if ($LASTEXITCODE -ge 8) { throw "Robocopy failed: exit $LASTEXITCODE; see $evidenceRoot/copy.log" }
$copyBefore = Get-SnapshotManifest $copyRoot $paths
if (($sourceBefore | ConvertTo-Json -Compress) -ne ($copyBefore | ConvertTo-Json -Compress)) { throw 'Local snapshot does not match the original source manifest.' }
$metadata.sourceStableDuringCopy = (($sourceBefore | ConvertTo-Json -Compress) -eq ((Get-SnapshotManifest $Repository $paths) | ConvertTo-Json -Compress))
if (-not $metadata.sourceStableDuringCopy) { throw 'Original source changed during copy; retry a fresh snapshot.' }
Write-Host "Local source snapshot ready: $copyRoot"

try {
    Push-Location $copyRoot
    # Use the selected interpreter for direct tests and subprocesses invoking python.
    $pythonExecutable = (& $Python -B -c 'import sys; print(sys.executable)').Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Selected Python cannot start.' }
    $env:PATH = (Split-Path -Parent $pythonExecutable) + ';' + $env:PATH
    $env:PYTHONPATH = $copyRoot
    $metadata.python = (& $pythonExecutable -B -c "import sys,bokeh,pytest; print(sys.version); print('bokeh='+bokeh.__version__); print('pytest='+pytest.__version__); assert bokeh.__version__ == '3.4.1'") -join "`n"
    if ($LASTEXITCODE -ne 0) { throw 'Python runtime must provide pytest and Bokeh 3.4.1.' }
    $metadata.node = (& node --version).Trim()
    $metadata.npm = (& npm.cmd --version).Trim()
    if (-not $CopyOnly) {
        if (($Suites -contains 'vitest') -or ($Suites -contains 'playwright')) {
            $installCode = Invoke-Logged 'npm-ci' 'npm.cmd' @('ci', '--no-audit', '--no-fund')
            if ($installCode -ne 0) { Write-Warning 'npm ci failed; JS suites will still run to record their actual result.' }
        }
        if ($Suites -contains 'vitest') {
            $null = Invoke-Logged 'vitest' 'npm.cmd' @('test', '--', '--run', '--reporter=default', '--reporter=json', ('--outputFile=' + (Join-Path $evidenceRoot 'vitest.json')))
        }
        if ($Suites -contains 'python') {
            $pytestArguments = @('-m', 'pytest') + $PythonTests + @(('--junitxml=' + (Join-Path $evidenceRoot 'pytest.xml')))
            $null = Invoke-Logged 'pytest' $pythonExecutable $pytestArguments
        }
        if ($Suites -contains 'playwright') {
            $null = Invoke-Logged 'playwright-install' 'npx.cmd' @('--no-install', 'playwright', 'install', 'chromium')
            $env:PLAYWRIGHT_JSON_OUTPUT_NAME = Join-Path $evidenceRoot 'playwright.json'
            $null = Invoke-Logged 'playwright' 'npx.cmd' @('--no-install', 'playwright', 'test', '--reporter=list,json', ('--output=' + (Join-Path $evidenceRoot 'playwright-artifacts')))
        }
    }
}
finally {
    Pop-Location
    $copyAfter = Get-SnapshotManifest $copyRoot $paths
    $metadata.copiedSourceUnchanged = (($copyBefore | ConvertTo-Json -Compress) -eq ($copyAfter | ConvertTo-Json -Compress))
    $metadata.counts = [ordered]@{}
    if (Test-Path -LiteralPath (Join-Path $evidenceRoot 'vitest.json')) {
        $vitest = Get-Content -LiteralPath (Join-Path $evidenceRoot 'vitest.json') -Raw | ConvertFrom-Json
        # Vitest 1.6 counts skipped cases as passed in its top-level JSON totals.
        $assertions = @($vitest.testResults | ForEach-Object { $_.assertionResults } | Where-Object { $_.status })
        $metadata.counts.vitest = @{ total = $assertions.Count; passed = @($assertions | Where-Object status -eq 'passed').Count; failed = @($assertions | Where-Object status -eq 'failed').Count; skipped = @($assertions | Where-Object status -eq 'skipped').Count; pending = @($assertions | Where-Object status -eq 'pending').Count }
    }
    if (Test-Path -LiteralPath (Join-Path $evidenceRoot 'pytest.xml')) {
        [xml]$pytest = Get-Content -LiteralPath (Join-Path $evidenceRoot 'pytest.xml') -Raw
        $suite = $pytest.testsuites.testsuite
        $metadata.counts.pytest = @{ total = $suite.tests; failures = $suite.failures; errors = $suite.errors; skipped = $suite.skipped }
    }
    if (Test-Path -LiteralPath (Join-Path $evidenceRoot 'playwright.json')) {
        $playwright = Get-Content -LiteralPath (Join-Path $evidenceRoot 'playwright.json') -Raw | ConvertFrom-Json
        $metadata.counts.playwright = $playwright.stats
    }
    $metadata.finishedUtc = (Get-Date).ToUniversalTime().ToString('o')
    $metadata.failedSteps = @($results.GetEnumerator() | Where-Object { $_.Value.exitCode -ne 0 } | ForEach-Object { $_.Key })
    $metadata.suitesPassed = ($metadata.failedSteps.Count -eq 0) -and $metadata.copiedSourceUnchanged
    # Keep generated caches/results local; only evidence travels back to Drive.
    $metadata | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $evidenceRoot 'run.json') -Encoding utf8
    New-Item -ItemType Directory -Path $driveEvidence -Force | Out-Null
    Get-ChildItem -LiteralPath $evidenceRoot -Force | Copy-Item -Destination $driveEvidence -Recurse -Force
    Write-Host "Evidence: $driveEvidence"
    Write-Host "Copied source unchanged: $($metadata.copiedSourceUnchanged)"
}
if (-not $metadata.suitesPassed) { exit 1 }
