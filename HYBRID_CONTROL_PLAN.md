# Hybrid Control Implementation Plan

## Purpose

Implement a safe hybrid control system for the Noise Survey Analysis app that supports:

- startup deep-link control through URL/query arguments
- runtime local automation through a localhost CLI/API

This plan assumes a single-user, single-machine, single-browser-session workflow:

- the Bokeh server runs on the user's laptop
- one browser session is treated as the active controlled session
- external control is localhost-only

## Goals

- Allow the app to open in a known state from a URL.
- Allow Codex or other local tooling to control an already-running session.
- Keep viewport/zoom handling reliable for Bokeh streaming and linked charts.
- Preserve the frontend store as the source of truth for UI state.
- Avoid unsafe generic remote execution patterns.

## Non-Goals

- Multi-user or multi-session routing.
- Internet-exposed webhook control.
- Arbitrary JavaScript execution.
- Arbitrary raw Redux state patching from Python.
- General plugin-style remote automation.

## Design Principles

1. Use typed commands, not free-form state mutation.
2. Keep control local to `127.0.0.1`.
3. Separate startup control from runtime control, but share validation rules.
4. Use the correct execution layer for each command:
   - viewport/range changes are Bokeh model operations
   - broader UI state changes flow through JS/store intents
5. Reuse existing architecture where possible:
   - `master_x_range` for zoom
   - existing workspace rehydrate flow for saved state
   - existing Redux-like store for UI state
6. Prefer explicit allowlists over generic "set anything" APIs.

## Recommended Hybrid Model

### 1. URL Deep-Link Layer

Use query/request arguments for startup-only control. These are applied when the Bokeh session is created.

Initial supported parameters:

- `config`
- `state`
- `start`
- `end`
- `param`
- `view`

Recommended behavior:

- `config` and `state` keep their current meaning.
- `start` and `end` define the initial viewport in epoch milliseconds.
- `param` sets the initial selected acoustic parameter.
- `view` sets the initial global view mode: `log` or `overview`.

This layer is for opening the app in a known initial state. It is not intended for controlling an already-open browser tab.

### 2. Local Runtime Control Layer

Add a localhost-only control API in the Python process and a thin CLI wrapper.

Recommended launch option:

- `--control-port 8765`

Recommended CLI examples:

- `nsa-ctl status`
- `nsa-ctl set-viewport --start 1710000000000 --end 1710001800000`
- `nsa-ctl set-parameter --value LAeq`
- `nsa-ctl set-view --value overview`
- `nsa-ctl apply-workspace --path C:\path\workspace.json`
- `nsa-ctl export-static-html`

This layer is for live control of the current session after the app is already running.

## Architecture

### A. Python Active Session Bridge

Create a small in-process bridge that tracks the active session and exposes safe operations against it.

Responsibilities:

- hold the active Bokeh `doc`
- hold references to core models such as `master_x_range`
- expose typed control methods such as:
  - `set_viewport(start, end)`
  - `set_parameter(value)`
  - `set_view_mode(value)`
  - `apply_workspace(payload_or_path)`
  - `export_static_html()`
  - `get_status()`
- schedule all Bokeh mutations via `doc.add_next_tick_callback(...)`
- return structured success/error payloads

Recommended new module area:

- `noise_survey_analysis/control/`

Suggested files:

- `noise_survey_analysis/control/session_bridge.py`
- `noise_survey_analysis/control/control_server.py`
- `noise_survey_analysis/control/commands.py`
- `noise_survey_analysis/control/validation.py`
- `noise_survey_analysis/control_cli.py`

### B. Execution Split by Command Type

#### Backend-native commands

These should execute directly in Python:

- `status`
- `set_viewport`
- `center_on_timestamp`
- `fit_full_range`
- `export_static_html`

Reason:

- viewport is fundamentally a Bokeh range operation
- Python already owns `master_x_range`
- linked streaming logic already depends on Bokeh range updates

#### Frontend/store-backed commands

These should be delivered to the browser and applied through JS/store flows:

- `set_parameter`
- `set_view_mode`
- `apply_workspace`
- later: marker/region/high-level UI intents if needed

Reason:

- these are UI-state concerns
- the frontend store already manages them
- renderers already sync widgets from store state

### C. Dedicated Automation Bridge Between Python and JS

Do not overload the existing session menu command path.

Current state:

- `session_action_source` is JS -> Python for session actions
- `session_status_source` is Python -> JS for status messages

Recommended addition:

- `automation_command_source` for Python -> JS typed commands
- `automation_result_source` for JS -> Python acknowledgements/results

Command shape:

```json
{
  "command": "set_parameter",
  "request_id": "abc123",
  "payload": {
    "value": "LAeq"
  }
}
```

Result shape:

```json
{
  "request_id": "abc123",
  "success": true,
  "message": "Parameter updated",
  "data": null
}
```

### D. Shared Validation Layer

Both URL arguments and CLI commands should use the same validation rules where possible.

Required validation rules:

- `start` and `end` must be finite numbers
- `end` must be greater than `start`
- view mode must be one of `log` or `overview`
- parameter must exist in the available dataset or allowed selector values
- workspace paths must exist and parse as expected
- command payloads must be bounded in size

Do not accept raw state blobs except through the existing workspace loader shape.

## State and Precedence Rules

The system must define a clear order of application.

Recommended precedence:

1. App defaults
2. Config-selected data load
3. Workspace restore via `state`
4. URL deep-link overrides
5. Runtime CLI/API commands

Interpretation:

- if a workspace restores one viewport but the URL supplies `start` and `end`, the URL wins at startup
- once the app is live, runtime commands always override the current session state

## Safe Command Surface

Initial allowlist:

- `status`
- `set_viewport`
- `center_on_timestamp`
- `fit_full_range`
- `set_parameter`
- `set_view_mode`
- `apply_workspace`
- `export_static_html`

Commands explicitly out of scope initially:

- `dispatch_action`
- `set_raw_state`
- `eval_js`
- arbitrary file writes

## Detailed Behavior by Feature

### Viewport / Zoom

Implementation path:

- Python updates `master_x_range.start` and `master_x_range.end` in the same callback.
- Bokeh syncs the range to the browser.
- existing JS range handlers observe the change and update store viewport state
- existing server streaming callbacks react to the same range change

Rules:

- always set both `start` and `end`
- never expose separate `set_start` or `set_end` commands
- clamp or reject invalid ranges

### Parameter Selection

Implementation path:

- Python sends `set_parameter` via `automation_command_source`
- JS validates against available selector values
- JS dispatches the existing parameter intent/action
- renderers update the visible selector widget if needed

### View Mode

Implementation path:

- Python sends `set_view_mode` via `automation_command_source`
- JS dispatches the existing view toggle action/intent
- renderers sync the toggle widget state

### Workspace Apply

Implementation path:

- CLI posts a workspace path or payload to the local API
- Python validates and reads the file if a path is provided
- Python sends `apply_workspace` to JS
- JS reuses `app.session.applyWorkspaceState(...)`

Reason:

- workspace application already exists in JS
- reusing the existing rehydrate flow reduces duplication

## URL Deep-Link Strategy

Startup control should stay small and explicit.

Recommended supported startup forms:

- `...?config=...`
- `...?state=...`
- `...?config=...&state=...`
- `...?config=...&start=...&end=...`
- `...?config=...&state=...&param=LAeq&view=overview&start=...&end=...`

Recommended parsing behavior:

- accept query/request arguments from the current Bokeh request
- normalize and validate them in Python
- apply them during startup after config/workspace load

Recommended restriction:

- avoid Windows file paths in ad hoc browser-typed URLs where possible
- use URL startup control mainly for reproducible entry points, not general live automation

## Local Control API Design

### Transport

Use a small localhost HTTP server bound to `127.0.0.1`.

Reason:

- simple to call from Codex, shell scripts, PowerShell, and Python
- easy to inspect and debug
- no browser automation required
- clearer than file watchers or ad hoc sockets

### Security Model

Minimum protections:

- bind only to `127.0.0.1`
- feature disabled unless explicitly enabled with `--control-port`
- optional session token required in header or request body
- small request body limits
- structured JSON only
- allowlist of commands only

Recommended token behavior:

- generate a random token on startup when control is enabled
- print it to the console
- optionally write it to a local temp file for CLI discovery

### Response Model

Every command should return structured JSON:

```json
{
  "success": true,
  "message": "Viewport updated",
  "data": {
    "start": 1710000000000,
    "end": 1710001800000
  }
}
```

For JS-mediated commands, the API should wait for an acknowledgement up to a bounded timeout, then return success or timeout.

## Implementation Phases

### Phase 1: Deep-Link Startup Support

Files likely touched:

- `noise_survey_analysis/main.py`
- `noise_survey_analysis/visualization/dashBuilder.py`
- `noise_survey_analysis/static/js/registry.js`
- `noise_survey_analysis/static/js/app.js`

Tasks:

- parse and validate `start`, `end`, `param`, `view`
- define precedence over workspace/default state
- pass normalized startup overrides into the app
- apply initial viewport safely
- add tests for parsing/precedence

Deliverable:

- app can open from URL with a known initial viewport/parameter/view mode

### Phase 2: Local Control Server and CLI

Files likely touched:

- `noise_survey_analysis/main.py`
- `noise_survey_analysis/control/session_bridge.py`
- `noise_survey_analysis/control/control_server.py`
- `noise_survey_analysis/control/commands.py`
- `noise_survey_analysis/control/validation.py`
- `noise_survey_analysis/control_cli.py`

Tasks:

- register the active session bridge
- add control server startup/shutdown
- implement `status`, `set_viewport`, `center_on_timestamp`, `fit_full_range`
- add CLI wrapper
- return structured JSON results

Deliverable:

- live viewport control from a local CLI

### Phase 3: Python -> JS Automation Bridge

Files likely touched:

- `noise_survey_analysis/main.py`
- `noise_survey_analysis/core/app_callbacks.py`
- `noise_survey_analysis/visualization/dashBuilder.py`
- `noise_survey_analysis/static/js/services/session/sessionManager.js`
- new JS automation bridge module if needed

Tasks:

- add `automation_command_source`
- add `automation_result_source`
- implement JS listeners and command handlers
- implement `set_parameter`, `set_view_mode`, `apply_workspace`
- add timeout and acknowledgement handling

Deliverable:

- live runtime control for store-backed UI state

### Phase 4: Hardening, Documentation, and Test Coverage

Files likely touched:

- `README.md`
- `USER_GUIDE.txt`
- `tests/`

Tasks:

- document startup URL usage
- document local control server and CLI usage
- add negative-path validation tests
- add manual test checklist items
- add simple integration coverage where practical

Deliverable:

- stable documented automation interface

## Testing Strategy

### Unit Tests

- validator tests for all command payloads
- URL parsing tests
- precedence tests for config/workspace/url overrides

### Integration Tests

- control server accepts valid commands and rejects invalid ones
- `set_viewport` updates the active Bokeh range
- JS automation command path returns ack for parameter/view/workspace commands

### Manual Tests

- launch app with URL overrides and verify startup state
- run CLI `status`
- run CLI `set-viewport`
- run CLI `set-parameter`
- run CLI `set-view`
- run CLI `apply-workspace`
- run CLI `export-static-html`

## Key Risks and Mitigations

### Risk: Store and Bokeh model drift

Mitigation:

- viewport commands change Bokeh range, not just store state
- store-backed commands go through JS intents/actions, not direct Python widget mutation

### Risk: Reusing the wrong command channel

Mitigation:

- keep session menu actions separate from automation commands
- add dedicated automation command/result sources

### Risk: Startup precedence becomes confusing

Mitigation:

- document and test a single precedence order
- keep URL overrides limited to a small explicit field set

### Risk: Unsafe local automation surface

Mitigation:

- localhost-only binding
- explicit opt-in
- token support
- typed command allowlist
- no arbitrary eval/state patch APIs

## Recommended First Slice

Implement in this order:

1. URL startup overrides for `start`, `end`, `param`, `view`
2. localhost control server with `status` and `set_viewport`
3. CLI wrapper
4. JS automation bridge for `set_parameter`, `set_view_mode`, `apply_workspace`

This sequence delivers useful control early while keeping the architecture clean.

## Acceptance Criteria

- A user can open the app with URL parameters that set initial viewport, parameter, and view mode.
- A local CLI can query the active session status.
- A local CLI can change the live viewport without reloading the browser.
- A local CLI can change parameter and view mode through the JS/store path.
- A local CLI can apply a saved workspace safely.
- The control surface remains localhost-only, typed, and documented.
