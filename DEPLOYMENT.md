# Team deployment

Development source: `G:\My Drive\Programing\Noise Survey Analysis`.
Team release: `G:\Shared drives\Venta\Software\Noise Survey Analysis`.
The team runs `START_HERE.bat` once on each PC, and again to refresh shortcuts.
The user guide is `deploy/share/README.txt`, published as `README.txt`.

Current published release: `2026.11.04.1222` (4 November 2026). The shared
copy includes the current dashboard, meter parsers, canonical SD importer and
YAMNet helper scripts. The optional classification TensorFlow environment stays
separate from the dashboard’s pinned runtime. See `deploy/RELEASE_CHECKS.md`.

## Supported installation

Windows 10/11 on Intel/AMD x64, with built-in Windows PowerShell 5.1.
No administrator account, system Python, winget, PATH changes or installed VLC
are required. The package uses a private Python 3.13 x64 and a private audio
runtime. ARM and 32-bit Windows are outside this release's tested scope.

Python uses the official Python NuGet distribution, including its standard
library, venv and pip. See [Python's Windows documentation](https://docs.python.org/3.13/using/windows.html#the-nuget-org-packages).
The Python and VLC archives retain their licence files. Their source URLs and
checksums are recorded in `runtime/bootstrap.json`. This avoids Windows Installer
and Store alias failures. The existing Python/VLC installations are unchanged.

Application code runs from the shared folder. Google Drive must have completed
syncing. Mark the entire software folder Available offline for offline use;
mark the relevant job folder offline too. Jobs paths follow the share's drive
letter. A copied package can also browse local data, and the SD importer offers
a Jobs-folder picker when it cannot locate the normal shared Jobs directory.

Local files are under `%LOCALAPPDATA%\NoiseSurveyAnalysis`: `python`, `venv`,
`vlc`, `pycache`, `logs`, and `install.json`. These are private per Windows user.

## Publish

```powershell
# Only needed initially or when changing bundled Python/audio versions:
.\deploy\prepare_bootstrap.ps1

# Current code, parsers, SD importer and launcher scripts:
.\deploy\deploy_to_shared.ps1

# If requirements-lock.txt changed and wheels are not already available:
.\deploy\deploy_to_shared.ps1 -RebuildWheelhouse
```

For another destination, create the dedicated folder and pass `-Destination`
to both scripts. The deploy script also accepts `-WhatIf` and `-SkipGitCheck`.
Default parser source is the sibling `SLM Parsers\SLM Parsers\src` repository;
`-ParserSource` overrides it. `-SdImporterSource` defaults to the canonical
Venta AI `skills/import-sd/scripts/sd-import-interactive.ps1`.

Each release includes the current dashboard package (including its NTi parser),
SVAN 971/958A and Noise Sentry parsers, .cil decoder, interactive SD importer,
launchers, guides, a complete 23-package lock and offline x64 cp313 wheels.
The parser publication excludes raw surveys, manuals, caches and the abandoned
experimental USB downloader. Manufacturer USB applications and Venta Excel
add-ins are outside this package; NTi reports are read directly by the dashboard.
SD import copies and verifies raw files. It does not create Excel TH workbooks.

Before changing code, deployment checks the offline package resolution and
backs up the previous application, parser and launcher files to
`runtime/previous-releases/<timestamp>.zip`. It then writes `runtime/updating.txt`.
A failed deployment leaves that marker so users cannot start a partial release;
fix the cause and deploy again. Do not remove the marker to bypass a failed release.
At completion it writes the manifest and SHA256 inventory, then removes the marker.
Setup and launches verify the inventory, so incomplete Drive syncs fail clearly.

A changed complete lock triggers a local environment rebuild. Health checks
import native libraries and compare every pinned distribution version. Install
uses only binary wheels, tries the offline wheelhouse first, and only contacts
PyPI as a bounded fallback. There is no unconditional pip upgrade/network check.
A per-user mutex prevents simultaneous environment rebuilds.

`-RebuildWheelhouse` must run with Python 3.13 x64. Other Python ABIs are not a
substitute for the published cp313 package store. The current tested direct
versions are intentionally retained; do not upgrade libraries without rerunning
the release checks. Every transitive dependency is pinned too.

The launcher binds to loopback, permits localhost and 127.0.0.1 websocket
origins, selects a free port, and captures server output in local logs.
All context menus use the same repair/health route as the dashboard.
Re-run setup after moving the share or changing its Windows integration.

## Release checks

The tests under `deploy/tests` operate on isolated local fixtures. Example:

```powershell
# Deploy into a local dedicated release folder, with runtime assets prepared.
# Point local installation at a disposable directory (never another app's folder).
$env:NSA_INSTALL_ROOT = 'C:\Temp\Venta NSA clean install'
$env:NSA_NONINTERACTIVE = '1'
& 'C:\Temp\Venta NSA release\setup_noise_survey.ps1' -NoIntegration
.\deploy\tests\test_installer.ps1 -ReleaseRoot 'C:\Temp\Venta NSA release' -InstallRoot $env:NSA_INSTALL_ROOT
.\deploy\tests\test_explorer_integration.ps1 -ReleaseRoot 'C:\Temp\Venta NSA release'
.\deploy\tests\test_sd_import.ps1 -Importer 'C:\Temp\Venta NSA release\SD Card Import\sd-import-interactive.ps1'
& "$env:NSA_INSTALL_ROOT\venv\Scripts\python.exe" .\deploy\tests\smoke_parsers.py 'C:\Temp\Venta NSA release'
```

`NSA_INSTALL_ROOT` and `NSA_NONINTERACTIVE` are test hooks, not user setup steps.
The normal desktop/Explorer integration is suppressed by `-NoIntegration`.
The integration test redirects its registry keys and desktop to isolated fixtures.
The SD test uses synthetic cards, including a 101 MB WAV and NTi recovery files.

Run application Python tests and JavaScript tests too. JavaScript tests must run
from a local non-synced directory; the development Drive node_modules is damaged.
See `deploy/RELEASE_CHECKS.md` for the tested release and remaining limits.

## Recovery

Users run `diagnose_noise_survey.bat` and send the resulting local report.
It includes package/import status, paths, registry commands and recent errors.
Close the dashboard console before a forced rebuild (`launch_noise_survey.bat -Repair`).
Uninstall removes this tool's local portable runtimes, menus and shortcuts;
shared code and survey data are untouched.

For rollback, first stop publishing, retain the failing release for comparison,
and restore the preceding ZIP's files into the same shared release directory.
Restore the preceding pinned wheel set if dependencies changed. Rebuild the
inventory with `python deploy/release_integrity.py create <release-folder>`,
then remove a stale updating marker only after confirming the restored release.
The archive includes the prior manifest, lock and inventory; it excludes the
large wheelhouse and bootstrap archives, which are retained separately.
