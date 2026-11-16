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

Use the shared launcher with the `-ControlPort` option:

```powershell
& "G:\Shared drives\Venta\Software\Noise Survey Analysis\launch_noise_survey.ps1" -ControlPort 8765

# With a config file
& "G:\Shared drives\Venta\Software\Noise Survey Analysis\launch_noise_survey.ps1" -ConfigPath "<config path>" -ControlPort 8765
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

The CLI is included in the shared `noise_survey_analysis` package. Run shared
setup once, then use its private Python:

```powershell
& "$env:LOCALAPPDATA\NoiseSurveyAnalysis\venv\Scripts\python.exe" "G:\Shared drives\Venta\Software\Noise Survey Analysis\Noise Survey Analysis\noise_survey_analysis\control_cli.py" status

# Optional alias for this PowerShell session
function nsa-ctl {
    & "$env:LOCALAPPDATA\NoiseSurveyAnalysis\venv\Scripts\python.exe" "G:\Shared drives\Venta\Software\Noise Survey Analysis\Noise Survey Analysis\noise_survey_analysis\control_cli.py" @args
}
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

**Request ids.** `request_id` is optional. For commands that go through the browser
(`apply_workspace`, `export_annotations`, `export_static_html`) the server always
appends a fresh unique suffix (or generates a UUID when none is given) and returns that
effective id in the response. The browser drops a command whose id repeats the previous
one, so a client-supplied repeat is never sent as-is. `nsa-ctl` also adds a new suffix on
every call.

**Acknowledgement.** `apply_workspace` and `export_annotations` wait up to 10 s for the
browser to acknowledge. No acknowledgement (no open tab, throttled tab, dropped command)
returns `success: false` (HTTP 500; `nsa-ctl` exits 1) with a message saying it may not
have been applied. The command was still sent, so check the dashboard before retrying.

**Workspace payloads** (inline or from `path`) must contain an `appState` object and a
`version` of 1 or 2 if present; `sourceConfigs` alone is rejected (same rule as the
browser). Files may carry a UTF-8 BOM. Workspace failures in the browser (bad file,
missing `appState`, source mismatch) also show a toast.

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

## Annotation Commands (agent suggestions)

An agent (a classifier script, an LLM) can read, propose and edit regions and markers in a running dashboard. Items it adds are **suggestions**: drawn as faint dashed bands/lines, listed with an "AI 0.82" badge, and reviewed by the user (A accept, D reject, `{` `}` step) in the Regions or Markers tab. These commands need an open dashboard tab, because the browser applies them; for a read without a browser use `nsa-ctl annotations` (below).

**Times.** Epoch milliseconds (JSON number) or ISO-8601 **with a UTC offset** (`2026-11-09T10:16:42Z`, `...+01:00`). A naive string such as `2026-11-09T10:16:42` is rejected, as is a number below 1e11 (probably epoch seconds). `start` must be before `end`. All times are epoch **milliseconds** (not seconds).

**Time basis (`time_basis`).** Accepted by `add_regions`, `add_markers`, `update_region`, `update_marker`, `list_annotations` and `show` (a top-level payload field). It says which clock the times in that call are on:

- `"source"` (the default): the true UTC instant of the data. Use this when the times come from the survey files. The instrument `_log.csv` / `_summary.csv` files hold **naive Europe/London wall-clock** times (BST, UTC+1, in summer; GMT, UTC+0, in winter), so convert to UTC first, then to epoch ms. The browser adds the position's chart offset to get display time (the chart axis, which is what regions and markers are stored in).
- `"display"`: times are already on the chart axis (source time plus the position's chart offset, `position_chart_offsets` in `list_annotations`; the offset is in ms and is **added** to source time to get display time, usually 0). Use this for times copied from the chart or from a previous `list_annotations` `start`/`end`.

With a zero chart offset the two are identical. Records returned by `list_annotations` carry both: `start`/`end` (and marker `timestamp`) are display time; `source_start`/`source_end`/`source_areas` (and marker `source_timestamp`, plus `*_iso` strings) are source time, so `source_*` can be matched straight against the survey files. A marker with no `position` uses a zero offset. The survey-range check is skipped for `"display"`.

Worked examples (offset 0):

| Log file row (naive London time) | UTC | Epoch ms | Send as |
|---|---|---|---|
| `2026-07-02 14:05:30` (BST, UTC+1) | `2026-07-02T13:05:30Z` | `1782997530000` | `"start": 1782997530000` or `"start": "2026-07-02T14:05:30+01:00"` |
| `2026-11-09 10:16:42` (GMT, UTC+0) | `2026-11-09T10:16:42Z` | `1794219402000` | `"start": 1794219402000` or `"start": "2026-11-09T10:16:42Z"` |

A common mistake is to treat the BST wall-clock `14:05:30` as UTC (`...T14:05:30Z`): that is an hour late. In Python: `pd.Timestamp("2026-07-02 14:05:30").tz_localize("Europe/London").tz_convert("UTC").value // 10**6`. If a position has chart offset +2000 ms, the same `source` call lands at display time 1782997532000; the stored region then reports `start: 1782997532000, source_start: 1782997530000`.

**Validation (HTTP 400, nothing applied).** `position` must be a registered position (when the server knows the list); `confidence` is 0 to 1 or null; at most 500 items per call; text limits: note 2,000 characters, rationale 2,000; unknown fields are errors; `client_ref` must be unique within a call. Agent-added items get `source: "agent"` and default to `status: "proposed"` (an add may use `"proposed"` or `"accepted"`).

**Fields stored on regions and markers:** `source` (`user`/`agent`), `status` (`proposed`/`accepted`/`rejected`; absent means an ordinary user item), `rationale` (read-only text for the reviewer), `confidence`, `agent {name, runId}`, `createdAt`, `reviewedAt`. `note` stays the user-editable label; fill it with what you think the event is and why. Editing bounds, note or category never changes `status`; only accept/reject does. Rejected items stay (hidden, under "Rejected (n)") so you do not propose them again.

Every successful call returns `{"success": true, "message": ..., "data": {...}}`; if the browser does not answer within 15 s the call is a failure (it may or may not have been applied).

### `add_regions`

```json
{"command": "add_regions", "payload": {
  "agent": {"name": "yamnet", "run_id": "2026-11-09-a"},
  "regions": [{
    "position": "6645-4",
    "start": "2026-11-09T10:16:42Z", "end": "2026-11-09T10:17:02Z",
    "note": "Dog barking, three barks",
    "category": "Dog bark",
    "rationale": "Harmonic bursts around 800 Hz, LAFmax +14 dB over background",
    "confidence": 0.82,
    "meter_states": {"6645-5A": "present"},
    "client_ref": "ev-001"
  }]}}
```

Use `areas: [{"start":..., "end":...}, ...]` instead of `start`/`end` for a multi-area region. `category` is an existing category id or label (case-insensitive); an unknown name creates a new category. Optional: `status`, `color`. Returns `{"ids": [12], "by_client_ref": {"ev-001": 12}, "categories_created": [...]}`. The user's selection is not changed. One Ctrl+Z removes the whole batch, including any categories the call created (the same holds for `add_markers`, `update_*` and `delete_*`: one command is one undo step).

### `update_region`, `delete_regions`

```json
{"command": "update_region", "payload": {"id": 12, "changes": {"note": "Two barks, not three", "end": "2026-11-09T10:16:58Z", "confidence": 0.7}}}
{"command": "delete_regions", "payload": {"ids": [12, 13]}}
```

`changes` may hold `start`, `end` (or `areas`), `note`, `category`, `meter_states`, `status`, `rationale`, `confidence`, `color`; the position cannot change. `update_region` returns `{"region": {...}}`. `delete_regions` returns `{"deleted": [...], "missing": [...]}`; ids that do not exist are reported, not an error. It refuses (failure, nothing deleted) if any id is a user-made region unless `"force": true`.

### `add_markers`, `update_marker`, `delete_markers`

Same shape with `markers: [{"timestamp", "position"?, "note", "rationale", "confidence", "status"?, "color"?, "client_ref"?}]`. `add_markers` returns `{"ids", "by_client_ref", "skipped"}`; a marker at a time that already has one is skipped. `update_marker` takes `{"id", "changes": {"timestamp", "position", "note", "status", "rationale", "confidence", "color"}}`; `delete_markers` takes `{"ids", "force"?}` with the same user-item protection.

### `list_annotations`

```json
{"command": "list_annotations", "payload": {"kind": "region", "status": "proposed", "source": "agent", "start": "2026-11-09T10:00:00Z", "end": "2026-11-09T12:00:00Z"}}
```

All fields optional (`kind`: `region`/`marker`; `start`/`end` select items overlapping the window). Returns `{"positions", "position_titles", "position_chart_offsets", "timezone", "viewport", "categories", "regions": [...], "markers": [...]}`. Region record: `id, position, start, end, start_iso, end_iso, source_start, source_end, source_start_iso, source_end_iso, areas, source_areas, note, category, category_label, categories, meter_states, color, source, status, rationale, confidence, agent {name, run_id}, created_at, reviewed_at, selected`. Marker record: `id, position, timestamp, timestamp_iso, source_timestamp, source_timestamp_iso, note, color, source, status, rationale, confidence, agent, created_at, reviewed_at, selected`. Items without provenance report `source: "user"`, `status: "accepted"`.

### `show`

```json
{"command": "show", "payload": {"region_id": 12, "message": "Is this a dog or a fox?", "parameter": "LAeq"}}
```

Exactly one of `region_id`, `marker_id`, or `start` + `end` (with optional `position`). Pads the window by 20% each side, selects the region/marker (`"select": false` to skip), scrolls the page to the position's chart (best effort), optionally switches `parameter`, and shows `message` as a toast. Returns `{"viewport": {"start", "end"}, "scrolled": bool}`.

### `export_annotations` and suggestions

`export_annotations` accepts `"include_proposed": true` (default false); the exporter leaves proposed and rejected items out otherwise.

### CLI

```powershell
nsa-ctl annotations --config "G:\...\noise_survey_config_6645.json"          # offline: reads <config_stem>.workspace.json
nsa-ctl annotations --config cfg.json --status proposed --kind region
nsa-ctl call add_regions --payload-file suggestions.json                     # any command, live
nsa-ctl call list_annotations --payload '{"status":"proposed"}'
nsa-ctl show --region-id 12 --message "Check this one"
nsa-ctl show --start 2026-11-09T10:16:00Z --end 2026-11-09T10:18:00Z --position 6645-4
```

`--start`/`--end` and `nsa-ctl show --start/--end` take `--time-basis source|display` (default `source`, see "Time basis"). `nsa-ctl annotations` needs no browser or server; it prints the same record shapes as `list_annotations` plus `counts`, `saved_at` and `workspace_file`. It reads the workspace file the dashboard autosaves beside the config (`--workspace PATH` reads another file) and fails with a clear message if there is none yet.

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
