# tests/test_app.py

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, PropertyMock, call, ANY
import os
import sys

# Add the project root to the path to ensure imports work
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Ensure the app module can be imported
try:
    # Import the main function and refactored classes/functions we need to mock/test
    from noise_survey_analysis.main import (
        create_app,
        # Import classes/functions used by create_app for patching targets
        load_and_process_data,
        synchronize_time_range,
        AudioPlaybackHandler,
        AppCallbacks,
        session_destroyed, # Import the actual function for checking registration
        DashboardBuilder,
        GENERAL_SETTINGS, # For mocking media_path
        CHART_SETTINGS,   # For mocking sync_charts
        VISUALIZATION_SETTINGS # If needed
    )
    # Import initialize_global_js from its actual location
    from noise_survey_analysis.visualization.interactive import initialize_global_js
    
    # Import necessary Bokeh models for spec checking and mocking targets
    from bokeh.document import Document
    from bokeh.models import (
        ColumnDataSource, Button, Select, Div, CustomJS, Span, Label, FactorRange,
        Model # Added Model for general checks
    )
    from bokeh.plotting import figure
    from bokeh.layouts import LayoutDOM # Base class for layouts like row/column
    from bokeh.core.properties import Instance # For checking layout types
except ImportError as e:
    # Fallback if the module structure is different
    # Adjust path as necessary if your test structure differs
    print(f"Import Error: {e}")
    pytest.skip("Could not import Noise Survey Analysis modules from main.py", allow_module_level=True)

# --- Mock Classes ---

class MockAudioPlaybackHandler:
    """Mock for core.audio_handler.AudioPlaybackHandler to avoid VLC dependency."""
    def __init__(self, media_path):
        self.media_path = media_path
        self._is_playing = False
        self._start_timestamp = datetime(2023, 1, 1, 10, 0, 0) # Mock start time

    def play(self, timestamp=None): # Updated signature based on app_callbacks
        print(f"MockAudio: Play called with timestamp {timestamp}")
        self._is_playing = True
        return True # Assume success

    def pause(self):
        print("MockAudio: Pause called")
        self._is_playing = False

    def seek(self, time_ms): # Assuming seek takes milliseconds
         print(f"MockAudio: Seek called to {time_ms} ms")
         # No actual seeking needed in mock

    def get_current_time(self): # Assuming returns seconds
        # Return a fixed value or slightly incrementing value if needed
        return 10.0 if self._is_playing else 0.0

    def is_playing(self):
        return self._is_playing

    def release(self):
        print("MockAudio: Release called")

    def get_start_timestamp(self): # Added method used in _play_click
        return self._start_timestamp

    # Add other methods if AppCallbacks uses them (e.g., set_time, get_current_position)
    def set_time(self, time_ms):
         print(f"MockAudio: Set time called to {time_ms} ms")

    def get_current_position(self): # Assuming returns datetime
        return self._start_timestamp + timedelta(seconds=self.get_current_time())


# --- Fixtures ---

@pytest.fixture
def mock_position_data_full():
    """Create a mock position data dictionary with all data types."""
    overview_df = pd.DataFrame({
        'Datetime': pd.to_datetime(['2023-01-01 10:00', '2023-01-01 10:05', '2023-01-01 10:10']),
        'LAeq': [60, 62, 61], 'LAF10': [65, 67, 66], 'LAF90': [55, 57, 56]
    })
    spectral_df = pd.DataFrame({
        'Datetime': pd.to_datetime(['2023-01-01 10:00', '2023-01-01 10:05', '2023-01-01 10:10']),
        'LZeq_31.5': [40, 42, 41], 'LZeq_63': [45, 47, 46], 'LZeq_125': [50, 52, 51],
        'LZeq_250': [51, 53, 52], 'LZeq_500': [52, 54, 53], 'LZeq_1000': [53, 55, 54],
        'LZeq_2000': [50, 52, 51], 'LZeq_4000': [47, 49, 48], 'LZeq_8000': [44, 46, 45]
    })
    log_df = pd.DataFrame({
        'Datetime': pd.to_datetime(['2023-01-01 10:00:01', '2023-01-01 10:00:02']),
        'LAeq_dt': [60.1, 60.3], 'LAF10': [65.1, 65.2], 'LAF90': [55.1, 55.2]
    })
    return {
        'SW': {'overview': overview_df.copy(), 'spectral': spectral_df.copy(), 'log': log_df.copy(), 'metadata': {'parser': 'sentry'}},
        'N': {'overview': overview_df.copy(), 'spectral': spectral_df.copy(), 'log': log_df.copy(), 'metadata': {'parser': 'nti'}}
    }

@pytest.fixture
def mock_position_data_no_spectral():
    """Create mock position data without spectral data."""
    overview_df = pd.DataFrame({
        'Datetime': pd.to_datetime(['2023-01-01 10:00', '2023-01-01 10:05']),
        'LAeq': [60, 62], 'LAF90': [55, 57]
    })
    log_df = pd.DataFrame({
        'Datetime': pd.to_datetime(['2023-01-01 10:00:01', '2023-01-01 10:00:02']),
        'LAeq_dt': [60.1, 60.3]
    })
    return {
        'SW': {'overview': overview_df.copy(), 'log': log_df.copy(), 'metadata': {'parser': 'sentry'}}
    }

@pytest.fixture
def mock_position_data_no_log():
    """Create mock position data without log data."""
    overview_df = pd.DataFrame({
        'Datetime': pd.to_datetime(['2023-01-01 10:00', '2023-01-01 10:05']),
        'LAeq': [60, 62]
    })
    spectral_df = pd.DataFrame({
        'Datetime': pd.to_datetime(['2023-01-01 10:00', '2023-01-01 10:05']),
        'LZeq_31.5': [40, 42], 'LZeq_63': [45, 47], 'LZeq_125': [50, 52],
        'LZeq_250': [51, 53], 'LZeq_500': [52, 54], 'LZeq_1000': [53, 55],
        'LZeq_2000': [50, 52], 'LZeq_4000': [47, 49], 'LZeq_8000': [44, 46]
    })
    return {
        'SW': {'overview': overview_df.copy(), 'spectral': spectral_df.copy(), 'metadata': {'parser': 'sentry'}}
    }

@pytest.fixture
def mock_position_data_empty():
    """Create empty mock position data."""
    return {}

@pytest.fixture
def mock_position_data_only_empty_dfs():
    """Create mock position data with only empty DataFrames."""
    return {
        'SW': {'overview': pd.DataFrame({'Datetime':[]}), 'spectral': pd.DataFrame({'Datetime':[]}), 'log': pd.DataFrame({'Datetime':[]}), 'metadata': {}}
    }

# --- Mock Settings Fixture (Optional - can be patched directly in tests) ---
@pytest.fixture
def mock_general_settings():
    return {"media_path": "/fake/path/audio.wav"}

@pytest.fixture
def mock_chart_settings_sync_on():
    return {"sync_charts": True, "default_spectral_param": "LZeq"} # Add other keys if needed by builder

@pytest.fixture
def mock_chart_settings_sync_off():
    return {"sync_charts": False, "default_spectral_param": "LZeq"} # Add other keys if needed by builder

@pytest.fixture
def mock_visualization_settings():
    return {"link_x_ranges": True} # Add other keys if needed by builder

# --- Tests for create_app ---

# Use the actual mock class for AudioPlaybackHandler
# Patch dependencies used within create_app, targeting their location in main.py
@patch('noise_survey_analysis.main.load_and_process_data')
@patch('noise_survey_analysis.main.synchronize_time_range')
@patch('noise_survey_analysis.main.AudioPlaybackHandler', MockAudioPlaybackHandler)
@patch('noise_survey_analysis.main.DashboardBuilder')
@patch('noise_survey_analysis.main.AppCallbacks')
@patch('noise_survey_analysis.visualization.interactive.initialize_global_js') # Updated patch target
@patch('noise_survey_analysis.main.Div') # Mock Div for error messages
class TestCreateApp:
    """Tests for the main create_app orchestrator function."""

    def _setup_mocks(self, mock_Div, mock_init_js, mock_AppCallbacks, mock_DashboardBuilder,
                     mock_AudioHandler, mock_sync_data, mock_load_data,
                     position_data_to_load, general_settings, chart_settings,
                     viz_settings):
        """Helper to configure mocks for a test case."""
        mock_load_data.return_value = position_data_to_load
        mock_sync_data.return_value = position_data_to_load # Assume sync returns same structure

        # Mock DashboardBuilder instance and its build() method
        mock_builder_instance = MagicMock(spec=DashboardBuilder)
        mock_main_layout = MagicMock(spec=LayoutDOM)
        # Simulate the bokeh_models dictionary returned by build()
        mock_bokeh_models = {
            'all_charts': [MagicMock(spec=figure)],
            'all_sources': {'pos_overview': MagicMock(spec=ColumnDataSource)},
            'charts_for_js': [MagicMock(spec=figure)],
            'click_lines': [MagicMock(spec=Span)], # Now a list
            'labels': [MagicMock(spec=Label)],     # Now a list
            'playback_source': MagicMock(spec=ColumnDataSource, name='playback_source'),
            'playback_controls': {'play_button': MagicMock(spec=Button), 'pause_button': MagicMock(spec=Button)},
            # Add spectral related models if data has spectral
            'param_select': MagicMock(spec=Select) if 'spectral' in list(position_data_to_load.values())[0] else None,
            'param_holder': MagicMock(spec=ColumnDataSource, name='param_holder') if 'spectral' in list(position_data_to_load.values())[0] else None,
            'spectral_figures': {'pos': MagicMock(spec=figure)} if 'spectral' in list(position_data_to_load.values())[0] else {},
            'hover_info_div': MagicMock(spec=Div, name='hover_info_div') if 'spectral' in list(position_data_to_load.values())[0] else None,
            'freq_bar_source': MagicMock(spec=ColumnDataSource, name='freq_bar_source') if 'spectral' in list(position_data_to_load.values())[0] else None,
            'freq_bar_x_range': MagicMock(spec=FactorRange) if 'spectral' in list(position_data_to_load.values())[0] else None,
        }
        mock_builder_instance.build.return_value = (mock_main_layout, mock_bokeh_models)
        mock_DashboardBuilder.return_value = mock_builder_instance

        # Mock AppCallbacks instance and its attach_callbacks() method
        mock_callbacks_instance = MagicMock(spec=AppCallbacks)
        mock_AppCallbacks.return_value = mock_callbacks_instance

        # Mock Document and session_context
        mock_doc = MagicMock(spec=Document)
        mock_doc.session_context = MagicMock()
        # Add a placeholder attribute to allow setting the callback manager
        mock_doc.session_context._app_callback_manager = None
        # Mock methods used by create_app
        mock_doc.add_root = MagicMock()
        mock_doc.on_session_destroyed = MagicMock()
        mock_doc.roots = [] # Simulate the roots list

        # Return mocks for use in test assertions
        return mock_doc, mock_builder_instance, mock_callbacks_instance

    def test_happy_path_full_data_audio_sync_on(
        self, mock_load_data, mock_sync_data, mock_AudioHandler, 
        mock_DashboardBuilder, mock_AppCallbacks, mock_init_js, mock_Div,
        mock_position_data_full, mock_general_settings, mock_chart_settings_sync_on,
        mock_visualization_settings
    ):
        """Test create_app with full data, audio enabled, and chart sync enabled."""

        # Use patch.dict to temporarily modify the imported settings dictionaries
        with patch.dict('noise_survey_analysis.main.GENERAL_SETTINGS', mock_general_settings), \
             patch.dict('noise_survey_analysis.main.CHART_SETTINGS', mock_chart_settings_sync_on), \
             patch.dict('noise_survey_analysis.main.VISUALIZATION_SETTINGS', mock_visualization_settings):

            mock_doc, mock_builder, mock_callbacks = self._setup_mocks(
                mock_Div, mock_init_js, mock_AppCallbacks, mock_DashboardBuilder,
                mock_AudioHandler, mock_sync_data, mock_load_data,
                mock_position_data_full, mock_general_settings, mock_chart_settings_sync_on,
                mock_visualization_settings
            )

            # Call the function under test
            create_app(mock_doc)

        # --- Assertions ---
        # Data loading and processing
        mock_load_data.assert_called_once()
        mock_sync_data.assert_called_once_with(mock_position_data_full) # Called because sync_charts is True

        # Audio Handler Initialization
        mock_AudioHandler.assert_called_once_with(mock_general_settings["media_path"])

        # Dashboard Builder Initialization and Build
        mock_DashboardBuilder.assert_called_once_with(
            position_data=mock_position_data_full,
            chart_settings=mock_chart_settings_sync_on,
            visualization_settings=mock_visualization_settings,
            audio_handler_available=True # Audio handler should be available
        )
        mock_builder.build.assert_called_once()
        layout_returned, models_returned = mock_builder.build()

        # AppCallbacks Initialization and Attachment
        mock_AppCallbacks.assert_called_once_with(
            doc=mock_doc,
            audio_handler=ANY, # Check instance of MockAudioPlaybackHandler
            models=models_returned
        )
        assert isinstance(mock_AppCallbacks.call_args[1]['audio_handler'], MockAudioPlaybackHandler)
        mock_callbacks.attach_callbacks.assert_called_once()

        # Session Cleanup Registration
        mock_doc.on_session_destroyed.assert_called_once_with(session_destroyed)
        # Check if the callback manager was stored on the session context
        assert mock_doc.session_context._app_callback_manager == mock_callbacks

        # JS Initialization
        mock_init_js.assert_called_once()
        # Verify the essential args passed to initialize_global_js
        js_args = mock_init_js.call_args[1]
        assert js_args['doc'] == mock_doc
        assert js_args['charts'] == models_returned['charts_for_js']
        assert js_args['sources'] == models_returned['all_sources']
        assert js_args['clickLines'] == models_returned['click_lines']
        assert js_args['labels'] == models_returned['labels']
        assert js_args['playback_source'] == models_returned['playback_source']
        assert js_args['play_button'] == models_returned['playback_controls']['play_button']
        # ... check other relevant args ...

        # Document Setup
        mock_doc.add_root.assert_any_call(layout_returned) # Check layout added
        # Check if essential sources were added (adjust keys based on create_app logic)
        essential_sources_keys = ['playback_source', 'param_holder']
        added_roots = [call_args[0][0] for call_args in mock_doc.add_root.call_args_list]
        for key in essential_sources_keys:
             if models_returned.get(key):
                 # Assert that the model object itself was added
                 assert models_returned[key] in added_roots
        assert mock_doc.title == "Noise Survey Analysis"

    def test_no_audio_path(
        self, mock_load_data, mock_sync_data, mock_AudioHandler, 
        mock_DashboardBuilder, mock_AppCallbacks, mock_init_js, mock_Div,
        mock_position_data_full, mock_chart_settings_sync_on, mock_visualization_settings
    ):
        """Test create_app when no media_path is provided."""
        no_audio_settings = {} # Empty GENERAL_SETTINGS means no media_path

        with patch.dict('noise_survey_analysis.main.GENERAL_SETTINGS', no_audio_settings), \
             patch.dict('noise_survey_analysis.main.CHART_SETTINGS', mock_chart_settings_sync_on), \
             patch.dict('noise_survey_analysis.main.VISUALIZATION_SETTINGS', mock_visualization_settings):

            mock_doc, mock_builder, mock_callbacks = self._setup_mocks(
                mock_Div, mock_init_js, mock_AppCallbacks, mock_DashboardBuilder,
                mock_AudioHandler, mock_sync_data, mock_load_data,
                mock_position_data_full, no_audio_settings, mock_chart_settings_sync_on,
                mock_visualization_settings
            )
            # Need to adjust mock models if audio components aren't created when no audio path
            models_returned = mock_builder.build()[1]
            models_returned['playback_source'] = None
            models_returned['playback_controls'] = {}

            create_app(mock_doc)

        # Assertions
        mock_load_data.assert_called_once()
        mock_sync_data.assert_called_once() # Still called if sync_charts is True
        mock_AudioHandler.assert_not_called() # Not initialized without path
        mock_DashboardBuilder.assert_called_once_with(
             ANY, chart_settings=ANY, visualization_settings=ANY, audio_handler_available=False # Check flag is False
        )
        mock_builder.build.assert_called_once()
        mock_AppCallbacks.assert_not_called() # Callbacks not set up without audio handler
        mock_callbacks.attach_callbacks.assert_not_called()
        mock_doc.on_session_destroyed.assert_not_called() # Cleanup not registered if callbacks not set up
        mock_init_js.assert_called_once() # JS still initialized, but may get None for audio args
        mock_doc.add_root.assert_any_call(mock_builder.build()[0]) # Layout still added

    def test_data_load_failure(
        self, mock_load_data, mock_sync_data, mock_AudioHandler, 
        mock_DashboardBuilder, mock_AppCallbacks, mock_init_js, mock_Div,
        mock_general_settings, mock_chart_settings_sync_on, mock_visualization_settings
    ):
        """Test create_app when load_and_process_data raises an exception."""
        mock_load_data.side_effect = Exception("Data load failed!")

        with patch.dict('noise_survey_analysis.main.GENERAL_SETTINGS', mock_general_settings), \
             patch.dict('noise_survey_analysis.main.CHART_SETTINGS', mock_chart_settings_sync_on), \
             patch.dict('noise_survey_analysis.main.VISUALIZATION_SETTINGS', mock_visualization_settings):

            mock_doc, mock_builder, mock_callbacks = self._setup_mocks(
                mock_Div, mock_init_js, mock_AppCallbacks, mock_DashboardBuilder,
                mock_AudioHandler, mock_sync_data, mock_load_data,
                {}, mock_general_settings, mock_chart_settings_sync_on,
                mock_visualization_settings
            )

            create_app(mock_doc)

        # Assertions
        mock_load_data.assert_called_once()
        mock_sync_data.assert_not_called()
        mock_AudioHandler.assert_not_called()
        mock_DashboardBuilder.assert_not_called()
        mock_AppCallbacks.assert_not_called()
        mock_init_js.assert_not_called()
        # Check that an error Div was added to the document
        mock_Div.assert_called_once()
        assert "Error: Failed during data loading/processing" in mock_Div.call_args[1]['text']
        mock_doc.add_root.assert_called_once_with(mock_Div.return_value)

    def test_empty_position_data(
        self, mock_load_data, mock_sync_data, mock_AudioHandler, 
        mock_DashboardBuilder, mock_AppCallbacks, mock_init_js, mock_Div,
        mock_general_settings, mock_chart_settings_sync_on, mock_visualization_settings,
        mock_position_data_empty # Use the empty data fixture
    ):
        """Test create_app when load_and_process_data returns an empty dictionary."""
        # Configure load_data mock to return the empty dictionary
        mock_load_data.return_value = mock_position_data_empty

        with patch.dict('noise_survey_analysis.main.GENERAL_SETTINGS', mock_general_settings), \
             patch.dict('noise_survey_analysis.main.CHART_SETTINGS', mock_chart_settings_sync_on), \
             patch.dict('noise_survey_analysis.main.VISUALIZATION_SETTINGS', mock_visualization_settings):

            mock_doc, mock_builder, mock_callbacks = self._setup_mocks(
                mock_Div, mock_init_js, mock_AppCallbacks, mock_DashboardBuilder,
                mock_AudioHandler, mock_sync_data, mock_load_data,
                mock_position_data_empty, mock_general_settings, mock_chart_settings_sync_on,
                mock_visualization_settings
            )

            create_app(mock_doc)

        # Assertions
        mock_load_data.assert_called_once()
        mock_sync_data.assert_not_called() # No data to sync
        mock_AudioHandler.assert_not_called() # Doesn't proceed to audio setup
        mock_DashboardBuilder.assert_not_called() # Doesn't proceed to dashboard building
        mock_AppCallbacks.assert_not_called()
        mock_init_js.assert_not_called()
        # Check that an error Div was added
        mock_Div.assert_called_once()
        assert "Error: No valid data loaded" in mock_Div.call_args[1]['text']
        mock_doc.add_root.assert_called_once_with(mock_Div.return_value)

    def test_dashboard_build_failure(
        self, mock_load_data, mock_sync_data, mock_AudioHandler, 
        mock_DashboardBuilder, mock_AppCallbacks, mock_init_js, mock_Div,
        mock_position_data_full, mock_general_settings, mock_chart_settings_sync_on,
        mock_visualization_settings
    ):
        """Test create_app when DashboardBuilder.build() raises an exception."""

        with patch.dict('noise_survey_analysis.main.GENERAL_SETTINGS', mock_general_settings), \
             patch.dict('noise_survey_analysis.main.CHART_SETTINGS', mock_chart_settings_sync_on), \
             patch.dict('noise_survey_analysis.main.VISUALIZATION_SETTINGS', mock_visualization_settings):

            mock_doc, mock_builder, mock_callbacks = self._setup_mocks(
                mock_Div, mock_init_js, mock_AppCallbacks, mock_DashboardBuilder,
                mock_AudioHandler, mock_sync_data, mock_load_data,
                mock_position_data_full, mock_general_settings, mock_chart_settings_sync_on,
                mock_visualization_settings
            )
            # Configure builder mock to raise exception on build()
            mock_builder.build.side_effect = Exception("Dashboard build failed!")

            create_app(mock_doc)

        # Assertions
        mock_load_data.assert_called_once()
        mock_sync_data.assert_called_once()
        mock_AudioHandler.assert_called_once()
        mock_DashboardBuilder.assert_called_once()
        mock_builder.build.assert_called_once() # build was called
        mock_AppCallbacks.assert_not_called() # Does not proceed to callbacks
        mock_init_js.assert_not_called()
        # Check error Div added
        mock_Div.assert_called_once()
        assert "Error: Failed to build dashboard layout" in mock_Div.call_args[1]['text']
        mock_doc.add_root.assert_called_once_with(mock_Div.return_value)

    # Add more tests:
    # - Test case where sync_charts is False (mock_sync_data should not be called)
    # - Test case with only spectral data (ensure builder/callbacks handle it)
    # - Test case where AppCallbacks fails to initialize or attach


# --- Removed test_main_standalone_execution ---
# The main() function was removed in the refactoring.
# The entry point for Bokeh server is now the `if __name__.startswith('bokeh_app_')` block.