# Deployment Guide

How the team's copy of Noise Survey Analysis is published and kept working.

## Locations

| | Path |
|---|---|
| Development | `G:\My Drive\Programing\Noise Survey Analysis` |
| Shared (team) | `G:\Shared drives\Venta\Software\Noise Survey Analysis` |

## How it works

The shared folder is synced (not streamed) to every machine by Google Drive, so
the application **runs in place from the shared drive**. There is no per-machine
copy of the code to keep in step — a deployment reaches everyone as soon as
Drive finishes syncing.

Only the machine-specific parts are local, under `%LOCALAPPDATA%\NoiseSurveyAnalysis\`:

| | |
|---|---|
| `venv\` | private Python environment the dashboard runs in |
| `pycache\` | Python bytecode cache, kept off the synced drive |
| `logs\` | setup and launch logs |
| `install.json` | what is installed, used to detect staleness |

Dependencies install from a **wheelhouse** on the shared drive
(`runtime\wheelhouse\cp313\` etc.) using `pip install --no-index`. That makes
installs deterministic and removes the dependency on PyPI, an internet
connection and any corporate proxy. PyPI is only a fallback.

`runtime\manifest.json` records the published version, which Python versions the
wheelhouse can serve, and the minimum Python. The launcher on each machine reads
it and repairs the local environment when anything no longer matches.

## Deploying

```powershell
cd "G:\My Drive\Programing\Noise Survey Analysis"
.\deploy\deploy_to_shared.ps1
```

| Flag | Effect |
|---|---|
| `-RebuildWheelhouse` | Re-download the pinned packages and publish them. Needed whenever `requirements-lock.txt` changes, and to add support for a new Python version. |
| `-WhatIf` | Show what would happen, change nothing. |
| `-SkipGitCheck` | Skip the uncommitted-changes prompt. |
| `-Destination <path>` | Publish somewhere else (for testing). |

The script warns about uncommitted changes before doing anything.

### What gets published

- `noise_survey_analysis\` — the Python package, excluding `__pycache__`, `*.pyc`,
  `.git`, and the stray `nul` / `repomix-output.xml` files that live in the dev tree
- `requirements.txt`, `requirements-lock.txt`
- `generate_job_config.py`, `combine_nti_reports.py`, `truncate_csv_by_date.py`
- `USER_GUIDE.txt`, `QUICKSTART.md`, `CONTROL_API.md`
- the team scripts from `deploy\share\` (setup, launch, diagnose, uninstall,
  generate_config, `_lib\`, `README.txt`)

Tests, `node_modules`, dev docs, plans, `tools\` and build artefacts are not
published. `config.json` on the share is never overwritten.

Stale files at the payload root that are no longer in the published set are
removed, so the share does not accumulate renamed or deleted files.

### Adding support for another Python version

The wheelhouse is per Python ABI. Run the deploy on a machine with that Python:

```powershell
.\deploy\deploy_to_shared.ps1 -RebuildWheelhouse
```

It adds `runtime\wheelhouse\cp312\` (or whichever) alongside the existing tags
and updates the manifest. Team machines pick the interpreter that matches an
available tag.

If a team member has a Python the wheelhouse does not cover, the install still
works — it just falls back to downloading from PyPI, and the log says so.

## Changing dependency versions

1. Edit `requirements-lock.txt` (pinned versions for the team) and, if the
   supported range has changed, `requirements.txt` (loose ranges for dev).
2. `.\deploy\deploy_to_shared.ps1 -RebuildWheelhouse`

Every machine notices the requirements hash has changed on next launch and
rebuilds its environment automatically. Nobody has to run setup again.

## What a team member does

Once, on a new machine:

```
G:\Shared drives\Venta\Software\Noise Survey Analysis\setup_noise_survey.bat
```

After that, the desktop shortcut. Setup:

- finds Python, or installs it via winget if absent (it re-scans the filesystem
  afterwards rather than trusting `PATH`, which is stale in the same process)
- builds the venv and installs from the wheelhouse
- verifies every package actually imports, rather than assuming pip succeeded
- checks for 64-bit VLC (audio only) and offers to install it
- registers the desktop shortcut and the Explorer right-click menus

`launch_noise_survey.bat` re-runs the health check on every start and repairs
silently, so a broken environment or a changed requirement fixes itself.

## Troubleshooting

Ask the team member to run:

```
G:\Shared drives\Venta\Software\Noise Survey Analysis\diagnose_noise_survey.bat
```

It writes a report to `%LOCALAPPDATA%\NoiseSurveyAnalysis\logs\` and opens it:
every Python found on the machine, the venv state, per-package import results,
VLC bitness, registry entries, and the tail of the last log. No survey data.

| Symptom | Cause and fix |
|---|---|
| "Application folder not found" | Google Drive not running, or the Venta shared drive not added for that account. |
| "main.py is missing" | Drive is still syncing. Wait, then retry. |
| Packages install but will not import | Usually a Python/wheelhouse ABI mismatch. The report shows both; publish a wheelhouse for their Python version. |
| Audio silent, everything else fine | VLC missing, or 32-bit VLC with 64-bit Python. |
| Port already in use | The launcher picks the next free port automatically from 5006. |

Force a full rebuild on a machine:

```
launch_noise_survey.bat -Repair
```

Remove everything local (leaves Python, VLC and all data alone):

```
uninstall_noise_survey.bat
```

## Rollback

The shared folder is not version-controlled. To roll back, check out the
previous commit in the development repo and deploy again:

```powershell
git checkout <commit>
.\deploy\deploy_to_shared.ps1
git checkout main
```
