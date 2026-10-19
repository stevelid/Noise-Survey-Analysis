"""Pure, duration-weighted annotation calculations shared by Python exporters.

Time spans are aligned display milliseconds. Source samples represent half-open
intervals starting at Datetime, capped at the nominal sample period across gaps.
LA90 is the duration-weighted inverse-CDF 10th percentile, not an energy mean
of interval percentiles. Estimates based on interval LAeq/LAF90 are labelled.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import math
import re
from typing import Any, Iterable

import numpy as np
import pandas as pd

TIME_MS_PER_SECOND = 1000.0
SPECTRAL_COLUMN = re.compile(r"^(L[A-Z][A-Za-z0-9]*)_([0-9.]+)(k)?(?:Hz)?$", re.I)


def union_intervals(areas: Iterable[dict | tuple]) -> list[tuple[float, float]]:
    result: list[tuple[float, float]] = []
    values = []
    for area in areas:
        try:
            start, end = (float(area["start"]), float(area["end"])) if isinstance(area, dict) else map(float, area)
        except (KeyError, TypeError, ValueError):
            continue
        if math.isfinite(start) and math.isfinite(end) and start != end:
            values.append((min(start, end), max(start, end)))
    for start, end in sorted(values):
        if result and start <= result[-1][1]:
            result[-1] = (result[-1][0], max(end, result[-1][1]))
        else:
            result.append((start, end))
    return result


def subtract_intervals(areas, exclusions) -> list[tuple[float, float]]:
    result = union_intervals(areas)
    for low, high in union_intervals(exclusions):
        remaining = []
        for start, end in result:
            if high <= start or low >= end:
                remaining.append((start, end))
            else:
                if start < low:
                    remaining.append((start, low))
                if high < end:
                    remaining.append((high, end))
        result = remaining
    return result


def intersect_intervals(left, right) -> list[tuple[float, float]]:
    """Intersect two unions without double-counting adjacent/context spans."""
    first, second = union_intervals(left), union_intervals(right)
    result = []
    i = j = 0
    while i < len(first) and j < len(second):
        start, end = max(first[i][0], second[j][0]), min(first[i][1], second[j][1])
        if start < end:
            result.append((start, end))
        if first[i][1] <= second[j][1]:
            i += 1
        else:
            j += 1
    return result


def background_intervals(region: dict, regions: list[dict], meter: str,
                         window_s: float = 300) -> list[tuple[float, float]]:
    """Pool context either side of every area, excluding present annotations."""
    width = window_s * TIME_MS_PER_SECOND
    areas = union_intervals(region.get("areas") or [region])
    context = [(start - width, start) for start, _ in areas]
    context += [(end, end + width) for _, end in areas]
    exclusions = []
    for candidate in regions:
        if candidate.get("meterStates", {}).get(meter) == "present" or candidate.get("positionId") == meter:
            exclusions.extend(candidate.get("areas") or [candidate])
    return subtract_intervals(context, [*areas, *exclusions])


def weighted_energy(values: np.ndarray, weights: np.ndarray) -> float | None:
    mask = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
    if not mask.any():
        return None
    # Subtract the maximum before exponentiation to avoid avoidable overflow.
    maximum = float(np.max(values[mask]))
    return float(maximum + 10 * np.log10(np.average(10**((values[mask] - maximum) / 10), weights=weights[mask])))


def weighted_quantile(values: np.ndarray, weights: np.ndarray, quantile: float = .1) -> float | None:
    mask = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
    if not mask.any():
        return None
    order = np.argsort(values[mask], kind="stable")
    ordered_values, ordered_weights = values[mask][order], weights[mask][order]
    index = int(np.searchsorted(np.cumsum(ordered_weights), quantile * np.sum(ordered_weights), side="left"))
    return float(ordered_values[min(index, len(ordered_values) - 1)])


@dataclass
class MetricResult:
    data_resolution: str
    sample_interval_s: float | None = None
    coverage: float = 0.0
    LAeq_dB: float | None = None
    LAFmax_dB: float | None = None
    LAF90_dB: float | None = None
    background_LA90_dB: float | None = None
    background_LAeq_dB: float | None = None
    diff_from_background_dB: float | None = None
    context_duration_s: float = 0.0
    percentile_method: str = "unavailable"
    missing_reasons: list[str] = field(default_factory=list)
    spectra: dict[str, dict[float, float | None]] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def datetime_milliseconds(values) -> np.ndarray:
    """Return UTC epoch milliseconds independently of pandas' storage unit.

    pandas 2/3 may retain seconds, milliseconds or microseconds rather than
    nanoseconds. Integer conversion alone therefore has no fixed time unit.
    """
    dates = pd.DatetimeIndex(pd.to_datetime(values, utc=True))
    return dates.as_unit("ns").asi8 / 1e6


def _sample_geometry(frame: pd.DataFrame, sample_interval_s: float | None):
    times = datetime_milliseconds(frame["Datetime"])
    positive = np.diff(times)
    positive = positive[positive > 0]
    nominal = sample_interval_s or frame.attrs.get("sample_interval_s")
    if not nominal and len(positive):
        nominal = float(np.median(positive)) / 1000
    nominal_ms = float(nominal or 0) * 1000
    if "__sample_interval_s" in frame:
        caps = pd.to_numeric(frame["__sample_interval_s"], errors="coerce").to_numpy(dtype=float) * 1000
        caps = np.where(np.isfinite(caps) & (caps > 0), caps, nominal_ms)
        nominal = max(float(nominal or 0), float(np.max(caps)) / 1000) if len(caps) else nominal
    else:
        caps = np.full(len(times), nominal_ms)
    # Gaps do not extend the preceding measured sample through missing data.
    ends = np.minimum(np.r_[times[1:], times[-1] + caps[-1]], times + caps)
    return times, ends, nominal


def _weights(times, ends, areas) -> np.ndarray:
    weights = np.zeros(len(times), dtype=float)
    for start, end in union_intervals(areas):
        weights += np.maximum(0, np.minimum(ends, end) - np.maximum(times, start)) / 1000
    return weights


@dataclass(frozen=True)
class PreparedColumn:
    """Finite samples on a column's native clock; shared across region queries."""
    values: np.ndarray
    starts: np.ndarray
    ends: np.ndarray
    periods: float | np.ndarray | None = None

    def in_windows(self, areas) -> PreparedColumn:
        # Ends are monotonic: no sample extends beyond the next native sample.
        # Merge index ranges too, since one long sample may touch two windows.
        ranges: list[tuple[int, int]] = []
        for start, end in union_intervals(areas):
            low = int(np.searchsorted(self.ends, start, side="right"))
            high = int(np.searchsorted(self.starts, end, side="left"))
            if low >= high:
                continue
            if ranges and low <= ranges[-1][1]:
                ranges[-1] = (ranges[-1][0], max(high, ranges[-1][1]))
            else:
                ranges.append((low, high))
        if not ranges:
            return EMPTY_COLUMN

        def select(values):
            if len(ranges) == 1:
                low, high = ranges[0]
                return values[low:high]
            return np.concatenate([values[low:high] for low, high in ranges])

        periods = select(self.periods) if isinstance(self.periods, np.ndarray) else self.periods
        return PreparedColumn(select(self.values), select(self.starts), select(self.ends), periods)


EMPTY_VALUES = np.array([], dtype=float)
EMPTY_COLUMN = PreparedColumn(EMPTY_VALUES, EMPTY_VALUES, EMPTY_VALUES)


@dataclass(frozen=True)
class PreparedMeterData:
    """One meter/resolution prepared once, without a global whole-file cache."""
    geometry: PreparedColumn
    columns: dict[str, PreparedColumn]
    sample_interval_s: float | None
    missing_reason: str | None = None


def prepare_meter_data(frame: pd.DataFrame | None,
                       sample_interval_s: float | None = None) -> PreparedMeterData:
    """Normalize and build native sample geometry once for repeated queries.

    The caller owns this object and releases it before loading another meter.
    All-finite bands share timestamp/end arrays; only sparse native clocks need
    their own geometry. Numeric values are copied so later caller edits cannot
    invalidate a prepared export halfway through its region queries.
    """
    if frame is None or frame.empty or "Datetime" not in frame:
        return PreparedMeterData(EMPTY_COLUMN, {}, None, "No source samples in requested windows")
    frame = frame.dropna(subset=["Datetime"]).sort_values("Datetime").drop_duplicates("Datetime", keep="first").reset_index(drop=True)
    if frame.empty:
        return PreparedMeterData(EMPTY_COLUMN, {}, None, "No valid source timestamps")
    starts, ends, nominal = _sample_geometry(frame, sample_interval_s)
    geometry = PreparedColumn(starts, starts, ends)
    columns = {}
    common_ends: dict[float, np.ndarray] = {}
    for name in frame:
        if name not in ("LAeq", "LAFmax", "LAF", "LAFp", "LAF90") and not SPECTRAL_COLUMN.match(str(name)):
            continue
        values = pd.to_numeric(frame[name], errors="coerce").to_numpy(dtype=float, copy=True)
        finite = np.isfinite(values)
        if not finite.any():
            columns[name] = EMPTY_COLUMN
            continue
        all_finite = bool(finite.all())
        times = starts if all_finite else starts[finite]
        values = values if all_finite else values[finite]
        period_name = f"__sample_interval_s:{name}"
        if period_name not in frame:
            period_name = "__sample_interval_s"
        if period_name in frame:
            periods = pd.to_numeric(frame[period_name], errors="coerce").to_numpy(dtype=float)
            if not all_finite:
                periods = periods[finite]
            periods = np.where(np.isfinite(periods) & (periods > 0), periods, float(sample_interval_s or nominal or 0))
            if periods.min() == periods.max():
                periods = float(periods[0])
        else:
            periods = float(sample_interval_s or nominal or 0)
        if all_finite and isinstance(periods, float) and periods in common_ends:
            stops = common_ends[periods]
        else:
            caps = periods * TIME_MS_PER_SECOND
            final_cap = caps[-1] if isinstance(caps, np.ndarray) else caps
            stops = np.minimum(np.r_[times[1:], times[-1] + final_cap], times + caps)
            if all_finite and isinstance(periods, float):
                common_ends[periods] = stops
        columns[name] = PreparedColumn(values, times, stops, periods)
    return PreparedMeterData(geometry, columns, nominal)


def spectral_provenance(data: PreparedMeterData, parameter: str, areas,
                        chart_offset_ms: float = 0) -> tuple[float, float | None]:
    """Minimum finite-band coverage and native period, using prepared clocks."""
    source_areas = [(start - chart_offset_ms, end - chart_offset_ms) for start, end in union_intervals(areas)]
    duration_s = sum(end - start for start, end in source_areas) / TIME_MS_PER_SECOND
    coverages, periods = [], []
    for name, column in data.columns.items():
        match = SPECTRAL_COLUMN.match(str(name))
        if not match or match.group(1) != parameter:
            continue
        selected = column.in_windows(source_areas)
        coverages.append(min(1.0, float(_weights(selected.starts, selected.ends, source_areas).sum()) / duration_s) if duration_s else 0.0)
        if len(selected.values) and selected.periods is not None:
            periods.append(float(np.max(selected.periods)))
    return min(coverages, default=0.0), max(periods, default=None)


def compute_region_metrics(frame: pd.DataFrame | PreparedMeterData, areas, *, meter: str = "",
                           chart_offset_ms: float = 0, resolution: str = "log",
                           sample_interval_s: float | None = None,
                           context_areas=None, min_context_s: float = 60) -> MetricResult:
    result = MetricResult(data_resolution=resolution)
    intervals = union_intervals(areas)
    source_areas = [(start - chart_offset_ms, end - chart_offset_ms) for start, end in intervals]
    requested_s = sum(end - start for start, end in intervals) / 1000
    data = frame if isinstance(frame, PreparedMeterData) else prepare_meter_data(frame, sample_interval_s)
    if data.missing_reason:
        result.missing_reasons.append(data.missing_reason)
        return result
    nominal = data.sample_interval_s
    needed = [*source_areas, *[(start - chart_offset_ms, end - chart_offset_ms)
                             for start, end in union_intervals(context_areas or [])]]
    selected_geometry = data.geometry.in_windows(needed)
    if not len(selected_geometry.starts) and not any(len(column.in_windows(needed).starts) for column in data.columns.values()):
        result.sample_interval_s = nominal
        result.missing_reasons.append("No source samples in requested windows")
        return result
    result.sample_interval_s = nominal
    weights = _weights(selected_geometry.starts, selected_geometry.ends, source_areas)
    result.coverage = min(1.0, float(weights.sum()) / requested_s) if requested_s > 0 else 0.0

    # Each parameter has its own native clock. Joining an NTi broadband file
    # with faster RTA rows must not shorten the broadband sample intervals.
    column_cache = {}

    def column_geometry(name: str):
        if name in column_cache:
            return column_cache[name]
        selected = data.columns.get(name, EMPTY_COLUMN).in_windows(needed)
        value = (selected.values, selected.starts, selected.ends,
                 _weights(selected.starts, selected.ends, source_areas))
        column_cache[name] = value
        return value

    energy_values, energy_times, energy_ends, energy_weights = column_geometry("LAeq")
    result.LAeq_dB = weighted_energy(energy_values, energy_weights)
    finite_energy_duration = float(energy_weights.sum())
    if len(energy_values) and requested_s > 0:
        result.coverage = min(1.0, finite_energy_duration / requested_s)
    if result.LAeq_dB is not None and finite_energy_duration + 1e-6 < requested_s:
        result.missing_reasons.append("LAeq has incomplete finite-sample coverage")
    maxima, _, _, maximum_weights = column_geometry("LAFmax")
    valid = np.isfinite(maxima) & (maximum_weights > 0)
    result.LAFmax_dB = float(maxima[valid].max()) if valid.any() else None
    # Real fast-level samples take precedence; interval statistics remain useful
    # estimates but are explicitly distinguished in exported provenance.
    candidates = ("LAF", "LAFp", "LAeq", "LAF90")
    percentile_column = next((name for name in candidates
                              if column_geometry(name)[3].sum() > 0), None)
    if percentile_column is None:
        percentile_column = next((name for name in candidates if len(column_geometry(name)[0])), None)
    if percentile_column:
        percentile_values, percentile_times, percentile_ends, percentile_weights = column_geometry(percentile_column)
        result.LAF90_dB = weighted_quantile(percentile_values, percentile_weights)
        indicative = resolution != "log" or (nominal or 0) >= 1 or percentile_column not in ("LAF", "LAFp")
        result.percentile_method = f"duration-weighted inverse-CDF p10 of {percentile_column}" + ("; indicative" if indicative else "")
    if context_areas:
        context = [(start - chart_offset_ms, end - chart_offset_ms) for start, end in union_intervals(context_areas)]
        if percentile_column:
            common_context = intersect_intervals(context, zip(energy_times, energy_ends))
            common_context = intersect_intervals(common_context, zip(percentile_times, percentile_ends))
        else:
            common_context = []
        result.context_duration_s = sum(end - start for start, end in common_context) / 1000
        if result.context_duration_s + 1e-6 >= min_context_s and percentile_column:
            result.background_LA90_dB = weighted_quantile(percentile_values, _weights(percentile_times, percentile_ends, common_context))
            result.background_LAeq_dB = weighted_energy(energy_values, _weights(energy_times, energy_ends, common_context))
        else:
            result.missing_reasons.append(f"Background context below {min_context_s:g} usable seconds")
    if result.LAeq_dB is not None and result.background_LA90_dB is not None:
        result.diff_from_background_dB = result.LAeq_dB - result.background_LA90_dB
    for name in data.columns:
        match = SPECTRAL_COLUMN.match(str(name))
        if not match:
            continue
        parameter, frequency, kilo = match.groups()
        frequency_hz = float(frequency) * (1000 if kilo else 1)
        values, _, _, spectral_weights = column_geometry(name)
        if "max" in parameter.lower():
            mask = np.isfinite(values) & (spectral_weights > 0)
            level = float(values[mask].max()) if mask.any() else None
        elif parameter.endswith("90"):
            level = weighted_quantile(values, spectral_weights)
        else:
            level = weighted_energy(values, spectral_weights)
        result.spectra.setdefault(parameter, {})[frequency_hz] = level
    if result.LAeq_dB is None:
        result.missing_reasons.append("LAeq column unavailable or contains no finite region samples")
    if result.LAFmax_dB is None:
        result.missing_reasons.append("Genuine LAFmax column unavailable")
    if result.coverage < 1 - 1e-6:
        result.missing_reasons.append("Requested area has incomplete timestamp coverage")
    return result
