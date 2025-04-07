# Noise Survey Analysis Debug Mode

This debug mode provides a special version of the application that exposes JavaScript structures and their changes for debugging purposes, without contaminating the main application code.

## Features

- Real-time visualization of JS state and models
- Change tracking for application state
- Interactive exploration of nested objects
- Side-by-side view with the normal application

## How to Use

1. Run the debug server:

```bash
python debug_app.py
```

This will start the application in debug mode on port 5007 (to avoid conflicts with the standard application).

2. The debug panel appears at the bottom-right of the screen. You can:
   - Take manual snapshots of app state
   - Enable auto-snapshots (every 1 second)
   - View changes between snapshots
   - Expand/collapse sections to explore nested data

3. The main application functions normally, so you can interact with it while monitoring state changes.

## Debug Panel Controls

- **Take Snapshot**: Captures the current state of the app
- **Auto Snapshot: On/Off**: Toggles automatic state capturing every second
- **Clear History**: Removes all previously recorded changes

## Debug Panel Sections

1. **Current App State**: Shows the current internal state of the application
2. **Current Models**: Displays the Bokeh models and sources used by the app
3. **Changes History**: Lists all detected changes between snapshots in chronological order

## Implementation Details

The debug mode consists of several components:

1. **debug.js**: A standalone JavaScript module that monitors the application state
2. **debug.html**: A custom template that includes both the main app and debugging tools
3. **debug_app.py**: A server script that loads the application with the debug template

This implementation follows these design principles:
- No modification of main application logic
- Separated concerns between app and debugging tools
- Non-invasive state inspection

## Extending

To track additional parts of the application:

1. Expose them through the `getState()` or `getModels()` methods in app.js
2. They will automatically appear in the debug panel

## Troubleshooting

- If the debug panel doesn't appear, check the browser console for errors
- If state isn't showing correctly, verify that app.js properly exposes state through getState() and getModels()
- For large nested objects, the panel may show truncated data to maintain performance 