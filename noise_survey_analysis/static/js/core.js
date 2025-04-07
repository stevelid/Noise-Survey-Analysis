/**
 * 
 * core.js
 * 
 * Core utility functions for Noise Survey Analysis visualization
 * 
 * This file contains common utility functions used across the application,
 * including functions for finding closest indices, creating label text,
 * positioning labels, and other shared utilities.
 */

// Global variables for chart references and models
//let chartRefs = [];
//let sources = {}; // Changed from dataSources to sources for consistency
//let clickLineModels = []; // Store the models passed from Python
//let labelModels = [];   // Store the models passed from Python
//let playback_source = null;
//let playback_button_model = null;
//let pause_button_model = null;

let verticalLinePosition = 0;
let activeChartIndex = -1;
let stepSize = 300000; // Default step size (5 minutes in ms)
let keyboardNavigationEnabled = false;

/**
 * Initialize global references to charts, sources, interaction models,
 * playback controls, and attach keyboard listener.
 * @param {Array} charts_arg - Array of Bokeh chart objects/models
 * @param {Object} sources_arg - Object containing data sources
 * @param {Array} clickLines_arg - Array of click line span models
 * @param {Array} labels_arg - Array of label models
 * @param {Object} playback_source_arg - The playback ColumnDataSource model
 * @param {Object} play_button_arg - The play button model
 * @param {Object} pause_button_arg - The pause button model
 */
function initializeReferences(charts_arg, sources_arg, clickLines_arg, labels_arg,
    playback_source_arg, play_button_arg, pause_button_arg) { // <-- Added args
console.log('initializeReferences called.');

// Store models passed directly as arguments
window.chartRefs = charts_arg || [];
window.sources = sources_arg || {};
window.clickLineModels = clickLines_arg || [];
window.labelModels = labels_arg || [];
window.playback_source = playback_source_arg; // <-- Use passed arg
window.play_button_model = play_button_arg;   // <-- Use passed arg
window.pause_button_model = pause_button_arg; // <-- Use passed arg

// Log confirmation or warnings based on passed arguments
if (!window.playback_source) console.warn("initializeReferences: playback_source_arg was not provided or invalid.");
else console.log("initializeReferences: playback_source assigned.");

if (!window.play_button_model) console.warn("initializeReferences: play_button_arg was not provided or invalid.");
else console.log("initializeReferences: play_button_model assigned.");

if (!window.pause_button_model) console.warn("initializeReferences: pause_button_arg was not provided or invalid.");
else console.log("initializeReferences: pause_button_model assigned.");


// --- Remove or comment out the old model searching logic ---
/*
if (typeof Bokeh !== 'undefined' && Bokeh.documents && Bokeh.documents[0]?.models) {
// ... old searching code ...
} else {
console.error("initializeReferences: Bokeh document/models structure not found!");
}
*/

// --- Attach Keyboard Listener --- (unchanged)
if (!window.keyboardNavigationEnabled) {
// Check if handleKeyPress is defined before adding listener
if (typeof handleKeyPress === 'function') {
document.addEventListener('keydown', handleKeyPress);
window.keyboardNavigationEnabled = true;
console.log('Keyboard navigation/control listener attached.');
} else {
console.warn('initializeReferences: handleKeyPress function not found. Keyboard listener not attached.');
}
}

// --- Export functions --- (Ensure these are still needed globally)
// window.initializeReferences = initializeReferences; // No need to export itself usually
window.findClosestIndex = findClosestIndex;
window.findClosestDateIndex = findClosestDateIndex;
window.createLabelText = createLabelText;
window.positionLabel = positionLabel;
window.calculateStepSize = calculateStepSize;

console.log("Core functions registered on window object. Global models assigned.");
}

/**
 * Find closest index in a date array (assumed sorted) to a given x position (timestamp)
 * @param {Array} dates - Array of date values (timestamps)
 * @param {number} x - X position (timestamp) to find
 * @returns {number} - Index of closest date, or -1 if array is empty/invalid or x is invalid
 */
function findClosestDateIndex(dates, x) {
    // Add checks for robustness
    // --- MODIFIED CHECK ---
    // Check if 'dates' exists, has a numeric 'length' property, and is not empty.
    // This works for standard arrays, typed arrays, and other array-like objects.
    if (!dates || typeof dates.length !== 'number' || dates.length === 0) {
        console.warn("findClosestDateIndex received invalid or empty 'dates' array-like object");
        console.log('dates:', dates);
        console.log('typeof dates:', typeof dates);
        console.log('dates.length:', dates.length);
        console.log('typeof dates.length:', typeof dates.length);
        console.log('dates[0]:', dates[0]);
        console.log('typeof dates[0]:', typeof dates[0]);
        console.log('dates[1]:', dates[1]);
        console.log('typeof dates[1]:', typeof dates[1]);
        return -1;
   }
   // --- END MODIFIED CHECK ---
    if (typeof x !== 'number' || isNaN(x)) {
         console.warn("findClosestDateIndex received invalid 'x' value:", x);
         return -1;
    }

    let low = 0;
    let high = dates.length - 1;
    let closest_idx = 0;
    let min_diff = Infinity;

    // Handle edge cases: x before start or after end
     if (x <= dates[0]) return 0;
     if (x >= dates[high]) return high;

    // Binary search can be efficient for large sorted arrays, but linear scan is simpler and often fast enough
    // Linear scan approach:
    min_diff = Math.abs(dates[0] - x); // Initialize difference
    for (let j = 1; j < dates.length; j++) {
        let diff = Math.abs(dates[j] - x);
        if (diff < min_diff) {
            min_diff = diff;
            closest_idx = j;
        }
        // Optimization: If the difference starts increasing again, we've passed the minimum
        // This assumes dates are somewhat monotonically related to their difference from x, which holds true here.
        else if (diff > min_diff) {
             break;
        }
    }

    return closest_idx;
}

/**
 * Find the closest index in an array to a target value
 * @param {Array} array - Array of values to search
 * @param {number} target - Target value to find
 * @returns {number} - Index of closest value or -1 if array is empty
 */
function findClosestIndex(array, target) {
    if (!array || array.length === 0) return -1;
    
    let minDiff = Infinity;
    let closestIndex = -1;
    
    for (let i = 0; i < array.length; i++) {
        let diff = Math.abs(array[i] - target);
        if (diff < minDiff) {
            minDiff = diff;
            closestIndex = i;
        }
    }
    
    return closestIndex;
}


/**
 * Create label text from data source at given index
 * @param {Object} source - Data source containing time series data
 * @param {number} closest_idx - Index in the data source to display
 * @returns {string} - Formatted label text with time and values
 */
function createLabelText(source, closest_idx) {
    let date = new Date(source.data.Datetime[closest_idx]);
    let formatted_date = date.toLocaleString();
    let label_text = 'Time: ' + formatted_date + '\n';
    
    for (let key in source.data) {
        if (key !== 'Datetime' && key !== 'index') {
            let value = source.data[key][closest_idx];
            if (value !== undefined && !isNaN(value)) {
                let formatted_value = parseFloat(value).toFixed(1);
                label_text += key + ': ' + formatted_value + ' dB\n';
            }
        }
    }
    
    return label_text;
}

/**
 * Position label based on x position and chart boundaries
 * @param {Object} labelModel - Bokeh label object to position
 * @param {Object} chart - Bokeh chart object
 * @param {number} x - X position for label
 */
function positionLabel(labelModel, chart, x) {
    let offset = (chart.x_range.end - chart.x_range.start) * 0.01;
    
    if (x + offset*15 > chart.x_range.end) {
        labelModel.x = x - offset;
        labelModel.text_align = 'right';
    } else {
        labelModel.x = x + offset;
        labelModel.text_align = 'left';
    }
    
    if (chart.y_range && typeof chart.y_range.end !== 'undefined') {
        // Position near the top, adjust based on text baseline if needed
        labelModel.y = chart.y_range.end * 0.95; // Example: 95% of the way up
        labelModel.text_baseline = "top";
    } else {
        // Fallback if y_range is unusual
        labelModel.y = 0;
        console.warn("Chart y_range missing or invalid for label positioning.");
    }
}

/**
 * Calculate time step size based on data
 * @param {Object} source - Data source with Datetime field
 * @returns {number} - Step size in milliseconds
 */
function calculateStepSize(source) {
    if (source && source.data && source.data.Datetime && source.data.Datetime.length > 10) {
        // Use the difference between consecutive points
        let diff = Math.abs(source.data.Datetime[10] - source.data.Datetime[9]);
        return diff > 0 ? diff : 3600000; // Default to 1 hour if calculation fails
    }
    return 3600000; // Default to 1 hour
}

// Export functions for use in other modules
window.initializeReferences = initializeReferences;
window.findClosestIndex = findClosestIndex;
window.findClosestDateIndex = findClosestDateIndex;
window.createLabelText = createLabelText;
window.positionLabel = positionLabel;
window.calculateStepSize = calculateStepSize; 