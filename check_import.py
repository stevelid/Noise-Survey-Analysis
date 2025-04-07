import sys
import os

# Add the current directory to the path
sys.path.insert(0, os.path.abspath('.'))

try:
    import noise_survey_analysis
    print('Successfully imported the package')
    
    # Try to import components used in tests
    try:
        from noise_survey_analysis.main import (
            create_app, load_and_process_data, synchronize_time_range,
            AudioPlaybackHandler, AppCallbacks, session_destroyed,
            DashboardBuilder
        )
        print('Successfully imported main components')
        
        # Try to import the visualization components and JS initialization
        try:
            from noise_survey_analysis.visualization.interactive import (
                initialize_global_js, add_hover_interaction, add_tap_interaction
            )
            print('Successfully imported interactive components')
            
            # Try to import the JS loader
            try:
                from noise_survey_analysis.js.loader import get_app_js
                print('Successfully imported JS loader')
            except ImportError as e:
                print(f'Error importing JS loader: {e}')
                
        except ImportError as e:
            print(f'Error importing interactive components: {e}')
    except ImportError as e:
        print(f'Error importing main components: {e}')
        
except ImportError as e:
    print(f'Error importing the package: {e}') 