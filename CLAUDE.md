# Noise Survey Analysis — Claude Code Quick Reference

## Project Overview
Bokeh-based interactive dashboard for acoustic noise survey data. Python backend + JavaScript Redux-style frontend.

## Key Paths
- Main app entry: `noise_survey_analysis/main.py`
- Dashboard builder: `noise_survey_analysis/visualization/dashBuilder.py`
- JS app logic: `noise_survey_analysis/js/` (Redux store, thunks, reducers, renderers)
- Static export: `noise_survey_analysis/export/static_export.py`
- Config generator: `generate_job_config.py`

## Running the Dashboard
```bash
cd "G:/My Drive/Programing/Noise Survey Analysis"
bokeh serve noise_survey_analysis --show --args --config "<path_to_config.json>"
```

## Generating a Static HTML Export
```bash
bokeh serve noise_survey_analysis --port 5007 --args --config "<path_to_config.json>" --create-static
# Then trigger a browser session to initiate export:
curl -s "http://localhost:5007/noise_survey_analysis" -o /dev/null
```
Output is saved next to the config file, named `{job_number}_survey_dashboard.html`.

## Config File Format
Stored in the job's surveys directory as `noise_survey_config_{job}.json`. Auto-generate with:
```bash
python generate_job_config.py <job_number>
```

## Playwright Testing (Static HTML)
```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1600, "height": 900})
    page.goto("file:///path/to/dashboard.html")
    page.wait_for_load_state("networkidle", timeout=30000)
    # ... test actions
    browser.close()
```

### Bokeh Model Access (Bokeh 3.x — IMPORTANT)
`doc._all_models` is a **Map**, not a plain object:
```javascript
const models = [...doc._all_models.values()];  // correct
Object.values(doc._all_models)                  // WRONG — returns []
```

### Programmatic Zoom
Set both `DataRange1d` (main charts) and `Range1d` (navigator) — must update both:
```python
page.evaluate("""
    () => {
        const doc = Bokeh.documents[0];
        const models = [...doc._all_models.values()];
        const dateRanges = models.filter(
            m => (m.type === 'Range1d' || m.type === 'DataRange1d') && m.start > 1e12
        );
        const newEnd = dateRanges[0].start + 6 * 3600 * 1000;
        dateRanges.forEach(r => { r.end = newEnd; });
    }
""")
```

## Architecture Summary
Unidirectional data flow: event handler → thunk → action → reducer → selector → renderer.
See AGENTS.md for full architectural details.

## Environment Notes
- Repo lives on Google Drive (`G:\My Drive\Programing\Noise Survey Analysis\`)
- Node tooling (npm, Vitest) must be run from a local non-synced path
- Python scripts run fine from the Drive path
