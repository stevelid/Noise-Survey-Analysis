"""
YAMNet local-processing benchmark and motorcycle-detection proof of concept.

Standalone, self-contained script. Does NOT import from or modify the
`noise_survey_analysis` dashboard package or its production config/workflow.
Run inside the isolated `.venv-yamnet-benchmark` environment (see README.md).

What it does, in order:
  1. Reports machine / package / GPU-availability info.
  2. Extracts (once, cached locally) a test excerpt from the job 6461 survey
     recording via a partial `soundfile` read (does not load the whole
     multi-gigabyte source file into memory).
  3. Loads YAMNet from TensorFlow Hub once, times model load and a warm-up
     inference separately from the timed benchmark runs.
  4. For several candidate chunk durations, repeats a full
     read -> resample -> infer -> postprocess pipeline 3x each and records
     per-stage timings plus an approximate peak-memory figure.
  5. Picks the best-performing chunk duration, runs one full frame-level
     pass over the test window, and saves raw per-frame scores for the
     motorcycle-relevant AudioSet classes.
  6. Sweeps several display thresholds over the SAME saved frame scores
     (no re-inference), merges frames into candidate events, and reports
     direct motorcycle candidates vs. supporting-vehicle candidates
     separately.
  7. Cuts short review clips around the top-scoring candidates.
  8. Writes machine-readable outputs (CSV) into results/.

Everything path/parameter-related is exposed as a CLI flag with a sensible
default matching the actual job 6461 audio location and the chosen test
window (see README.md for the exact rerun command and the reasoning behind
the default offsets).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import sys
import threading
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import psutil
import soundfile as sf
from scipy.signal import resample_poly

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------

YAMNET_HUB_URL = "https://tfhub.dev/google/yamnet/1"
YAMNET_SAMPLE_RATE = 16000
# YAMNet's internal analysis window is 0.96 s with a 0.48 s hop (50% overlap
# patches). This is not an exposed model output, so frame center timestamps
# are computed from this constant rather than read from the model.
YAMNET_FRAME_HOP_SECONDS = 0.48

DEFAULT_SOURCE_AUDIO = (
    r"G:\Shared drives\Venta\Jobs\6461 Bath Road, Bridgwater"
    r"\6461 Surveys\971-3\R14.WAV"
)
# R14.WAV starts at 2026-06-30 13:30:00 (per L292_log.csv). The chosen
# excerpt starts 2026-07-01 08:00:00 (Wednesday, weekday morning) — 18h30m
# = 66600 s into the file — to maximise the chance of daytime commuter/
# leisure motorcycle traffic on Bath Road while staying well clear of the
# file's start/end and any header edge cases.
DEFAULT_OFFSET_SECONDS = 66600
DEFAULT_EXCERPT_SECONDS = 3600  # 60 min cached locally; lets --extend reuse it
DEFAULT_TEST_WINDOW_SECONDS = 1800  # 30 min used for the repeated chunk-size matrix

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_DATA_DIR = SCRIPT_DIR / "data"
DEFAULT_RESULTS_DIR = SCRIPT_DIR / "results"
DEFAULT_TFHUB_CACHE = SCRIPT_DIR / "tfhub_cache"

# Motorcycle-related AudioSet class name substrings (case-insensitive).
# "Motorcycle" itself is treated separately (direct candidate). Everything
# else here is a *supporting* signal only — never silently promoted to a
# confirmed motorcycle detection.
RELEVANT_KEYWORDS = [
    "motorcycle",
    "moped",
    "vehicle",
    "engine",
    "accelerat",
    "revving",
    "vroom",
    "traffic",
    "road",
    "car",
    "truck",
    "bus",
    "skidding",
    "tire squeal",
    "race car",
]
DIRECT_CLASS_NAME = "Motorcycle"


# --------------------------------------------------------------------------
# Memory sampling (background thread, ~50 ms poll of process RSS)
# --------------------------------------------------------------------------

class MemorySampler:
    def __init__(self, interval_s: float = 0.05):
        self._interval = interval_s
        self._proc = psutil.Process(os.getpid())
        self._samples: list[tuple[float, float]] = []  # (timestamp, rss_mb)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()

    def _run(self):
        while not self._stop.is_set():
            rss_mb = self._proc.memory_info().rss / (1024 * 1024)
            self._samples.append((time.time(), rss_mb))
            time.sleep(self._interval)

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=2)

    def peak_between(self, t_start: float, t_end: float) -> float:
        vals = [rss for ts, rss in self._samples if t_start <= ts <= t_end]
        return max(vals) if vals else float("nan")

    def peak_overall(self) -> float:
        vals = [rss for _, rss in self._samples]
        return max(vals) if vals else float("nan")


# --------------------------------------------------------------------------
# System / environment reporting
# --------------------------------------------------------------------------

def gather_system_info() -> dict:
    import tensorflow as tf
    import tensorflow_hub

    try:
        cpu_count_logical = psutil.cpu_count(logical=True)
        cpu_count_physical = psutil.cpu_count(logical=False)
    except Exception:
        cpu_count_logical = cpu_count_physical = None

    gpus = tf.config.list_physical_devices("GPU")

    info = {
        "os": platform.platform(),
        "python_version": sys.version,
        "cpu_processor": platform.processor(),
        "cpu_logical_cores": cpu_count_logical,
        "cpu_physical_cores": cpu_count_physical,
        "total_ram_gb": round(psutil.virtual_memory().total / (1024 ** 3), 1),
        "tensorflow_version": tf.__version__,
        "tensorflow_hub_version": tensorflow_hub.__version__,
        "numpy_version": np.__version__,
        "pandas_version": pd.__version__,
        "soundfile_version": sf.__version__,
        "gpu_devices_detected": [str(g) for g in gpus],
        "tensorflow_built_with_cuda": tf.test.is_built_with_cuda(),
        "gpu_note": (
            "No GPU detected by TensorFlow. Note that TensorFlow >= 2.11 "
            "does not support GPU acceleration on native Windows at all "
            "(CUDA or otherwise) without WSL2 or the separate "
            "tensorflow-directml-plugin; the machine's AMD Radeon RX 6700 XT "
            "is also not CUDA-capable, so standard GPU acceleration is not "
            "available on this machine as configured."
        ),
    }
    return info


# --------------------------------------------------------------------------
# Audio helpers
# --------------------------------------------------------------------------

def probe_audio(path: Path) -> dict:
    info = sf.info(str(path))
    size_bytes = os.path.getsize(path)
    return {
        "path": str(path),
        "format": info.format,
        "subtype": info.subtype,
        "sample_rate": info.samplerate,
        "channels": info.channels,
        "frames": info.frames,
        "duration_seconds": info.frames / info.samplerate,
        "size_bytes": size_bytes,
        "size_gb": round(size_bytes / (1024 ** 3), 3),
    }


def extract_excerpt(
    source_path: Path,
    offset_seconds: float,
    duration_seconds: float,
    out_path: Path,
) -> dict:
    """Partial-read a slice of the (very large) source recording and cache
    it locally as a small mono WAV. Uses soundfile's frame-range read, which
    seeks rather than loading the whole multi-GB source file."""
    timing = {}
    if out_path.exists():
        timing["excerpt_extraction_seconds"] = 0.0
        timing["excerpt_reused_from_cache"] = True
        return timing

    out_path.parent.mkdir(parents=True, exist_ok=True)
    info = sf.info(str(source_path))
    start_frame = int(round(offset_seconds * info.samplerate))
    n_frames = int(round(duration_seconds * info.samplerate))
    if start_frame + n_frames > info.frames:
        raise ValueError(
            f"Requested excerpt [{offset_seconds}s, "
            f"{offset_seconds + duration_seconds}s) exceeds source duration "
            f"({info.frames / info.samplerate:.1f}s) for {source_path}"
        )

    t0 = time.perf_counter()
    data, sr = sf.read(
        str(source_path),
        start=start_frame,
        frames=n_frames,
        dtype="int16",
        always_2d=False,
    )
    sf.write(str(out_path), data, sr, subtype="PCM_16")
    timing["excerpt_extraction_seconds"] = time.perf_counter() - t0
    timing["excerpt_reused_from_cache"] = False
    return timing


def load_mono_float(path: Path, start_s: float = 0.0, duration_s: float | None = None):
    """Read audio (downmixing to mono if needed) as float32 in [-1, 1]."""
    info = sf.info(str(path))
    start_frame = int(round(start_s * info.samplerate))
    n_frames = int(round(duration_s * info.samplerate)) if duration_s is not None else -1
    data, sr = sf.read(
        str(path),
        start=start_frame,
        frames=n_frames if n_frames > 0 else info.frames - start_frame,
        dtype="float32",
        always_2d=True,
    )
    if data.shape[1] > 1:
        data = data.mean(axis=1)
    else:
        data = data[:, 0]
    return data, sr


def resample_to_16k(waveform: np.ndarray, orig_sr: int) -> np.ndarray:
    if orig_sr == YAMNET_SAMPLE_RATE:
        return waveform
    from math import gcd

    g = gcd(orig_sr, YAMNET_SAMPLE_RATE)
    up = YAMNET_SAMPLE_RATE // g
    down = orig_sr // g
    return resample_poly(waveform, up, down).astype(np.float32)


# --------------------------------------------------------------------------
# YAMNet
# --------------------------------------------------------------------------

def load_yamnet(tfhub_cache_dir: Path):
    tfhub_cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("TFHUB_CACHE_DIR", str(tfhub_cache_dir))

    already_cached = any(tfhub_cache_dir.rglob("*"))

    import tensorflow_hub as hub

    t0 = time.perf_counter()
    model = hub.load(YAMNET_HUB_URL)
    load_seconds = time.perf_counter() - t0

    class_map_path = model.class_map_path().numpy().decode("utf-8")
    class_names = []
    with open(class_map_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            class_names.append(row["display_name"])

    return model, class_names, load_seconds, already_cached


def relevant_class_indices(
    class_names: list[str],
    direct_class_name: str = DIRECT_CLASS_NAME,
    supporting_keywords: list[str] | None = None,
) -> dict[str, list[int]]:
    """Locate the exact target AudioSet class plus any "supporting" classes
    whose name contains one of the given keywords. Generalised beyond
    motorcycle detection — pass a different `direct_class_name` (must match
    an entry in YAMNet's class map exactly, case-insensitive) and your own
    `supporting_keywords` list for any other target sound. `supporting_keywords`
    defaults to the built-in vehicle/engine list only when detecting the
    default "Motorcycle" target; for any other target it defaults to none
    (no supporting classes) unless you supply your own list."""
    if supporting_keywords is None:
        supporting_keywords = (
            RELEVANT_KEYWORDS if direct_class_name.strip().lower() == DIRECT_CLASS_NAME.lower() else []
        )
    direct_lower = direct_class_name.strip().lower()
    direct_idx = [i for i, n in enumerate(class_names) if n.strip().lower() == direct_lower]
    supporting_idx = []
    for i, n in enumerate(class_names):
        nl = n.strip().lower()
        if nl == direct_lower:
            continue
        if any(k.strip().lower() in nl for k in supporting_keywords):
            supporting_idx.append(i)
    return {"direct": direct_idx, "supporting": supporting_idx}


# --------------------------------------------------------------------------
# Chunked inference pipeline (one benchmark "row")
# --------------------------------------------------------------------------

@dataclass
class PipelineResult:
    audio_read_seconds: float
    resample_seconds: float
    inference_seconds: float
    postprocessing_seconds: float
    total_seconds: float
    audio_seconds_processed: float
    n_chunks: int
    frame_df: pd.DataFrame = field(repr=False)


def run_pipeline(
    excerpt_path: Path,
    test_window_seconds: float,
    chunk_duration_seconds: float,
    overlap_seconds: float,
    model,
    class_indices: dict[str, list[int]],
    class_names: list[str],
) -> PipelineResult:
    # --- audio read (fresh disk read every run, for honest per-run timing) ---
    t0 = time.perf_counter()
    waveform, orig_sr = load_mono_float(excerpt_path, 0.0, test_window_seconds)
    audio_read_seconds = time.perf_counter() - t0

    # --- resample whole window once ---
    t0 = time.perf_counter()
    waveform_16k = resample_to_16k(waveform, orig_sr)
    resample_seconds = time.perf_counter() - t0

    # --- chunk + infer ---
    chunk_samples = int(round(chunk_duration_seconds * YAMNET_SAMPLE_RATE))
    overlap_samples = int(round(overlap_seconds * YAMNET_SAMPLE_RATE))
    step_samples = max(chunk_samples - overlap_samples, 1)

    total_samples = len(waveform_16k)
    all_relevant_idx = sorted(set(class_indices["direct"]) | set(class_indices["supporting"]))

    rows = []
    inference_seconds = 0.0
    n_chunks = 0
    start = 0
    while start < total_samples:
        end = min(start + chunk_samples, total_samples)
        chunk = waveform_16k[start:end]
        chunk_offset_s = start / YAMNET_SAMPLE_RATE

        t0 = time.perf_counter()
        scores, _embeddings, _log_mel = model(chunk)
        scores_np = scores.numpy()
        inference_seconds += time.perf_counter() - t0
        n_chunks += 1

        for frame_i in range(scores_np.shape[0]):
            frame_time = chunk_offset_s + frame_i * YAMNET_FRAME_HOP_SECONDS
            row = {"frame_time": round(frame_time, 3), "chunk_index": n_chunks - 1}
            for idx in all_relevant_idx:
                row[class_names[idx]] = float(scores_np[frame_i, idx])
            rows.append(row)

        if end >= total_samples:
            break
        start += step_samples

    # --- postprocessing: assemble frame dataframe, dedupe overlap ---
    t0 = time.perf_counter()
    frame_df = pd.DataFrame(rows)
    if not frame_df.empty:
        frame_df = (
            frame_df.sort_values(["frame_time", "chunk_index"])
            .drop_duplicates(subset="frame_time", keep="first")
            .reset_index(drop=True)
        )
    postprocessing_seconds = time.perf_counter() - t0

    total_seconds = (
        audio_read_seconds + resample_seconds + inference_seconds + postprocessing_seconds
    )

    return PipelineResult(
        audio_read_seconds=audio_read_seconds,
        resample_seconds=resample_seconds,
        inference_seconds=inference_seconds,
        postprocessing_seconds=postprocessing_seconds,
        total_seconds=total_seconds,
        audio_seconds_processed=test_window_seconds,
        n_chunks=n_chunks,
        frame_df=frame_df,
    )


def count_candidates(frame_df: pd.DataFrame, threshold: float) -> tuple[int, int]:
    if frame_df.empty or DIRECT_CLASS_NAME not in frame_df.columns:
        return 0, 0
    positive = frame_df[frame_df[DIRECT_CLASS_NAME] >= threshold]
    n_frames = len(positive)
    events = merge_events(frame_df, DIRECT_CLASS_NAME, threshold, gap_seconds=1.5)
    return n_frames, len(events)


# --------------------------------------------------------------------------
# Event merging (threshold sweep re-uses saved scores, no re-inference)
# --------------------------------------------------------------------------

def merge_events(
    frame_df: pd.DataFrame,
    score_column: str,
    threshold: float,
    gap_seconds: float = 1.5,
    support_columns: list[str] | None = None,
) -> list[dict]:
    if frame_df.empty or score_column not in frame_df.columns:
        return []

    df = frame_df.sort_values("frame_time").reset_index(drop=True)
    positive = df[df[score_column] >= threshold]
    if positive.empty:
        return []

    events = []
    cur_start = None
    cur_end = None
    cur_scores = []
    cur_rows = []

    def flush():
        if cur_start is None:
            return
        peak = max(cur_scores)
        mean = sum(cur_scores) / len(cur_scores)
        sub = pd.DataFrame(cur_rows)
        top_classes = []
        if support_columns:
            means = sub[support_columns + [score_column]].mean().sort_values(ascending=False)
            top_classes = list(means.index[:3])
        events.append(
            {
                "start_time": cur_start,
                "end_time": cur_end,
                "duration_seconds": round(cur_end - cur_start, 3),
                "peak_score": round(peak, 4),
                "mean_score": round(mean, 4),
                "n_frames": len(cur_scores),
                "top_classes": ", ".join(top_classes) if top_classes else "",
            }
        )

    for _, row in positive.iterrows():
        t = row["frame_time"]
        if cur_start is None:
            cur_start, cur_end = t, t + YAMNET_FRAME_HOP_SECONDS
            cur_scores = [row[score_column]]
            cur_rows = [row.to_dict()]
            continue
        if t - cur_end <= gap_seconds:
            cur_end = t + YAMNET_FRAME_HOP_SECONDS
            cur_scores.append(row[score_column])
            cur_rows.append(row.to_dict())
        else:
            flush()
            cur_start, cur_end = t, t + YAMNET_FRAME_HOP_SECONDS
            cur_scores = [row[score_column]]
            cur_rows = [row.to_dict()]
    flush()
    return events


# --------------------------------------------------------------------------
# Review clip export
# --------------------------------------------------------------------------

def write_review_clips(
    excerpt_path: Path,
    events: list[dict],
    out_dir: Path,
    pad_seconds: float = 3.0,
    max_clips: int = 10,
    label_prefix: str = "6461_R14",
    excerpt_start_wallclock: str = "",
):
    out_dir.mkdir(parents=True, exist_ok=True)
    info = sf.info(str(excerpt_path))
    total_duration = info.frames / info.samplerate

    ranked = sorted(events, key=lambda e: e["peak_score"], reverse=True)[:max_clips]
    written = []
    for ev in ranked:
        start = max(0.0, ev["start_time"] - pad_seconds)
        end = min(total_duration, ev["end_time"] + pad_seconds)
        start_frame = int(round(start * info.samplerate))
        n_frames = int(round((end - start) * info.samplerate))
        data, sr = sf.read(str(excerpt_path), start=start_frame, frames=n_frames, dtype="int16")
        fname = (
            f"{label_prefix}_t{ev['start_time']:.1f}s_score{ev['peak_score']:.2f}.wav"
        )
        out_path = out_dir / fname
        sf.write(str(out_path), data, sr, subtype="PCM_16")
        written.append(
            {
                "clip_file": fname,
                "excerpt_offset_start_s": start,
                "excerpt_offset_end_s": end,
                "excerpt_wallclock_reference": excerpt_start_wallclock,
                "peak_score": ev["peak_score"],
                "mean_score": ev["mean_score"],
                "top_classes": ev.get("top_classes", ""),
            }
        )
    return written


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-audio", type=Path, default=Path(DEFAULT_SOURCE_AUDIO))
    parser.add_argument("--offset-seconds", type=float, default=DEFAULT_OFFSET_SECONDS)
    parser.add_argument("--excerpt-seconds", type=float, default=DEFAULT_EXCERPT_SECONDS)
    parser.add_argument("--test-window-seconds", type=float, default=DEFAULT_TEST_WINDOW_SECONDS)
    parser.add_argument(
        "--chunk-durations",
        type=str,
        default="30,120,300,600",
        help="Comma-separated chunk durations in seconds to benchmark.",
    )
    parser.add_argument("--overlap-seconds", type=float, default=1.0)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument(
        "--thresholds",
        type=str,
        default="0.05,0.10,0.20,0.30,0.50",
    )
    parser.add_argument("--gap-seconds", type=float, default=1.5)
    parser.add_argument("--max-clips", type=int, default=10)
    parser.add_argument("--extend-60min", action="store_true")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--tfhub-cache-dir", type=Path, default=DEFAULT_TFHUB_CACHE)
    args = parser.parse_args()

    args.results_dir.mkdir(parents=True, exist_ok=True)
    (args.results_dir / "clips").mkdir(parents=True, exist_ok=True)

    mem = MemorySampler()
    mem.start()
    script_t0 = time.perf_counter()

    print("=" * 70)
    print("YAMNet local benchmark — job 6461 (Bath Road, Bridgwater)")
    print("=" * 70)

    # 1. System info -------------------------------------------------------
    sys_info = gather_system_info()
    with open(args.results_dir / "system_info.json", "w") as f:
        json.dump(sys_info, f, indent=2)
    for k, v in sys_info.items():
        print(f"  {k}: {v}")

    # source audio probe
    print("\nProbing source audio ...")
    src_info = probe_audio(args.source_audio)
    with open(args.results_dir / "source_audio_info.json", "w") as f:
        json.dump(src_info, f, indent=2)
    for k, v in src_info.items():
        print(f"  {k}: {v}")

    # 2. Excerpt extraction (cached) ----------------------------------------
    excerpt_path = args.data_dir / (
        f"6461_R14_excerpt_off{int(args.offset_seconds)}s_"
        f"dur{int(args.excerpt_seconds)}s.wav"
    )
    print(f"\nExtracting/using cached excerpt: {excerpt_path}")
    extraction_timing = extract_excerpt(
        args.source_audio, args.offset_seconds, args.excerpt_seconds, excerpt_path
    )
    print(f"  {extraction_timing}")

    # 3. Load YAMNet + warm-up ----------------------------------------------
    print("\nLoading YAMNet from TensorFlow Hub ...")
    model, class_names, model_load_seconds, already_cached = load_yamnet(args.tfhub_cache_dir)
    print(f"  model_load_seconds: {model_load_seconds:.3f} (already cached: {already_cached})")

    class_indices = relevant_class_indices(class_names)
    print(f"  direct 'Motorcycle' class index: {class_indices['direct']}")
    print(f"  supporting class count: {len(class_indices['supporting'])}")
    supporting_names = [class_names[i] for i in class_indices["supporting"]]
    print(f"  supporting classes: {supporting_names}")

    print("\nRunning warm-up inference (graph tracing, excluded from timings) ...")
    dummy = np.zeros(int(2 * YAMNET_SAMPLE_RATE), dtype=np.float32)
    t0 = time.perf_counter()
    _ = model(dummy)
    warmup_seconds = time.perf_counter() - t0
    print(f"  cold_start_warmup_inference_seconds: {warmup_seconds:.3f}")

    cold_start_total = model_load_seconds + warmup_seconds
    print(f"  cold_start_total_seconds (load + warm-up): {cold_start_total:.3f}")

    # 4. Chunk-duration benchmark matrix -------------------------------------
    chunk_durations = [float(x) for x in args.chunk_durations.split(",") if x.strip()]
    thresholds = [float(x) for x in args.thresholds.split(",") if x.strip()]

    print(f"\nBenchmarking chunk durations {chunk_durations} "
          f"over a {args.test_window_seconds:.0f}s test window, "
          f"{args.repeats} repeats each ...")

    benchmark_rows = []
    frame_dfs_by_duration: dict[float, pd.DataFrame] = {}

    src_probe = probe_audio(args.source_audio)

    for chunk_duration in chunk_durations:
        for run_number in range(1, args.repeats + 1):
            run_t0 = time.time()
            result = run_pipeline(
                excerpt_path,
                args.test_window_seconds,
                chunk_duration,
                args.overlap_seconds,
                model,
                class_indices,
                class_names,
            )
            run_t1 = time.time()
            peak_mem = mem.peak_between(run_t0, run_t1)

            n_frames_candidates, n_events = count_candidates(result.frame_df, threshold=0.20)
            realtime_factor = (
                result.audio_seconds_processed / result.total_seconds
                if result.total_seconds > 0
                else float("nan")
            )

            row = {
                "source_file": str(excerpt_path.name),
                "source_duration_tested": args.test_window_seconds,
                "original_sample_rate": src_probe["sample_rate"],
                "original_channels": src_probe["channels"],
                "chunk_duration": chunk_duration,
                "run_number": run_number,
                "audio_read_seconds": round(result.audio_read_seconds, 4),
                "resample_seconds": round(result.resample_seconds, 4),
                "inference_seconds": round(result.inference_seconds, 4),
                "postprocessing_seconds": round(result.postprocessing_seconds, 4),
                "total_seconds": round(result.total_seconds, 4),
                "realtime_factor": round(realtime_factor, 2),
                "audio_seconds_processed_per_second": round(realtime_factor, 2),
                "approximate_peak_memory_mb": round(peak_mem, 1),
                "number_of_motorcycle_candidate_frames": n_frames_candidates,
                "number_of_merged_motorcycle_events": n_events,
                "n_chunks": result.n_chunks,
            }
            benchmark_rows.append(row)
            print(
                f"  chunk={chunk_duration:>6.0f}s run={run_number} "
                f"total={result.total_seconds:6.2f}s "
                f"realtime_factor={realtime_factor:6.1f}x "
                f"peak_mem={peak_mem:7.1f}MB "
                f"events={n_events}"
            )

            # keep the last run's frame_df per duration for later analysis
            frame_dfs_by_duration[chunk_duration] = result.frame_df

    benchmark_df = pd.DataFrame(benchmark_rows)
    benchmark_df.to_csv(args.results_dir / "benchmark_timings.csv", index=False)
    print(f"\nWrote {args.results_dir / 'benchmark_timings.csv'}")

    # median total_seconds per chunk duration -> pick best
    medians = benchmark_df.groupby("chunk_duration")["total_seconds"].median()
    best_chunk_duration = medians.idxmin()
    print(f"\nBest-performing chunk duration by median total time: {best_chunk_duration}s")
    print(medians)

    # optional extended 60-min run at the best chunk duration (single run, not repeated)
    extended_row = None
    if args.extend_60min and args.excerpt_seconds >= 3600:
        print(f"\nRunning extended 60-minute test at chunk_duration={best_chunk_duration}s ...")
        run_t0 = time.time()
        ext_result = run_pipeline(
            excerpt_path, 3600.0, best_chunk_duration, args.overlap_seconds,
            model, class_indices, class_names,
        )
        run_t1 = time.time()
        peak_mem = mem.peak_between(run_t0, run_t1)
        realtime_factor = ext_result.audio_seconds_processed / ext_result.total_seconds
        n_frames_candidates, n_events = count_candidates(ext_result.frame_df, threshold=0.20)
        extended_row = {
            "source_file": str(excerpt_path.name),
            "source_duration_tested": 3600.0,
            "original_sample_rate": src_probe["sample_rate"],
            "original_channels": src_probe["channels"],
            "chunk_duration": best_chunk_duration,
            "run_number": "extended_60min",
            "audio_read_seconds": round(ext_result.audio_read_seconds, 4),
            "resample_seconds": round(ext_result.resample_seconds, 4),
            "inference_seconds": round(ext_result.inference_seconds, 4),
            "postprocessing_seconds": round(ext_result.postprocessing_seconds, 4),
            "total_seconds": round(ext_result.total_seconds, 4),
            "realtime_factor": round(realtime_factor, 2),
            "audio_seconds_processed_per_second": round(realtime_factor, 2),
            "approximate_peak_memory_mb": round(peak_mem, 1),
            "number_of_motorcycle_candidate_frames": n_frames_candidates,
            "number_of_merged_motorcycle_events": n_events,
            "n_chunks": ext_result.n_chunks,
        }
        pd.DataFrame([extended_row]).to_csv(
            args.results_dir / "benchmark_timings_extended_60min.csv", index=False
        )
        frame_dfs_by_duration[("extended", best_chunk_duration)] = ext_result.frame_df
        print(f"  extended run: total={ext_result.total_seconds:.2f}s "
              f"realtime_factor={realtime_factor:.1f}x")

    # 5. Frame-level detail pass at the best chunk duration ------------------
    best_frame_df = frame_dfs_by_duration.get(("extended", best_chunk_duration))
    if best_frame_df is None:
        best_frame_df = frame_dfs_by_duration[best_chunk_duration]
    best_frame_df.to_parquet(args.results_dir / "frame_scores_best_chunk.parquet", index=False)
    best_frame_df.to_csv(args.results_dir / "frame_scores_best_chunk.csv", index=False)
    print(f"\nWrote frame-level scores ({len(best_frame_df)} frames) at "
          f"chunk_duration={best_chunk_duration}s")

    # 6. Threshold sweep (re-uses saved scores, no re-inference) -------------
    supporting_names = [class_names[i] for i in class_indices["supporting"]
                        if class_names[i] in best_frame_df.columns]
    sweep_rows = []
    events_by_threshold = {}
    for th in thresholds:
        direct_events = merge_events(
            best_frame_df, DIRECT_CLASS_NAME, th, args.gap_seconds, supporting_names
        )
        n_direct_frames = int((best_frame_df[DIRECT_CLASS_NAME] >= th).sum()) \
            if DIRECT_CLASS_NAME in best_frame_df.columns else 0
        events_by_threshold[th] = direct_events
        sweep_rows.append({
            "threshold": th,
            "n_direct_motorcycle_frames": n_direct_frames,
            "n_direct_motorcycle_events": len(direct_events),
        })
    pd.DataFrame(sweep_rows).to_csv(args.results_dir / "threshold_sweep.csv", index=False)
    print("\nThreshold sweep (direct 'Motorcycle' class):")
    for r in sweep_rows:
        print(f"  threshold={r['threshold']:.2f}  "
              f"frames={r['n_direct_motorcycle_frames']}  "
              f"events={r['n_direct_motorcycle_events']}")

    # supporting-vehicle candidates (engine/revving/etc.) at a fixed screening threshold,
    # excluding periods already covered by a direct motorcycle event at that threshold
    support_threshold = 0.20
    support_events_all = []
    for name in supporting_names:
        support_events_all.extend(
            [{**e, "class": name} for e in merge_events(best_frame_df, name, support_threshold, args.gap_seconds)]
        )
    direct_ranges = [(e["start_time"], e["end_time"]) for e in events_by_threshold.get(support_threshold, [])]

    def overlaps_direct(ev):
        return any(not (ev["end_time"] < s or ev["start_time"] > e) for s, e in direct_ranges)

    supporting_only = [e for e in support_events_all if not overlaps_direct(e)]
    pd.DataFrame(supporting_only).to_csv(
        args.results_dir / "supporting_vehicle_candidates.csv", index=False
    )
    print(f"\nSupporting vehicle candidates (no direct motorcycle overlap) "
          f"at threshold={support_threshold}: {len(supporting_only)}")

    # export the merged direct-motorcycle events at the primary reporting threshold
    primary_threshold = 0.20
    primary_events = events_by_threshold[primary_threshold]
    pd.DataFrame(primary_events).to_csv(
        args.results_dir / f"motorcycle_events_threshold_{primary_threshold}.csv", index=False
    )

    # 7. Review clips ---------------------------------------------------------
    clip_source_events = primary_events
    if not clip_source_events:
        # no convincing detections at the primary threshold: fall back to the
        # lowest threshold's events so the model's behaviour can still be reviewed
        lowest_th = min(thresholds)
        clip_source_events = events_by_threshold[lowest_th]
        print(f"\nNo events at threshold={primary_threshold}; falling back to "
              f"threshold={lowest_th} for review clips ({len(clip_source_events)} events).")

    from datetime import datetime, timedelta
    survey_start = datetime(2026, 6, 30, 13, 30, 0)
    excerpt_wallclock_start = survey_start + timedelta(seconds=args.offset_seconds)

    written_clips = write_review_clips(
        excerpt_path,
        clip_source_events,
        args.results_dir / "clips",
        pad_seconds=3.0,
        max_clips=args.max_clips,
        label_prefix="6461_R14",
        excerpt_start_wallclock=excerpt_wallclock_start.isoformat(),
    )
    pd.DataFrame(written_clips).to_csv(args.results_dir / "clips_manifest.csv", index=False)
    print(f"\nWrote {len(written_clips)} review clips to {args.results_dir / 'clips'}")

    # 8. Processing-time projections (steady state, best chunk duration) ------
    # medians.min() is the *fastest median total_seconds* (for the test window);
    # the realtime factor is audio-seconds-processed divided by that time.
    best_median_total_seconds = medians.min()
    steady_state_realtime_factor = args.test_window_seconds / best_median_total_seconds
    steady_state_seconds_per_hour_audio = 3600.0 / steady_state_realtime_factor
    projections = {}
    for label, hours in [("1_hour", 1), ("8_hours", 8), ("24_hours", 24), ("7_days", 24 * 7)]:
        projections[label] = round(steady_state_seconds_per_hour_audio * hours, 1)
    projections["_note"] = (
        "Projections use the measured steady-state realtime_factor for the "
        "best-performing chunk duration and EXCLUDE the one-off model "
        "download and the one-off model load / warm-up "
        f"(model_load_seconds={model_load_seconds:.3f}, "
        f"warmup_seconds={warmup_seconds:.3f}, both incurred once per process)."
    )
    projections["steady_state_realtime_factor"] = round(steady_state_realtime_factor, 2)
    projections["best_chunk_duration_seconds"] = float(best_chunk_duration)
    with open(args.results_dir / "processing_time_projections.json", "w") as f:
        json.dump(projections, f, indent=2)
    print("\nProcessing time projections (steady state, excl. one-off model load):")
    for k, v in projections.items():
        print(f"  {k}: {v}")

    mem.stop()
    script_total = time.perf_counter() - script_t0
    print(f"\nTotal benchmark script wall time: {script_total:.1f}s")
    print(f"Approximate overall peak memory: {mem.peak_overall():.1f} MB")
    print(f"\nAll outputs saved under: {args.results_dir}")


if __name__ == "__main__":
    main()
