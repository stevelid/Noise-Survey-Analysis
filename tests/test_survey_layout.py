"""Survey folder-layout inference.

Every path in these tests is taken verbatim from a structural survey of 44 real job
folders, so the cases are the ones that actually occur rather than invented ones.
"""
import os
import tempfile
import unittest

import pandas as pd

from noise_survey_analysis.core import survey_layout as layout


class FileClassificationTests(unittest.TestCase):
    """NTi follows an exact grammar; Svan a simple suffix convention."""

    def _classify(self, filename):
        return layout.classify_file(os.path.join('/job', filename), filename)

    def test_nti_log_and_report_roles(self):
        log = self._classify('2025-08-29_SLM_000_123_Log.txt')
        self.assertEqual(log.instrument, 'NTi')
        self.assertEqual(log.role, 'log')
        self.assertEqual(log.session, '2025-08-29_SLM_000')

        report = self._classify('2025-08-29_SLM_000_123_Report.txt')
        self.assertEqual(report.role, 'summary')

        rpt = self._classify('2025-08-29_SLM_000_123_Rpt_Report.txt')
        self.assertEqual(rpt.role, 'summary')

    def test_nti_band_token_identifies_spectral_content(self):
        # '123' is broadband, 'RTA_3rd' is third-octave. This replaces the previous
        # size-threshold guessing, which the survey showed does not discriminate.
        self.assertFalse(self._classify('2025-08-29_SLM_000_123_Log.txt').has_spectral)
        self.assertTrue(self._classify('2025-08-29_SLM_000_RTA_3rd_Log.txt').has_spectral)

    def test_all_files_of_one_nti_session_share_a_session_key(self):
        session_files = [
            '2025-08-29_SLM_004.XL2',
            '2025-08-29_SLM_004_123_Log.txt',
            '2025-08-29_SLM_004_123_Report.txt',
            '2025-08-29_SLM_004_123_Rpt_Report.txt',
            '2025-08-29_SLM_004_RTA_3rd_Log.txt',
            '2025-08-29_SLM_004_RTA_3rd_Report.txt',
            '2025-08-29_SLM_004_RTA_3rd_Rpt_Report.txt',
        ]
        sessions = {self._classify(name).session for name in session_files}
        self.assertEqual(sessions, {'2025-08-29_SLM_004'})

    def test_nti_sessions_are_kept_distinct(self):
        self.assertNotEqual(
            self._classify('2025-08-29_SLM_004_123_Log.txt').session,
            self._classify('2025-08-29_SLM_005_123_Log.txt').session,
        )

    def test_nti_raw_and_voice_note(self):
        self.assertEqual(self._classify('2025-08-29_SLM_000.XL2').role, 'raw')
        self.assertEqual(self._classify('2025-04-28_SLM_003_VoiceNote.txt').role, 'voice_note')

    def test_svan_log_summary_and_raw(self):
        log = self._classify('5882 Warbrook House 971-2_log.csv')
        self.assertEqual((log.instrument, log.role), ('Svan', 'log'))

        summary = self._classify('5882 Warbrook House 971-2_summary.csv')
        self.assertEqual((summary.instrument, summary.role), ('Svan', 'summary'))

        raw = self._classify('L350.SVL')
        self.assertEqual((raw.instrument, raw.role), ('Svan', 'raw'))

    def test_analysis_workbooks_are_flagged_not_treated_as_instrument_output(self):
        for name in ('5882 Raw data (971-2).xlsx', '4792 North DT.xlsx',
                     '5882.Quote Cost Calculator.xlsx', '2054.NAW Assessment.xls'):
            with self.subTest(name=name):
                facts = self._classify(name)
                self.assertTrue(facts.is_analysis_workbook)
                self.assertEqual(facts.instrument, '')

    def test_svan_overview_workbook_is_data_not_clutter(self):
        """SvanFileParser claims "*overview.xlsx", so it is instrument output.

        Demoting every spreadsheet would have hidden a real Svan export.
        """
        facts = self._classify('L419 overview.xlsx')
        self.assertFalse(facts.is_analysis_workbook)


class SurveyRootTests(unittest.TestCase):
    """The '<job> Surveys' folder isolated 199/200 data files in the survey."""

    def test_prefers_the_surveys_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ('5882 Admin', '5882 Corres In', '5882 Report', '5882 Surveys'):
                os.mkdir(os.path.join(tmp, name))
            self.assertEqual(
                layout.find_survey_root(tmp),
                os.path.join(tmp, '5882 Surveys'),
            )

    def test_falls_back_to_the_job_folder_when_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.mkdir(os.path.join(tmp, '2690 Admin'))
            # Nothing is hidden from jobs that break the convention.
            self.assertEqual(layout.find_survey_root(tmp), tmp)


class VisitAndPositionTests(unittest.TestCase):
    def test_recognises_real_visit_folders(self):
        for name in ('july 2026', 'March 2026 Testing', '4792 250829 Glazing Tests',
                     '6145 Verification Monitoring', '5882 Manuals'):
            with self.subTest(name=name):
                self.assertTrue(layout.looks_like_visit_folder(name))

    def test_month_and_hint_words_match_whole_tokens_only(self):
        """Substring matching would make "summary" a visit (it contains "mar")."""
        for name in ('P1_summary', 'summary', 'Contest Road', 'Cartesian House',
                     'Marlow Gardens'):
            with self.subTest(name=name):
                self.assertFalse(layout.looks_like_visit_folder(name))

    def test_separators_do_not_hide_a_month_token(self):
        for name in ('july_2026', 'july-2026', '2026.march'):
            with self.subTest(name=name):
                self.assertTrue(layout.looks_like_visit_folder(name))

    def test_recorder_tokens_are_not_mistaken_for_visits(self):
        for name in ('971-2', 'L350', '4792-3', '6466-4', 'NS1A'):
            with self.subTest(name=name):
                self.assertFalse(layout.looks_like_visit_folder(name))

    def test_visit_then_position(self):
        got = layout.derive_group(
            '4792 Surveys/4792 250829 Glazing Tests/4792-2/2025-08-29_SLM_000_123_Log.txt',
            survey_root_name='4792 Surveys',
        )
        self.assertEqual(got, {'visit': '4792 250829 Glazing Tests', 'position': '4792-2'})

    def test_position_directly_under_survey_root(self):
        got = layout.derive_group(
            '6145 Surveys/6145-3 - front/data_log.csv',
            survey_root_name='6145 Surveys',
        )
        # A human label like "front" survives intact - it is a better starting name
        # than anything synthesised.
        self.assertEqual(got, {'visit': '', 'position': '6145-3 - front'})

    def test_files_loose_in_a_visit_folder(self):
        got = layout.derive_group(
            '5882 Surveys/july 2026/something_log.csv',
            survey_root_name='5882 Surveys',
        )
        self.assertEqual(got, {'visit': 'july 2026', 'position': ''})

    def test_flat_layout_yields_no_folder_grouping(self):
        got = layout.derive_group('6468 Surveys/L350.SVL', survey_root_name='6468 Surveys')
        self.assertEqual(got, {'visit': '', 'position': ''})

    def test_position_label_falls_back_to_the_meter_token(self):
        self.assertEqual(
            layout.position_label_from_filename('5882 Warbrook House 971-2_log.csv'),
            '5882 Warbrook House 971-2',
        )
        self.assertEqual(layout.position_label_from_filename('L350.SVL'), 'L350')
        self.assertEqual(
            layout.position_label_from_filename('2025-08-29_SLM_000_123_Log.txt'),
            '2025-08-29_SLM_000',
        )


class TimeSpanProbeTests(unittest.TestCase):
    """Span comes from ~8 KB at each end, not from parsing the file."""

    def _write_log(self, directory, name, start, rows, step_seconds):
        path = os.path.join(directory, name)
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write('Date & time,LAeq\n')
            for index in range(rows):
                stamp = start + pd.Timedelta(seconds=index * step_seconds)
                handle.write(f"{stamp.strftime('%Y-%m-%d %H:%M:%S')},{50 + index % 7}\n")
        return path

    def test_recovers_span_of_a_long_file_without_reading_it_all(self):
        start = pd.Timestamp('2024-05-13 09:00:00')
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_log(tmp, 'L419_log.csv', start, rows=40000, step_seconds=1)
            probed_start, probed_end = layout.peek_time_span(path)

        self.assertEqual(probed_start, start)
        self.assertEqual(probed_end, start + pd.Timedelta(seconds=39999))

    def test_short_manual_reading_is_classified_as_a_spot_measurement(self):
        start = pd.Timestamp('2025-04-28 11:00:00')
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_log(tmp, '2025-04-28_SLM_000_123_Log.txt', start,
                                   rows=300, step_seconds=1)  # five minutes
            probed = layout.span_seconds(*layout.peek_time_span(path))

        self.assertAlmostEqual(probed, 299, delta=2)
        self.assertTrue(layout.is_spot_measurement(probed))

    def test_unattended_survey_is_not_a_spot_measurement(self):
        start = pd.Timestamp('2024-05-13 09:00:00')
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_log(tmp, 'L419_log.csv', start, rows=20000, step_seconds=30)
            probed = layout.span_seconds(*layout.peek_time_span(path))

        self.assertGreater(probed, layout.SPOT_MEASUREMENT_MAX_SECONDS)
        self.assertFalse(layout.is_spot_measurement(probed))

    def test_unknown_duration_is_never_hidden_as_a_spot_measurement(self):
        self.assertFalse(layout.is_spot_measurement(None))

    def test_unreadable_file_probes_cleanly(self):
        self.assertEqual(layout.peek_time_span('/no/such/file.csv'), (None, None))
        self.assertIsNone(layout.span_seconds(None, None))

    def test_file_without_timestamps_probes_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'notes.txt')
            with open(path, 'w', encoding='utf-8') as handle:
                handle.write('no timestamps here at all\n')
            self.assertEqual(layout.peek_time_span(path), (None, None))


if __name__ == '__main__':
    unittest.main()
