# TL;DR
See `QUICKSTART.md` for the fast path: start the server and load a job's config file.

bokeh serve noise_survey_analysis --show
bokeh serve noise_survey_analysis --show --args --config /path/to/your/workspace.json
python -m noise_survey_analysis.main --generate-static /path/to/your/config.json

**Create static HTML from live server (opt-in):**
bokeh serve noise_survey_analysis --show --args --create-static

# Noise Survey Analysis Tool

An interactive Bokeh application for loading, analyzing, and visualizing noise survey data from various sound level meters.

## Overview

This tool provides a powerful, interactive dashboard for analyzing noise survey data from multiple measurement positions and file types simultaneously. It is designed for performance and interactivity, even with large datasets from manufacturers like Svan, NTi, and Noise Sentry.

## Key Features

*   **Unified Dashboard:** View time history, spectrograms, and frequency data for multiple positions in a single, synchronized view.
*   **Multi-Source Data Import:** Automatically parses and aggregates data from various formats, including NTi `.txt`, Svan `.csv`/`.xlsx`, Noise Sentry `.csv`, and generic line-only tabular files.
*   **High-Performance Spectrograms:** Utilizes an efficient rendering strategy for smooth, interactive spectrograms, even with millions of data points.
*   **Synchronized Chart Interaction:**
    *   Pan and zoom on one chart updates all other time-based charts simultaneously.
    *   A global range selector provides a full survey overview for easy navigation.
    *   Hovering over charts shows live data details and a synchronized vertical line.
    *   Clicking on a chart sets a persistent cursor and updates a detailed "Frequency Slice" bar chart.
*   **Synchronized Audio Playback (Live Server Only):**
    *   Listen to `.wav` audio recordings synchronized with the visualization timeline.
    *   Audio start precedence is: parser-produced `*_audio_index.json` wave marker plus embedded WAV/BWF timestamp, embedded timestamp alone, then filesystem modified-time minus duration as a last resort.
    *   When high-resolution logger data is available, short bounded RMS-envelope correlation windows verify the proposed anchor and only apply a shift when multiple strong, unique matches agree. The playback panel shows anchor provenance and confidence.
    *   Playback seeks automatically when you click on the charts.
    *   Clear visual indicators show which position is currently playing.
    *   Controls for play/pause, playback speed, and a +20dB volume boost for quiet recordings.
*   **Audio File Scanning (Wider Format Support):**
    *   The audio directory scanner now uses `soundfile` (libsndfile) to read durations, enabling support for common formats like WAV, FLAC, OGG, etc. WAV remains supported even without `soundfile`.
*   **Keyboard Navigation:** Use arrow keys for fine-grained time-stepping.
*   **Static HTML Export:** Generate a single, self-contained HTML file of the dashboard for easy sharing and reporting (audio playback is disabled in static mode). This is now opt-in via `--create-static` flag when running the live server.
*   **Flexible Region Management:** Build multi-segment regions, merge related selections, and append new segments with the dedicated Add Area mode while metrics update automatically for the combined duration.

## Getting Started

### 1. Prerequisites

*   Python 3.10+ (the codebase uses `X | None` type syntax)
*   **VLC Media Player:** Must be installed on your system for audio playback to function in the live server mode.
*   `soundfile` Python package (included in `requirements.txt`) to read audio durations for multiple formats. On most platforms, wheels include `libsndfile`.
    *   If you build from source or encounter installation issues, install `libsndfile` via your OS package manager (e.g., `brew install libsndfile` on macOS, `apt-get install libsndfile1` on Debian/Ubuntu). Windows wheels typically bundle it.
*   Install the required Python packages:
    ```bash
    pip install -r requirements.txt
    ```

### 2. Run the Application

You can run the tool in three ways from your terminal:

**A) Live Interactive Server (Recommended)**

This is the primary mode for analysis. It starts a local web server and opens the interactive data source selector.

```bash
bokeh serve noise_survey_analysis --show
```

Your browser will open to the **Data Source Selector**, where you can:
*   **Scan a job directory** by providing a base path and job number.
*   **Drag and drop** data files or folders directly onto the window.
*   Select the files you want to include, assign position names, and load the dashboard.
*   **Save the selection** as a portable configuration file (`.json`) for quick reloading later.

**B) Live Server with a Configuration File**

If you have a previously saved configuration file, you can bypass the selector and load the dashboard directly. This is ideal for quickly revisiting a specific analysis.

```bash
bokeh serve noise_survey_analysis --show --args --config /path/to/your/config.json
```

**Optional: Generate Static HTML from Live Server**

By default, the live server does **not** generate static HTML files. To create a static HTML export while running the live server, add the `--create-static` flag:

```bash
# With data source selector
bokeh serve noise_survey_analysis --show --args --create-static

# With a config file
bokeh serve noise_survey_analysis --show --args --config /path/to/your/config.json --create-static
```

When `--create-static` is used, the application will generate a static HTML file in the background after you select data sources. The static file will be saved in the same directory as the auto-generated config file.

**C) Generate a Static HTML File**

This mode processes data from a specified configuration file and packages the dashboard into a single `.html` file that you can easily email or archive. Audio playback is disabled in this mode.

```bash
python -m noise_survey_analysis.main --generate-static /path/to/your/config.json
```

This will generate a dashboard HTML file in the same directory as your configuration file.

### 4. Configuration File Format (`.json`)

Configuration files are the most robust way to manage your data selections. They are generated automatically when you click "Save Config" in the Data Source Selector, but you can also edit them manually.

The format is designed to be portable, meaning you can move the config file along with its data, and the application will still be able to find the files.

Here is an example of the `v1.2` format:

```json
{
  "version": "1.2",
  "created_at": "2023-10-27T15:00:00.000000",
  "config_base_path": "C:/Users/YourUser/Documents/NoiseSurveys/Job1234",
  "sources": [
    {
      "path": "Svan/Logs/Position1_data.csv",
      "position": "North",
      "type": "svan_log",
      "parser_type": "svan"
    },
    {
      "path": "Audio/Position1/",
      "position": "North",
      "type": "audio_dir",
      "parser_type": "audio"
    },
    {
      "path": "NTi/Position2_data.txt",
      "position": "East",
      "type": "nti_log",
      "parser_type": "nti"
    }
  ]
}
```

**Key Fields:**

*   `"config_base_path"`: The absolute path to the directory that serves as the root for all relative paths below. This is the key to portability.
*   `"sources"`: A list of data source entries.
*   `"path"`: The path to the data file or directory, relative to the `config_base_path`. The application combines these two paths to find the data.
*   `"position"`: The name for the measurement position that appears in the dashboard.
*   `"parser_type"`: The specific parser to use (`svan`, `nti`, `sentry`, `audio`, `generic`, or `auto`).

### Generic parser (`parser_type: "generic"`)

Use `generic` when you want to plot line data from a non-standard file format without adding a dedicated parser.

Requirements:
*   At least one datetime-like column (`Datetime`, `Timestamp`, or a `Date` + `Time` pair).
*   At least one numeric column.

Behavior:
*   Loads data into time-series line charts only (`totals_df`).
*   Keeps only plottable numeric columns plus `Datetime`.
*   Does not produce spectral data (`spectral_df` stays empty).

Limitations:
*   Spectrogram charts and spectral parameter workflows are unavailable for generic sources.
*   Features that expect standard metrics (`LAeq`, `LAFmax`, `LAF90`, etc.) may show blank or `N/A` if those columns are not present in the source.

## Working with annotations

The Regions / Markers / Classifications sidebar stays beside the charts and scrolls independently. The region list fills the remaining height below selected-item details, with review filters collapsed initially. Less-used operations sit under **Actions and settings**.

### Regions across meters

A region is one sound event, with one or more time areas, an origin meter, a category and notes. Its state at each meter is **present** (`●`), **absent** (`✕`, checked and not there), or **unchecked** (`○`). The origin stays present; other meters initially remain unchecked.

- **Create:** Shift+drag on a chart, Shift+click from the current cursor, or press `R`, move the cursor, then press `R` again on the same meter.
- **Review other meters:** select the region, then click its meter buttons or its visible band on another chart. States cycle unchecked → present → absent → unchecked. Keys `1`–`9` address meters in display order. These keys ignore text fields, modifiers and held-key repeats.
- **Read the bands:** present uses the category colour; absent uses grey; unchecked uses a faint dashed ghost. Under Actions and settings, show ghosts for no regions, the selected region (default), or all regions.
- **Categorise:** choose a category, edit its name/colour, or add one. Click the native colour swatch to choose an opaque override; **Use category** clears it. Existing named/transparent colours remain unchanged until you choose a new colour or reset. Deleting a category reassigns its regions to Other.
- **Find events:** filter by category, present at a meter, present at one meter only, or remaining unchecked meters.
- **Inspect levels:** metrics start collapsed. Show metrics calculates the selected region at each meter; the show/hide choice is saved in the workspace. Resolution and missing values are explicit. The list itself does not calculate every region's levels.
- **Inspect a spectrum:** open Average spectrum under Actions and settings; it calculates the origin meter independently of the per-meter metrics table.
- **Refine:** use Add area, Merge or Split areas under Actions and settings. Merges require the same origin. Unchecked defers to a known state; present versus absent becomes unchecked and the message lists meters to re-check. Splits preserve category and states.
- **Take notes:** save on leaving the field or Ctrl+Enter; Esc cancels an HTML-panel draft. `N` focuses the selected region's note. `[` / `]` browse regions and `B` returns to the earlier view.
- **Undo:** Ctrl+Z / Ctrl+Y undo/redo annotation edits, meter states and category changes. Deleting a region removes that annotation across meters.

Comparison's **Make Region** creates one region with included meters present. Auto Day & Night creates one region per actual daytime/nighttime period across all meters, using survey civil time (Europe/London by default), including clock changes and partial periods at survey boundaries.

The copy-to-meter selector and copy-all button have been retired: the state strip records the same sound across meters without duplicate annotations. The sidebar uses the HTML implementation throughout.

### Markers and classifications

Markers remain global point annotations, drawn on every chart. Add one with `M` or a double-click; duplicate timestamps are rejected. Their saved metric snapshots, notes, colours and shortcuts are preserved. The duplicate Add Marker at Tap button has been retired. Clear all markers from the Markers tab and confirm the request; the main toolbar no longer offers an immediate clear-all action.

Classifications remain a separate candidate layer. Selection leaves the cursor, viewport and audio unchanged. Press `P` or Preview for explicit playback, use source/score/role filters, then **Elevate to Region** when a candidate deserves a manual annotation. Elevation reuses or creates its category and starts other meters unchecked.

## Importing, Exporting, and Restoring Your Work

### Annotation CSV files

**Menu → Export Annotations — Quick (CSV)** is the default annotation transfer: REGIONS, MARKERS and NOTES only. It preserves categories, notes, areas, meter states, offsets/source times and saved marker snapshots without calculating region levels. Headline metric fields are blank, and NOTES identifies the annotations-only mode.

**Menu → Export Annotations + Analysis (Browser CSV)** adds the browser's calculated levels and spectra in the full sectioned layout:

| Section | Purpose |
| --- | --- |
| REGIONS | One importable row per region: category, notes, colour override, areas, meter states, source-time provenance and headline origin levels. |
| OVERALL | One row per region × meter, including absent and unchecked meters, with broadband levels, background comparison and data resolution. |
| SPECTRAL | One row per region × meter × parameter, with frequency-ordered bands as columns. |
| MARKERS | Global marker annotations and their saved metric snapshots. |
| NOTES | Sources, offsets, calculation methods, resolution choices and caveats. |

Select a section's header and rows in Excel to format that section as a table. Times are Excel-compatible UTC date-times. Metadata preserves the category catalog and meter identities/titles. Import reads REGIONS and MARKERS; analysis rows never become annotations. Old unsectioned CSV and annotation JSON still import.

The browser analysis export uses the best available data for each region and meter: complete log coverage, then overview, then explicitly labelled partial log data if nothing better is available. Coverage and missing-data reasons prevent a streamed fragment from appearing complete. Under Actions and settings, configure the background window/minimum context and optionally include separate log/overview analysis rows; this option is off by default and does not add metric calculations to Quick export. These settings are saved in the workspace.

To calculate from the source files independently of the browser's streamed buffer, use **Menu → Export Annotations — Full Resolution** in server mode, or:

```powershell
nsa-ctl export-annotations --output "C:\Survey\annotations.full-resolution.csv"
nsa-ctl export-annotations --output "C:\Survey\both-resolutions.csv" --include-all-resolutions
```

The dashboard/control server must be running for `nsa-ctl`. For an independent export, drag a workspace or annotation CSV onto `export_annotations.bat`; saved source references must still resolve. Python loads source windows per meter instead of retaining all meter logs together. Its default selects complete log coverage, then overview, then partial log coverage if that is all available. Spectra make this choice independently for each parameter. Resolution, coverage and missing-data reasons are explicit; separate log/overview rows remain optional.

The default background is **LA90 of pooled context samples** from five minutes before/after each region area, excluding regions present at that meter; LAeq of the same usable context is also reported. At least sixty seconds is required. Configure the window/minimum through export options (`--background-window-s`, `--min-context-s`), and inspect NOTES for the applied settings. LAF90 from overview, 1 s data or interval levels is indicative. Missing genuine LAFmax stays blank.

For Python analysis, use `read_export_section(path, "OVERALL")` from `noise_survey_analysis.export.annotations` to obtain a DataFrame without manually splitting the file.

### Classification annotation files

Use **Menu ▸ Import Classifications (CSV/JSON)** or the **Classifications ▸ Import** button to load intervals produced by an external audio classifier. These intervals are kept in a separate layer from manual markers and regions. Importing a classification file replaces the current classification layer, but does not replace existing markers or regions.

CSV files must contain one row per classified interval. Required columns are `position_id`, `source_id`, `start`, and `end`. The parser also accepts common aliases such as `position`, `source`, `start_utc`, `end_utc`, `start_ms`, and `end_ms`.

Recommended CSV shape:

```csv
position_id,source_id,source_label,start,end,state,confidence,description,audio_file,color
P1,extract_fan,Extract fan,2026-06-20 13:05:10,2026-06-20 13:22:40,on,0.91,steady tonal fan,audio_001.wav,#e4572e
P2,music,Music,2026-06-20T21:15:00Z,2026-06-20T21:28:00Z,uncertain,0.62,possible amplified music,audio_009.wav,#7a5c99
```

Field notes:

* `position_id` must match the dashboard measurement position ID.
* `source_id` is the stable machine-readable source key, for example `extract_fan`.
* `source_label` is the display label shown in the panel.
* `start` and `end` may be epoch milliseconds or ISO-like date/time strings. Date/time strings without a timezone are treated as UTC.
* `state` may be `on`, `off`, or `uncertain`; blank values default to `on`.
* `confidence` may be `0-1` or `0-100`; both are normalised internally.
* `description`, `audio_file`, and `color` are optional.

JSON files may either be a bare array of classification objects or an object containing `classifications`, `audio_classifications`, or typed `annotations`:

```json
{
  "classifications": [
    {
      "positionId": "P1",
      "sourceId": "extract_fan",
      "sourceLabel": "Extract fan",
      "start": "2026-06-20T13:05:10Z",
      "end": "2026-06-20T13:22:40Z",
      "state": "on",
      "confidence": 0.91,
      "description": "steady tonal fan",
      "audioFile": "audio_001.wav",
      "color": "#e4572e"
    }
  ]
}
```

Imported classification intervals appear as low-height coloured lanes on the charts for their own position. Select an interval in the Classifications tab and use **Elevate to Region** to convert it into a normal region for metrics, notes, and reporting.

### Workspace saves

**Menu → Save Workspace** writes version 2 JSON containing annotations, categories, meter states, source references and UI settings. Load it from the menu or launch with `--state workspace.json`. Server source paths must still be available; static HTML can save and restore its browser annotation state, while server-only data/audio operations require the live application.

Version 1 files pass through an explicit migration. Legacy copies on different meters combine only when every normalized area endpoint matches within 1 ms and either a non-empty whitespace-normalized note or non-empty colour matches. A group uses a fixed representative and never combines two copies from the same origin; an import message reports how many copies merged. Version 2 annotations are not deduplicated. Unsupported future versions are rejected without replacing the current session.

Keep the original saved files when comparing older program versions: reverting code does not downgrade a version 2 workspace or sectioned CSV.

### Static HTML export from the dashboard menu

In live server sessions, use **Menu ▸ Generate Static HTML (Offline)** to create a self-contained HTML snapshot with overview/log data embedded for offline review. The export runs in the background and writes the file next to the auto-saved selector config.

## Project Structure

```
├── noise_survey_analysis/
│   ├── core/                 # Core backend logic
│   │   ├── __init__.py
│   │   ├── app_callbacks.py  # Python-side server callbacks
│   │   ├── app_setup.py      # Logic for loading and preparing configurations
│   │   ├── audio_handler.py  # VLC audio playback logic
│   │   ├── config.py         # Default configuration values
│   │   ├── data_manager.py   # Orchestrates data loading and aggregation
│   │   ├── data_parsers.py   # Parsers for different file formats (Svan, NTi, etc.)
│   │   ├── data_processors.py# Prepares data for complex Bokeh glyphs
│   │   └── utils.py          # Utility functions
│   ├── js/                   # Helper for loading JS code
│   │   └── loader.py
│   ├── static/js/            # Client-side JavaScript for interactivity
│   │   ├── app.js            # Main JS entry point
│   │   ├── core/             # Redux-style primitives (actions, root reducer)
│   │   │   ├── actions.js
│   │   │   └── rootReducer.js
│   │   ├── features/         # Feature-specific reducers, thunks, selectors, utils
│   │   │   ├── audio/
│   │   │   │   ├── audioReducer.js
│   │   │   │   └── audioThunks.js
│   │   │   ├── interaction/
│   │   │   │   ├── interactionReducer.js
│   │   │   │   └── interactionThunks.js
│   │   │   ├── markers/
│   │   │   │   ├── markersReducer.js
│   │   │   │   └── markersSelectors.js
│   │   │   ├── regions/
│   │   │   │   ├── regionReducer.js
│   │   │   │   ├── regionSelectors.js
│   │   │   │   ├── regionThunks.js
│   │   │   │   └── regionUtils.js
│   │   │   └── view/
│   │   │       ├── viewReducer.js
│   │   │       └── viewSelectors.js
│   │   ├── services/         # App-wide services and handlers
│   │   │   ├── eventHandlers.js
│   │   │   └── renderers.js
│   │   ├── chart-classes.js  # OO classes for charts
│   │   ├── data-processors.js# JS data processing (slicing, filtering)
│   │   ├── registry.js       # Registry wiring between models/controllers
│   │   ├── store.js          # Redux-like store implementation
│   │   ├── thunks.js         # Aggregated thunks facade
│   │   └── utils.js          # JS utility functions
│   ├── ui/                   # UI Widget and Component creation
│   │   ├── __init__.py
│   │   ├── components.py       # Stable imports for feature components
│   │   ├── component_parts/    # Panels, controls, charts and shared helpers
│   │   └── data_source_selector.py # The interactive UI for selecting data
│   ├── visualization/        # Dashboard assembly and orchestration
│   │   ├── __init__.py
│   │   └── dashBuilder.py
│   ├── __init__.py
│   └── main.py               # Main application entry point
├── config.json               # User configuration for data sources
├── README.md                 # This file
└── requirements.txt          # Python dependencies
```

## Additional Documentation

- **`.claude.md`** — Quick reference for Claude AI assistant (architecture summary, common patterns, launch modes)
- **`AGENTS.md`** — Comprehensive developer handbook (architectural principles, layer responsibilities, naming conventions)
- **`CONTROL_API.md`** — CLI and HTTP API reference for programmatic dashboard control
- **`DEPLOYMENT.md`** — Deployment guide for production environments
- **`HYBRID_CONTROL_PLAN.md`** — Historical design document for the control system (✅ completed)
- **`GLYPH_REFACTOR_OPTIONS.md`** — Architecture decision record for spectrogram streaming
- **`TODO.txt`** — Feature roadmap and improvement ideas
- **`USER_GUIDE.txt`** — Detailed user manual

---

## Core Architectural Concepts

### Data Flow

The application follows a clear, structured data flow:

*   **Application Start (main.py):** The app starts. If a `--config` argument is provided, it loads that file directly. Otherwise, it displays the interactive **Data Source Selector**.
*   **Data Selection (ui/data_source_selector.py):** The user selects files, which generates a source configuration in memory.
*   **Configuration Loading (core/app_setup.py):** The `load_config_and_prepare_sources` function parses the configuration (from file or the selector), resolves file paths, and groups data by position.
*   **Data Management (data_manager.py):** DataManager iterates through the configs. For each file path, it uses NoiseParserFactory to get the correct parser.
*   **Parsing (data_parsers.py):** The appropriate parser (e.g., NTiFileParser) reads a file and converts it into a standardized ParsedData object, separating broadband (totals_df) and spectral (spectral_df) data.
*   **Aggregation (data_manager.py):** DataManager adds the ParsedData to a PositionData object, which aggregates all data for a single measurement position (e.g., merging a log file and a summary file for the same site).
*   **Processing (data_processors.py):** Before visualization, GlyphDataProcessor transforms the raw spectral DataFrames into the specific, pre-padded data structures required by Bokeh's high-performance Image glyph.
*   **Component Creation (components.py):** Classes like TimeSeriesComponent and SpectrogramComponent create the individual Bokeh figures and their ColumnDataSources.
*   **Dashboard Assembly (dashBuilder.py):** DashBuilder orchestrates the entire process: it calls the data processor, instantiates all UI components, assembles them into a final layout, and sets up the JavaScript bridge.

### JavaScript State Management

The front-end interactivity is managed by a self-contained JavaScript application architecture (in `static/js/`). It follows a modern state management pattern similar to Redux:

*   **core/actions.js** defines the global action vocabulary and creators. `store.js` uses **core/rootReducer.js** to combine the feature reducers into the application state tree.
*   **features/** contains isolated slices for each domain (view, interaction, markers, regions, audio). Each feature provides its own reducer, selectors, and thunks so business logic stays modular.
*   **services/eventHandlers.js** listens for Bokeh UI events (e.g., tap, zoom), translates them into semantic thunks, and dispatches them.
*   **data-processors.js** computes derived data (e.g., slicing spectrogram buffers) whenever state changes.
*   **services/renderers.js** consumes the latest state plus derived data to update the visible Bokeh models.

This pattern keeps the code organized, predictable, and easier to debug and extend.

## Testing Notes

- Edit and commit in the Drive repository. Run `./scripts/run_checkpoint_tests.ps1 -Stage <checkpoint>` to create a fresh throwaway local snapshot and run Vitest, Python and Playwright there; Drive can produce unreliable test output. The runner excludes `.git` and `node_modules`, checks source hashes, and copies reports back to `docs/evaluation/`. Do not edit or commit in the local snapshot.
- `tests/data-processors-python-chain.test.js` is the seam test for spectrogram streaming. It generates a real Python reservoir payload with `tests/helpers/generate_spectrogram_chain_fixture.py` and feeds that payload into the JS selector logic.
- The chain test covers the edge cases that previously needed slow browser smoke tests: viewport inside the reservoir but outside the initial display chunk, near-edge pans that should still show log data, partial-overlap fallback, and oversized viewport fallback.


