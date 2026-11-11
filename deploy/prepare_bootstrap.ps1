<# Download the official offline prerequisites. No installed software is changed. #>
[CmdletBinding()]
param([string]$Destination = 'G:\Shared drives\Venta\Software\Noise Survey Analysis')
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$runtime = Join-Path $Destination 'runtime'
$assets = Join-Path $runtime 'installers'
New-Item -ItemType Directory -Path $assets -Force | Out-Null
$specs = @(
    @{ Name='python'; Version='3.13.16'; File='python-3.13.16-nuget.zip';
       Url='https://api.nuget.org/v3-flatcontainer/python/3.13.16/python.3.13.16.nupkg';
       Sha256='95fad176338f1d6a799e45946488063f4aa61764e6cff2f132ddeffbf7a04c34' },
    @{ Name='vlc'; Version='3.0.24'; File='vlc-3.0.24-win64.zip';
       Url='https://download.videolan.org/pub/videolan/vlc/3.0.24/win64/vlc-3.0.24-win64.zip'; Sha256='' }
)
$result = [ordered]@{}
foreach ($spec in $specs) {
    $hash = $spec.Sha256
    if (-not $hash) {
        $checksum = (Invoke-WebRequest -UseBasicParsing -Uri ($spec.Url + '.sha256')).Content
        if ($checksum -is [byte[]]) { $checksum = [Text.Encoding]::UTF8.GetString($checksum) }
        if ($checksum -notmatch '\b([a-fA-F0-9]{64})\b') { throw "No official checksum for $($spec.File)" }
        $hash = $Matches[1]
    }
    $path = Join-Path $assets $spec.File
    if (-not (Test-Path -LiteralPath $path) -or (Get-FileHash -LiteralPath $path).Hash -ine $hash) {
        $tempFile = Join-Path $env:TEMP ([guid]::NewGuid().ToString() + '-' + $spec.File)
        Write-Host "Downloading $($spec.File)..."
        Invoke-WebRequest -UseBasicParsing -Uri $spec.Url -OutFile $tempFile
        if ((Get-FileHash -LiteralPath $tempFile).Hash -ine $hash) { throw "Checksum mismatch: $tempFile" }
        Copy-Item -LiteralPath $tempFile -Destination $path -Force
        Remove-Item -LiteralPath $tempFile -Force
    }
    $result[$spec.Name] = @{ version=$spec.Version; file=('installers/' + $spec.File); sha256=$hash; url=$spec.Url }
    Write-Host "Verified $($spec.File)"
}
$result | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $runtime 'bootstrap.json') -Encoding UTF8
