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


def compute_region_metrics(frame: pd.DataFrame, areas, *, meter: str = "",
                           chart_offset_ms: float = 0, resolution: str = "log",
                           sample_interval_s: float | None = None,
                           context_areas=None, min_context_s: float = 60) -> MetricResult:
    result = MetricResult(data_resolution=resolution)
    intervals = union_intervals(areas)
    source_areas = [(start - chart_offset_ms, end - chart_offset_ms) for start, end in intervals]
    requested_s = sum(end - start for start, end in intervals) / 1000
    if frame is None or frame.empty or "Datetime" not in frame:
        result.missing_reasons.append("No source samples in requested windows")
        return result
    frame = frame.dropna(subset=["Datetime"]).sort_values("Datetime").drop_duplicates("Datetime", keep="first").reset_index(drop=True)
    if frame.empty:
        result.missing_reasons.append("No valid source timestamps")
        return result
    times, ends, nominal = _sample_geometry(frame, sample_interval_s)
    needed = [*source_areas, *[(start - chart_offset_ms, end - chart_offset_ms)
                             for start, end in union_intervals(context_areas or [])]]
    keep = np.zeros(len(frame), dtype=bool)
    for start, end in union_intervals(needed):
        keep |= (times < end) & (times + float(nominal or 0) * 1000 > start)
    frame = frame.loc[keep].reset_index(drop=True)
    if frame.empty:
        result.sample_interval_s = nominal
        result.missing_reasons.append("No source samples in requested windows")
        return result
    times, ends, nominal = _sample_geometry(frame, sample_interval_s or nominal)
    result.sample_interval_s = nominal
    weights = _weights(times, ends, source_areas)
    result.coverage = min(1.0, float(weights.sum()) / requested_s) if requested_s > 0 else 0.0

    # Each parameter has its own native clock. Joining an NTi broadband file
    # with faster RTA rows must not shorten the broadband sample intervals.
    column_cache = {}

    def column_geometry(name: str):
        if name in column_cache:
            return column_cache[name]
        if name not in frame:
            value = (np.array([]), np.array([]), np.array([]), np.array([]))
        else:
            values = pd.to_numeric(frame[name], errors="coerce").to_numpy(dtype=float)
            selected = frame.loc[np.isfinite(values), ["Datetime"]].copy()
            values = values[np.isfinite(values)]
            period_column = f"__sample_interval_s:{name}"
            if period_column in frame:
                selected["__sample_interval_s"] = frame.loc[selected.index, period_column]
            elif "__sample_interval_s" in frame:
                selected["__sample_interval_s"] = frame.loc[selected.index, "__sample_interval_s"]
            if selected.empty:
                value = (np.array([]), np.array([]), np.array([]), np.array([]))
            else:
                start, stop, _ = _sample_geometry(selected, sample_interval_s or nominal)
                value = (values, start, stop, _weights(start, stop, source_areas))
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
    for name in frame.columns:
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
