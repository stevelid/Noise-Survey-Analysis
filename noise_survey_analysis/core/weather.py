"""Read a configured site-wide weather CSV independently of acoustic positions."""
import logging
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd

logger = logging.getLogger(__name__)

PCE = {
    "wind": "wind avg (m/s)",
    "gust": "wind gust (m/s)",
    "direction": "wind dir (deg)",
    "rain": "rain in interval (mm)",
}
VISUAL_CROSSING = {
    "wind": "windspeed",
    "gust": "windgust",
    "direction": "winddir",
    "rain": "precip",
}
VC_UNITS = {"metric": (1 / 3.6, 1), "uk": (1 / 3.6, 1), "us": (0.44704, 25.4)}


@dataclass
class WeatherData:
    label: str
    samples: pd.DataFrame


def _timestamps(frame, source, timezone):
    if source == "pce":
        return pd.to_datetime(frame["datetime (utc)"], format="ISO8601", errors="coerce", utc=True)
    if "datetimeepoch" in frame:
        return pd.to_datetime(pd.to_numeric(frame["datetimeepoch"], errors="coerce"),
                              unit="s", errors="coerce", utc=True)

    values = frame["datetime"]
    populated = values.dropna().astype(str).str.strip()
    has_offset = populated.str.contains(r"(?:Z|[+-][0-9]{2}:?[0-9]{2})$", case=False)
    if not populated.empty and has_offset.all():
        return pd.to_datetime(values, format="ISO8601", errors="coerce", utc=True)
    if has_offset.any():
        raise ValueError("Visual Crossing timestamps mix local times and UTC offsets.")
    if not timezone:
        raise ValueError("Set weather.timezone for local Visual Crossing timestamps, or include datetimeEpoch.")
    try:
        tz = ZoneInfo(timezone)
    except (ValueError, ZoneInfoNotFoundError) as exc:
        raise ValueError(f"Unknown weather timezone: {timezone}") from exc
    local = pd.to_datetime(values, format="ISO8601", errors="coerce")
    utc = local.dt.tz_localize(tz, ambiguous="NaT", nonexistent="NaT").dt.tz_convert("UTC")
    if (local.notna() & utc.isna()).any():
        logger.warning("Skipped ambiguous or nonexistent Visual Crossing local times. Use datetimeEpoch for DST transitions.")
    return utc


def parse_weather_csv(path: Path, options: dict) -> WeatherData:
    frame = pd.read_csv(path, encoding="utf-8-sig")
    frame.columns = frame.columns.str.strip().str.casefold()
    source = options.get("format", "auto")
    pce_fields = "datetime (utc)" in frame and bool(set(PCE.values()) & set(frame.columns))
    vc_fields = {"datetime", "datetimeepoch"} & set(frame.columns) and bool(set(VISUAL_CROSSING.values()) & set(frame.columns))
    if source == "auto":
        source = "pce" if pce_fields else "visual_crossing" if vc_fields else None
    if source == "pce" and pce_fields:
        columns, factors, interval, label = PCE, (1, 1), 5, "On-site PCE"
    elif source == "visual_crossing" and vc_fields:
        units = options.get("units")
        if units not in VC_UNITS:
            raise ValueError("Set weather.units to metric, uk or us for Visual Crossing.")
        columns, factors, interval, label = VISUAL_CROSSING, VC_UNITS[units], 60, "Visual Crossing"
    else:
        raise ValueError(f"Weather headers did not match the configured format ({source or 'auto'}).")

    time = _timestamps(frame, source, options.get("timezone"))
    data = pd.DataFrame({"time": time})
    for name, header in columns.items():
        if header in frame:
            values = pd.to_numeric(frame[header], errors="coerce")
            data[name] = values.where(values.ge(0) & values.lt(float("inf")))
        else:
            data[name] = float("nan")
    data[["wind", "gust"]] *= factors[0]
    data["rain"] *= factors[1]
    data["direction"] = data["direction"].where(data["direction"].le(360)) % 360
    if source == "pce" and "sensor lost" in frame:
        lost = ~frame["sensor lost"].fillna("").astype(str).str.strip().str.casefold().isin(
            ("", "false", "no", "0", "0.0"))
        data.loc[lost, list(columns)] = float("nan")
    # Preserve direction-only exports and gaps. Suppress a stale vane when reported wind is zero.
    calm = data[["wind", "gust"]].max(axis=1).eq(0)
    data.loc[calm, "direction"] = float("nan")

    data = data.dropna(subset=["time"]).sort_values("time", kind="stable").drop_duplicates("time", keep="last")
    data["interval_start"] = data["time"] - pd.Timedelta(minutes=interval)
    if source == "pce":
        previous = data["time"].shift()
        step = data["time"] - previous
        adjacent = step.between(pd.Timedelta(minutes=4), pd.Timedelta(minutes=6))
        data.loc[adjacent, "interval_start"] = previous[adjacent]

    start = pd.to_datetime(options["start"], utc=True) if options.get("start") else None
    end = pd.to_datetime(options["end"], utc=True) if options.get("end") else None
    if start is not None and end is not None and start >= end:
        raise ValueError("weather.start must precede weather.end.")
    if start is not None:
        data = data.loc[data["time"].gt(start)]
    if end is not None:
        data = data.loc[data["time"].le(end)]
    if data.empty or not data[list(columns)].notna().any().any():
        raise ValueError("No usable wind or rain data in the selected period.")
    return WeatherData(label, data)


def load_weather(options: dict | None) -> WeatherData | None:
    if not options:
        return None
    path = Path(options["path"])
    try:
        return parse_weather_csv(path, options)
    except (OSError, TypeError, ValueError) as exc:
        logger.warning("Weather chart unavailable for %s: %s", path, exc)
        return None
