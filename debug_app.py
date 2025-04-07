"""
Simplified Debug version of the Noise Survey Analysis application.

This script provides a debug entry point with a state monitor text box.
"""

import os
import sys
import logging
from bokeh.server.server import Server
from bokeh.application import Application
from bokeh.application.handlers.function import FunctionHandler
from tornado.ioloop import IOLoop
from noise_survey_analysis.main import create_app
from bokeh.models import Div, CustomJS, Button, Row, Column, Select
from bokeh.model import Model

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def modify_doc(doc):
    """
    Create the app and add a debug state monitor text box.
    """
    # Use the standard app creation logic with default data sources
    create_app(doc, custom_data_sources=None)  # Explicitly use default sources
    
    # Add a debug state monitor div
    state_monitor = Div(
        text="<h3>State Monitor</h3><pre>Initializing...</pre>",
        width=800,
        height=500,
        styles={'overflow-y': 'scroll', 'background-color': '#f0f0f0', 'padding': '10px', 'border': '1px solid #ddd'}
    )
    
    # Create update button
    update_button = Button(
        label="Update State Monitor", 
        button_type="primary",
        width=200
    )
    
    # Create view selector dropdown
    view_select = Select(
        title="View Mode:",
        value="app_state",
        options=[
            ("app_state", "App State"),
            ("methods", "Available Methods"), 
            ("models", "Full Model State"),
            ("internals", "Internal Variables"),
            ("exposed_debug", "Exposed Debug Objects"),
            ("all", "All Information")
        ],
        width=200
    )
    
    # Create the update callback JavaScript that uses the Bokeh state_monitor reference directly
    update_js_code = """
        function getMethodsFromObject(obj, parentName = '') {
            const methods = {};
            
            if (!obj || typeof obj !== 'object') return {};
            
            // Get methods from the object itself
            for (const key in obj) {
                try {
                    const fullKey = parentName ? `${parentName}.${key}` : key;
                    const value = obj[key];
                    
                    // Check if it's a function
                    if (typeof value === 'function') {
                        let paramStr = 'unknown';
                        try {
                            // Try to get function parameters from toString
                            const fnStr = value.toString();
                            const paramMatch = fnStr.match(/\\(([^)]*)\\)/);
                            paramStr = paramMatch ? paramMatch[1] : '';
                        } catch (e) {}
                        
                        methods[fullKey] = `function(${paramStr})`;
                    }
                    
                    // Recursively get methods from nested namespaces (like .frequency or .interactions)
                    if (typeof value === 'object' && value !== null && !Array.isArray(value) && key !== 'prototype') {
                        const nestedMethods = getMethodsFromObject(value, fullKey);
                        Object.assign(methods, nestedMethods);
                    }
                } catch (e) {
                    console.error(`Error getting methods for ${key}:`, e);
                }
            }
            
            return methods;
        }
        
        function getModelDetails(model) {
            if (!model) return null;
            
            // For simple values, return directly
            if (typeof model !== 'object' || model === null) {
                return model;
            }
            
            // For arrays, return length and sample items
            if (Array.isArray(model)) {
                return {
                    type: 'Array',
                    length: model.length,
                    sample: model.length > 0 ? model.slice(0, Math.min(3, model.length)) : []
                };
            }
            
            // For objects, build a descriptive summary
            const details = {};
            for (const key in model) {
                try {
                    const value = model[key];
                    
                    if (value === null) {
                        details[key] = null;
                    } else if (typeof value === 'function') {
                        // Skip functions to avoid circular references
                        details[key] = 'function';
                    } else if (Array.isArray(value)) {
                        details[key] = {
                            type: 'Array',
                            length: value.length,
                            sample: value.length > 0 ? value.slice(0, Math.min(3, value.length)) : []
                        };
                    } else if (typeof value === 'object') {
                        // For nested objects, just provide type info to avoid deep recursion
                        details[key] = {
                            type: value.constructor ? value.constructor.name : 'Object',
                            properties: Object.keys(value).slice(0, 10)
                        };
                    } else {
                        details[key] = value;
                    }
                } catch (e) {
                    details[key] = `[Error: ${e.message}]`;
                }
            }
            
            return details;
        }
        
        function getAccessibleProperties(obj) {
            if (!obj || typeof obj !== 'object') return {};
            
            const properties = {};
            for (const key in obj) {
                try {
                    const value = obj[key];
                    
                    if (value === null) {
                        properties[key] = null;
                    } else if (typeof value === 'function') {
                        properties[key] = 'function';
                    } else if (Array.isArray(value)) {
                        properties[key] = `Array[${value.length}]`;
                        // For small arrays, show content
                        if (value.length <= 5) {
                            properties[key] = value;
                        }
                    } else if (typeof value === 'object') {
                        // For certain types of Bokeh objects, provide more details
                        if (value.type && value.id) {
                            properties[key] = `${value.type}(${value.id})`;
                        } else {
                            // Show available keys
                            properties[key] = `Object{${Object.keys(value).slice(0, 7).join(", ")}}`;
                        }
                    } else {
                        properties[key] = value;
                    }
                } catch (e) {
                    properties[key] = `[Error: ${e.message}]`;
                }
            }
            
            return properties;
        }
        
        function updateStateMonitor() {
            console.log("updateStateMonitor called");
            
            // Use the direct Bokeh model reference passed in args
            const monitor = state_monitor;
            const viewMode = view_select.value;
            console.log("View mode:", viewMode);
            
            let stateText = "<h3>State Monitor</h3><pre>";
            
            try {
                // Always show basic app info
                stateText += "--- Monitoring Mode: " + viewMode + " ---\\n\\n";
                
                // App State View
                if (viewMode === "app_state" || viewMode === "all") {
                    if (window.NoiseSurveyApp && window.NoiseSurveyApp.getState) {
                        console.log("Getting NoiseSurveyApp state");
                        const state = window.NoiseSurveyApp.getState();
                        stateText += "=== App State ===\\n";
                        stateText += JSON.stringify(state, null, 2) + "\\n\\n";
                    } else {
                        stateText += "NoiseSurveyApp state not available\\n\\n";
                    }
                }
                
                // Available Methods View
                if (viewMode === "methods" || viewMode === "all") {
                    stateText += "=== Available Methods ===\\n";
                    
                    if (window.NoiseSurveyApp) {
                        const methods = getMethodsFromObject(window.NoiseSurveyApp);
                        stateText += "NoiseSurveyApp Methods:\\n";
                        stateText += JSON.stringify(methods, null, 2) + "\\n\\n";
                    } else {
                        stateText += "NoiseSurveyApp not available\\n\\n";
                    }
                    
                    // Check for other global objects with methods
                    if (window.interactions) {
                        stateText += "Legacy Interactions Methods:\\n";
                        const legacyMethods = getMethodsFromObject(window.interactions);
                        stateText += JSON.stringify(legacyMethods, null, 2) + "\\n\\n";
                    }
                    
                    if (window.NoiseFrequency) {
                        stateText += "Legacy NoiseFrequency Methods:\\n";
                        const freqMethods = getMethodsFromObject(window.NoiseFrequency);
                        stateText += JSON.stringify(freqMethods, null, 2) + "\\n\\n";
                    }
                }
                
                // Full Model State View
                if (viewMode === "models" || viewMode === "all") {
                    stateText += "=== Model State ===\\n";
                    
                    // Try to access the internal _models directly
                    if (window._models) {
                        stateText += "Internal _models Direct Access:\\n";
                        const modelDetails = getModelDetails(window._models);
                        stateText += JSON.stringify(modelDetails, null, 2) + "\\n\\n";
                    } else {
                        stateText += "Internal _models not directly accessible\\n\\n";
                    }
                    
                    // Get models through NoiseSurveyApp.getModels (safe public API)
                    if (window.NoiseSurveyApp && window.NoiseSurveyApp.getModels) {
                        stateText += "Models via NoiseSurveyApp.getModels():\\n";
                        const models = window.NoiseSurveyApp.getModels();
                        stateText += JSON.stringify(models, null, 2) + "\\n\\n";
                    }
                }
                
                // Exposed Debug Objects View
                if (viewMode === "exposed_debug" || viewMode === "all") {
                    stateText += "=== Exposed Debug Objects ===\\n";
                    
                    // Check for exposed debug models
                    if (window.__debugNoiseSurveyModels) {
                        stateText += "Exposed Debug Models (__debugNoiseSurveyModels):\\n";
                        
                        // Get top-level structure
                        const modelKeys = Object.keys(window.__debugNoiseSurveyModels);
                        stateText += `Available keys (${modelKeys.length}): ${modelKeys.join(", ")}\\n\\n`;
                        
                        // Process each top-level key
                        for (const key of modelKeys) {
                            try {
                                const value = window.__debugNoiseSurveyModels[key];
                                stateText += `--- ${key} ---\\n`;
                                
                                if (value === null) {
                                    stateText += "null\\n";
                                } else if (Array.isArray(value)) {
                                    stateText += `Array with ${value.length} items\\n`;
                                    if (value.length > 0) {
                                        if (typeof value[0] === 'object' && value[0] !== null) {
                                            // For arrays of objects, show first item details
                                            stateText += `First item properties: ${Object.keys(value[0]).join(", ")}\\n`;
                                            if (value[0].name) {
                                                stateText += `Names: [${value.slice(0, Math.min(5, value.length)).map(v => v.name || "unnamed").join(", ")}${value.length > 5 ? ", ..." : ""}]\\n`;
                                            }
                                        } else {
                                            // For arrays of primitives, show sample
                                            stateText += `Sample: [${value.slice(0, Math.min(5, value.length))}${value.length > 5 ? ", ..." : ""}]\\n`;
                                        }
                                    }
                                } else if (typeof value === 'object') {
                                    // For objects, show properties
                                    const properties = getAccessibleProperties(value);
                                    stateText += JSON.stringify(properties, null, 2) + "\\n";
                                } else {
                                    stateText += JSON.stringify(value) + "\\n";
                                }
                                stateText += "\\n";
                            } catch (e) {
                                stateText += `Error accessing ${key}: ${e.message}\\n\\n`;
                            }
                        }
                    } else {
                        stateText += "Exposed debug models not found. Make sure window.__debugNoiseSurveyModels is defined in app.js\\n\\n";
                    }
                    
                    // Check for exposed debug state
                    if (window.__debugNoiseSurveyState) {
                        stateText += "Exposed Debug State (__debugNoiseSurveyState):\\n";
                        stateText += JSON.stringify(window.__debugNoiseSurveyState, null, 2) + "\\n\\n";
                    } else {
                        stateText += "Exposed debug state not found. Make sure window.__debugNoiseSurveyState is defined in app.js\\n\\n";
                    }
                }
                
                // Internal Variables View
                if (viewMode === "internals" || viewMode === "all") {
                    stateText += "=== Internal Variables ===\\n";
                    
                    // Internal _state object
                    if (window._state) {
                        stateText += "Internal _state:\\n";
                        stateText += JSON.stringify(window._state, null, 2) + "\\n\\n";
                    } else {
                        stateText += "Internal _state not directly accessible\\n\\n";
                    }
                    
                    // Show playback source if available
                    if (window._models && window._models.playbackSource) {
                        stateText += "Playback Source:\\n";
                        stateText += JSON.stringify(window._models.playbackSource.data, null, 2) + "\\n\\n";
                    }
                    
                    // Show global variables
                    stateText += "Global Variables:\\n";
                    const globals = {};
                    if (window.globalVerticalLinePosition !== undefined) 
                        globals.globalVerticalLinePosition = window.globalVerticalLinePosition;
                    if (window.globalActiveChartIndex !== undefined) 
                        globals.globalActiveChartIndex = window.globalActiveChartIndex;
                    if (window.chartRefs)
                        globals.chartRefs = `Array[${window.chartRefs.length}]`;
                    if (window.barSource)
                        globals.barSource = "Available";
                    if (window.barXRange)
                        globals.barXRange = "Available";
                    
                    stateText += JSON.stringify(globals, null, 2) + "\\n\\n";
                }
                
                stateText += "\\nLast updated: " + new Date().toLocaleTimeString();
            } catch (e) {
                console.error("Error in updateStateMonitor:", e);
                stateText += "ERROR: " + e.message + "\\n";
                stateText += "Stack: " + e.stack + "\\n";
            }
            
            stateText += "</pre>";
            
            // Update the Bokeh model directly
            console.log("Setting monitor text");
            monitor.text = stateText;
            
            console.log("updateStateMonitor completed");
        }
    """
    
    # Add periodic update callback with state_monitor reference
    periodic_callback = CustomJS(
        args=dict(state_monitor=state_monitor, view_select=view_select), 
        code=update_js_code + """
            // Update immediately
            updateStateMonitor();
            
            // Set up auto-refresh
            if (!window._stateMonitorInterval) {
                window._stateMonitorInterval = setInterval(updateStateMonitor, 2000);
                console.log("State monitor auto-refresh started");
            }
        """
    )
    
    # Button click callback with state_monitor reference
    button_callback = CustomJS(
        args=dict(state_monitor=state_monitor, view_select=view_select),
        code=update_js_code + """
            // Update when button is clicked
            updateStateMonitor();
        """
    )
    update_button.js_on_click(button_callback)
    
    # View select change callback
    view_select.js_on_change('value', CustomJS(
        args=dict(state_monitor=state_monitor, view_select=view_select),
        code=update_js_code + """
            // Update when view mode changes
            updateStateMonitor();
        """
    ))
    
    # Create a layout with the controls and state monitor
    debug_tools = Column(
        Row(update_button, view_select),
        state_monitor
    )
    
    # Add the elements to the document
    doc.add_root(debug_tools)
    doc.add_root(periodic_callback)
    
    # Optional: Use debug template if available
    script_dir = os.path.dirname(os.path.abspath(__file__))
    debug_template_path = os.path.join(script_dir, "noise_survey_analysis", "debug.html")
    
    if os.path.exists(debug_template_path):
        with open(debug_template_path, 'r') as f:
            doc.template = f.read()
        logger.info("Debug template applied")
    
    logger.info("Debug app with state monitor prepared")

def run_debug_server(port=5007):
    """
    Run the Bokeh server with the Debug version of Noise Survey Analysis application.
    """
    logger.info(f"Starting Debug server on port: {port}")
    
    # Create a Bokeh application using our function handler
    bokeh_app = Application(FunctionHandler(modify_doc))
    
    # Start the server
    server = Server({'/': bokeh_app}, port=port, io_loop=IOLoop.current(),
                   allow_websocket_origin=[f"localhost:{port}"])
    
    server.start()
    logger.info(f"Server started at http://localhost:{port}")
    
    # Open the application in a browser
    try:
        server.io_loop.add_callback(lambda: os.system(f"start http://localhost:{port}"))
        server.io_loop.start()
    except KeyboardInterrupt:
        logger.info("Server stopped")
        sys.exit(0)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run Debug version with state monitor")
    parser.add_argument("--port", type=int, default=5007, help="Port (default: 5007)")
    args = parser.parse_args()
    
    run_debug_server(port=args.port) 