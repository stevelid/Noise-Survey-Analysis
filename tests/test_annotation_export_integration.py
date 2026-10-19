"""Backend/control/drop integration; tests create outputs only in scratch folders."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from bokeh.models import ColumnDataSource
import pandas as pd
import pytest

from noise_survey_analysis.core.annotation_export_service import export_workspace_request
from noise_survey_analysis.core.app_callbacks import AppCallbacks
from noise_survey_analysis.control.commands import ControlResult
from noise_survey_analysis.control.control_server import _dispatch
from noise_survey_analysis.control.session_bridge import SessionBridge
from noise_survey_analysis.control.validation import validate_command_payload
from noise_survey_analysis.export.annotations import export_annotations, load_annotation_input, read_export_section

BASE = 1_700_000_000_000
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def survey(tmp_path):
    source = tmp_path / "source log & O'Brien.csv"
    pd.DataFrame({"Datetime": pd.to_datetime([BASE, BASE + 1000], unit="ms", utc=True),
                  "LAeq": [60, 70], "LAFmax": [65, 75]}).to_csv(source, index=False)
    workspace = {"version": 2, "sourceConfigs": [{"position_name": "P1", "parser_type": "generic", "timezone": "UTC", "file_paths": [str(source)]}],
                 "appState": {"view": {"availablePositions": ["P1"], "positionChartOffsets": {"P1": 1000}},
                 "regions": {"byId": {"1": {"id": 1, "positionId": "P1", "areas": [{"start": BASE + 1000, "end": BASE + 3000}],
                     "note": 'Quoted, "note"\nSecond line', "categoryId": "other", "color": None, "meterStates": {"P1": "present"}}}, "allIds": [1]},
                 "markers": {"byId": {}, "allIds": []}}}
    path = tmp_path / "workspace & O'Brien.json"
    path.write_text(json.dumps(workspace), encoding="utf-8")
    return workspace, path


def test_service_real_export_uses_source_folder_and_preserves_v2_snapshot(survey, tmp_path):
    workspace, _ = survey
    result = export_workspace_request({"workspace": workspace, "background_window_s": 120, "min_context_s": 10})
    output = Path(result["output_path"])
    assert result["success"]
    assert output.parent == tmp_path
    assert output.name.startswith("annotations-") and output.name.endswith(".full-resolution.csv")
    assert read_export_section(output, "OVERALL").loc[0, "LAeq_dB"] == pytest.approx(67.403627)
    restored = load_annotation_input(output)
    assert restored["version"] == 2
    assert restored["appState"]["view"]["positionChartOffsets"] == {"P1": 1000}
    assert restored["appState"]["regions"]["byId"]["1"]["note"] == workspace["appState"]["regions"]["byId"]["1"]["note"]
    assert "pooled 120s" in read_export_section(output, "NOTES").set_index("key").loc["background_method", "value"]


@pytest.mark.parametrize("settings", [
    {"include_all_resolutions": 1}, {"background_window_s": []}, {"background_window_s": float("nan")},
    {"background_window_s": True}, {"background_window_s": 0}, {"min_context_s": -1},
    {"min_context_s": float("inf")}, {"output_path": "  "}, {"output_path": "bad\x00path"},
])
def test_service_rejects_invalid_settings_before_writing(survey, tmp_path, settings):
    workspace, _ = survey
    before = set(tmp_path.iterdir())
    with pytest.raises(ValueError):
        export_workspace_request({"workspace": workspace, **settings})
    assert set(tmp_path.iterdir()) == before


def test_service_without_sources_defaults_to_current_folder(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = export_workspace_request({"workspace": {"version": 2, "sourceConfigs": [], "appState": {"regions": []}}})
    assert Path(result["output_path"]).parent == tmp_path


def test_atomic_write_keeps_existing_export_and_removes_partial_file(survey, tmp_path, monkeypatch):
    workspace, _ = survey
    output = tmp_path / "existing.csv"
    output.write_bytes(b"keep this complete previous export\n")
    before = set(tmp_path.iterdir())
    import noise_survey_analysis.export.annotations as exporter
    original = exporter._write_section

    def fail_midway(writer, name, columns, rows):
        if name == "SPECTRAL":
            raise OSError("Simulated write failure")
        return original(writer, name, columns, rows)

    monkeypatch.setattr(exporter, "_write_section", fail_midway)
    with pytest.raises(OSError, match="Simulated"):
        export_annotations(workspace, output)
    assert output.read_bytes() == b"keep this complete previous export\n"
    assert set(tmp_path.iterdir()) == before


def test_locked_target_does_not_destroy_existing_export_or_leave_temp(survey, tmp_path, monkeypatch):
    workspace, _ = survey
    output = tmp_path / "open in Excel.csv"
    output.write_bytes(b"previous\n")
    before = set(tmp_path.iterdir())

    def locked(*args, **kwargs):
        raise PermissionError("Excel has locked the output")

    monkeypatch.setattr(Path, "replace", locked)
    with pytest.raises(PermissionError, match="Excel"):
        export_annotations(workspace, output)
    assert output.read_bytes() == b"previous\n"
    assert set(tmp_path.iterdir()) == before


class QueuedDoc:
    def __init__(self):
        self.pending = []

    def add_next_tick_callback(self, callback):
        self.pending.append(callback)

    def flush(self):
        while self.pending:
            self.pending.pop(0)()


def callbacks():
    doc = QueuedDoc()
    instance = AppCallbacks(doc, None, ColumnDataSource(data={}), ColumnDataSource(data={}),
        session_action_source=ColumnDataSource(data={"command": [None], "request_id": [None], "payload": [None]}),
        session_status_source=ColumnDataSource(data={}), streaming_enabled=False)
    return instance, doc


def test_callback_queues_worker_snapshot_and_publishes_only_via_document_tick(survey, monkeypatch):
    workspace, _ = survey
    instance, doc = callbacks()
    workers = []
    calls = []

    class Worker:
        def __init__(self, target, **kwargs):
            workers.append(target)

        def start(self):
            pass

    def exporter(payload):
        calls.append(payload)
        return {"success": True, "output_path": "C:/job/export.csv", "message": "Export complete"}

    monkeypatch.setattr("noise_survey_analysis.core.app_callbacks.threading.Thread", Worker)
    monkeypatch.setattr("noise_survey_analysis.core.annotation_export_service.export_workspace_request", exporter)
    payload = {"workspace": workspace}
    instance._handle_session_action_command("data", {}, {"command": ["export_annotations"], "request_id": ["export-1"], "payload": [payload]})
    assert calls == [] and instance._annotation_export_in_progress
    assert instance.session_status_source.data == {}
    workspace["appState"]["regions"]["byId"]["1"]["note"] = "changed after queue"
    doc.flush()
    assert instance.session_status_source.data["done"] == [False]
    assert instance.session_action_source.data["command"] == [None]
    instance._handle_annotation_export(payload, "duplicate")
    assert len(workers) == 1
    workers[0]()
    assert calls[0]["workspace"]["appState"]["regions"]["byId"]["1"]["note"] != "changed after queue"
    assert not instance._annotation_export_in_progress
    # The worker scheduled completion; it did not touch a Bokeh model directly.
    assert instance.session_status_source.data["done"] == [False]
    doc.flush()
    assert instance.session_status_source.data["request_id"] == ["export-1"]
    assert instance.session_status_source.data["output_path"] == ["C:/job/export.csv"]
    assert instance.session_status_source.data["done"] == [True]


@pytest.mark.parametrize("failure", ["worker", "start"])
def test_export_failure_releases_busy_flag_and_reports_error_on_tick(monkeypatch, failure):
    instance, doc = callbacks()

    class Worker:
        def __init__(self, target, **kwargs):
            self.target = target

        def start(self):
            if failure == "start":
                raise RuntimeError("worker cannot start")
            self.target()

    def exporter(payload):
        raise ValueError("invalid workspace")

    monkeypatch.setattr("noise_survey_analysis.core.app_callbacks.threading.Thread", Worker)
    monkeypatch.setattr("noise_survey_analysis.core.annotation_export_service.export_workspace_request", exporter)
    instance._handle_annotation_export({}, "failed")
    assert not instance._annotation_export_in_progress
    doc.flush()
    assert instance.session_status_source.data["level"] == ["error"]
    assert instance.session_status_source.data["done"] == [True]
    assert instance.session_status_source.data["request_id"] == ["failed"]


def test_control_validation_keeps_background_options_and_rejects_non_objects():
    assert validate_command_payload("export_annotations", {
        "output_path": "C:/job & O'Brien/review.csv", "include_all_resolutions": True,
        "background_window_s": 120, "min_context_s": 20}) == {
        "output_path": "C:/job & O'Brien/review.csv", "include_all_resolutions": True,
        "background_window_s": 120, "min_context_s": 20}
    with pytest.raises(ValueError, match="object"):
        validate_command_payload("export_annotations", [1])


def test_cli_background_options_reach_control_payload(tmp_path, monkeypatch):
    from noise_survey_analysis import control_cli
    sent = []
    monkeypatch.setattr(control_cli, "_discover_server", lambda: (8765, "test-token"))
    monkeypatch.setattr(control_cli, "_post", lambda port, token, body: sent.append(body) or {"success": True, "message": "queued"})
    output = tmp_path / "review & O'Brien.csv"
    assert control_cli.main(["export-annotations", "--output", str(output), "--include-all-resolutions",
                             "--background-window-s", "120", "--min-context-s", "20"]) == 0
    assert sent[0]["command"] == "export_annotations"
    assert sent[0]["payload"] == {"output_path": str(output.resolve()), "include_all_resolutions": True,
                                  "background_window_s": 120, "min_context_s": 20}


def test_dispatch_and_bridge_request_current_frontend_workspace_without_path_escaping():
    bridge = SessionBridge()
    payload = {"output_path": "C:/job & O'Brien/a,b.csv", "include_all_resolutions": False,
               "background_window_s": 300, "min_context_s": 60}
    sent = []

    class ImmediateDoc:
        def add_next_tick_callback(self, callback):
            callback()

    class Source:
        @property
        def data(self):
            return {}

        @data.setter
        def data(self, value):
            sent.append(value)
            bridge.record_js_result({"request_id": value["request_id"][0], "success": True, "message": "queued"})

    bridge.register(ImmediateDoc(), automation_command_source=Source())
    result = _dispatch(bridge, "export_annotations", payload, "control-export")
    assert result.success and result.message == "queued"
    assert sent[0]["command"] == ["export_annotations"]
    assert json.loads(sent[0]["payload"][0]) == payload


def _powershell_literal(value):
    return "'" + str(value).replace("'", "''") + "'"


@pytest.mark.skipif(os.name != "nt", reason="Windows Explorer drop launchers")
@pytest.mark.parametrize("kind", ["workspace", "csv", "bat"])
def test_windows_drop_handles_quoted_paths_and_csv_metadata_without_picker(tmp_path, survey, kind):
    """Use the real launcher/module, with a scratch runtime-discovery library.

    No setup/installation or GUI is allowed in this test. An unexpected picker
    raises immediately; the self-contained CSV must find its embedded sources.
    """
    powershell = shutil.which("powershell.exe")
    if not powershell:
        pytest.skip("Windows PowerShell unavailable")
    workspace, workspace_path = survey
    share = tmp_path / "launcher & O'Brien" / "deploy" / "share"
    (share / "_lib").mkdir(parents=True)
    for filename in ("export_annotations.ps1", "export_annotations.bat"):
        shutil.copyfile(ROOT / "deploy" / "share" / filename, share / filename)
    library = f"""
function Get-NsaPaths {{ param($ShareRoot) [pscustomobject]@{{ VenvPython={_powershell_literal(sys.executable)}; App={_powershell_literal(ROOT)} }} }}
function Invoke-NsaEnsureReady {{ param($Paths, [switch]$Quiet) [pscustomobject]@{{ Ready=$true }} }}
function Write-NsaOk {{ param($Text) Write-Output $Text }}
function Write-NsaFail {{ param($Text) Write-Output $Text }}
function Wait-NsaForUser {{ }}
function Add-Type {{ throw 'Unexpected file picker' }}
"""
    (share / "_lib" / "nsa-common.ps1").write_text(library, encoding="utf-8")
    if kind == "csv":
        input_path = export_annotations(workspace, tmp_path / "carried annotations & O'Brien.csv")
    else:
        input_path = workspace_path
    output = tmp_path / "review output & O'Brien.csv"
    if kind == "bat":
        cmd = shutil.which("cmd.exe")
        if not cmd:
            pytest.skip("cmd.exe unavailable")
        # Windows paths cannot contain double quotes; both paths are quoted so
        # ampersands remain filename characters through the batch wrapper.
        command = f'"{cmd}" /d /s /c ""{share / "export_annotations.bat"}" "{input_path}""'
        result = subprocess.run(command, input="\n\n", capture_output=True, text=True, errors="replace", timeout=60)
        output = input_path.with_suffix(".full-resolution.csv")
    else:
        result = subprocess.run([powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
            str(share / "export_annotations.ps1"), "-InputPath", str(input_path), "-Output", output.name,
            "-BackgroundWindowSeconds", "120", "-MinimumContextSeconds", "10"],
            input="\n", cwd=tmp_path, capture_output=True, text=True, errors="replace", timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert output.exists(), result.stdout + result.stderr
    assert read_export_section(output, "OVERALL").loc[0, "LAeq_dB"] == pytest.approx(67.403627)
