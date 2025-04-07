"""
Simple tests to check that we can properly import and instantiate the refactored components
"""

import sys
import os
import pytest
from unittest.mock import MagicMock, patch

# Add the project root to the path to ensure imports work
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def test_imports():
    """Test that we can import all the necessary modules and components"""
    # Try importing the main module
    from noise_survey_analysis import main
    assert main is not None, "Failed to import main module"
    
    # Try importing specific classes/functions
    from noise_survey_analysis.visualization.interactive import initialize_global_js
    assert callable(initialize_global_js), "initialize_global_js is not callable"
    
    from noise_survey_analysis.visualization.dashboard import DashboardBuilder
    assert DashboardBuilder is not None, "Failed to import DashboardBuilder"
    
    from noise_survey_analysis.core.app_callbacks import AppCallbacks, session_destroyed
    assert AppCallbacks is not None, "Failed to import AppCallbacks"
    assert callable(session_destroyed), "session_destroyed is not callable"

@patch('noise_survey_analysis.core.app_callbacks.AudioPlaybackHandler')
def test_appcallbacks_initialization(mock_audio_handler):
    """Test that we can initialize AppCallbacks"""
    from noise_survey_analysis.core.app_callbacks import AppCallbacks
    
    # Mock the necessary dependencies
    mock_doc = MagicMock()
    mock_models = {
        'playback_source': MagicMock(),
        'playback_controls': {
            'play_button': MagicMock(),
            'pause_button': MagicMock()
        }
    }
    
    # Should be able to initialize with these mocks
    callbacks = AppCallbacks(doc=mock_doc, audio_handler=mock_audio_handler, models=mock_models)
    assert callbacks is not None, "Failed to initialize AppCallbacks"

@patch('noise_survey_analysis.visualization.dashboard.figure')
def test_dashboardbuilder_initialization(mock_figure):
    """Test that we can initialize DashboardBuilder"""
    from noise_survey_analysis.visualization.dashboard import DashboardBuilder
    
    # Mock the necessary dependencies
    position_data = {
        'SW': {
            'overview': MagicMock(),
            'spectral': MagicMock(),
            'log': MagicMock(),
            'metadata': {'parser': 'test'}
        }
    }
    chart_settings = {'sync_charts': True}
    visualization_settings = {}
    
    # Should be able to initialize with these mocks
    builder = DashboardBuilder(
        position_data=position_data,
        chart_settings=chart_settings,
        visualization_settings=visualization_settings,
        audio_handler_available=True
    )
    assert builder is not None, "Failed to initialize DashboardBuilder"

if __name__ == "__main__":
    # Run the tests when this file is executed directly
    pytest.main(["-v", __file__]) 