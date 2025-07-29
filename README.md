# Noise Survey Analysis Tool

An interactive Bokeh application for loading, analyzing, and visualizing noise survey data from various sound level meters.

## Overview

This tool provides a dashboard for analyzing noise survey data from multiple positions and file types simultaneously. It is designed for performance and interactivity, even with large datasets.

## Usage

This application generates a standalone HTML dashboard from noise survey data. The primary method for configuring the application is through the `config.json` file.

### 1. Configure the Data Sources

Before running the application, open the `config.json` file and edit it to point to your data files.

**Example `config.json`:**
```json
{
  "output_filename": "my_survey_dashboard.html",
  "sources": [
    {
      "position_name": "Svan (North)",
      "enabled": true,
      "file_paths": [
        "path/to/your/svan_log.csv",
        "path/to/your/svan_summary.csv"
      ]
    },
    {
      "position_name": "NS (South)",
      "enabled": true,
      "file_paths": [
        "path/to/your/ns_log.csv",
        "path/to/your/ns_summary.csv"
      ]
    },
    {
      "position_name": "Disabled Position",
      "enabled": false,
      "file_paths": [
        "path/to/another/log.csv"
      ]
    }
  ]
}
```

**Configuration Options:**

*   `output_filename`: The name of the HTML file that will be generated.
*   `sources`: A list of data sources to include in the dashboard. Each source has the following properties:
    *   `position_name`: A descriptive name for the measurement location. This will be displayed in the dashboard.
    *   `enabled`: Set to `true` to process this source, or `false` to skip it.
    *   `file_paths`: A list of file paths for the data from this position. You can include log files, summary files, etc.

### 2. Generate the Dashboard

Once you have configured your data sources, run the main script from your terminal:
```bash
python noise_survey_analysis/main.py
```

The script will read the `config.json` file, process the data, and save the HTML dashboard.

### Output Location

The generated HTML file will be saved in the lowest common parent directory of all the `enabled` source files. For example, if all your files are in subfolders of `G:/Shared drives/Venta/Jobs/5980 Overstrand Road, Cromer/5980 Surveys/`, the dashboard will be saved in that `5980 Surveys` folder.

If the source files do not share a common path (e.g., they are on different drives), the dashboard will be saved in the project's root directory.

### Key Features

*   **Multi-Source Data Import:** Load data from various formats, including NTi TXT, Svan CSV/XLSX, and Noise Sentry CSV.
*   **Time Series Visualization:** Display broadband sound levels (e.g., LAeq, LAF90) on interactive time history charts.
*   **Advanced Spectral Analysis:**
    *   High-performance spectrograms using Bokeh's Image glyph.
    *   Interactive frequency slice bar chart that updates on hover/click.
*   **Synchronized Chart Interaction:**
    *   Pan and zoom on one chart updates all other time-based charts.
    *   A global range selector provides an overview for easy navigation.
    *   Hovering over charts shows data details and a synchronized vertical line.
    *   Clicking on a chart sets a persistent cursor and updates the "Frequency Slice" bar chart at the bottom.
*   **Synchronized Audio Playback:**
    *   Listen to audio synchronized with the visualization timeline (requires VLC).
    *   Controls for play/pause, playback speed, and volume boost.
*   **Keyboard Navigation:** Use arrow keys for time-stepping and the spacebar for play/pause.
*   **Static HTML Export:** Generate a standalone HTML file of the dashboard for sharing (with no live backend).

## Project Structure

```
├── noise_survey_analysis/
│   ├── core/                 # Core functionality (config, data management, parsing, processing, audio, callbacks)
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── data_manager.py
│   │   ├── data_parsers.py
│   │   ├── data_processors.py
│   │   ├── audio_handler.py
│   │   └── app_callbacks.py
│   ├── ui/                   # UI Widget and Component creation
│   │   ├── __init__.py
│   │   └── components.py
│   ├── visualization/        # Dashboard orchestration
│   │   ├── __init__.py
│   │   └── dashBuilder.py
│   ├── js/                   # Helper for loading JS code
│   │   └── loader.py
│   ├── static/js/            # Client-side JavaScript for interactivity
│   │   └── app.js
│   ├── __init__.py
│   └── main.py               # Main Bokeh application entry point and orchestrator
├── tests/                      # (Future location for Pytest tests)
├── README.md                 # This file
└── GEMINI.md                 # Development notes for the Gemini agent
```

## Requirements

*   Python 3.8+
*   Bokeh (`pip install bokeh`)
*   Pandas (`pip install pandas`)
*   NumPy (`pip install numpy`)
*   `python-vlc` (`pip install python-vlc`)
*   `openpyxl` (for reading Svan `.xlsx` files: `pip install openpyxl`)
*   **VLC Media Player:** Must be installed separately on your system for audio playback to function.

## How to Run

### Configure Data Sources:

Open `noise_survey_analysis/main.py` and edit the `SOURCE_CONFIGURATIONS` list. For each position you want to analyze, add a dictionary specifying its `position_name` and the `file_paths` or `file_path`.

```python
# Example from noise_survey_analysis/main.py
SOURCE_CONFIGURATIONS = [
    # NTi position with multiple data files and an audio directory
    {"position_name": "SiteNTi", "file_paths": {
        r"G:\Path\To\Your\2025-02-15_SLM_000_RTA_3rd_Log.txt",
        r"G:\Path\To\Your\2025-02-15_SLM_000_123_Log.txt"
    }, "enabled": True},
    {"position_name": "SiteNTi", "file_path": r"G:\Path\To\Your\Audio\Directory", "enabled": True},

    # Svan position with summary and log files
    {"position_name": "East", "file_paths": {
        r"G:\Path\To\Your\summary.csv",
        r"G:\Path\To\Your\log.csv"
    }, "enabled": True},
]
```

### Run the Application:

Navigate to the project's root directory in your terminal and use one of the following commands:

**For the live interactive server (with audio):**

```bash
bokeh serve noise_survey_analysis/main.py
```

**To generate a static, standalone HTML file (no audio or live interaction):**

```bash
python noise_survey_analysis/main.py
```

This will create a `noise_survey_dashboard_static.html` file in the project root.

### Interact with the Dashboard:

*   **Visibility:** Use the checkboxes in the top control panel to show or hide individual charts.
*   **Zoom/Pan:** Use the range selector at the top to select a time period, or use mouse wheel/drag gestures on the main charts. All time charts are linked.
*   **Inspect Data:** Hover over any chart to see a gray line with live data details. Click on a chart to set a persistent red cursor, which also updates the "Frequency Slice" bar chart at the bottom.
*   **Audio:** Click the "Play" button for a specific position to start audio playback from the red cursor's timestamp.
*   **Keyboard:**
    *   **Left/Right Arrow Keys:** Step the red cursor through time.
    *   **Spacebar:** Toggle audio play/pause for the currently selected position.

## Core Architectural Concepts

### Data Flow

The application follows a clear, structured data flow:

*   **Configuration (`main.py`):** The `SOURCE_CONFIGURATIONS` list defines what data to load.
*   **Data Management (`data_manager.py`):** `DataManager` iterates through the configs. For each file, it uses `NoiseParserFactory` to get the correct parser.
*   **Parsing (`data_parsers.py`):** The appropriate parser (e.g., `NTiFileParser`) reads a file and converts it into a standardized `ParsedData` object, separating broadband (`totals_df`) and spectral (`spectral_df`) data.
*   **Aggregation (`data_manager.py`):** `DataManager` adds the `ParsedData` to a `PositionData` object, which aggregates all data for a single measurement position (e.g., merging a log file and a report file for the same site).
*   **Processing (`data_processors.py`):** Before visualization, `GlyphDataProcessor` transforms the raw spectral DataFrames into the specific, pre-padded data structures required by Bokeh's `Image` glyph for spectrograms.
*   **Component Creation (`components.py`):** Classes like `TimeSeriesComponent` and `SpectrogramComponent` create the individual Bokeh figures and their `ColumnDataSources`.
*   **Dashboard Assembly (`dashBuilder.py`):** `DashBuilder` orchestrates the entire process: it calls the data processor, instantiates all UI components, assembles them into a final layout, and sets up the JavaScript bridge.

### The JavaScript Bridge

Communication between the Python backend and the JavaScript front-end is managed by the `DashBuilder`. It constructs a single dictionary of all necessary Bokeh models (charts, sources, widgets) and passes it to the `app.js` script upon initialization.

This approach avoids scattering `CustomJS` callbacks with tangled arguments throughout the Python code. The `_assemble_js_bridge_dictionary` method in `DashBuilder` is the single source of truth for the models provided to the front end.

```javascript
// A simplified view of how app.js receives the models
// const models = {
//     charts: [figure1, figure2, ...],
//     timeSeriesSources: { 'Position1': { overview: cds, log: cds }, ... },
//     preparedGlyphData: { 'Position1': { ...prepared data... } },
//     audio_controls: { 'Position1': { play_toggle: button, ... } },
//     barSource: frequency_bar_chart_cds,
//     ... other models
// };
window.NoiseSurveyApp.init(models, /* options */);
```

### Spectrogram Data Handling: The Fixed-Size Buffer Solution

A key technical challenge is efficiently displaying high-resolution spectrograms. Bokeh's `Image` glyph is highly performant but requires its data source to have a fixed size after initialization. You cannot send a smaller or larger data array to update it later.

This application solves this with a two-part strategy:

1.  **Python-Side Padding:** In `data_processors.py`, a `MAX_DATA_SIZE` constant defines a fixed chunk length. All spectral data, whether it's low-resolution overview or high-resolution log data, is padded to this exact size before being sent to the browser. This ensures the JavaScript `ColumnDataSource` is always initialized with a consistently sized data buffer.
2.  **JavaScript In-Place Updates:** In `app.js`, when a user zooms to a level where high-resolution data should be shown, the code does not try to replace the data source. Instead, it:
    *   Calculates the slice of data corresponding to the visible time range from the full dataset held in memory.
    *   Uses a utility function to extract this data slice, ensuring it matches the buffer's fixed size (padding if necessary).
    *   Directly modifies the contents of the existing `source.data.image[0]` array in-place.
    *   Calls `source.change.emit()` to notify Bokeh to redraw the spectrogram with the new visual data.

This method provides fast, responsive spectrograms by minimizing data transfer and avoiding the overhead of recreating Bokeh objects in the browser.

## Future Work

This project has a clear roadmap for enhancements:

*   **Enhanced File Input:** Allow selecting a parent directory to have the app automatically scan for and identify survey files.
*   **Annotations/Notes:** Implement a system to add, save, and load notes linked to specific timestamps on the charts.
*   **Statistical Analysis:** Add functionality to select a data range on the charts and calculate/display/copy key statistics (LAeq, L90, etc.) and average spectra for that period.
*   **Session Management:** Explore saving and loading a complete analysis session (file configurations, views, notes).