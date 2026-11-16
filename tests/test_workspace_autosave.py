import json
import time
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bokeh.models import ColumnDataSource

from noise_survey_analysis.core import workspace_autosave as wa
from noise_survey_analysis.core.app_callbacks import AppCallbacks


def payload(note="a", session="S1"):
    return {"version": 2, "sourceConfigs": [], "sessionId": session, "rev": 1,
            "appState": {"regions": {"byId": {"1": {"id": 1, "note": note}}, "allIds": [1]}}}


class AutosaveFileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.config = Path(self.tmp.name) / "noise_survey_config_6645.json"
        self.config.write_text("{}", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_paths_sit_beside_the_config(self):
        self.assertEqual(wa.workspace_autosave_path(self.config).name, "noise_survey_config_6645.workspace.json")
        self.assertEqual(wa.workspace_backup_path(self.config, "20261116-101500").name,
                         "noise_survey_config_6645.workspace.20261116-101500.bak.json")

    def test_write_then_restore_round_trip_and_no_temp_left(self):
        writer = wa.WorkspaceAutosave.for_config(self.config)
        result = writer.save(payload("hello"))
        self.assertTrue(result.ok)
        self.assertEqual(result.rev, 1)
        restored = wa.read_workspace_autosave(self.config)
        self.assertEqual(restored["appState"]["regions"]["byId"]["1"]["note"], "hello")
        self.assertEqual(restored["autosave"]["rev"], 1)
        self.assertNotIn("sessionId", restored)
        self.assertEqual([p.name for p in Path(self.tmp.name).glob("*.tmp")], [])
        self.assertEqual(wa.list_workspace_backups(self.config), [])  # nothing to back up yet

    def test_backup_is_made_once_per_session_at_first_write(self):
        wa.WorkspaceAutosave.for_config(self.config).save(payload("old"))
        second = wa.WorkspaceAutosave.for_config(self.config)
        second.save(payload("new1", "S2"))
        second.save(payload("new2", "S2"))
        backups = wa.list_workspace_backups(self.config)
        self.assertEqual(len(backups), 1)
        backup = json.loads(backups[0].read_text(encoding="utf-8"))
        self.assertEqual(backup["appState"]["regions"]["byId"]["1"]["note"], "old")
        live = wa.read_workspace_autosave(self.config)
        self.assertEqual(live["appState"]["regions"]["byId"]["1"]["note"], "new2")
        self.assertEqual(live["autosave"]["rev"], 3)

    def test_second_tab_with_older_rev_is_refused(self):
        tab_a = wa.WorkspaceAutosave.for_config(self.config)
        tab_b = wa.WorkspaceAutosave.for_config(self.config)  # both opened at rev 0
        self.assertTrue(tab_a.save(payload("from A", "A")).ok)
        refused = tab_b.save(payload("from B", "B"))
        self.assertEqual(refused.status, "conflict")
        self.assertEqual(wa.read_workspace_autosave(self.config)["appState"]["regions"]["byId"]["1"]["note"], "from A")
        self.assertTrue(tab_a.save(payload("A again", "A")).ok)
        # A tab opened after A's writes starts from the current rev and may write.
        tab_c = wa.WorkspaceAutosave.for_config(self.config)
        self.assertTrue(tab_c.save(payload("from C", "C")).ok)

    def test_corrupt_autosave_is_moved_aside_not_overwritten(self):
        target = wa.workspace_autosave_path(self.config)
        target.write_text("{not json", encoding="utf-8")
        result = wa.WorkspaceAutosave.for_config(self.config).save(payload())
        self.assertTrue(result.ok)
        aside = list(Path(self.tmp.name).glob("*.corrupt-*.json"))
        self.assertEqual(len(aside), 1)
        self.assertEqual(aside[0].read_text(encoding="utf-8"), "{not json")

    def test_replace_retries_on_permission_error(self):
        real = wa.os.replace
        calls = {"n": 0}

        def flaky(src, dst):
            calls["n"] += 1
            if calls["n"] < 3:
                raise PermissionError("locked by Drive")
            return real(src, dst)

        with patch.object(wa.os, "replace", flaky), patch.object(wa, "_REPLACE_DELAY_S", 0):
            self.assertTrue(wa.WorkspaceAutosave.for_config(self.config).save(payload()).ok)
        self.assertGreaterEqual(calls["n"], 3)

    def test_unavailable_without_config_and_rejects_bad_payload(self):
        self.assertEqual(wa.WorkspaceAutosave.for_config(None).save(payload()).status, "unavailable")
        self.assertEqual(wa.WorkspaceAutosave.for_config(self.config).save({"x": 1}).status, "error")

    def test_latest_workspace_is_available_without_a_browser(self):
        wa.WorkspaceAutosave.for_config(self.config).save(payload("kept"))
        self.assertEqual(wa.latest_workspace(self.config)["appState"]["regions"]["byId"]["1"]["note"], "kept")


class FreshSessionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.config = Path(self.tmp.name) / "job.json"
        self.config.write_text("{}", encoding="utf-8")
        wa.WorkspaceAutosave.for_config(self.config).save(payload("precious"))
        self.live = wa.workspace_autosave_path(self.config)
        self.before = self.live.read_bytes()

    def tearDown(self):
        self.tmp.cleanup()

    def test_fresh_session_with_no_edits_leaves_file_byte_identical(self):
        fresh = wa.WorkspaceAutosave.for_config(self.config)
        fresh.preserve_existing = True  # as main.py sets for --no-restore / ?fresh=1
        # The browser sends nothing until the user edits, so no save() call happens.
        self.assertEqual(self.live.read_bytes(), self.before)
        self.assertEqual(list(Path(self.tmp.name).glob("job.workspace.2*.json")), [])

    def test_fresh_session_edit_keeps_old_file_under_timestamped_name(self):
        fresh = wa.WorkspaceAutosave.for_config(self.config)
        fresh.preserve_existing = True
        self.assertTrue(fresh.save(payload("new", "F")).ok)
        kept = list(Path(self.tmp.name).glob("job.workspace.2*.json"))
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0].read_bytes(), self.before)
        self.assertEqual(wa.read_workspace_autosave(self.config)["appState"]["regions"]["byId"]["1"]["note"], "new")
        self.assertEqual(wa.list_workspace_backups(self.config), [])


def rich_payload(n_regions, n_markers=0, session="S1", **extra):
    state = {"regions": {"byId": {str(i): {"id": i} for i in range(n_regions)}, "allIds": list(range(n_regions))},
             "markers": {"byId": {str(i): {"id": i} for i in range(n_markers)}, "allIds": list(range(n_markers))}}
    return {"version": 2, "sourceConfigs": [], "sessionId": session, "appState": state, **extra}


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.config = Path(self.tmp.name) / "job.json"
        self.config.write_text("{}", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def sizes(self):
        return [wa._annotation_count(json.loads(p.read_text(encoding="utf-8")))
                for p in wa.list_workspace_backups(self.config)]

    def test_each_session_start_adds_a_timestamped_backup_and_only_ten_are_kept(self):
        wa.WorkspaceAutosave.for_config(self.config).save(rich_payload(3))
        for n in range(14):
            writer = wa.WorkspaceAutosave.for_config(self.config)
            writer.save(rich_payload(3, session=f"S{n}"))
            writer.save(rich_payload(3, session=f"S{n}"))  # same session: no second backup
        backups = wa.list_workspace_backups(self.config)
        self.assertEqual(len(backups), wa.BACKUP_KEEP)
        for backup in backups:
            self.assertRegex(backup.name, r"^job\.workspace\.\d{8}-\d{6}(-\d+)?\.bak\.json$")

    def test_shrinking_save_keeps_a_backup_of_the_bigger_file(self):
        wa.WorkspaceAutosave.for_config(self.config).save(rich_payload(5, 2))
        later = wa.WorkspaceAutosave.for_config(self.config)
        later.save(rich_payload(5, 2, session="S2"))  # session-start backup (7 items)
        later.save(rich_payload(1, 0, session="S2"))  # 7 -> 1: the 7-item content is already backed up
        self.assertIn(7, self.sizes())
        # content bigger than the last backup must be backed up again before it shrinks
        later.save(rich_payload(9, 0, session="S2"))
        later.save(rich_payload(2, 0, session="S2"))
        self.assertIn(9, self.sizes())
        self.assertEqual(wa._annotation_count(wa.read_workspace_autosave(self.config)), 2)

    def test_repeated_small_deletions_do_not_churn_backups(self):
        wa.WorkspaceAutosave.for_config(self.config).save(rich_payload(10))
        later = wa.WorkspaceAutosave.for_config(self.config)
        later.save(rich_payload(10, session="S2"))
        for remaining in (9, 8, 7, 6):
            later.save(rich_payload(remaining, session="S2"))
        self.assertEqual(len(wa.list_workspace_backups(self.config)), 1)


class ReloadRaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.config = Path(self.tmp.name) / "job.json"
        self.config.write_text("{}", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_ordered_read_waits_for_a_slow_queued_writer(self):
        old_tab = wa.WorkspaceAutosave.for_config(self.config)
        old_tab.save(rich_payload(1, session="OLD"))
        real = wa.os.replace

        def slow(src, dst):
            time.sleep(0.4)
            return real(src, dst)

        with patch.object(wa.os, "replace", slow):
            AppCallbacks._autosave_executor.submit(old_tab.save, rich_payload(4, session="OLD", final=True))
            fresh = AppCallbacks.read_autosave_in_order(self.config)
        self.assertEqual(wa._annotation_count(fresh.last_payload), 4)
        self.assertEqual(fresh.base_rev, 2)
        self.assertTrue(fresh.save(rich_payload(5, session="NEW")).ok)

    def test_newer_rev_from_an_ended_session_is_adopted_with_a_backup(self):
        old_tab = wa.WorkspaceAutosave.for_config(self.config)
        old_tab.save(rich_payload(1, session="OLD"))
        new_tab = wa.WorkspaceAutosave.for_config(self.config)  # read lost the race: rev 1
        old_tab.save(rich_payload(4, session="OLD", final=True))  # pagehide flush lands afterwards
        result = new_tab.save(rich_payload(2, session="NEW"))
        self.assertTrue(result.ok, result.message)
        self.assertEqual(result.rev, 3)
        sizes = [wa._annotation_count(json.loads(p.read_text(encoding="utf-8")))
                 for p in wa.list_workspace_backups(self.config)]
        self.assertEqual(sizes, [4])
        self.assertTrue(new_tab.save(rich_payload(2, session="NEW")).ok)

    def test_ended_session_without_final_flag_is_adopted_too(self):
        old_tab = wa.WorkspaceAutosave.for_config(self.config)
        old_tab.save(rich_payload(1, session="GONE"))
        new_tab = wa.WorkspaceAutosave.for_config(self.config)
        old_tab.save(rich_payload(2, session="GONE"))
        self.assertEqual(new_tab.save(rich_payload(2, session="NEW")).status, "conflict")
        old_tab.end()
        self.assertTrue(new_tab.save(rich_payload(2, session="NEW")).ok)

    def test_a_live_rival_tab_is_still_a_conflict(self):
        a = wa.WorkspaceAutosave.for_config(self.config)
        b = wa.WorkspaceAutosave.for_config(self.config)
        self.assertTrue(a.save(rich_payload(2, session="A")).ok)
        self.assertEqual(b.save(rich_payload(3, session="B")).status, "conflict")

    def test_final_write_outside_the_adopt_window_is_not_adopted(self):
        a = wa.WorkspaceAutosave.for_config(self.config)
        b = wa.WorkspaceAutosave.for_config(self.config)
        a.save(rich_payload(2, session="A", final=True))
        with patch.object(wa, "ADOPT_WINDOW_S", -5.0):
            self.assertEqual(b.save(rich_payload(3, session="B")).status, "conflict")


class AutosaveActionTests(unittest.TestCase):
    class Doc:
        def add_next_tick_callback(self, callback):
            callback()

    def test_session_action_writes_and_publishes_a_silent_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "c.json"
            config.write_text("{}", encoding="utf-8")
            status = ColumnDataSource(data={"request_id": [None], "level": ["info"], "message": [""],
                                            "output_path": [""], "done": [False], "updated_at": [0]})
            callbacks = AppCallbacks(self.Doc(), None, ColumnDataSource(data={}), ColumnDataSource(data={}),
                                     session_status_source=status,
                                     workspace_autosave=wa.WorkspaceAutosave.for_config(config))
            callbacks._session_action_autosave_workspace(payload("x"), "req1")
            callbacks._autosave_executor.submit(lambda: None).result(timeout=10)
            self.assertTrue(wa.workspace_autosave_path(config).exists())
            self.assertTrue(status.data["output_path"][0].startswith("autosave:ok:1:"))
            self.assertEqual(status.data["done"], [False])

    def test_session_action_reports_unavailable_without_autosave(self):
        status = ColumnDataSource(data={"request_id": [None], "level": ["info"], "message": [""],
                                        "output_path": [""], "done": [False], "updated_at": [0]})
        callbacks = AppCallbacks(self.Doc(), None, ColumnDataSource(data={}), ColumnDataSource(data={}),
                                 session_status_source=status)
        callbacks._session_action_autosave_workspace(payload(), "req2")
        self.assertTrue(status.data["output_path"][0].startswith("autosave:unavailable"))


if __name__ == "__main__":
    unittest.main()
