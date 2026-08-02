"""The picker presents positions, filtered by visit, with recommendations pre-selected.

Built on a reconstruction of a real job folder: an unattended Svan survey, a folder of
short manual NTi readings, and a later visit in its own folder.
"""
import datetime
import os
import tempfile
import unittest
from unittest.mock import MagicMock

from noise_survey_analysis.core.data_loaders import scan_directory_for_sources
from noise_survey_analysis.core.survey_layout import find_survey_root
from noise_survey_analysis.ui.data_source_selector import ALL_VISITS, DataSourceSelector


def _write_log(path, start, rows, step_seconds):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write('Date & time,LAeq\n')
        for index in range(rows):
            stamp = start + datetime.timedelta(seconds=index * step_seconds)
            handle.write(f"{stamp.strftime('%Y-%m-%d %H:%M:%S')},55.0\n")


def build_job_folder(root):
    """Mirrors the shape found in the real folder survey."""
    job = os.path.join(root, '5882 Warbrook House, Eversley')

    # Everything outside the Surveys folder must never reach the picker.
    for folder in ('5882 Admin', '5882 Corres In', '5882 Report'):
        os.makedirs(os.path.join(job, folder), exist_ok=True)
        with open(os.path.join(job, folder, '5882.260115.Q2.pdf'), 'w') as handle:
            handle.write('x')

    surveys = os.path.join(job, '5882 Surveys')

    # Unattended Svan survey: log + summary, several days.
    _write_log(os.path.join(surveys, '5882 Warbrook House 971-2_log.csv'),
               datetime.datetime(2026, 7, 13, 9, 0), rows=3000, step_seconds=60)
    _write_log(os.path.join(surveys, '5882 Warbrook House 971-2_summary.csv'),
               datetime.datetime(2026, 7, 13, 9, 0), rows=200, step_seconds=900)

    # Manual NTi readings: five sessions of five minutes each.
    for index in range(5):
        base = datetime.datetime(2025, 4, 28, 11, 0) + datetime.timedelta(minutes=20 * index)
        for suffix in ('_123_Log.txt', '_RTA_3rd_Log.txt'):
            _write_log(os.path.join(surveys, '5882 Manuals',
                                    f'2025-04-28_SLM_{index:03d}{suffix}'),
                       base, rows=300, step_seconds=1)

    # A later visit, with its own position folder.
    _write_log(os.path.join(surveys, 'july 2026', '971-3', 'data_log.csv'),
               datetime.datetime(2026, 7, 15, 8, 0), rows=4000, step_seconds=60)
    return job


class PickerGroupingTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        job = build_job_folder(self._tmp.name)

        self.selector = DataSourceSelector(doc=MagicMock(), on_data_sources_selected=MagicMock())
        self.selector.scanned_sources = scan_directory_for_sources(find_survey_root(job))
        self.selector._update_available_files_table()

    def _rows(self):
        return self.selector.available_files_source.data

    def test_material_outside_the_surveys_folder_never_appears(self):
        paths = [s['file_path'] for s in self.selector.scanned_sources]
        self.assertTrue(paths)
        for path in paths:
            self.assertIn('5882 Surveys', path)

    def test_positions_are_listed_not_files(self):
        # Two Svan files collapse to one position; five NTi sessions stay distinct.
        self.selector.visit_select.value = ALL_VISITS
        self.selector._render_visible_groups()
        labels = set(self.selector.available_files_source.data['position'])
        self.assertIn('5882 Warbrook House 971-2', labels)
        counts = dict(zip(self._rows()['position'], self._rows()['file_count']))
        self.assertEqual(counts['5882 Warbrook House 971-2'], 2)

    def test_short_manual_readings_are_hidden_by_default(self):
        self.selector.visit_select.value = ALL_VISITS
        self.selector._render_visible_groups()
        visible = set(self._rows()['position'])
        self.assertFalse(any(label.startswith('2025-04-28_SLM') for label in visible))

    def test_manual_readings_can_be_shown_on_request(self):
        self.selector.visit_select.value = ALL_VISITS  # all visits
        self.selector.show_spot_checkbox.active = [0]  # include short readings
        self.selector._render_visible_groups()

        visible = set(self._rows()['position'])
        sessions = {label for label in visible if label.startswith('2025-04-28_SLM')}
        self.assertEqual(len(sessions), 5, "each manual session should be one row")

    def test_visit_options_offer_every_visit_plus_all(self):
        values = [value for value, _ in self.selector.visit_select.options]
        self.assertIn(ALL_VISITS, values)
        self.assertIn("", values, "the unnamed visit must be selectable in its own right")
        self.assertIn("july 2026", values)
        self.assertIn("5882 Manuals", values)

    def test_selecting_a_visit_filters_the_positions(self):
        self.selector.visit_select.value = "july 2026"
        self.selector._render_visible_groups()

        self.assertEqual(set(self._rows()['position']), {'971-3'})

    def test_recommended_positions_are_preselected(self):
        self.selector.visit_select.value = ALL_VISITS
        self.selector._render_visible_groups()

        selected = self.selector.available_files_table.source.selected.indices
        self.assertTrue(selected)
        recommended = self._rows()['recommended']
        self.assertTrue(all(recommended[index] for index in selected))

    def test_adding_a_position_adds_all_of_its_files(self):
        self.selector.visit_select.value = ALL_VISITS
        self.selector._render_visible_groups()
        index = list(self._rows()['position']).index('5882 Warbrook House 971-2')
        self.selector.available_files_table.source.selected.indices = [index]

        self.selector._add_selected_files()

        included = self.selector.included_files_source.data
        self.assertEqual(len(included['fullpath']), 2)
        self.assertEqual(set(included['position']), {'5882 Warbrook House 971-2'})
        self.assertTrue(any(p.endswith('_log.csv') for p in included['fullpath']))
        self.assertTrue(any(p.endswith('_summary.csv') for p in included['fullpath']))

    def test_adding_the_same_position_twice_does_not_duplicate(self):
        self.selector.visit_select.value = ALL_VISITS
        self.selector._render_visible_groups()
        index = list(self._rows()['position']).index('5882 Warbrook House 971-2')

        for _ in range(2):
            self.selector.available_files_table.source.selected.indices = [index]
            self.selector._add_selected_files()

        self.assertEqual(len(self.selector.included_files_source.data['fullpath']), 2)

    def test_period_and_duration_are_shown(self):
        self.selector.visit_select.value = ALL_VISITS
        self.selector._render_visible_groups()
        index = list(self._rows()['position']).index('5882 Warbrook House 971-2')

        self.assertTrue(self._rows()['period'][index], "period should be probed from the files")
        self.assertTrue(self._rows()['duration'][index])

    def test_contents_describe_what_the_position_offers(self):
        self.selector.visit_select.value = ALL_VISITS
        self.selector._render_visible_groups()
        index = list(self._rows()['position']).index('5882 Warbrook House 971-2')

        self.assertEqual(self._rows()['contents'][index], 'log + summary')

    def test_empty_scan_clears_the_table(self):
        self.selector.scanned_sources = []
        self.selector._update_available_files_table()
        self.assertEqual(list(self._rows()['position']), [])


class PeriodFormattingTests(unittest.TestCase):
    def test_formats_read_naturally(self):
        fmt = DataSourceSelector._format_period
        self.assertEqual(fmt('2026-07-13T09:00:00', '2026-07-17T09:00:00'), '13-17 Jul 2026')
        self.assertEqual(fmt('2026-07-13T09:00:00', '2026-07-13T17:00:00'), '13 Jul 2026')
        self.assertEqual(fmt('2026-06-28T09:00:00', '2026-07-02T09:00:00'), '28 Jun - 02 Jul 2026')
        self.assertEqual(fmt('', ''), '')

    def test_unparseable_span_is_blank_not_an_error(self):
        self.assertEqual(DataSourceSelector._format_period('not-a-date', ''), '')


if __name__ == '__main__':
    unittest.main()


class PositionNameCleanupTests(unittest.TestCase):
    """Labels come from meter/recorder folders, so casing must survive intact."""

    def _cleaned(self, name):
        selector = DataSourceSelector(doc=MagicMock(), on_data_sources_selected=MagicMock())
        selector.included_files_source.data = {
            key: ([name] if key == 'position' else [''])
            for key in selector.included_files_source.data.keys()
        }
        return selector.included_files_source.data['position'][0]

    def test_names_starting_with_a_digit_keep_their_casing(self):
        # str.capitalize() lowercases the remainder, and most real position names
        # start with a job or recorder number.
        self.assertEqual(self._cleaned('5882 Warbrook House 971-2'), '5882 Warbrook House 971-2')
        self.assertEqual(self._cleaned('6145-3 - Front'), '6145-3 - Front')

    def test_leading_lowercase_letter_is_still_capitalised(self):
        self.assertEqual(self._cleaned('front facade'), 'Front facade')

    def test_surrounding_whitespace_is_trimmed(self):
        self.assertEqual(self._cleaned('  971-2  '), '971-2')


class VisitSentinelTests(unittest.TestCase):
    """The unnamed visit has an empty name, so "" cannot also mean "no filter"."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        job = build_job_folder(self._tmp.name)
        self.selector = DataSourceSelector(doc=MagicMock(), on_data_sources_selected=MagicMock())
        self.selector.scanned_sources = scan_directory_for_sources(find_survey_root(job))
        self.selector._update_available_files_table()

    def test_unnamed_visit_filters_to_itself_not_to_everything(self):
        self.selector.visit_select.value = ""   # the "Main survey" entry
        self.selector._render_visible_groups()

        positions = set(self.selector.available_files_source.data['position'])
        self.assertEqual(positions, {'5882 Warbrook House 971-2'})

    def test_all_visits_shows_every_visit(self):
        self.selector.visit_select.value = ALL_VISITS
        self.selector._render_visible_groups()

        positions = set(self.selector.available_files_source.data['position'])
        self.assertIn('5882 Warbrook House 971-2', positions)
        self.assertIn('971-3', positions)

    def test_defaults_to_the_newest_visit_when_there_is_a_choice(self):
        self.assertEqual(self.selector.visit_select.value, 'july 2026')


class FilterVisibilityTests(unittest.TestCase):
    """A filtered view must announce itself, not look like a short job."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        job = build_job_folder(self._tmp.name)
        self.selector = DataSourceSelector(doc=MagicMock(), on_data_sources_selected=MagicMock())
        self.selector.scanned_sources = scan_directory_for_sources(find_survey_root(job))
        self.selector._update_available_files_table()

    def test_status_reports_what_is_hidden(self):
        text = self.selector.status_div.text
        self.assertIn('of 7 position(s)', text)
        self.assertIn('short manual reading', text)

    def test_showing_everything_leaves_nothing_to_announce(self):
        self.selector.visit_select.value = ALL_VISITS
        self.selector.show_spot_checkbox.active = [0]
        before = self.selector.status_div.text
        self.selector._render_visible_groups()
        # Nothing hidden, so the message is not replaced with a filter notice.
        self.assertEqual(len(self.selector.visible_groups), len(self.selector.survey_groups))
        self.assertEqual(self.selector.status_div.text, before)
