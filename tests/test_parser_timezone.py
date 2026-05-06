"""
test_parser_timezone.py
Tests for the configurable timezone support added to AbstractNoiseParser and
NoiseParserFactory.  All tests are pure in-memory — no real survey files needed.
"""
import logging
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from noise_survey_analysis.core.data_manager import DataManager
from noise_survey_analysis.core.data_parsers import (
    DEFAULT_TIMEZONE,
    AbstractNoiseParser,
    NoiseParserFactory,
)


# ---------------------------------------------------------------------------
# Minimal concrete subclass for testing AbstractNoiseParser directly
# ---------------------------------------------------------------------------

class _ConcreteParser(AbstractNoiseParser):
    """Minimal concrete parser used only in tests."""

    def parse(self, file_path, return_all_columns=False):
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Helper: build a tiny DataFrame with a single naive timestamp column
# ---------------------------------------------------------------------------

def _make_df(ts: str) -> pd.DataFrame:
    return pd.DataFrame({'Datetime': [ts]})


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestParserTimezoneDefault(unittest.TestCase):
    """Test 1 — default resolves to Europe/London and converts BST → UTC correctly."""

    def test_attribute_is_europe_london(self):
        parser = _ConcreteParser()
        self.assertEqual(parser.timezone, 'Europe/London')

    def test_bst_to_utc_conversion(self):
        """2024-06-01 12:00 local (BST = UTC+1) should become 2024-06-01 11:00 UTC."""
        parser = _ConcreteParser()
        df = _make_df('2024-06-01 12:00:00')
        result = parser._normalize_datetime_column(df, ['Datetime'])
        self.assertFalse(result.empty)
        ts = result['Datetime'].iloc[0]
        self.assertIsNotNone(ts.tzinfo)
        expected = pd.Timestamp('2024-06-01 11:00:00', tz='UTC')
        self.assertEqual(ts, expected)


class TestParserTimezoneExplicit(unittest.TestCase):
    """Test 2 — explicit timezone changes the UTC conversion."""

    def test_new_york_edt_to_utc(self):
        """2024-06-01 12:00 EDT (UTC-4) should become 2024-06-01 16:00 UTC."""
        parser = _ConcreteParser(timezone='America/New_York')
        self.assertEqual(parser.timezone, 'America/New_York')
        df = _make_df('2024-06-01 12:00:00')
        result = parser._normalize_datetime_column(df, ['Datetime'])
        self.assertFalse(result.empty)
        ts = result['Datetime'].iloc[0]
        expected = pd.Timestamp('2024-06-01 16:00:00', tz='UTC')
        self.assertEqual(ts, expected)


class TestParserTimezoneDst(unittest.TestCase):
    """DST transition handling for localized parser timestamps."""

    def test_ambiguous_fall_back_hour_is_inferred_from_duplicate_sequence(self):
        parser = _ConcreteParser()
        df = pd.DataFrame({
            'Datetime': [
                '2024-10-27 00:30:00',
                '2024-10-27 01:30:00',
                '2024-10-27 01:30:00',
                '2024-10-27 02:30:00',
            ]
        })

        result = parser._normalize_datetime_column(df, ['Datetime'])

        self.assertEqual(
            list(result['Datetime']),
            [
                pd.Timestamp('2024-10-26 23:30:00', tz='UTC'),
                pd.Timestamp('2024-10-27 00:30:00', tz='UTC'),
                pd.Timestamp('2024-10-27 01:30:00', tz='UTC'),
                pd.Timestamp('2024-10-27 02:30:00', tz='UTC'),
            ],
        )

    def test_nonexistent_spring_forward_hour_shifts_to_valid_time(self):
        parser = _ConcreteParser()
        df = pd.DataFrame({
            'Datetime': [
                '2024-03-31 00:30:00',
                '2024-03-31 01:30:00',
                '2024-03-31 02:30:00',
            ]
        })

        result = parser._normalize_datetime_column(df, ['Datetime'])

        self.assertEqual(
            list(result['Datetime']),
            [
                pd.Timestamp('2024-03-31 00:30:00', tz='UTC'),
                pd.Timestamp('2024-03-31 01:00:00', tz='UTC'),
                pd.Timestamp('2024-03-31 01:30:00', tz='UTC'),
            ],
        )


class TestParserTimezoneInvalid(unittest.TestCase):
    """Test 3 — invalid timezone warns and falls back to Europe/London."""

    def test_invalid_warns_and_falls_back(self):
        with self.assertLogs(
            logger='noise_survey_analysis.core.data_parsers',
            level=logging.WARNING,
        ) as cm:
            parser = _ConcreteParser(timezone='Mars/Olympus_Mons')

        self.assertEqual(parser.timezone, DEFAULT_TIMEZONE)
        # Check that the warning mentions the bad name and the fallback
        joined = ' '.join(cm.output)
        self.assertIn('Mars/Olympus_Mons', joined)
        self.assertIn('Europe/London', joined)


class TestParserTimezoneNoneAndEmpty(unittest.TestCase):
    """Test 4 — both None and '' should resolve to Europe/London."""

    def test_none_defaults(self):
        parser = _ConcreteParser(timezone=None)
        self.assertEqual(parser.timezone, DEFAULT_TIMEZONE)

    def test_empty_string_defaults(self):
        parser = _ConcreteParser(timezone='')
        self.assertEqual(parser.timezone, DEFAULT_TIMEZONE)


class TestFactoryThreadsTimezone(unittest.TestCase):
    """Test 6 — NoiseParserFactory.get_parser passes timezone to the concrete parser."""

    def test_svan_parser_gets_timezone(self):
        parser = NoiseParserFactory.get_parser('data.csv', parser_type='svan', timezone='UTC')
        self.assertIsNotNone(parser)
        self.assertEqual(parser.timezone, 'UTC')

    def test_generic_parser_gets_timezone(self):
        parser = NoiseParserFactory.get_parser('data.csv', parser_type='generic', timezone='UTC')
        self.assertIsNotNone(parser)
        self.assertEqual(parser.timezone, 'UTC')

    def test_sentry_parser_gets_timezone(self):
        parser = NoiseParserFactory.get_parser('data.csv', parser_type='sentry', timezone='America/New_York')
        self.assertIsNotNone(parser)
        self.assertEqual(parser.timezone, 'America/New_York')

    def test_nti_parser_gets_timezone(self):
        parser = NoiseParserFactory.get_parser('data.csv', parser_type='nti', timezone='America/New_York')
        self.assertIsNotNone(parser)
        self.assertEqual(parser.timezone, 'America/New_York')

    def test_no_timezone_arg_still_defaults(self):
        """Existing call sites that omit timezone must continue to get Europe/London."""
        parser = NoiseParserFactory.get_parser('data.csv', parser_type='svan')
        self.assertIsNotNone(parser)
        self.assertEqual(parser.timezone, DEFAULT_TIMEZONE)


class TestParserTimezoneSourceConfig(unittest.TestCase):
    """Test source-config timezone propagation through DataManager."""

    def test_generic_source_config_timezone_controls_naive_datetime_parse(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / 'generic.csv'
            file_path.write_text(
                'Datetime,LAeq\n2024-06-01 12:00:00,50\n',
                encoding='utf-8',
            )

            manager = DataManager(
                source_configurations=[{
                    'position_name': 'P1',
                    'file_path': str(file_path),
                    'parser_type': 'generic',
                    'timezone': 'America/New_York',
                }],
                use_cache=False,
            )

            parsed_time = manager['P1'].log_totals['Datetime'].iloc[0]
            self.assertEqual(parsed_time, pd.Timestamp('2024-06-01 16:00:00', tz='UTC'))
            metadata = manager['P1'].source_file_metadata[0]['parser_specific_details']
            self.assertEqual(metadata['timezone'], 'America/New_York')

    def test_default_source_config_timezone_remains_europe_london(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / 'generic.csv'
            file_path.write_text(
                'Datetime,LAeq\n2024-06-01 12:00:00,50\n',
                encoding='utf-8',
            )

            manager = DataManager(
                source_configurations=[{
                    'position_name': 'P1',
                    'file_path': str(file_path),
                    'parser_type': 'generic',
                }],
                use_cache=False,
            )

            parsed_time = manager['P1'].log_totals['Datetime'].iloc[0]
            self.assertEqual(parsed_time, pd.Timestamp('2024-06-01 11:00:00', tz='UTC'))
            metadata = manager['P1'].source_file_metadata[0]['parser_specific_details']
            self.assertEqual(metadata['timezone'], DEFAULT_TIMEZONE)

    def test_deferred_log_source_preserves_timezone_for_lazy_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / 'generic_log.csv'
            rows = ['Datetime,LAeq']
            rows.extend(f'2024-06-01 12:00:{i % 60:02d},{50 + (i % 5)}' for i in range(90000))
            file_path.write_text('\n'.join(rows), encoding='utf-8')

            manager = DataManager(
                source_configurations=[{
                    'position_name': 'P1',
                    'file_path': str(file_path),
                    'parser_type': 'generic',
                    'timezone': 'America/New_York',
                }],
                use_cache=False,
            )

            position = manager['P1']
            self.assertEqual(position.log_file_paths[0]['timezone'], 'America/New_York')
            position.load_log_data_lazy(manager.parser_factory, use_cache=False)

            parsed_time = position.log_totals['Datetime'].iloc[0]
            self.assertEqual(parsed_time, pd.Timestamp('2024-06-01 16:00:00', tz='UTC'))
            metadata = position.source_file_metadata[0]['parser_specific_details']
            self.assertEqual(metadata['timezone'], 'America/New_York')


if __name__ == '__main__':
    unittest.main()
