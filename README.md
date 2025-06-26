# Noise Survey Analysis Tool

An interactive Bokeh application for loading, analyzing, and visualizing noise survey data from various sound level meters.

## Overview

This tool provides a dashboard for analyzing noise survey data, featuring:

* Data import from multiple source formats (currently Noise Sentry CSV, NTi TXT, Svan XLSX).
* Configuration via `noise_survey_analysis/core/config.py`.
* Time series visualization of broadband sound levels (e.g., LAeq, LAF90).
* Spectral analysis including image-based spectrograms and interactive frequency slice bar charts.
* Interactive chart navigation: synchronized zooming/panning, hover/tap to inspect data points.
* Keyboard navigation (arrow keys for time stepping, spacebar for play/pause).
* Synchronized audio playback (requires VLC) linked to the visualization timeline.

## Project Structure (Post-Refactoring Target)

├── noise_survey_analysis/
│   ├── core/                 # Core functionality (config, loading, parsing, processing, audio, callbacks)
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── data_loaders.py
│   │   ├── data_parsers.py
│   │   ├── data_processors.py
│   │   ├── audio_handler.py
│   │   └── app_callbacks.py    # NEW: Handles Python-side callbacks
│   ├── visualization/        # Bokeh visualization components & orchestration
│   │   ├── __init__.py
│   │   ├── components.py       # RENAMED: Creates individual chart figures/sources
│   │   ├── interactive.py      # Adds interactive elements (lines, hover), JS init setup
│   │   └── dashboard.py        # NEW: Orchestrates viz creation, builds layout
│   ├── ui/                   # NEW: UI Widget Creation
│   │   ├── __init__.py
│   │   └── controls.py         # Functions to create Bokeh widget sets
│   ├── static/js/            # Client-side JavaScript files for interactivity
│   │   ├── core.js
│   │   ├── charts.js
│   │   ├── frequency.js
│   │   └── audio.js
│   ├── __init__.py
│   └── app.py                # Main Bokeh application *entry point* and *orchestrator*
├── tests/                      # Pytest tests (mirroring structure)
│   ├── core/
│   ├── visualization/
│   ├── ui/
│   └── test_app.py
├── DEVELOPMENT_PLAN.md       # Refactoring and enhancement plan
├── README.md                 # This file
└── run_app.py                # Script to run the Bokeh server

## Requirements

* Python 3.8+
* Bokeh (`pip install bokeh`)
* Pandas (`pip install pandas`)
* NumPy (`pip install numpy`)
* python-vlc (`pip install python-vlc`)
* VLC media player (must be installed separately on your system for audio playback)
* `openpyxl` (for reading Svan `.xlsx` files: `pip install openpyxl`)

## Usage

1.  **Configure Data:** Edit `noise_survey_analysis/core/config.py` to define your `DEFAULT_DATA_SOURCES`, specifying the `position_name`, `file_path`, `parser_type`, and `enabled` status for each data file. **TODO:** Move the `media_path` definition from `noise_survey_analysis/app.py` into `config.py`.
2.  **Run the Application:** Execute the `run_app.py` script from your terminal in the project's root directory:
    ```bash
    python run_app.py
    ```
    This will start the Bokeh server and open the application in your default web browser.
3.  **Interact:**
    * Use checkboxes to toggle chart visibility.
    * Use the range selector at the bottom to zoom into specific time periods.
    * Hover over charts to see a vertical line and details (in spectrogram hover div).
    * Click on a chart to set the red vertical line and update the frequency slice chart.
    * Use the playback controls (Play, Pause, Stop, Speed) to listen to audio synchronized with the red line.
    * Use keyboard arrow keys (Left/Right) to step the red line through time.
    * Use the Spacebar to toggle Play/Pause.
    * Use the "Parameter" dropdown (if spectral data is present) to change the spectrogram display.

## Data and Visualization Model Structures

### Data Loading Structure (`position_data`)

The application loads data through the `load_and_process_data()` function in `data_loaders.py`, which returns a dictionary with the following structure:

```
{
    'Position1': {
        'overview': DataFrame,    # Time series data for broadband metrics (LAeq, LAF90, etc.)
        'spectral': DataFrame,    # Spectral data with frequency bands
        'log': DataFrame,         # Detailed logging data with timestamps
        'spectral_log': DataFrame, # Logged spectral data
        'audio': '/path/to/audio.wav',  # Path to associated audio file
        'metadata': {
            'parser_type': 'sentry|nti|svan',
            'original_path': '/path/to/original/file.csv',
            'audio_path': '/path/to/audio/directory',
            'RPT': {...},         # Specific metadata from RPT parser
            'RTA': {...},         # Specific metadata from RTA parser
            'audio': {...}        # Audio file metadata
        }
    },
    'Position2': { ... }
}
```

### Bokeh Models Dictionary (`bokeh_models`)

The application uses a well-organized hierarchical structure for `bokeh_models` to maintain all Bokeh UI components. The `DashboardBuilder` class maintains this dictionary for all Bokeh objects using the following structure:

```
{
    'charts': {
        'all': [],                    # All Bokeh Figure objects
        'time_series': [],            # Time-based charts for synchronization
        'for_js_interaction': []      # Charts requiring JS callbacks
    },
    
    'sources': {
        'data': {},                   # Main data sources by key
        'playback': {                 # Playback-related sources
            'position': None,         # Current playback position 
            'seek_command': None,     # For sending seek commands
            'play_request': None      # For play requests from JS
        },
        'frequency': {                # Frequency analysis sources
            'bar': None,              # For frequency bar chart
            'table': None             # For frequency data table
        }
    },
    
    'ui': {
        'position_elements': {},      # UI elements by position
        'controls': {                 # UI controls
            'playback': {},           # Play/pause buttons
            'parameter': {            # Parameter selection
                'select': None,       # Dropdown for parameter selection
                'holder': None        # Hidden div for selected parameter
            },
            'init_js': None           # Button to initialize JS
        },
        'visualization': {            # Visual elements
            'click_lines': {},        # Vertical lines for clicked positions
            'labels': {},             # Text labels for data points
            'range_selectors': {}     # Range selectors for zooming
        }
    },
    
    'frequency_analysis': {           # Frequency analysis components 
        'bar_chart': {                # Bar chart components
            'figure': None,           # The bar chart figure
            'x_range': None           # X range for the chart
        }
    },
    
    'spectral_data': {                # Spectral data by position
        'position': {
            'available_params': [],   # Available spectral parameters
            'current_param': 'LZeq',  # Currently selected parameter
            'prepared_data': {        # Pre-processed data by parameter
                'param_name': {       # Detailed parameter data
                    'frequencies': ndarray,     # Array of frequency values (e.g. [25, 31.5, 40, ...])
                    'frequency_labels': list,   # List of formatted frequency labels (e.g. ["25 Hz", "31.5 Hz", ...])
                    'times_ms': ndarray,        # Array of timestamps in milliseconds (epoch time)
                    'times_dt': ndarray,        # Array of datetime64 objects
                    'levels_matrix': ndarray,   # 2D matrix of sound levels in shape (n_times, n_freqs)
                    'levels_matrix_transposed': ndarray, # Transposed matrix (n_freqs, n_times) for Bokeh image glyph
                    'freq_indices': ndarray,    # Array of frequency indices [0, 1, 2, ...]
                    'min_val': float,           # Minimum level value for color mapping
                    'max_val': float,           # Maximum level value for color mapping
                    'n_times': int,             # Number of time points
                    'n_freqs': int,             # Number of frequency bands
                    'x': float,                 # X coordinate for Bokeh image glyph (start time)
                    'y': float,                 # Y coordinate for Bokeh image glyph (typically -0.5)
                    'dw': float,                # Width for Bokeh image glyph (time span)
                    'dh': float                 # Height for Bokeh image glyph (frequency span)
                }
            }
        }
    }
}
```

#### Using the Hierarchical Structure

**Python Example**:
```python
# Access the charts with the hierarchical structure
charts = builder.bokeh_models['charts']['all']

# Creating a frequency chart
chart, source = create_frequency_bar_chart()
builder.bokeh_models['frequency_analysis']['bar_chart']['figure'] = chart
builder.bokeh_models['sources']['frequency']['bar'] = source

# Access spectral data for a position 
param_data = builder.bokeh_models['spectral_data']['NE']['prepared_data']['LZeq']
```

**JavaScript Example**:
```javascript
// The JS initialization receives this structure
function initializeApp(models, options) {
    // All models are passed in the hierarchical structure
    const charts = models.charts || [];
    const sources = models.sources || {};
    const barChart = models.barChart;
    
    console.log(`Initializing app with ${charts.length} charts`);
    // ... rest of initialization
}
```

## Development Plan

This project is undergoing refactoring and enhancement according to the [Development Plan](DEVELOPMENT_PLAN.md). Key goals include:

* Improved code structure and maintainability.
* Improved JavaScript stability and state handling.
* Enhanced file/directory input UI.
* Annotation/note-taking features.
* Data range selection for statistical analysis.
* Static HTML export options.
* Addition of automated tests.

## License

This project is intended for internal use.


## Future (wanted) features: 
1. Enhanced File/Directory Input:

-Allow selecting a parent directory instead of manually listing each file path in the config.
Scan the selected directory (and subdirectories) for relevant noise survey files (based on configurable criteria like filename patterns, file types: .csv, .txt, .xlsx, etc., potentially size).
-Present the identified files to the user.
-Allow the user to select which files to include in the analysis.
-Automatically suggest or allow user assignment of "position names" (e.g., based on subfolder names where files are located).

2. Chart Annotation / Note-Taking System:

-Ability to add notes directly linked to specific points in time on the charts.
-Display unobtrusive visual markers on the charts indicating where notes exist.
-Provide an easy-to-use interface for taking notes (e.g., a popup dialog or side panel).
-When creating a note, automatically pre-populate it with relevant context from the chart at the selected time (e.g., timestamp, position name, key sound levels like LAeq, LAF90).
-Define a clear UI trigger to initiate note creation (e.g., button click when the red vertical line is active, right-click menu option on the line, dedicated key press).
-Save the notes persistently, associated with the specific survey data/job folder (e.g., in a JSON or CSV file within that folder).
-Automatically load existing notes for a survey when the data is loaded in a new session.

3. Data Range Selection and Statistical Analysis:

-Allow users to select a specific range of data directly on the time-history charts (e.g., by dragging handles on the range selector, using a box select tool).
-Calculate and display statistical results for the selected data range (e.g., overall LAeq, L10, L90, Lmax for the period).
-Calculate and display the average frequency spectrum for the selected time range.
-Provide an easy way to copy the calculated statistics and spectral data (e.g., formatted text in a display area or <textarea> for easy pasting into reports).
-Potentially integrate the display/copying of these statistics within the note-taking feature for the selected range.

4. Export and Session Management:

-Option to save the current view (charts and layout) as a standalone HTML file (understanding this will be static, without audio or server-side interactivity).
-Explore saving the configuration of a specific analysis session (selected files, chosen views, possibly notes) associated with the job folder.
-Explore functionality to reload a saved session configuration, automatically setting up the Bokeh server with the previously selected files and settings for that specific job.