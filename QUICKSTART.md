# Quick Start

## One-time setup

Open `G:\Shared drives\Venta\Software\Noise Survey Analysis` and run
`START_HERE.bat`. Setup supplies the private Python, required packages and audio
runtime. Run it again after moving the folder or to refresh shortcuts/menus.

## Open a survey

Use the **Noise Survey Analysis** desktop shortcut. In the data selector, enter
the job number and scan the job’s Surveys folder. If a config already exists,
right-click `noise_survey_config_XXXX.json` and choose **Open in Noise Survey Analysis**.

A configured launch can also be made from PowerShell:

```powershell
& "G:\Shared drives\Venta\Software\Noise Survey Analysis\launch_noise_survey.ps1" -ConfigPath "<full config path>"
```

The shared launcher checks its runtime, chooses a free port and opens the survey.
Keep the console open. Load a large survey once and allow parsing/alignment to
finish; reopening a URL creates another independent dashboard session.

## Generate a config

Use `generate_config.bat` in the shared folder, or:

```powershell
& "G:\Shared drives\Venta\Software\Noise Survey Analysis\generate_config.ps1" -JobNumber 1234
```

This saves the config alongside the survey data. For a subset of measurements,
add `-ScanDir "<survey subfolder>"`.

## Other modes

- Restore a workspace: use the shared launcher with `-StatePath "<workspace.json>"`.
- Enable local CLI control: add `-ControlPort 8765`; see `CONTROL_API.md`.
- Static HTML export: from the shared payload folder, use the installed private
  Python with `-m noise_survey_analysis.main --generate-static "<config>"`.

## Troubleshooting

Run `diagnose_noise_survey.bat` for a report. Run `START_HERE.bat` to repair the
runtime/integration. For audio, check that the position has audio files and that
setup’s audio check passed. A first load can take minutes for a large survey.

Team guide: `README.txt` in the shared release root. Workflow instructions:
`G:\Shared drives\Venta\Venta AI\skills\load-survey-analysis\core.md`.
