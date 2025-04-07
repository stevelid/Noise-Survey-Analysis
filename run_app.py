"""
Run the Noise Survey Analysis application.

This script provides a simple entry point to run the Bokeh server
with the Noise Survey Analysis application.

Usage:
    python run_app.py
"""

import os
import sys
import subprocess

def run_bokeh_server():
    """
    Run the Bokeh server with the Noise Survey Analysis application.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    app_path = os.path.join(script_dir, "noise_survey_analysis", "app.py")
    
    if not os.path.exists(app_path):
        print(f"Error: Application file not found at {app_path}")
        sys.exit(1)
    
    print("Starting Noise Survey Analysis application...")
    print(f"Application path: {app_path}")
    
    # Run the Bokeh server with the application
    cmd = ["bokeh", "serve", "--show", app_path]
    subprocess.run(cmd)

if __name__ == "__main__":
    run_bokeh_server() 