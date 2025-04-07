"""
loader.py

JavaScript loading utilities for Noise Survey Analysis.

This module provides functions to load the JavaScript files for the Bokeh application.
"""

import os
import logging

logger = logging.getLogger(__name__)

# Path to JavaScript files
JS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'js')

def load_js_file(filename):
    """
    Load a JavaScript file from the static/js directory.
    
    Parameters:
    filename (str): Name of the JavaScript file to load
    
    Returns:
    str: Content of the JavaScript file, or empty string if file not found
    """
    filepath = os.path.join(JS_DIR, filename)
    
    try:
        with open(filepath, 'r') as f:
            content = f.read()
        logger.info(f"Loaded JavaScript file: {filename}")
        return content
    except Exception as e:
        logger.error(f"Error loading JavaScript file {filename}: {e}")
        return ""

def get_core_js():
    """
    Get the core utility JavaScript.
    
    Returns:
    str: Content of the core.js file
    """
    return load_js_file('core.js')

def get_charts_js():
    """
    Get the chart interaction JavaScript.
    
    Returns:
    str: Content of the charts.js file
    """
    return load_js_file('charts.js')

def get_audio_js():
    """
    Get the audio playback visualization JavaScript.
    
    Returns:
    str: Content of the audio.js file
    """
    return load_js_file('audio.js')

def get_frequency_js():
    """
    Get the frequency visualization JavaScript.
    
    Returns:
    str: Content of the frequency.js file
    """
    return load_js_file('frequency.js')

def get_combined_js():
    """
    Get all JavaScript files combined.
    
    Returns:
    str: Combined JavaScript content
    """
    core_js = get_core_js()
    charts_js = get_charts_js()
    audio_js = get_audio_js()
    frequency_js = get_frequency_js()
    
    combined = "\n// CORE JS\n" + core_js + "\n\n// CHARTS JS\n" + charts_js + "\n\n// AUDIO JS\n" + audio_js + "\n\n// FREQUENCY JS\n" + frequency_js
    return combined 