# Quick Start

Get the dashboard running and load a survey config in under a minute.

## 1. One-time setup

```powershell
cd "G:\My Drive\Programing\Noise Survey Analysis"
pip install -r requirements.txt
```

Also install **VLC Media Player** (any recent version) if you want audio playback — it's only needed for that, not for charts/data.

## 2. Start the server

```powershell
cd "G:\My Drive\Programing\Noise Survey Analysis"
bokeh serve noise_survey_analysis --unused-session-lifetime 300000
```

Leave this PowerShell window open — the server keeps running here. `Ctrl+C` to stop it.

> The `--unused-session-lifetime 300000` flag matters for large surveys: it gives the server up to 5 minutes to finish loading data before an idle browser tab gets discarded. Without it, a slow first load on a big dataset can get killed and silently restart.

## 3. Open the dashboard and load a config

**If you already have a config JSON for the job** (`noise_survey_config_XXXX.json`), put its path in the URL:

```
http://localhost:5006/noise_survey_analysis?config=G:/Shared%20drives/Venta/Jobs/XXXX%20Job%20Name/XXXX%20Surveys/noise_survey_config_XXXX.json
```

- Use **forward slashes**, and URL-encode spaces as `%20`.
- Open this URL **once**. Every new tab/reload starts a fresh session against the same server — reopening it is how you get duplicate sessions, not how you refresh the view.
- First load of a large survey (multi-GB audio, hundreds of MB of log data) can take a while — the page shows "Initializing Dashboard..." until it's ready. This is normal; don't reload while it's working.

**If you don't have a config yet**, generate one:

```powershell
cd "G:\My Drive\Programing\Noise Survey Analysis"
python generate_job_config.py <job_number>
```

This scans the job's Surveys folder and writes `noise_survey_config_<job_number>.json` next to the data. If it can't find the job (e.g. it searches from the wrong drive), pass the Jobs folder explicitly:

```powershell
python generate_job_config.py <job_number> "G:\Shared drives\Venta\Jobs"
```

Then use that generated file's path in the URL as above.

**No config at all / just exploring a folder?** Open the server with no query string:

```
http://localhost:5006/noise_survey_analysis
```

This shows an interactive file/data-source picker instead.

## Other useful modes

| Want to... | Command |
|---|---|
| Share a report without needing a server | `python -m noise_survey_analysis.main --generate-static "<config_path>"` — produces a self-contained HTML file (no audio, no server needed) |
| Resume a saved workspace (regions, zoom, etc.) | `bokeh serve noise_survey_analysis --show --args --state "<workspace.json>"` |
| Script the dashboard (CLI/HTTP control) | Add `--args --config "<config>" --control-port 8765` — see `CONTROL_API.md` |

## Troubleshooting

- **Blank page / "Initializing Dashboard..." never finishes:** almost always still working, not stuck — parsing a large `*_log.csv` and aligning multi-GB audio files (especially over a Shared Drive) can genuinely take a minute or two the *first* time. Give it a few minutes before assuming it's hung. Subsequent loads of the same data are much faster (cached).
- **Reopening the URL didn't refresh anything:** it created a second, independent session instead. Close the extra tab and reuse the original one.
- **Audio doesn't play:** confirm VLC is installed and that the position actually has audio files (`audio` source type in the config).
- Full option/API reference: `README.md` and `CONTROL_API.md`. Day-to-day workflow conventions (which folder holds what, launch-mode choices): `G:\My Drive\Venta AI\skills\load-survey-analysis\core.md`.
