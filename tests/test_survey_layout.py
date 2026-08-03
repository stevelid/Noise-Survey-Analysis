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


def _source(visit='', label='P1', session='', role='log', duration=4 * 3600,
            recommended=True, spot=False, spectral=False, size=1024,
            start='2026-07-13T09:00:00', end='2026-07-17T09:00:00', instrument='Svan',
            parser_type='svan'):
    return {
        'visit': visit, 'group_label': label, 'session': session, 'role': role,
        'duration_seconds': duration, 'recommended': recommended,
        'is_spot_measurement': spot, 'has_spectral': spectral,
        'file_size_bytes': size, 'start_time': start, 'end_time': end,
        'instrument': instrument, 'parser_type': parser_type,
    }


class GroupingTests(unittest.TestCase):
    def test_svan_log_summary_and_audio_collapse_to_one_position(self):
        groups = layout.build_groups([
            _source(label='971-2', role='log'),
            _source(label='971-2', role='summary'),
            _source(label='971-2', role='audio', instrument='', parser_type='audio'),
        ])

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].label, '971-2')
        self.assertEqual(groups[0].file_count, 3)
        self.assertEqual(groups[0].describe_contents(), 'log + summary + audio')

    def test_nti_sessions_stay_separate_but_their_files_collapse(self):
        """13 manual readings should be 13 rows, not the ~70 files they comprise."""
        sources = []
        for index in range(13):
            session = f'2025-04-28_SLM_{index:03d}'
            for role in ('log', 'summary', 'raw', 'log', 'summary'):
                sources.append(_source(
                    visit='5882 Manuals', label='5882 Manuals', session=session,
                    role=role, duration=300, spot=True, recommended=False,
                    instrument='NTi', parser_type='nti',
                ))

        groups = layout.build_groups(sources)

        self.assertEqual(len(groups), 13)
        self.assertTrue(all(g.file_count == 5 for g in groups))
        self.assertTrue(all(g.is_spot_measurement for g in groups))
        self.assertTrue(all(not g.recommended for g in groups))

    def test_visits_separate_the_same_recorder(self):
        groups = layout.build_groups([
            _source(visit='', label='971-2'),
            _source(visit='july 2026', label='971-2'),
        ])
        self.assertEqual(len(groups), 2)
        self.assertEqual({g.visit for g in groups}, {'', 'july 2026'})

    def test_a_long_log_beside_short_extras_is_not_a_spot_measurement(self):
        groups = layout.build_groups([
            _source(label='971-2', role='log', duration=4 * 86400, spot=False),
            _source(label='971-2', role='summary', duration=120, spot=True),
        ])
        self.assertEqual(len(groups), 1)
        self.assertFalse(groups[0].is_spot_measurement)
        self.assertTrue(groups[0].recommended)

    def test_group_span_covers_all_its_files(self):
        groups = layout.build_groups([
            _source(label='971-2', start='2026-07-13T09:00:00', end='2026-07-15T09:00:00'),
            _source(label='971-2', role='summary',
                    start='2026-07-12T08:00:00', end='2026-07-17T10:00:00'),
        ])
        self.assertEqual(groups[0].start_time, '2026-07-12T08:00:00')
        self.assertEqual(groups[0].end_time, '2026-07-17T10:00:00')

    def test_spectral_is_true_when_any_file_carries_it(self):
        groups = layout.build_groups([
            _source(label='4792-2', spectral=False),
            _source(label='4792-2', role='summary', spectral=True),
        ])
        self.assertTrue(groups[0].has_spectral)

    def test_recommended_groups_sort_first(self):
        groups = layout.build_groups([
            _source(visit='5882 Manuals', label='SLM_000', session='s0',
                    duration=300, spot=True, recommended=False),
            _source(visit='july 2026', label='971-2'),
        ])
        self.assertTrue(groups[0].recommended)
        self.assertEqual(groups[0].label, '971-2')

    def test_saved_configs_are_not_positions(self):
        groups = layout.build_groups([
            _source(label='Config (5882)', parser_type='config', role=''),
            _source(label='971-2'),
        ])
        self.assertEqual([g.label for g in groups], ['971-2'])

    def test_empty_scan_yields_no_groups(self):
        self.assertEqual(layout.build_groups([]), [])
        self.assertEqual(layout.build_groups(None), [])


class VisitSummaryTests(unittest.TestCase):
    def test_visits_are_summarised_newest_first(self):
        groups = layout.build_groups([
            _source(visit='', label='971-2',
                    start='2025-04-28T09:00:00', end='2025-04-28T17:00:00'),
            _source(visit='july 2026', label='971-2',
                    start='2026-07-13T09:00:00', end='2026-07-17T09:00:00'),
            _source(visit='july 2026', label='971-3',
                    start='2026-07-13T09:00:00', end='2026-07-17T09:00:00'),
        ])

        visits = layout.list_visits(groups)

        self.assertEqual([v['label'] for v in visits], ['july 2026', 'Main survey'])
        self.assertEqual(visits[0]['position_count'], 2)
        self.assertEqual(visits[0]['recommended_count'], 2)

    def test_unnamed_visit_is_labelled_for_display(self):
        visits = layout.list_visits(layout.build_groups([_source(visit='', label='L350')]))
        self.assertEqual(visits[0]['label'], 'Main survey')
        self.assertEqual(visits[0]['visit'], '')


class DurationFormattingTests(unittest.TestCase):
    def test_reads_naturally_across_scales(self):
        self.assertEqual(layout.format_duration(45), '45 s')
        self.assertEqual(layout.format_duration(600), '10 min')
        self.assertEqual(layout.format_duration(4 * 3600), '4.0 h')
        self.assertEqual(layout.format_duration(4 * 86400), '4.0 d')
        self.assertEqual(layout.format_duration(None), '')


class ReviewFindingTests(unittest.TestCase):
    """Cases from the Codex review of PR #81, each verified to fail beforehand."""

    def _write_nti_log(self, directory, name, start, rows):
        """Real NTi shape: tab-separated, Date and Time as separate columns.

        NTiFileParser reads its table with sep='\\t', so a comma-separated fixture with
        a combined "Date & time" column is not what these files look like - and probing
        such a fixture proved nothing.
        """
        path = os.path.join(directory, name)
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write('# Broadband LOG Results\n')
            handle.write('Date\tTime\tLAeq\n')
            for index in range(rows):
                stamp = start + pd.Timedelta(seconds=index)
                handle.write(f"{stamp.strftime('%Y-%m-%d')}\t{stamp.strftime('%H:%M:%S')}\t55.0\n")
        return path

    def test_tab_separated_nti_timestamps_are_probed(self):
        start = pd.Timestamp('2025-04-28 11:00:00')
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_nti_log(tmp, '2025-04-28_SLM_000_123_Log.txt', start, rows=300)
            probed_start, probed_end = layout.peek_time_span(path)

        self.assertEqual(probed_start, start)
        self.assertEqual(probed_end, start + pd.Timedelta(seconds=299))

    def test_short_nti_reading_is_classified_as_spot(self):
        """Without tab support the span was unknown, so these were recommended."""
        start = pd.Timestamp('2025-04-28 11:00:00')
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_nti_log(tmp, '2025-04-28_SLM_000_123_Log.txt', start, rows=300)
            duration = layout.span_seconds(*layout.peek_time_span(path))

        self.assertIsNotNone(duration)
        self.assertTrue(layout.is_spot_measurement(duration))

    def test_a_date_never_pairs_with_a_time_on_the_following_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'odd.txt')
            with open(path, 'w', encoding='utf-8') as handle:
                handle.write('2025-04-28\n11:00:00\n')
            self.assertEqual(layout.peek_time_span(path), (None, None))

    def test_suffixed_svan_log_names_keep_their_role(self):
        """SvanFileParser accepts _LOG.CSV and _LOG_*.CSV, e.g. _log_1s.csv."""
        for name in ('P1_log.csv', 'P1_log_1s.csv', 'P1_log_10s.csv', 'P1_LOG_100ms.csv'):
            with self.subTest(name=name):
                facts = layout.classify_file('/job/' + name, name)
                self.assertEqual(facts.instrument, 'Svan')
                self.assertEqual(facts.role, 'log')

    def test_suffixed_svan_logs_group_with_their_own_summary(self):
        """Otherwise "P1_log_1s" split away from "P1" as a separate, wrong position."""
        for name in ('P1_log_1s.csv', 'P1_log_10s.csv', 'P1_summary.csv'):
            with self.subTest(name=name):
                self.assertEqual(layout.position_label_from_filename(name), 'P1')
