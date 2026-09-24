"""
Run YAMNet sound-event detection over a stretch of survey audio (any AudioSet
class — motorcycle, dog, music, aircraft, etc. — via --target-class) and
export the qualifying events as a Classifications CSV the dashboard already
knows how to import (Side panel -> Classifications -> Import).

Defaults are job-6461-specific (motorcycle detection on R14.WAV) since that's
what this script was first built for, but every default is a CLI flag —
see `classify-survey-audio` skill (G:\\My Drive\\Venta AI\\skills\\classify-survey-audio\\core.md)
for the general workflow on a different job or a different target sound.

This does NOT clip audio and does NOT modify the dashboard. It produces a
CSV compatible with `classificationUtils.js.parseClassificationsCsv`
(columns: position_id, source_id, source_label, start, end, state,
confidence, description, audio_file, color). Once imported, each event
becomes a clickable classification interval at the correct position/time —
elevate it to a region (button in the panel) to play the underlying audio
directly in the dashboard, exactly as with any other region.

Reuses the model-loading / resampling / event-merging code from
benchmark_yamnet.py rather than duplicating it.

Run inside the same isolated .venv-yamnet-benchmark environment used for
the earlier speed benchmark.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import soundfile as sf

try:
    from . import benchmark_yamnet as bm
except ImportError:  # Direct script execution: its directory is on sys.path.
    import benchmark_yamnet as bm

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_RESULTS_DIR = SCRIPT_DIR / "results" / "full_day"
DEFAULT_TFHUB_CACHE = SCRIPT_DIR / "tfhub_cache"

# Survey start (naive local wall-clock, per L292_log.csv) and its timezone —
# matches noise_survey_analysis/core/data_parsers.py DEFAULT_TIMEZONE, so
# exported event times land on the exact same instant the dashboard already
# plots for the log/audio data.
SURVEY_START_LOCAL = datetime(2026, 6, 30, 13, 30, 0)
SURVEY_TIMEZONE = "Europe/London"

# From the job's noise_survey_config_6461.json "sources" entries — must match
# exactly, since the dashboard keys position data by this string.
DEFAULT_POSITION_ID = "MP1 - A39 north-west (971-3)"

DEFAULT_SOURCE_AUDIO = bm.DEFAULT_SOURCE_AUDIO
# 2026-07-01 00:00:00 local is 10.5 h (37,800 s) into R14.WAV (which starts
# 2026-06-30 13:30:00 local) — a full weekday calendar day, entirely inside
# R14 without touching the R14/R15 boundary.
DEFAULT_OFFSET_SECONDS = 37800
DEFAULT_DURATION_SECONDS = 86400  # 24 hours
DEFAULT_CHUNK_SECONDS = 120  # best-performing chunk size from the benchmark
DEFAULT_OVERLAP_SECONDS = 1.0
DEFAULT_HIGH_THRESHOLD = 0.20   # "on" — matches the two manually-confirmed real detections
DEFAULT_LOW_THRESHOLD = 0.10    # "uncertain" — worth a look, not a confident call
DEFAULT_GAP_SECONDS = 1.5


def local_offset_to_epoch_ms(offset_seconds: float, survey_start_local: datetime, tz_name: str) -> int:
    local_dt = survey_start_local + timedelta(seconds=offset_seconds)
    aware = local_dt.replace(tzinfo=ZoneInfo(tz_name))
    return int(round(aware.astimezone(timezone.utc).timestamp() * 1000))


def _read_with_retry(source_path: Path, pos: int, n: int, max_attempts: int = 5):
    """Multi-hour reads over a mounted Google Drive Shared Drive occasionally hit a
    transient libsndfile 'System error' (network hiccup, not a real corrupt-file
    condition) — retry with backoff rather than aborting a run hours in."""
    import time as _time
    last_exc = None
    for attempt in range(1, max_attempts + 1):
        try:
            return sf.read(str(source_path), start=pos, frames=n, dtype="float32", always_2d=True)
        except sf.LibsndfileError as exc:
            last_exc = exc
            if attempt == max_attempts:
                break
            wait = min(2 ** attempt, 30)
            print(f"  [retry] transient read error at frame {pos} (attempt {attempt}/{max_attempts}): "
                  f"{exc} — retrying in {wait}s")
            _time.sleep(wait)
    raise last_exc


def iter_source_chunks(source_path: Path, offset_seconds: float, duration_seconds: float,
                        chunk_seconds: float, overlap_seconds: float,
                        timings: dict | None = None):
    """Read contiguous (overlapping) chunks directly from the source WAV via
    partial soundfile reads — never loads the whole day into memory at once.

    `timings`, if given, accumulates seconds spent purely in the file read into
    timings['audio_read_seconds'] so callers can separate I/O cost from model
    cost. Purely additive: chunk boundaries, overlap handling and the yielded
    values are unchanged, since exported timestamps depend on them."""
    info = sf.info(str(source_path))
    sr = info.samplerate
    start_frame_abs = int(round(offset_seconds * sr))
    total_frames = int(round(duration_seconds * sr))
    end_frame_abs = start_frame_abs + total_frames
    if end_frame_abs > info.frames:
        raise ValueError(
            f"Requested window exceeds source duration "
            f"({info.frames / sr:.1f}s available, "
            f"{offset_seconds + duration_seconds:.1f}s requested)"
        )

    chunk_frames = int(round(chunk_seconds * sr))
    overlap_frames = int(round(overlap_seconds * sr))
    step_frames = max(chunk_frames - overlap_frames, 1)

    pos = start_frame_abs
    while pos < end_frame_abs:
        n = min(chunk_frames, end_frame_abs - pos)
        _t_read = time.perf_counter()
        data, read_sr = _read_with_retry(source_path, pos, n)
        if timings is not None:
            timings["audio_read_seconds"] = (
                timings.get("audio_read_seconds", 0.0) + (time.perf_counter() - _t_read)
            )
        if data.shape[1] > 1:
            data = data.mean(axis=1)
        else:
            data = data[:, 0]
        chunk_offset_seconds = (pos - start_frame_abs) / sr
        yield data, read_sr, chunk_offset_seconds
        if pos + n >= end_frame_abs:
            break
        pos += step_frames


def _slugify(label: str) -> str:
    return "".join(c.lower() if c.isalnum() else "_" for c in label.strip()).strip("_")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-audio", type=Path, default=Path(DEFAULT_SOURCE_AUDIO))
    parser.add_argument("--offset-seconds", type=float, default=DEFAULT_OFFSET_SECONDS)
    parser.add_argument("--duration-seconds", type=float, default=DEFAULT_DURATION_SECONDS)
    parser.add_argument("--chunk-seconds", type=float, default=DEFAULT_CHUNK_SECONDS)
    parser.add_argument("--overlap-seconds", type=float, default=DEFAULT_OVERLAP_SECONDS)
    parser.add_argument("--target-class", type=str, default="Motorcycle",
                         help="Exact YAMNet/AudioSet class name to detect (case-insensitive, "
                              "must match the class map exactly — e.g. 'Motorcycle', "
                              "'Dog', 'Music', 'Aircraft'). See class_names.csv in the "
                              "TF-Hub cache, or the AudioSet ontology, for valid names.")
    parser.add_argument("--supporting-keywords", type=str, default=None,
                         help="Comma-separated substrings identifying weaker 'supporting' "
                              "classes to also track (e.g. 'engine,revving,vehicle'). Only "
                              "used with --include-supporting. Defaults to a built-in "
                              "vehicle/engine list when --target-class is Motorcycle; "
                              "otherwise defaults to none.")
    parser.add_argument("--high-threshold", type=float, default=DEFAULT_HIGH_THRESHOLD,
                         help="Peak score at/above which an event is exported as state='on'.")
    parser.add_argument("--low-threshold", type=float, default=DEFAULT_LOW_THRESHOLD,
                         help="Peak score at/above which (but below --high-threshold) an "
                              "event is exported as state='uncertain'.")
    parser.add_argument("--gap-seconds", type=float, default=DEFAULT_GAP_SECONDS)
    parser.add_argument("--survey-start-local", type=str,
                         default=SURVEY_START_LOCAL.isoformat(),
                         help="Naive local wall-clock survey start, ISO format "
                              "(e.g. 2026-06-30T13:30:00) — read from the job's "
                              "*_log.csv first row. REQUIRED to change for any job "
                              "other than 6461, or exported timestamps will silently "
                              "be wrong. Must match the dashboard's own parsing "
                              "(Europe/London local by default — see --timezone).")
    parser.add_argument("--timezone", type=str, default=SURVEY_TIMEZONE,
                         help="IANA timezone the survey start is local to — must "
                              "match noise_survey_analysis's DEFAULT_TIMEZONE "
                              "(data_parsers.py) for exported times to line up "
                              "with the dashboard.")
    parser.add_argument("--position-id", type=str, default=DEFAULT_POSITION_ID)
    parser.add_argument("--source-id", type=str, default=None,
                         help="Defaults to yamnet_<target_class>.")
    parser.add_argument("--source-label", type=str, default=None,
                         help="Defaults to 'YAMNet: <target_class>'.")
    parser.add_argument("--include-supporting", action="store_true",
                         help="Also export a second CSV of supporting-class events "
                              "(per --supporting-keywords) that do not overlap a direct "
                              "target-class event.")
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--tfhub-cache-dir", type=Path, default=DEFAULT_TFHUB_CACHE)
    args = parser.parse_args()

    target_class = args.target_class
    slug = _slugify(target_class)
    source_id = args.source_id or f"yamnet_{slug}"
    source_label = args.source_label or f"YAMNet: {target_class}"
    uses_legacy_6461_defaults = (
        target_class.strip().casefold() == "motorcycle"
        and args.position_id == DEFAULT_POSITION_ID
        and args.source_id is None
        and args.source_label is None
    )
    supporting_keywords = (
        [k.strip() for k in args.supporting_keywords.split(",") if k.strip()]
        if args.supporting_keywords else None
    )
    survey_start_local = datetime.fromisoformat(args.survey_start_local)
    tz_name = args.timezone

    args.results_dir.mkdir(parents=True, exist_ok=True)

    day_start_local = survey_start_local + timedelta(seconds=args.offset_seconds)
    day_end_local = day_start_local + timedelta(seconds=args.duration_seconds)
    print(f"Processing {args.source_audio.name}: "
          f"{day_start_local.isoformat()} to {day_end_local.isoformat()} "
          f"({tz_name} local), {args.duration_seconds / 3600:.1f} h, "
          f"target class: {target_class!r}")

    print("Loading YAMNet ...")
    model, class_names, model_load_s, cached = bm.load_yamnet(args.tfhub_cache_dir)
    class_indices = bm.relevant_class_indices(class_names, target_class, supporting_keywords)
    if not class_indices["direct"]:
        raise ValueError(
            f"--target-class {target_class!r} does not exactly match any YAMNet class name "
            f"(case-insensitive). Check the AudioSet ontology / class_names.csv for the exact "
            f"label text."
        )
    all_relevant_idx = sorted(set(class_indices["direct"]) | set(class_indices["supporting"]))
    print(f"  model_load_seconds={model_load_s:.2f} (cached={cached})")

    dummy = np.zeros(int(2 * bm.YAMNET_SAMPLE_RATE), dtype=np.float32)
    t0 = time.perf_counter()
    _ = model(dummy)
    print(f"  warmup_seconds={time.perf_counter() - t0:.2f}")

    print(f"Streaming audio in {args.chunk_seconds:.0f}s chunks from source "
          f"(no full-day file kept in memory) ...")
    t_start = time.perf_counter()
    rows = []
    n_chunks = 0
    for waveform, orig_sr, chunk_offset_s in iter_source_chunks(
        args.source_audio, args.offset_seconds, args.duration_seconds,
        args.chunk_seconds, args.overlap_seconds,
    ):
        waveform_16k = bm.resample_to_16k(waveform, orig_sr)
        scores, _emb, _mel = model(waveform_16k)
        scores_np = scores.numpy()
        n_chunks += 1
        for frame_i in range(scores_np.shape[0]):
            frame_time = chunk_offset_s + frame_i * bm.YAMNET_FRAME_HOP_SECONDS
            row = {"frame_time": round(frame_time, 3), "chunk_index": n_chunks - 1}
            for idx in all_relevant_idx:
                row[class_names[idx]] = float(scores_np[frame_i, idx])
            rows.append(row)
        if n_chunks % 60 == 0:
            elapsed = time.perf_counter() - t_start
            processed_h = chunk_offset_s / 3600
            print(f"  ... {processed_h:.2f}h of audio processed "
                  f"({elapsed:.1f}s wall time so far)")

    inference_wall_seconds = time.perf_counter() - t_start
    print(f"Done streaming: {n_chunks} chunks, {len(rows)} frames, "
          f"{inference_wall_seconds:.1f}s wall time "
          f"({args.duration_seconds / inference_wall_seconds:.0f}x realtime)")

    frame_df = pd.DataFrame(rows)
    frame_df = (
        frame_df.sort_values(["frame_time", "chunk_index"])
        .drop_duplicates(subset="frame_time", keep="first")
        .reset_index(drop=True)
    )
    frame_df.to_parquet(args.results_dir / "frame_scores_full_day.parquet", index=False)
    print(f"Wrote frame-level scores: {args.results_dir / 'frame_scores_full_day.parquet'} "
          f"({len(frame_df)} frames)")

    supporting_names = [class_names[i] for i in class_indices["supporting"]
                         if class_names[i] in frame_df.columns]

    # direct target-class events at the low threshold (superset); tier by peak score
    all_events = bm.merge_events(
        frame_df, target_class, args.low_threshold, args.gap_seconds, supporting_names
    )
    for ev in all_events:
        ev["state"] = "on" if ev["peak_score"] >= args.high_threshold else "uncertain"

    print(f"Direct {target_class!r} candidate events >= {args.low_threshold}: {len(all_events)} "
          f"({sum(1 for e in all_events if e['state'] == 'on')} at 'on' confidence "
          f">= {args.high_threshold}, "
          f"{sum(1 for e in all_events if e['state'] == 'uncertain')} 'uncertain')")

    classification_rows = []
    for ev in all_events:
        start_ms = local_offset_to_epoch_ms(args.offset_seconds + ev["start_time"], survey_start_local, tz_name)
        end_ms = local_offset_to_epoch_ms(args.offset_seconds + ev["end_time"], survey_start_local, tz_name)
        classification_rows.append({
            "position_id": args.position_id,
            "source_id": source_id,
            "source_label": source_label,
            "start": start_ms,
            "end": end_ms,
            "state": ev["state"],
            "confidence": ev["peak_score"],
            "description": (
                f"YAMNet peak {ev['peak_score']:.2f}, mean {ev['mean_score']:.2f} "
                f"over {ev['n_frames']} frame(s). Co-occurring: {ev.get('top_classes', '')}. "
                f"Not independently verified — spot-check by listening before relying on this."
            ),
            "audio_file": args.source_audio.name,
            "color": "",
        })

    direct_filename = (
        "6461_motorcycle_classifications.csv"
        if uses_legacy_6461_defaults
        else f"classifications_{slug}.csv"
    )
    classifications_path = args.results_dir / direct_filename
    pd.DataFrame(classification_rows, columns=[
        "position_id", "source_id", "source_label", "start", "end",
        "state", "confidence", "description", "audio_file", "color",
    ]).to_csv(classifications_path, index=False)
    print(f"Wrote dashboard-importable classifications CSV: {classifications_path} "
          f"({len(classification_rows)} rows)")

    if args.include_supporting:
        if not supporting_names:
            print("\n--include-supporting was set but no supporting classes are configured "
                  "(pass --supporting-keywords) — skipping supporting export.")
        support_events_all = []
        for name in supporting_names:
            for e in bm.merge_events(frame_df, name, args.high_threshold, args.gap_seconds):
                support_events_all.append({**e, "class": name})
        direct_on_ranges = [
            (e["start_time"], e["end_time"]) for e in all_events if e["state"] == "on"
        ]

        def overlaps_direct(ev):
            return any(not (ev["end_time"] < s or ev["start_time"] > e) for s, e in direct_on_ranges)

        supporting_only = [e for e in support_events_all if not overlaps_direct(e)]
        support_rows = []
        for ev in supporting_only:
            start_ms = local_offset_to_epoch_ms(args.offset_seconds + ev["start_time"], survey_start_local, tz_name)
            end_ms = local_offset_to_epoch_ms(args.offset_seconds + ev["end_time"], survey_start_local, tz_name)
            support_rows.append({
                "position_id": args.position_id,
                "source_id": f"yamnet_supporting_{_slugify(ev['class'])}",
                "source_label": f"YAMNet: {ev['class']} (supporting, not {target_class})",
                "start": start_ms,
                "end": end_ms,
                "state": "uncertain",
                "confidence": ev["peak_score"],
                "description": f"Supporting class signal ({ev['class']}); "
                                f"NOT a direct {target_class} detection.",
                "audio_file": args.source_audio.name,
                "color": "",
            })
        supporting_filename = (
            "6461_supporting_vehicle_classifications.csv"
            if uses_legacy_6461_defaults
            else f"classifications_{slug}_supporting.csv"
        )
        supporting_path = args.results_dir / supporting_filename
        pd.DataFrame(support_rows, columns=[
            "position_id", "source_id", "source_label", "start", "end",
            "state", "confidence", "description", "audio_file", "color",
        ]).to_csv(supporting_path, index=False)
        print(f"Wrote supporting classifications CSV: {supporting_path} "
              f"({len(support_rows)} rows)")

    summary = {
        "source_audio": str(args.source_audio),
        "window_local_start": day_start_local.isoformat(),
        "window_local_end": day_end_local.isoformat(),
        "timezone": tz_name,
        "duration_hours": args.duration_seconds / 3600,
        "chunk_seconds": args.chunk_seconds,
        "n_chunks": n_chunks,
        "n_frames": len(frame_df),
        "inference_wall_seconds": round(inference_wall_seconds, 1),
        "realtime_factor": round(args.duration_seconds / inference_wall_seconds, 1),
        "high_threshold": args.high_threshold,
        "low_threshold": args.low_threshold,
        "target_class": target_class,
        "source_id": source_id,
        "n_events_on": sum(1 for e in all_events if e["state"] == "on"),
        "n_events_uncertain": sum(1 for e in all_events if e["state"] == "uncertain"),
        "position_id": args.position_id,
    }
    with open(args.results_dir / "run_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    print("\nSummary:")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    print(f"\nAll outputs saved under: {args.results_dir}")
    print(
        "\nTo view: open the target job's dashboard, then in the side panel go to "
        "Classifications -> Import, and select "
        f"{classifications_path.name}. Select an event in the table, then use "
        "'Elevate to Region' to play its audio directly."
    )


if __name__ == "__main__":
    main()
