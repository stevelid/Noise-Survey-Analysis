param([Parameter(Mandatory=$true)][string]$Importer)
$ErrorActionPreference = 'Stop'
$scratch = Join-Path $env:TEMP ('Venta SD test ' + [guid]::NewGuid().ToString('N'))
$jobs = Join-Path $scratch 'Jobs'
$job = Join-Path $jobs '9999 Installer test'
New-Item -ItemType Directory -Path $job -Force | Out-Null
function Read-Host { param([string]$Prompt) return 'y' }

$card = Join-Path $scratch 'Svantek card'
$data = Join-Path $card 'SVANTEK'
New-Item -ItemType Directory -Path $data -Force | Out-Null
Set-Content -LiteralPath (Join-Path $data 'meter.txt') -Value "meter=971-2`nserial=143568" -Encoding ASCII
Set-Content -LiteralPath (Join-Path $data 'L001.SVL') -Value 'synthetic parser fixture - not real meter data' -Encoding ASCII
$wav = Join-Path $data 'large.WAV'
$stream = [IO.File]::Create($wav)
$stream.SetLength(101MB)
$stream.Dispose()
& $Importer -JobNumber 9999 -DriveRoot $card -JobsBasePath $jobs -KeepCardFiles
$copied = Join-Path $job '9999 Surveys\971-2\large.WAV'
if (-not (Test-Path -LiteralPath $wav) -or (Get-FileHash -LiteralPath $wav).Hash -ne (Get-FileHash -LiteralPath $copied).Hash) { throw 'Svantek copy or source retention failed.' }
Write-Host 'PASS: Svantek file copy, SHA256 verification and >100 MB source retention'

$nti = Join-Path $scratch 'NTi card'
New-Item -ItemType Directory -Path (Join-Path $nti 'XL2_SYS'), (Join-Path $nti 'Projects\9999-4'), (Join-Path $nti 'RESTORE_AFTER_POWERFAIL') -Force | Out-Null
$date = (Get-Date).ToString('yyyy-MM-dd')
$report = Join-Path $nti ('RESTORE_AFTER_POWERFAIL\' + $date + '_SLM_001_123_Rpt_Report.txt')
Set-Content -LiteralPath $report -Value 'NTi XL2, SNo. A2A-15993-E0' -Encoding ASCII
& $Importer -JobNumber 9999 -DriveRoot $nti -JobsBasePath $jobs -KeepCardFiles
$copiedReport = Join-Path $job ('9999 Surveys\9999-4\' + [IO.Path]::GetFileName($report))
if ((Get-FileHash -LiteralPath $report).Hash -ne (Get-FileHash -LiteralPath $copiedReport).Hash) { throw 'NTi restore copy failed.' }
Write-Host 'PASS: NTi power-failure restore copy and source retention'
Write-Host "Synthetic fixtures retained at $scratch"
