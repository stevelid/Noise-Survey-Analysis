"""Conservative multi-window clock alignment between monitoring positions."""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from .config import METER_ALIGNMENT_SETTINGS


logger = logging.getLogger(__name__)


class MeterAlignmentProcessor:
    """Estimate constant chart offsets without altering source timestamps."""

    def __init__(self, settings: dict[str, Any] | None = None) -> None:
        self.settings = dict(METER_ALIGNMENT_SETTINGS)
        if settings:
            self.settings.update(settings)

    def align_positions(self, app_data: Any) -> dict[str, dict[str, Any]]:
        """Estimate offsets relative to the first position with 1-second log data."""
        if not self.settings.get('enabled', True):
            return {}

        available: list[tuple[str, pd.Series]] = []
        for position_name in app_data.positions():
            try:
                position_data = app_data[position_name]
            except KeyError:
                continue
            series = self._select_series(position_data)
            if series is not None:
                available.append((position_name, series))

        if len(available) < 2:
            return {}

        reference_name, reference = available[0]
        results: dict[str, dict[str, Any]] = {
            reference_name: {
                'accepted': True,
                'reference_position': reference_name,
                'chart_offset_seconds': 0.0,
                'reason': 'reference position',
                'windows_tested': 0,
                'windows_accepted': 0,
            }
        }
        setattr(app_data[reference_name], 'meter_alignment_result', results[reference_name])
        setattr(app_data[reference_name], 'auto_chart_offset_seconds', 0.0)

        for position_name, target in available[1:]:
            result = self.estimate_offset(reference, target)
            result['reference_position'] = reference_name
            results[position_name] = result
            position_data = app_data[position_name]
            setattr(position_data, 'meter_alignment_result', result)
            if result['accepted']:
                setattr(position_data, 'auto_chart_offset_seconds', result['chart_offset_seconds'])
                logger.info(
                    "Meter alignment accepted for '%s' relative to '%s': chart offset %+.1fs "
                    "(%d windows, median r=%.3f).",
                    position_name,
                    reference_name,
                    result['chart_offset_seconds'],
                    result['windows_accepted'],
                    result['median_score'],
                )
            else:
                logger.info(
                    "Meter alignment not applied for '%s' relative to '%s': %s.",
                    position_name,
                    reference_name,
                    result['reason'],
                )
        return results

    @staticmethod
    def _select_series(position_data: Any) -> pd.Series | None:
        data = getattr(position_data, 'log_totals', None)
        if data is None or data.empty or 'Datetime' not in data.columns:
            return None

        selected = None
        for target in ('LAeq', 'LZeq'):
            for column in data.columns:
                if str(column).strip() == target:
                    selected = column
                    break
            if selected is not None:
                break
        if selected is None:
            return None

        times = pd.to_datetime(data['Datetime'], errors='coerce', utc=True)
        values = pd.to_numeric(data[selected], errors='coerce')
        series = pd.Series(values.to_numpy(dtype=float), index=pd.DatetimeIndex(times))
        series = series[~series.index.isna() & np.isfinite(series.to_numpy())]
        series = series[~series.index.duplicated(keep='last')].sort_index()
        if len(series) < 2:
            return None

        median_step = series.index.to_series().diff().dropna().median()
        if pd.isna(median_step) or median_step > pd.Timedelta(seconds=2):
            return None
        return series

    def estimate_offset(self, reference: pd.Series, target: pd.Series) -> dict[str, Any]:
        search = int(self.settings['search_seconds'])
        window = int(self.settings['window_seconds'])
        min_overlap = int(self.settings['min_overlap_seconds'])

        start = max(reference.index.min(), target.index.min()).ceil('s')
        end = min(reference.index.max(), target.index.max()).floor('s')
        overlap_seconds = int((end - start).total_seconds()) if end > start else 0
        if overlap_seconds < min_overlap:
            return self._rejected('insufficient overlapping 1-second data')

        index = pd.date_range(start, end, freq='s')
        reference_values = reference.reindex(index).interpolate(limit=2).to_numpy(dtype=float)
        target_values = target.reindex(index).interpolate(limit=2).to_numpy(dtype=float)
        reference_highpass = self._highpass(reference_values)
        target_highpass = self._highpass(target_values)

        starts = self._candidate_starts(reference_highpass, target_highpass, window, search)
        window_results = []
        for window_start in starts:
            result = self._window_lag(
                reference_highpass,
                target_highpass,
                window_start,
                window,
                search,
            )
            if result is not None:
                result['timestamp'] = index[window_start].isoformat()
                window_results.append(result)

        accepted_windows = [
            result for result in window_results
            if result['score'] >= float(self.settings['min_window_score'])
            and result['uniqueness_margin'] >= float(self.settings['min_window_margin'])
        ]
        minimum_windows = int(self.settings['min_accepted_windows'])
        if len(accepted_windows) < minimum_windows:
            return self._rejected(
                f"only {len(accepted_windows)} of {len(window_results)} windows were distinctive enough",
                window_results,
                accepted_windows,
            )

        lags = np.asarray([result['lag_seconds'] for result in accepted_windows], dtype=float)
        scores = np.asarray([result['score'] for result in accepted_windows], dtype=float)
        median_lag = float(np.median(lags))
        median_score = float(np.median(scores))
        lag_spread = float(np.max(np.abs(lags - median_lag)))
        drift_seconds = self._estimated_drift_seconds(accepted_windows, overlap_seconds)

        accepted = (
            median_score >= float(self.settings['min_median_score'])
            and lag_spread <= float(self.settings['max_lag_spread_seconds'])
            and abs(drift_seconds) <= float(self.settings['max_drift_seconds'])
        )
        if not accepted:
            reasons = []
            if median_score < float(self.settings['min_median_score']):
                reasons.append(f"median correlation {median_score:.3f} was too low")
            if lag_spread > float(self.settings['max_lag_spread_seconds']):
                reasons.append(f"window lags varied by {lag_spread:.1f}s")
            if abs(drift_seconds) > float(self.settings['max_drift_seconds']):
                reasons.append(f"estimated drift was {drift_seconds:+.1f}s across the overlap")
            result = self._rejected('; '.join(reasons), window_results, accepted_windows)
            result.update({
                'estimated_lag_seconds': median_lag,
                'median_score': median_score,
                'lag_spread_seconds': lag_spread,
                'estimated_drift_seconds': drift_seconds,
            })
            return result

        # A positive lag means the target event appears later than the reference
        # lookup window, so its chart must be shifted earlier by the same amount.
        return {
            'accepted': True,
            'chart_offset_seconds': -median_lag,
            'estimated_lag_seconds': median_lag,
            'median_score': median_score,
            'lag_spread_seconds': lag_spread,
            'estimated_drift_seconds': drift_seconds,
            'windows_tested': len(window_results),
            'windows_accepted': len(accepted_windows),
            'reason': 'independent windows agreed',
            'window_results': window_results,
        }

    @staticmethod
    def _highpass(values: np.ndarray) -> np.ndarray:
        series = pd.Series(values, dtype=float)
        baseline = series.rolling(61, center=True, min_periods=1).mean()
        result = (series - baseline).to_numpy(dtype=float)
        return np.clip(result, -20.0, 20.0)

    def _candidate_starts(
        self,
        reference: np.ndarray,
        target: np.ndarray,
        window: int,
        search: int,
    ) -> list[int]:
        first = search
        last = len(reference) - window - search
        if last <= first:
            return []

        max_windows = int(self.settings['max_windows'])
        step = max(60, int(self.settings['candidate_step_seconds']))
        edges = np.linspace(first, last + 1, max_windows + 1).astype(int)
        selected: list[int] = []
        for left, right in zip(edges[:-1], edges[1:]):
            best: tuple[float, int] | None = None
            for start in range(left, max(left + 1, right - window + 1), step):
                ref_window = reference[start:start + window]
                target_window = target[start:start + window]
                valid = np.isfinite(ref_window) & np.isfinite(target_window)
                if valid.mean() < 0.95:
                    continue
                information = float(np.std(ref_window[valid]) * np.std(target_window[valid]))
                if best is None or information > best[0]:
                    best = (information, start)
            if best is not None:
                selected.append(best[1])
        return selected

    @staticmethod
    def _window_lag(
        reference: np.ndarray,
        target: np.ndarray,
        start: int,
        window: int,
        search: int,
    ) -> dict[str, float] | None:
        ref_window = reference[start:start + window]
        target_extended = target[start - search:start + window + search]
        if len(ref_window) != window or len(target_extended) != window + 2 * search:
            return None
        if not np.all(np.isfinite(ref_window)) or not np.all(np.isfinite(target_extended)):
            return None

        ref_centered = ref_window - np.mean(ref_window)
        ref_energy = float(np.dot(ref_centered, ref_centered))
        if ref_energy <= 1e-9:
            return None

        numerators = np.correlate(target_extended, ref_centered, mode='valid')
        cumulative = np.concatenate(([0.0], np.cumsum(target_extended)))
        cumulative_sq = np.concatenate(([0.0], np.cumsum(target_extended * target_extended)))
        sums = cumulative[window:] - cumulative[:-window]
        sums_sq = cumulative_sq[window:] - cumulative_sq[:-window]
        target_energy = sums_sq - (sums * sums) / window
        denominators = np.sqrt(np.maximum(ref_energy * target_energy, 1e-30))
        scores = numerators / denominators
        if not np.any(np.isfinite(scores)):
            return None

        best_index = int(np.nanargmax(scores))
        best_score = float(scores[best_index])
        best_lag = best_index - search
        lag_axis = np.arange(-search, search + 1)
        alternatives = scores[np.abs(lag_axis - best_lag) > 2]
        runner_up = float(np.nanmax(alternatives)) if alternatives.size else -1.0
        return {
            'lag_seconds': float(best_lag),
            'score': best_score,
            'uniqueness_margin': best_score - runner_up,
        }

    @staticmethod
    def _estimated_drift_seconds(window_results: list[dict[str, Any]], overlap_seconds: int) -> float:
        if len(window_results) < 3 or overlap_seconds <= 0:
            return 0.0
        times = pd.to_datetime([result['timestamp'] for result in window_results], utc=True)
        seconds = (times - times.min()).total_seconds().to_numpy(dtype=float)
        if np.ptp(seconds) <= 0:
            return 0.0
        lags = np.asarray([result['lag_seconds'] for result in window_results], dtype=float)
        slope = float(np.polyfit(seconds, lags, 1)[0])
        return slope * overlap_seconds

    @staticmethod
    def _rejected(
        reason: str,
        window_results: list[dict[str, Any]] | None = None,
        accepted_windows: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return {
            'accepted': False,
            'chart_offset_seconds': 0.0,
            'reason': reason,
            'windows_tested': len(window_results or []),
            'windows_accepted': len(accepted_windows or []),
            'window_results': window_results or [],
        }
