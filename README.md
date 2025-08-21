# Noise Survey Analysis Tool

An interactive Bokeh application for loading, analyzing, and visualizing noise survey data from various sound level meters.

## Overview

This tool provides a powerful, interactive dashboard for analyzing noise survey data from multiple measurement positions and file types simultaneously. It is designed for performance and interactivity, even with large datasets from manufacturers like Svan, NTi, and Noise Sentry.

## Key Features

*   **Unified Dashboard:** View time history, spectrograms, and frequency data for multiple positions in a single, synchronized view.
*   **Multi-Source Data Import:** Automatically parses and aggregates data from various formats, including NTi `.txt`, Svan `.csv`/`.xlsx`, and Noise Sentry `.csv`.
*   **High-Performance Spectrograms:** Utilizes an efficient rendering strategy for smooth, interactive spectrograms, even with millions of data points.
*   **Synchronized Chart Interaction:**
    *   Pan and zoom on one chart updates all other time-based charts simultaneously.
    *   A global range selector provides a full survey overview for easy navigation.
    *   Hovering over charts shows live data details and a synchronized vertical line.
    *   Clicking on a chart sets a persistent cursor and updates a detailed "Frequency Slice" bar chart.
*   **Synchronized Audio Playback (Live Server Only):**
    *   Listen to `.wav` audio recordings synchronized with the visualization timeline.
    *   Playback seeks automatically when you click on the charts.
    *   Clear visual indicators show which position is currently playing.
    *   Controls for play/pause, playback speed, and a +20dB volume boost for quiet recordings.
*   **Keyboard Navigation:** Use arrow keys for fine-grained time-stepping.
*   **Static HTML Export:** Generate a single, self-contained HTML file of the dashboard for easy sharing and reporting (audio playback is disabled in static mode).

## Getting Started

### 1. Prerequisites

*   Python 3.8+
*   **VLC Media Player:** Must be installed on your system for audio playback to function in the live server mode.
*   Install the required Python packages:
    ```bash
    pip install -r requirements.txt
    ```

### 2. Run the Application

You can run the tool in two modes from your terminal:

**A) Live Interactive Server (Recommended)**

This is the primary mode for analysis. It starts a local web server and opens an interactive data source selector.

```bash
bokeh serve noise_survey_analysis --show
```

Your browser will open to the **Data Source Selector**, where you can:
*   **Scan a job directory** by providing a base path and job number.
*   **Drag and drop** data files or folders directly onto the window.
*   Select the files you want to include, assign position names, and load the dashboard.
*   Optionally **save the selection** as a configuration file for quick reloading later.

**B) Live Server with Direct Configuration Load**

If you have a previously saved configuration file, you can bypass the selector and load the dashboard directly.

```bash
bokeh serve noise_survey_analysis --show --args --config /path/to/your/config.json
```

**C) Generate a Static HTML File**

This mode processes data from the default `config.json` and packages the dashboard into a single `.html` file that you can easily email or archive. Audio playback is disabled in this mode.

```bash
python noise_survey_analysis/main.py
```

This will generate the file specified by `output_filename` in `config.json`. The file will be saved in the lowest common directory of your source files.

### 4. Advanced Configuration (Manual `config.json`)

While the interactive Data Source Selector is the primary way to load data, you can still manually create or edit a `config.json` file. This is useful for generating static reports or for complex setups.

Here is an example demonstrating key features:

```json
{
  "output_filename": "advanced_survey_dashboard.html",
  "sources": [
    {
      "position_name": "North - Detailed",
      "enabled": true,
      "return_all_columns": true,
      "file_paths": [
        "C:\\path\\to\\data\\L259_log.csv",
        "C:\\path\\to\\data\\L259_summary.csv"
      ]
    },
    {
      "position_name": "East with Audio",
      "enabled": true,
      "file_paths": [
        "C:\\path\\to\\data\\Sentry_log.csv",
        "C:\\path\\to\\audio\\files\\"
      ]
    }
  ]
}
```

**Key Configuration Options:**

*   `"output_filename"`: (String) The name of the generated static HTML file.
*   `"sources"`: (List) A list of measurement positions.
*   `"position_name"`: (String) The name for the position that appears in the dashboard.
*   `"enabled"`: (Boolean) Set to `false` to exclude this position from loading.
*   `"file_paths"`: (List of Strings) A list of all files and directories for this position.
    *   **Audio Directories**: To include audio, simply add the path to the directory containing your `.wav` files. The application will automatically find and list them.
*   `"return_all_columns"`: (Boolean) Optional. If set to `true`, the parser will load every available column from the data file, not just the standard ones (like `LAeq`, `LAFmax`, etc.). This is useful for non-standard or diagnostic parameters.

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
│   │   ├── chart-classes.js  # OO classes for charts
│   │   ├── data-processors.js# JS data processing (slicing, filtering)
│   │   ├── event-handlers.js # Functions that respond to Bokeh events
│   │   ├── renderers.js      # Functions that update the UI
│   │   ├── state-management.js # Central JS state store and dispatcher
│   │   └── utils.js          # JS utility functions
│   ├── ui/                   # UI Widget and Component creation
│   │   ├── __init__.py
│   │   ├── components.py
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

The front-end interactivity is managed by a self-contained JavaScript application architecture (in static/js/). It follows a modern state management pattern similar to Redux:

*   **state-management.js:** Holds the single source of truth for the UI state. The dispatchAction function is the only way to modify the state.
*   **event-handlers.js:** Listens for Bokeh UI events (e.g., tap, zoom), translates them into semantic actions (e.g., { type: 'TAP', payload: ... }), and dispatches them.
*   **data-processors.js:** When the state changes, these functions compute the derived data needed for the charts (e.g., slicing the correct chunk of spectrogram data).
*   **renderers.js:** These functions take the new state and derived data and update the Bokeh models to change what the user sees on screen.

This pattern keeps the code organized, predictable, and easier to debug and extend.

