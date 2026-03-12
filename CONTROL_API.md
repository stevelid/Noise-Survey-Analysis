# Control API Reference

Complete reference for the Noise Survey Analysis remote control interface.

## Overview

The Noise Survey Analysis dashboard can be controlled programmatically via:
1. **CLI (`nsa-ctl`)** — Local command-line tool
2. **HTTP API** — Direct REST API calls

This enables automation workflows such as:
- Opening the dashboard at a specific timestamp from a URL
- Scripting viewport changes during analysis
- Applying saved workspaces automatically
- Exporting static HTML on demand

## Runtime Design

The live control path now assumes a single active frontend session.

- **Viewport commands** (`set-viewport`, `center-on`, `fit-full-range`) update Bokeh ranges directly on the server.
- **Simple UI state commands** (`set-parameter`, `set-view`) write to a dedicated `control_state_source`.
- The frontend mirrors `control_state_source` into the real Bokeh widgets (`global_parameter_selector`, `global_view_toggle`) and the JS store.
- **Workspace apply** still uses the JS automation bridge because it is a higher-level store rehydration action rather than a simple mirrored control.

This is intentionally simpler than the earlier generic Python -> JS command/ack bus for every UI action.

---

## Security Model

- **Localhost-only:** The control server binds to `127.0.0.1` only — never `0.0.0.0`
- **Opt-in:** Control server is disabled unless explicitly started with `--control-port`
- **Session token:** A random token is generated on startup; required for all commands
- **Payload limits:** Maximum 1 MiB JSON body size

---

## Enabling the Control Server

Start the Bokeh server with the `--control-port` flag:

```bash
# Start with control server on port 8765 (default)
bokeh serve noise_survey_analysis --show --args --control-port 8765

# With a config file
bokeh serve noise_survey_analysis --show --args --config config.json --control-port 8765
```

When the control server starts, it prints:
```
[NSA Control] Listening on http://127.0.0.1:8765
[NSA Control] Session token: <random-hex-token>
```

The token is also written to a temp file for CLI auto-discovery.

---

## CLI Reference (`nsa-ctl`)

### Installation

The CLI is included in the `noise_survey_analysis` package:

```bash
# Run directly
python noise_survey_analysis/control_cli.py <command>

# Or create a shortcut alias
doskey nsa-ctl=python "G:\My Drive\Programing\Noise Survey Analysis\noise_survey_analysis\control_cli.py" $*
```

### Global Options

| Option | Description | Default |
|--------|-------------|---------|
| `--port` | Control server port | Auto-discovered or 8765 |
| `--token` | Session token | Auto-discovered from temp file |

### Commands

#### `status`

Query the current session status.

```bash
nsa-ctl status
```

**Output:**
```json
{
  "success": true,
  "message": "active",
  "data": {
    "active": true,
    "viewport": {
      "start": 1710000000000,
      "end": 1710001800000
    },
    "parameter": "LZeq",
    "view_mode": "log"
  }
}
```

---

#### `set-viewport`

Set the time range viewport (epoch milliseconds).

```bash
nsa-ctl set-viewport --start 1710000000000 --end 1710001800000
```

**Parameters:**
- `--start` (required): Start timestamp in epoch milliseconds
- `--end` (required): End timestamp in epoch milliseconds

**Output:**
```json
{
  "success": true,
  "message": "Viewport update scheduled",
  "data": {
    "start": 1710000000000,
    "end": 1710001800000
  }
}
```

---

#### `center-on`

Center the viewport on a specific timestamp.

```bash
# Center on timestamp with default 30-minute half-width
nsa-ctl center-on --timestamp 1710000900000

# Center with custom half-width (e.g., 1 hour total width)
nsa-ctl center-on --timestamp 1710000900000 --half-width-ms 3600000
```

**Parameters:**
- `--timestamp` (required): Center timestamp in epoch milliseconds
- `--half-width-ms` (optional): Half-width in milliseconds (default: 1800000 = 30 min)

---

#### `fit-full-range`

Reset viewport to show the full data range.

```bash
nsa-ctl fit-full-range
```

---

#### `set-parameter`

Change the active acoustic parameter.

```bash
nsa-ctl set-parameter --value LAeq
```

**Parameters:**
- `--value` (required): Parameter name (e.g., `LAeq`, `LZFmax`, `LAF90`)

**Implementation note:** This updates the dedicated control-state source, which the frontend mirrors into the real parameter widget and JS store.

---

#### `set-view`

Toggle between log and overview view modes.

```bash
nsa-ctl set-view --value log
nsa-ctl set-view --value overview
```

**Parameters:**
- `--value` (required): Either `log` or `overview`

**Implementation note:** This updates the dedicated control-state source, which the frontend mirrors into the real view toggle and JS store.

---

#### `apply-workspace`

Apply a saved workspace file or inline JSON.

```bash
# From file
nsa-ctl apply-workspace --path C:/path/to/workspace.json

# Inline JSON (useful for scripting)
nsa-ctl apply-workspace --inline '{"sourceConfigs": [...], "appState": {...}}'
```

**Parameters:**
- `--path`: Path to workspace JSON file
- `--inline`: Raw workspace JSON string (mutually exclusive with `--path`)

---

#### `export-static-html`

Trigger a static HTML export.

```bash
nsa-ctl export-static-html
```

**Note:** The export runs in the background. Output is saved next to the config file.

---

### CLI Examples

```bash
# Complete workflow example
nsa-ctl status
nsa-ctl fit-full-range
nsa-ctl set-parameter --value LAeq
nsa-ctl set-view --value log
nsa-ctl center-on --timestamp 1710000900000 --half-width-ms 300000  # 10-min view
nsa-ctl export-static-html
```

---

## HTTP API Reference

### Base URL

```
http://127.0.0.1:<port>
```

Default port: `8765`

### Authentication

All commands (except `/health`) require the session token:
- **Header:** `X-Control-Token: <token>`
- **Or body field:** `"token": "<token>"`

### Endpoints

#### `GET /health`

Health check endpoint (no token required).

```bash
curl http://127.0.0.1:8765/health
```

**Response:**
```json
{
  "status": "ok",
  "active": true
}
```

---

#### `POST /control`

Main control endpoint. Accepts all commands.

**Request format:**
```bash
curl -X POST http://127.0.0.1:8765/control \
  -H "Content-Type: application/json" \
  -H "X-Control-Token: <token>" \
  -d '{
    "command": "<command-name>",
    "request_id": "unique-request-id",
    "payload": { ... }
  }'
```

**Response format:**
```json
{
  "success": true,
  "message": "Description of outcome",
  "data": { ... },
  "request_id": "unique-request-id"
}
```

---

### Command Reference

#### `status`

Get current session information.

```bash
curl -X POST http://127.0.0.1:8765/control \
  -H "Content-Type: application/json" \
  -H "X-Control-Token: <token>" \
  -d '{"command": "status", "request_id": "req-1"}'
```

**Response:**
```json
{
  "success": true,
  "message": "active",
  "data": {
    "active": true,
    "viewport": {
      "start": 1710000000000.0,
      "end": 1710001800000.0
    }
  },
  "request_id": "req-1"
}
```

---

#### `set_viewport`

Update the time range viewport.

```bash
curl -X POST http://127.0.0.1:8765/control \
  -H "Content-Type: application/json" \
  -H "X-Control-Token: <token>" \
  -d '{
    "command": "set_viewport",
    "request_id": "req-2",
    "payload": {
      "start": 1710000000000,
      "end": 1710001800000
    }
  }'
```

**Payload fields:**
- `start` (number): Start timestamp (epoch ms)
- `end` (number): End timestamp (epoch ms)

---

#### `center_on_timestamp`

Center viewport on a specific time.

```bash
curl -X POST http://127.0.0.1:8765/control \
  -H "Content-Type: application/json" \
  -H "X-Control-Token: <token>" \
  -d '{
    "command": "center_on_timestamp",
    "request_id": "req-3",
    "payload": {
      "timestamp": 1710000900000,
      "half_width_ms": 1800000
    }
  }'
```

**Payload fields:**
- `timestamp` (number): Center timestamp (epoch ms)
- `half_width_ms` (number, optional): Half-width in ms (default: 1800000)

---

#### `fit_full_range`

Reset to full data range.

```bash
curl -X POST http://127.0.0.1:8765/control \
  -H "Content-Type: application/json" \
  -H "X-Control-Token: <token>" \
  -d '{
    "command": "fit_full_range",
    "request_id": "req-4"
  }'
```

---

#### `set_parameter`

Change the active parameter.

```bash
curl -X POST http://127.0.0.1:8765/control \
  -H "Content-Type: application/json" \
  -H "X-Control-Token: <token>" \
  -d '{
    "command": "set_parameter",
    "request_id": "req-5",
    "payload": {
      "value": "LAeq"
    }
  }'
```

**Payload fields:**
- `value` (string): Parameter name

---

#### `set_view_mode`

Change view mode.

```bash
curl -X POST http://127.0.0.1:8765/control \
  -H "Content-Type: application/json" \
  -H "X-Control-Token: <token>" \
  -d '{
    "command": "set_view_mode",
    "request_id": "req-6",
    "payload": {
      "value": "log"
    }
  }'
```

**Payload fields:**
- `value` (string): `"log"` or `"overview"`

---

#### `apply_workspace`

Apply a saved workspace.

```bash
# From file path
curl -X POST http://127.0.0.1:8765/control \
  -H "Content-Type: application/json" \
  -H "X-Control-Token: <token>" \
  -d '{
    "command": "apply_workspace",
    "request_id": "req-7",
    "payload": {
      "path": "C:/path/to/workspace.json"
    }
  }'

# Or inline payload
curl -X POST http://127.0.0.1:8765/control \
  -H "Content-Type: application/json" \
  -H "X-Control-Token: <token>" \
  -d '{
    "command": "apply_workspace",
    "request_id": "req-7",
    "payload": {
      "payload": {"sourceConfigs": [...], "appState": {...}}
    }
  }'
```

**Payload fields (one required):**
- `path` (string): Path to workspace JSON file
- `payload` (object): Inline workspace object

---

#### `export_static_html`

Trigger static HTML export.

```bash
curl -X POST http://127.0.0.1:8765/control \
  -H "Content-Type: application/json" \
  -H "X-Control-Token: <token>" \
  -d '{
    "command": "export_static_html",
    "request_id": "req-8"
  }'
```

---

### Error Responses

**Invalid token:**
```json
{
  "success": false,
  "message": "Unauthorized",
  "request_id": "req-1"
}
```

**Invalid command:**
```json
{
  "success": false,
  "message": "Command 'invalid_cmd' is not allowed",
  "request_id": "req-2"
}
```

**Invalid payload:**
```json
{
  "success": false,
  "message": "start must be less than end",
  "request_id": "req-3"
}
```

**No active session:**
```json
{
  "success": false,
  "message": "no active session",
  "request_id": "req-4"
}
```

---

## Python API

For Python automation scripts, use the control modules directly:

```python
from noise_survey_analysis.control import SessionBridge, ControlServer
from noise_survey_analysis.control.commands import ControlCommand

# Create bridge and server
bridge = SessionBridge()
server = ControlServer(bridge)

# Start control server
token = server.start(port=8765)
print(f"Token: {token}")

# Use the bridge directly
result = bridge.set_viewport(
    start=1710000000000,
    end=1710001800000,
    request_id="script-1"
)
print(result.to_dict())

# Stop server
server.stop()
```

---

## URL Deep-Link Parameters

When launching the dashboard, you can specify initial state via URL query parameters:

```
http://localhost:5006/noise_survey_analysis?config=path/to/config.json&start=1710000000000&end=1710001800000&param=LAeq&view=log
```

**Supported parameters:**
- `config`: Path to config JSON file
- `state`: Path to workspace JSON file
- `start`: Initial viewport start (epoch ms)
- `end`: Initial viewport end (epoch ms)
- `param`: Initial parameter (e.g., `LAeq`)
- `view`: Initial view mode (`log` or `overview`)

**Precedence order:**
1. App defaults
2. Config-selected data load
3. Workspace restore (`state`)
4. URL deep-link overrides
5. Runtime CLI/API commands

---

## Common Workflows

### Automated Report Generation

```bash
# 1. Start server with control enabled
bokeh serve noise_survey_analysis --show --args --config job1234.json --control-port 8765 &

# 2. Wait for server ready
sleep 5

# 3. Navigate to specific time ranges and export
nsa-ctl center-on --timestamp 1710000000000
nsa-ctl export-static-html

nsa-ctl center-on --timestamp 1710003600000
nsa-ctl export-static-html
```

### Integration with External Tools

```python
import requests
import json

# Control an active session
TOKEN = "<session-token>"
PORT = 8765

def set_viewport(start_ms, end_ms):
    resp = requests.post(
        f"http://127.0.0.1:{PORT}/control",
        headers={
            "Content-Type": "application/json",
            "X-Control-Token": TOKEN
        },
        json={
            "command": "set_viewport",
            "request_id": "auto-1",
            "payload": {"start": start_ms, "end": end_ms}
        }
    )
    return resp.json()

# Example: Jump to event at specific time
event_time = 1710000900000  # From detection algorithm
set_viewport(event_time - 300000, event_time + 300000)  # 10-min window
```

---

## Troubleshooting

### "Connection failed"

- Verify the control server is enabled (`--control-port` flag)
- Check the correct port is being used
- Ensure you're connecting to `127.0.0.1`, not `localhost`

### "Unauthorized"

- Token has changed (server was restarted)
- Check the current token in the server console output
- Token file is in temp directory: `%TEMP%\nsa_control_token.txt`

### Commands timeout

- Browser may not have loaded the dashboard yet
- JS bridge commands need an active Bokeh session
- Check that the dashboard is fully initialized

### Viewport not updating

- Verify `start` < `end` (both epoch milliseconds)
- Check that timestamps are within the data range
- Use `fit_full_range` to see the full dataset first

---

## See Also

- `README.md` — General usage guide
- `HYBRID_CONTROL_PLAN.md` — Original design document
- `noise_survey_analysis/control/` — Implementation source code
