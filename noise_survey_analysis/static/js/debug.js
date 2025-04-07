/**
 * debug.js
 * 
 * Debug utilities for Noise Survey Analysis Visualization
 * This file provides tools to monitor and display JavaScript structures
 * from the main app.js without contaminating the main application logic.
 */

window.NoiseSurveyDebug = (function() {
    'use strict';

    // Private state for the debugger
    let _debugState = {
        trackedObjects: {},
        changeHistory: [],
        snapshotInterval: null,
        lastSnapshot: null,
        isActive: false,
        containerElement: null,
        maxHistoryLength: 50,
        expandedSections: {}
    };

    // Create or get the debug container
    function _getDebugContainer() {
        if (_debugState.containerElement) {
            console.log("NoiseSurveyDebug: Found existing debug-container element.");
            return _debugState.containerElement;
        }

        let container = document.getElementById('debug-container');
        if (!container) {
            console.log("NoiseSurveyDebug: Creating debug-container element.");
            container = document.createElement('div');
            container.id = 'debug-container';
            container.className = 'debug-panel';
            document.body.appendChild(container);

            // Add basic styles if they don't exist
            if (!document.getElementById('debug-styles')) {
                const style = document.createElement('style');
                style.id = 'debug-styles';
                style.textContent = `
                    .debug-panel {
                        position: fixed !important;
                        bottom: 0 !important;
                        right: 0 !important;
                        width: 50% !important;
                        height: 50% !important;
                        background: rgba(0, 0, 0, 0.9) !important;
                        color: #00ff00 !important;
                        font-family: monospace !important;
                        overflow: auto !important;
                        z-index: 100000 !important;
                        padding: 10px !important;
                        border-top-left-radius: 5px !important;
                        font-size: 12px !important;
                        resize: both !important;
                        border: 3px solid red !important;
                        box-shadow: 0 0 15px rgba(255, 0, 0, 0.7) !important;
                    }
                    .debug-controls {
                        position: sticky;
                        top: 0;
                        background: #222;
                        padding: 5px;
                        border-bottom: 1px solid #444;
                        margin-bottom: 10px;
                        display: flex;
                        gap: 10px;
                    }
                    .debug-section {
                        margin-bottom: 15px;
                        border: 1px solid #444;
                        border-radius: 3px;
                        padding: 5px;
                    }
                    .debug-section-header {
                        font-weight: bold;
                        cursor: pointer;
                        background: #333;
                        padding: 5px;
                        margin-bottom: 5px;
                    }
                    .debug-object {
                        margin-left: 15px;
                    }
                    .debug-property {
                        display: flex;
                    }
                    .debug-key {
                        color: #88f;
                        margin-right: 5px;
                    }
                    .debug-value {
                        color: #0f0;
                    }
                    .debug-value-number {
                        color: #f80;
                    }
                    .debug-value-string {
                        color: #0f0;
                    }
                    .debug-value-boolean {
                        color: #f0f;
                    }
                    .debug-value-object {
                        color: #ff0;
                        cursor: pointer;
                    }
                    .debug-changes {
                        background: #300;
                        border-left: 3px solid #f00;
                        padding-left: 5px;
                    }
                    .debug-button {
                        background: #555;
                        border: none;
                        color: white;
                        padding: 3px 8px;
                        border-radius: 3px;
                        cursor: pointer;
                    }
                    .debug-button:hover {
                        background: #777;
                    }
                    .debug-expanded > .debug-object {
                        display: block;
                    }
                    .debug-collapsed > .debug-object {
                        display: none;
                    }
                `;
                document.head.appendChild(style);
            }

            // Add controls
            const controls = document.createElement('div');
            controls.className = 'debug-controls';
            
            const takeSnapshotBtn = document.createElement('button');
            takeSnapshotBtn.className = 'debug-button';
            takeSnapshotBtn.textContent = 'Take Snapshot';
            takeSnapshotBtn.onclick = () => { takeSnapshot(); };
            
            const toggleAutoBtn = document.createElement('button');
            toggleAutoBtn.className = 'debug-button';
            toggleAutoBtn.textContent = 'Auto Snapshot: Off';
            toggleAutoBtn.onclick = () => { 
                toggleAutoSnapshot(); 
                toggleAutoBtn.textContent = _debugState.snapshotInterval ? 
                    'Auto Snapshot: On' : 'Auto Snapshot: Off';
            };

            const clearBtn = document.createElement('button');
            clearBtn.className = 'debug-button';
            clearBtn.textContent = 'Clear History';
            clearBtn.onclick = () => { 
                _debugState.changeHistory = [];
                _debugState.lastSnapshot = null;
                renderDebugInfo();
            };

            // Add force visibility button
            const forceVisibleBtn = document.createElement('button');
            forceVisibleBtn.className = 'debug-button';
            forceVisibleBtn.style.backgroundColor = '#f00';
            forceVisibleBtn.textContent = 'Force Visible';
            forceVisibleBtn.onclick = () => {
                container.style.display = 'block !important';
                container.style.visibility = 'visible !important';
                container.style.opacity = '1 !important';
                container.style.backgroundColor = 'rgba(255, 0, 0, 0.9) !important';
                container.style.zIndex = '999999 !important';
                
                // Add text to show it's working
                const msg = document.createElement('div');
                msg.textContent = 'DEBUG PANEL FORCE VISIBLE: ' + new Date().toLocaleTimeString();
                msg.style.color = 'white';
                msg.style.fontWeight = 'bold';
                container.appendChild(msg);
                
                console.log('Debug panel force visible at ' + new Date().toLocaleTimeString());
            };

            controls.appendChild(takeSnapshotBtn);
            controls.appendChild(toggleAutoBtn);
            controls.appendChild(clearBtn);
            controls.appendChild(forceVisibleBtn);
            container.appendChild(controls);
            
            // Add a notification about visibility
            const notification = document.createElement('div');
            notification.textContent = 'DEBUG PANEL LOADED: ' + new Date().toLocaleTimeString();
            notification.style.color = 'yellow';
            notification.style.fontWeight = 'bold';
            container.appendChild(notification);
        } else {
            console.log("NoiseSurveyDebug: Found existing debug-container element.");
        }

        _debugState.containerElement = container;
        console.log("NoiseSurveyDebug: Debug container element acquired:", container);
        // Log computed style to check visibility
        setTimeout(() => {
             if (_debugState.containerElement) {
                 const styles = window.getComputedStyle(_debugState.containerElement);
                 console.log("NoiseSurveyDebug: Computed styles for container:", { display: styles.display, visibility: styles.visibility, opacity: styles.opacity, zIndex: styles.zIndex });
             }
        }, 100); // Short delay to allow styles to apply
        return container;
    }

    // Format JS values for display
    function _formatValue(value, depth = 0, path = '', expanded = false) {
        if (value === null) return '<span class="debug-value-object">null</span>';
        if (value === undefined) return '<span class="debug-value-object">undefined</span>';

        const maxDepth = 1; // Limit nesting display
        
        if (depth > maxDepth) {
            if (Array.isArray(value)) {
                return `<span class="debug-value-object">Array(${value.length})</span>`;
            }
            if (typeof value === 'object') {
                return `<span class="debug-value-object">Object</span>`;
            }
        }

        if (typeof value === 'number') {
            return `<span class="debug-value-number">${value}</span>`;
        }
        if (typeof value === 'string') {
            return `<span class="debug-value-string">"${value}"</span>`;
        }
        if (typeof value === 'boolean') {
            return `<span class="debug-value-boolean">${value}</span>`;
        }
        
        if (Array.isArray(value)) {
            if (value.length === 0) return '[]';
            
            const expandClass = (expanded) ? 'debug-expanded' : 'debug-collapsed';
            let html = `<span class="debug-value-object" data-path="${path}" onclick="NoiseSurveyDebug.toggleExpand(event)">Array(${value.length})</span>`;
            html += `<div class="debug-object ${expandClass}">`;
            
            // Sample first 10 items only for large arrays
            const displayItems = value.length > 10 ? value.slice(0, 10) : value;
            
            for (let i = 0; i < displayItems.length; i++) {
                html += `<div class="debug-property">`;
                html += `<span class="debug-key">[${i}]:</span>`;
                html += `<span class="debug-value">${_formatValue(value[i], depth + 1, `${path}[${i}]`)}</span>`;
                html += `</div>`;
            }
            
            if (value.length > 10) {
                html += `<div class="debug-property"><span class="debug-key">...</span><span class="debug-value">${value.length - 10} more items</span></div>`;
            }
            
            html += `</div>`;
            return html;
        }
        
        if (typeof value === 'object') {
            const keys = Object.keys(value);
            if (keys.length === 0) return '{}';
            
            const expandClass = (expanded) ? 'debug-expanded' : 'debug-collapsed';
            let html = `<span class="debug-value-object" data-path="${path}" onclick="NoiseSurveyDebug.toggleExpand(event)">Object{${keys.length}}</span>`;
            html += `<div class="debug-object ${expandClass}">`;
            
            // Sample first 10 properties only for large objects
            const displayKeys = keys.length > 10 ? keys.slice(0, 10) : keys;
            
            for (const key of displayKeys) {
                html += `<div class="debug-property">`;
                html += `<span class="debug-key">${key}:</span>`;
                html += `<span class="debug-value">${_formatValue(value[key], depth + 1, path ? `${path}.${key}` : key)}</span>`;
                html += `</div>`;
            }
            
            if (keys.length > 10) {
                html += `<div class="debug-property"><span class="debug-key">...</span><span class="debug-value">${keys.length - 10} more properties</span></div>`;
            }
            
            html += `</div>`;
            return html;
        }
        
        return `<span class="debug-value">${value}</span>`;
    }

    // Compare objects to find changes
    function _findChanges(oldObj, newObj, path = '') {
        if (!oldObj || !newObj) return [];
        
        const changes = [];
        const allKeys = new Set([...Object.keys(oldObj), ...Object.keys(newObj)]);
        
        for (const key of allKeys) {
            const keyPath = path ? `${path}.${key}` : key;
            
            // Key exists in both objects
            if (key in oldObj && key in newObj) {
                if (typeof oldObj[key] === 'object' && oldObj[key] !== null && 
                    typeof newObj[key] === 'object' && newObj[key] !== null) {
                    // Recursively check nested objects
                    changes.push(..._findChanges(oldObj[key], newObj[key], keyPath));
                } 
                else if (oldObj[key] !== newObj[key]) {
                    changes.push({
                        path: keyPath,
                        oldValue: oldObj[key],
                        newValue: newObj[key]
                    });
                }
            }
            // Key only in old object (removed)
            else if (key in oldObj) {
                changes.push({
                    path: keyPath,
                    oldValue: oldObj[key],
                    newValue: undefined,
                    type: 'removed'
                });
            }
            // Key only in new object (added)
            else {
                changes.push({
                    path: keyPath,
                    oldValue: undefined,
                    newValue: newObj[key],
                    type: 'added'
                });
            }
        }
        
        return changes;
    }

    // Take a snapshot of the NoiseSurveyApp object
    function takeSnapshot() {
        if (!window.NoiseSurveyApp) {
            console.warn('NoiseSurveyApp not found for debugging');
            return;
        }
        
        const currentSnapshot = {
            timestamp: new Date(),
            appState: {},
            models: {}
        };
        
        // Get exposed state and models from the app
        if (typeof window.NoiseSurveyApp.getState === 'function') {
            currentSnapshot.appState = window.NoiseSurveyApp.getState();
        }
        
        if (typeof window.NoiseSurveyApp.getModels === 'function') {
            currentSnapshot.models = window.NoiseSurveyApp.getModels();
        }
        
        // Find changes compared to last snapshot
        let changes = [];
        if (_debugState.lastSnapshot) {
            changes = [
                ..._findChanges(_debugState.lastSnapshot.appState, currentSnapshot.appState, 'appState'),
                ..._findChanges(_debugState.lastSnapshot.models, currentSnapshot.models, 'models')
            ];
            
            if (changes.length > 0) {
                _debugState.changeHistory.push({
                    timestamp: new Date(),
                    changes: changes
                });
                
                // Limit history length
                if (_debugState.changeHistory.length > _debugState.maxHistoryLength) {
                    _debugState.changeHistory.shift();
                }
            }
        }
        
        _debugState.lastSnapshot = currentSnapshot;
        renderDebugInfo();
        
        return changes;
    }

    // Toggle auto snapshot
    function toggleAutoSnapshot() {
        if (_debugState.snapshotInterval) {
            clearInterval(_debugState.snapshotInterval);
            _debugState.snapshotInterval = null;
        } else {
            _debugState.snapshotInterval = setInterval(takeSnapshot, 1000);
        }
    }

    // Render the debug information
    function renderDebugInfo() {
        const container = _getDebugContainer();
        
        // Clear previous content except controls
        const controls = container.querySelector('.debug-controls');
        container.innerHTML = '';
        container.appendChild(controls);
        
        if (!_debugState.lastSnapshot) {
            const message = document.createElement('div');
            message.textContent = 'No data captured yet. Click "Take Snapshot" to capture app state.';
            container.appendChild(message);
            return;
        }
        
        // Current state section
        const stateSection = document.createElement('div');
        stateSection.className = 'debug-section';
        
        const stateHeader = document.createElement('div');
        stateHeader.className = 'debug-section-header';
        stateHeader.textContent = 'Current App State';
        stateHeader.onclick = () => {
            const content = stateSection.querySelector('.debug-section-content');
            content.style.display = content.style.display === 'none' ? 'block' : 'none';
        };
        
        const stateContent = document.createElement('div');
        stateContent.className = 'debug-section-content';
        stateContent.innerHTML = _formatValue(_debugState.lastSnapshot.appState, 0, 'appState', true);
        
        stateSection.appendChild(stateHeader);
        stateSection.appendChild(stateContent);
        container.appendChild(stateSection);
        
        // Current models section
        const modelsSection = document.createElement('div');
        modelsSection.className = 'debug-section';
        
        const modelsHeader = document.createElement('div');
        modelsHeader.className = 'debug-section-header';
        modelsHeader.textContent = 'Current Models';
        modelsHeader.onclick = () => {
            const content = modelsSection.querySelector('.debug-section-content');
            content.style.display = content.style.display === 'none' ? 'block' : 'none';
        };
        
        const modelsContent = document.createElement('div');
        modelsContent.className = 'debug-section-content';
        modelsContent.innerHTML = _formatValue(_debugState.lastSnapshot.models, 0, 'models', true);
        
        modelsSection.appendChild(modelsHeader);
        modelsSection.appendChild(modelsContent);
        container.appendChild(modelsSection);
        
        // Changes history
        if (_debugState.changeHistory.length > 0) {
            const changesSection = document.createElement('div');
            changesSection.className = 'debug-section';
            
            const changesHeader = document.createElement('div');
            changesHeader.className = 'debug-section-header';
            changesHeader.textContent = `Changes History (${_debugState.changeHistory.length})`;
            changesHeader.onclick = () => {
                const content = changesSection.querySelector('.debug-section-content');
                content.style.display = content.style.display === 'none' ? 'block' : 'none';
            };
            
            const changesContent = document.createElement('div');
            changesContent.className = 'debug-section-content';
            
            // Display changes in reverse chronological order
            for (let i = _debugState.changeHistory.length - 1; i >= 0; i--) {
                const changeGroup = _debugState.changeHistory[i];
                const changeTime = changeGroup.timestamp.toLocaleTimeString();
                
                const changeEntry = document.createElement('div');
                changeEntry.className = 'debug-changes';
                
                const changeHeader = document.createElement('div');
                changeHeader.className = 'debug-section-header';
                changeHeader.textContent = `${changeTime} (${changeGroup.changes.length} changes)`;
                changeHeader.style.fontSize = '90%';
                changeHeader.onclick = (e) => {
                    const content = changeEntry.querySelector('.debug-changes-content');
                    content.style.display = content.style.display === 'none' ? 'block' : 'none';
                    e.stopPropagation();
                };
                
                const changeContent = document.createElement('div');
                changeContent.className = 'debug-changes-content';
                changeContent.style.display = 'none'; // Collapsed by default
                
                let changesHtml = '';
                for (const change of changeGroup.changes) {
                    const type = change.type || 'changed';
                    changesHtml += `<div class="debug-property">`;
                    changesHtml += `<span class="debug-key">${change.path} (${type}):</span>`;
                    changesHtml += `<span class="debug-value">`;
                    
                    if (type !== 'added') {
                        changesHtml += `From: ${_formatValue(change.oldValue)}`;
                    }
                    
                    if (type !== 'removed') {
                        if (type !== 'added') changesHtml += ` → `;
                        changesHtml += `To: ${_formatValue(change.newValue)}`;
                    }
                    
                    changesHtml += `</span></div>`;
                }
                
                changeContent.innerHTML = changesHtml;
                changeEntry.appendChild(changeHeader);
                changeEntry.appendChild(changeContent);
                changesContent.appendChild(changeEntry);
            }
            
            changesSection.appendChild(changesHeader);
            changesSection.appendChild(changesContent);
            container.appendChild(changesSection);
        }
    }

    // Toggle expanded/collapsed sections
    function toggleExpand(event) {
        event.stopPropagation();
        const target = event.target;
        const path = target.getAttribute('data-path');
        
        if (path) {
            _debugState.expandedSections[path] = !_debugState.expandedSections[path];
            const objectContainer = target.nextElementSibling;
            
            if (objectContainer && objectContainer.classList.contains('debug-object')) {
                if (_debugState.expandedSections[path]) {
                    objectContainer.classList.remove('debug-collapsed');
                    objectContainer.classList.add('debug-expanded');
                } else {
                    objectContainer.classList.remove('debug-expanded');
                    objectContainer.classList.add('debug-collapsed');
                }
            }
        }
    }

    // Initialize the debug environment
    function initialize() {
        if (_debugState.isActive) {
            console.log("NoiseSurveyDebug: Already initialized.");
            return;
        }
        
        console.log("NoiseSurveyDebug: Attempting initialization...");

        // Check if NoiseSurveyApp exists and add necessary hooks
        if (window.NoiseSurveyApp) {
            console.log('NoiseSurveyDebug: Found NoiseSurveyApp. Initializing debug tools.');
            
            // If app doesn't have getState and getModels methods, create temporary versions
            if (typeof window.NoiseSurveyApp.getState !== 'function' || 
                typeof window.NoiseSurveyApp.getModels !== 'function') {
                
                console.log('NoiseSurveyDebug: Adding access methods to NoiseSurveyApp');
                
                // Create a deep copy function to avoid modification of the original objects
                const deepCopy = (obj) => {
                    if (obj === null || typeof obj !== 'object') return obj;
                    if (obj instanceof Date) return new Date(obj.getTime());
                    if (Array.isArray(obj)) return obj.map(item => deepCopy(item));
                    
                    const result = {};
                    for (const key in obj) {
                        if (key.startsWith('_')) continue; // Skip private members
                        if (Object.prototype.hasOwnProperty.call(obj, key)) {
                            result[key] = deepCopy(obj[key]);
                        }
                    }
                    return result;
                };
                
                // Add getState method if not present
                if (typeof window.NoiseSurveyApp.getState !== 'function') {
                    window.NoiseSurveyApp.getState = function() {
                        if (!this._state) return {};
                        return deepCopy(this._state);
                    };
                }
                
                // Add getModels method if not present
                if (typeof window.NoiseSurveyApp.getModels !== 'function') {
                    window.NoiseSurveyApp.getModels = function() {
                        if (!this._models) return {};
                        return deepCopy(this._models);
                    };
                }
            }
            
            _getDebugContainer();
            renderDebugInfo(); // Initial render (might be empty)
            _debugState.isActive = true;
            console.log('NoiseSurveyDebug: Initialization complete.');
            
            // Take initial snapshot after a short delay to allow app state to settle
            setTimeout(() => {
                console.log("NoiseSurveyDebug: Taking initial snapshot.");
                takeSnapshot();
            }, 500);

        } else {
            console.warn('NoiseSurveyDebug: NoiseSurveyApp not found yet. Debug features will be limited. Will retry shortly.');
            // Optionally, retry initialization after a delay
            // setTimeout(initialize, 1000); // Uncomment to enable retry
        }
    }

    // Public API
    return {
        initialize: initialize,
        takeSnapshot: takeSnapshot,
        toggleAutoSnapshot: toggleAutoSnapshot,
        toggleExpand: toggleExpand,
        renderDebugInfo: renderDebugInfo
    };
})();

// Auto-initialize: Check readiness periodically
function attemptDebugInitialization() {
    console.log("NoiseSurveyDebug: Checking readiness for initialization...");
    // Check for Bokeh documents and the main app object
    if (typeof Bokeh !== 'undefined' && Bokeh.documents && Bokeh.documents.length > 0 && window.NoiseSurveyApp) {
        console.log("NoiseSurveyDebug: Bokeh and NoiseSurveyApp detected. Initializing now.");
        window.NoiseSurveyDebug.initialize();
    } else {
        console.log("NoiseSurveyDebug: Not ready yet. Retrying in 1 second.");
        // Retry after a delay if not ready
        setTimeout(attemptDebugInitialization, 1000); 
    }
}

// Start the initialization check process after the document is loaded
if (document.readyState === 'complete' || document.readyState === 'interactive') {
    console.log("NoiseSurveyDebug: Document loaded, starting initialization check.");
    attemptDebugInitialization();
} else {
    console.log("NoiseSurveyDebug: Adding DOMContentLoaded listener for initialization check.");
    document.addEventListener('DOMContentLoaded', () => {
        console.log("NoiseSurveyDebug: DOMContentLoaded event fired, starting initialization check.");
        attemptDebugInitialization();
    });
} 