"""
PANNs (Cnn14_DecisionLevelMax) local-processing benchmark — proof of concept,
mirrors tools/yamnet_benchmark/benchmark_yamnet.py for a like-for-like
comparison against YAMNet on the same job 6461 audio excerpt.

Standalone, self-contained. Does NOT modify the dashboard. Run inside the
isolated `.venv-panns-benchmark` environment (see README.md).

Reuses the same cached 60-minute excerpt produced by the YAMNet benchmark
(tools/yamnet_benchmark/data/...) rather than re-extracting from the
multi-gigabyte source file a second time — same audio, so timings and
detections are directly comparable.

PANNs specifics vs. the YAMNet version:
  - Sample rate: 32,000 Hz (not 16,000) — resampled 12 kHz -> 32 kHz exactly
    (8:3 polyphase ratio).
  - Model: Cnn14_DecisionLevelMax via `panns_inference.SoundEventDetection`,
    which gives framewise (not just clip-level) scores across 527 AudioSet
    classes — the same taxonomy YAMNet uses, so "Motorcycle" and the
    supporting vehicle/engine classes map directly across both benchmarks.
  - Frame hop is measured empirically from the model's own output shape
    (found to be ~10 ms / ~100 Hz here — much finer than YAMNet's fixed
    0.48 s hop), rather than assumed.
  - `panns_inference`'s own checkpoint auto-download shells out to `wget`,
    which isn't available on Windows by default — this script downloads the
    checkpoint itself (stdlib `urllib`, no extra dependency) and passes an
    explicit `checkpoint_path`, timing the download the same way the YAMNet
    benchmark timed the TF-Hub download.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import psutil
import soundfile as sf
from scipy.signal import resample_poly

PANNS_SAMPLE_RATE = 32000
CHECKPOINT_URL = (
    "https://zenodo.org/record/3987831/files/"
    "Cnn14_DecisionLevelMax_mAP%3D0.385.pth?download=1"
)
CHECKPOINT_MIN_BYTES = 3 * 10 ** 8  # panns_inference's own "is this a real file" check

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_RESULTS_DIR = SCRIPT_DIR / "results"
DEFAULT_CHECKPOINT_PATH = Path.home() / "panns_data" / "Cnn14_DecisionLevelMax.pth"

# Reuse the exact excerpt already extracted for the YAMNet benchmark —
# same audio, so the two benchmarks are directly comparable.
YAMNET_BENCHMARK_DATA_DIR = SCRIPT_DIR.parent / "yamnet_benchmark" / "data"
DEFAULT_EXCERPT_PATH = (
    YAMNET_BENCHMARK_DATA_DIR / "6461_R14_excerpt_off66600s_dur3600s.wav"
)
DEFAULT_TEST_WINDOW_SECONDS = 1800  # 30 min, matching the YAMNet matrix

RELEVANT_KEYWORDS = [
    "motorcycle", "moped", "vehicle", "engine", "accelerat", "revving",
    "vroom", "traffic", "road", "car", "truck", "bus", "skidding",
    "tire squeal", "race car",
]
DIRECT_CLASS_NAME = "Motorcycle"


class MemorySampler:
    def __init__(self, interval_s: float = 0.05):
        self._interval = interval_s
        self._proc = psutil.Process(os.getpid())
        self._samples: list[tuple[float, float]] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()

    def _run(self):
        while not self._stop.is_set():
            self._samples.append((time.time(), self._proc.memory_info().rss / (1024 * 1024)))
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


def gather_system_info() -> dict:
    import torch

    return {
        "os": platform.platform(),
        "python_version": sys.version,
        "cpu_processor": platform.processor(),
        "cpu_logical_cores": psutil.cpu_count(logical=True),
        "cpu_physical_cores": psutil.cpu_count(logical=False),
        "total_ram_gb": round(psutil.virtual_memory().total / (1024 ** 3), 1),
        "torch_version": torch.__version__,
        "torch_cuda_available": torch.cuda.is_available(),
        "gpu_note": (
            "torch.cuda.is_available() is False — this venv installed the "
            "CPU-only torch wheel (torch==2.13.0+cpu). The machine's AMD "
            "Radeon RX 6700 XT is not CUDA-capable in any case, matching "
            "the YAMNet benchmark's finding of no usable GPU acceleration "
            "path on this machine."
        ),
    }


def ensure_checkpoint(path: Path, url: str) -> tuple[float, bool]:
    """Download the PANNs checkpoint ourselves (panns_inference's own
    auto-download shells out to `wget`, unavailable on Windows). Returns
    (download_seconds, already_present)."""
    if path.exists() and path.stat().st_size >= CHECKPOINT_MIN_BYTES:
        return 0.0, True
    path.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    urllib.request.urlretrieve(url, str(path))
    return time.perf_counter() - t0, False


def resample_to_32k(waveform: np.ndarray, orig_sr: int) -> np.ndarray:
    if orig_sr == PANNS_SAMPLE_RATE:
        return waveform
    from math import gcd
    g = gcd(orig_sr, PANNS_SAMPLE_RATE)
    up = PANNS_SAMPLE_RATE // g
    down = orig_sr // g
    return resample_poly(waveform, up, down).astype(np.float32)


def load_mono_float(path: Path, start_s: float, duration_s: float):
    info = sf.info(str(path))
    start_frame = int(round(start_s * info.samplerate))
    n_frames = int(round(duration_s * info.samplerate))
    data, sr = sf.read(str(path), start=start_frame, frames=n_frames, dtype="float32", always_2d=True)
    if data.shape[1] > 1:
        data = data.mean(axis=1)
    else:
        data = data[:, 0]
    return data, sr


def relevant_class_indices(labels: list[str]) -> dict[str, list[int]]:
    direct = [i for i, n in enumerate(labels) if n.strip().lower() == DIRECT_CLASS_NAME.lower()]
    supporting = []
    for i, n in enumerate(labels):
        nl = n.strip().lower()
        if nl == DIRECT_CLASS_NAME.lower():
            continue
        if any(k in nl for k in RELEVANT_KEYWORDS):
            supporting.append(i)
    return {"direct": direct, "supporting": supporting}


@dataclass
class PipelineResult:
    audio_read_seconds: float
    resample_seconds: float
    inference_seconds: float
    postprocessing_seconds: float
    total_seconds: float
    audio_seconds_processed: float
    n_chunks: int
    frame_hop_seconds: float
    frame_df: pd.DataFrame = field(repr=False)


def run_pipeline(
    excerpt_path: Path,
    test_window_seconds: float,
    chunk_duration_seconds: float,
    overlap_seconds: float,
    sed_model,
    labels: list[str],
    class_indices: dict[str, list[int]],
) -> PipelineResult:
    import torch

    t0 = time.perf_counter()
    waveform, orig_sr = load_mono_float(excerpt_path, 0.0, test_window_seconds)
    audio_read_seconds = time.perf_counter() - t0

    t0 = time.perf_counter()
    waveform_32k = resample_to_32k(waveform, orig_sr)
    resample_seconds = time.perf_counter() - t0

    chunk_samples = int(round(chunk_duration_seconds * PANNS_SAMPLE_RATE))
    overlap_samples = int(round(overlap_seconds * PANNS_SAMPLE_RATE))
    step_samples = max(chunk_samples - overlap_samples, 1)
    total_samples = len(waveform_32k)
    all_relevant_idx = sorted(set(class_indices["direct"]) | set(class_indices["supporting"]))

    rows = []
    inference_seconds = 0.0
    n_chunks = 0
    frame_hop_seconds = None
    start = 0
    with torch.no_grad():
        while start < total_samples:
            end = min(start + chunk_samples, total_samples)
            chunk = waveform_32k[start:end]
            chunk_offset_s = start / PANNS_SAMPLE_RATE
            chunk_duration_actual = len(chunk) / PANNS_SAMPLE_RATE

            t0 = time.perf_counter()
            framewise_output = sed_model.inference(chunk[None, :])
            inference_seconds += time.perf_counter() - t0
            n_chunks += 1

            scores_np = framewise_output[0]  # (frames_num, classes_num)
            n_frames = scores_np.shape[0]
            if frame_hop_seconds is None and n_frames > 1:
                frame_hop_seconds = chunk_duration_actual / n_frames

            hop = frame_hop_seconds or (chunk_duration_actual / max(n_frames, 1))
            for frame_i in range(n_frames):
                frame_time = chunk_offset_s + frame_i * hop
                row = {"frame_time": round(frame_time, 3), "chunk_index": n_chunks - 1}
                for idx in all_relevant_idx:
                    row[labels[idx]] = float(scores_np[frame_i, idx])
                rows.append(row)

            if end >= total_samples:
                break
            start += step_samples

    t0 = time.perf_counter()
    frame_df = pd.DataFrame(rows)
    if not frame_df.empty:
        frame_df = (
            frame_df.sort_values(["frame_time", "chunk_index"])
            .drop_duplicates(subset="frame_time", keep="first")
            .reset_index(drop=True)
        )
    postprocessing_seconds = time.perf_counter() - t0

    total_seconds = audio_read_seconds + resample_seconds + inference_seconds + postprocessing_seconds

    return PipelineResult(
        audio_read_seconds=audio_read_seconds,
        resample_seconds=resample_seconds,
        inference_seconds=inference_seconds,
        postprocessing_seconds=postprocessing_seconds,
        total_seconds=total_seconds,
        audio_seconds_processed=test_window_seconds,
        n_chunks=n_chunks,
        frame_hop_seconds=frame_hop_seconds or float("nan"),
        frame_df=frame_df,
    )


def merge_events(frame_df, score_column, threshold, gap_seconds=1.5, support_columns=None):
    if frame_df.empty or score_column not in frame_df.columns:
        return []
    df = frame_df.sort_values("frame_time").reset_index(drop=True)
    positive = df[df[score_column] >= threshold]
    if positive.empty:
        return []

    events = []
    cur_start = cur_end = None
    cur_scores, cur_rows = [], []

    def flush():
        if cur_start is None:
            return
        peak = max(cur_scores)
        mean = sum(cur_scores) / len(cur_scores)
        top_classes = []
        if support_columns:
            sub = pd.DataFrame(cur_rows)
            means = sub[support_columns + [score_column]].mean().sort_values(ascending=False)
            top_classes = list(means.index[:3])
        events.append({
            "start_time": cur_start, "end_time": cur_end,
            "duration_seconds": round(cur_end - cur_start, 3),
            "peak_score": round(peak, 4), "mean_score": round(mean, 4),
            "n_frames": len(cur_scores),
            "top_classes": ", ".join(top_classes) if top_classes else "",
        })

    hop_estimate = None
    times = positive["frame_time"].tolist()
    if len(times) > 1:
        diffs = np.diff(sorted(df["frame_time"].tolist()))
        hop_estimate = float(np.median(diffs)) if len(diffs) else 0.01
    hop_estimate = hop_estimate or 0.01

    for _, row in positive.iterrows():
        t = row["frame_time"]
        if cur_start is None:
            cur_start, cur_end = t, t + hop_estimate
            cur_scores, cur_rows = [row[score_column]], [row.to_dict()]
            continue
        if t - cur_end <= gap_seconds:
            cur_end = t + hop_estimate
            cur_scores.append(row[score_column])
            cur_rows.append(row.to_dict())
        else:
            flush()
            cur_start, cur_end = t, t + hop_estimate
            cur_scores, cur_rows = [row[score_column]], [row.to_dict()]
    flush()
    return events


def write_review_clips(excerpt_path, events, out_dir, pad_seconds=3.0, max_clips=10, label_prefix="6461_R14_panns"):
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
        fname = f"{label_prefix}_t{ev['start_time']:.1f}s_score{ev['peak_score']:.2f}.wav"
        sf.write(str(out_dir / fname), data, sr, subtype="PCM_16")
        written.append({"clip_file": fname, "peak_score": ev["peak_score"],
                         "mean_score": ev["mean_score"], "top_classes": ev.get("top_classes", "")})
    return written


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--excerpt-path", type=Path, default=DEFAULT_EXCERPT_PATH)
    parser.add_argument("--test-window-seconds", type=float, default=DEFAULT_TEST_WINDOW_SECONDS)
    parser.add_argument("--chunk-durations", type=str, default="30,120,300,600")
    parser.add_argument("--overlap-seconds", type=float, default=1.0)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--thresholds", type=str, default="0.05,0.10,0.20,0.30,0.50")
    parser.add_argument("--gap-seconds", type=float, default=1.5)
    parser.add_argument("--max-clips", type=int, default=10)
    parser.add_argument("--extend-60min", action="store_true")
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--checkpoint-path", type=Path, default=DEFAULT_CHECKPOINT_PATH)
    args = parser.parse_args()

    if not args.excerpt_path.exists():
        raise FileNotFoundError(
            f"Excerpt not found at {args.excerpt_path}. Run the YAMNet "
            f"benchmark first (tools/yamnet_benchmark/benchmark_yamnet.py) "
            f"to produce it, or pass --excerpt-path explicitly."
        )

    args.results_dir.mkdir(parents=True, exist_ok=True)
    (args.results_dir / "clips").mkdir(parents=True, exist_ok=True)

    mem = MemorySampler()
    mem.start()

    print("=" * 70)
    print("PANNs (Cnn14_DecisionLevelMax) local benchmark — job 6461")
    print("=" * 70)

    sys_info = gather_system_info()
    with open(args.results_dir / "system_info.json", "w") as f:
        json.dump(sys_info, f, indent=2)
    for k, v in sys_info.items():
        print(f"  {k}: {v}")

    excerpt_info = sf.info(str(args.excerpt_path))
    print(f"\nUsing shared excerpt: {args.excerpt_path}")
    print(f"  sample_rate={excerpt_info.samplerate}, channels={excerpt_info.channels}, "
          f"duration={excerpt_info.frames / excerpt_info.samplerate:.1f}s")

    print(f"\nEnsuring checkpoint at {args.checkpoint_path} ...")
    download_seconds, already_present = ensure_checkpoint(args.checkpoint_path, CHECKPOINT_URL)
    print(f"  checkpoint_download_seconds: {download_seconds:.2f} (already present: {already_present})")

    print("\nLoading Cnn14_DecisionLevelMax (CPU) ...")
    from panns_inference import SoundEventDetection, config as panns_config
    t0 = time.perf_counter()
    sed_model = SoundEventDetection(checkpoint_path=str(args.checkpoint_path), device="cpu")
    model_load_seconds = time.perf_counter() - t0
    labels = panns_config.labels
    print(f"  model_load_seconds: {model_load_seconds:.3f}")

    class_indices = relevant_class_indices(labels)
    print(f"  direct 'Motorcycle' class index: {class_indices['direct']}")
    print(f"  supporting class count: {len(class_indices['supporting'])}")

    print("\nRunning warm-up inference (excluded from timings) ...")
    dummy = np.zeros(int(2 * PANNS_SAMPLE_RATE), dtype=np.float32)
    t0 = time.perf_counter()
    import torch
    with torch.no_grad():
        _ = sed_model.inference(dummy[None, :])
    warmup_seconds = time.perf_counter() - t0
    print(f"  cold_start_warmup_inference_seconds: {warmup_seconds:.3f}")
    cold_start_total = download_seconds + model_load_seconds + warmup_seconds
    print(f"  cold_start_total_seconds (download + load + warm-up): {cold_start_total:.3f}")

    chunk_durations = [float(x) for x in args.chunk_durations.split(",") if x.strip()]
    thresholds = [float(x) for x in args.thresholds.split(",") if x.strip()]

    print(f"\nBenchmarking chunk durations {chunk_durations} over a "
          f"{args.test_window_seconds:.0f}s window, {args.repeats} repeats each ...")

    benchmark_rows = []
    frame_dfs_by_duration = {}
    measured_frame_hop = None

    for chunk_duration in chunk_durations:
        for run_number in range(1, args.repeats + 1):
            run_t0 = time.time()
            result = run_pipeline(
                args.excerpt_path, args.test_window_seconds, chunk_duration,
                args.overlap_seconds, sed_model, labels, class_indices,
            )
            run_t1 = time.time()
            peak_mem = mem.peak_between(run_t0, run_t1)
            measured_frame_hop = result.frame_hop_seconds

            events_20 = merge_events(result.frame_df, DIRECT_CLASS_NAME, 0.20, args.gap_seconds)
            n_frames_20 = int((result.frame_df[DIRECT_CLASS_NAME] >= 0.20).sum()) \
                if DIRECT_CLASS_NAME in result.frame_df.columns else 0
            realtime_factor = result.audio_seconds_processed / result.total_seconds if result.total_seconds > 0 else float("nan")

            row = {
                "source_file": args.excerpt_path.name,
                "source_duration_tested": args.test_window_seconds,
                "chunk_duration": chunk_duration,
                "run_number": run_number,
                "frame_hop_seconds": round(result.frame_hop_seconds, 4),
                "audio_read_seconds": round(result.audio_read_seconds, 4),
                "resample_seconds": round(result.resample_seconds, 4),
                "inference_seconds": round(result.inference_seconds, 4),
                "postprocessing_seconds": round(result.postprocessing_seconds, 4),
                "total_seconds": round(result.total_seconds, 4),
                "realtime_factor": round(realtime_factor, 2),
                "audio_seconds_processed_per_second": round(realtime_factor, 2),
                "approximate_peak_memory_mb": round(peak_mem, 1),
                "number_of_motorcycle_candidate_frames": n_frames_20,
                "number_of_merged_motorcycle_events": len(events_20),
                "n_chunks": result.n_chunks,
            }
            benchmark_rows.append(row)
            print(f"  chunk={chunk_duration:>6.0f}s run={run_number} "
                  f"total={result.total_seconds:7.2f}s realtime_factor={realtime_factor:6.1f}x "
                  f"peak_mem={peak_mem:7.1f}MB events={len(events_20)}")

            frame_dfs_by_duration[chunk_duration] = result.frame_df

    benchmark_df = pd.DataFrame(benchmark_rows)
    benchmark_df.to_csv(args.results_dir / "benchmark_timings.csv", index=False)
    print(f"\nWrote {args.results_dir / 'benchmark_timings.csv'}")

    medians = benchmark_df.groupby("chunk_duration")["total_seconds"].median()
    best_chunk_duration = medians.idxmin()
    print(f"\nBest-performing chunk duration by median total time: {best_chunk_duration}s")
    print(medians)

    if args.extend_60min:
        excerpt_duration = sf.info(str(args.excerpt_path)).frames / sf.info(str(args.excerpt_path)).samplerate
        ext_window = min(3600.0, excerpt_duration)
        print(f"\nRunning extended {ext_window:.0f}s test at chunk_duration={best_chunk_duration}s ...")
        run_t0 = time.time()
        ext_result = run_pipeline(
            args.excerpt_path, ext_window, best_chunk_duration, args.overlap_seconds,
            sed_model, labels, class_indices,
        )
        run_t1 = time.time()
        peak_mem = mem.peak_between(run_t0, run_t1)
        realtime_factor = ext_result.audio_seconds_processed / ext_result.total_seconds
        events_20 = merge_events(ext_result.frame_df, DIRECT_CLASS_NAME, 0.20, args.gap_seconds)
        n_frames_20 = int((ext_result.frame_df[DIRECT_CLASS_NAME] >= 0.20).sum()) \
            if DIRECT_CLASS_NAME in ext_result.frame_df.columns else 0
        extended_row = {
            "source_file": args.excerpt_path.name, "source_duration_tested": ext_window,
            "chunk_duration": best_chunk_duration, "run_number": "extended",
            "frame_hop_seconds": round(ext_result.frame_hop_seconds, 4),
            "audio_read_seconds": round(ext_result.audio_read_seconds, 4),
            "resample_seconds": round(ext_result.resample_seconds, 4),
            "inference_seconds": round(ext_result.inference_seconds, 4),
            "postprocessing_seconds": round(ext_result.postprocessing_seconds, 4),
            "total_seconds": round(ext_result.total_seconds, 4),
            "realtime_factor": round(realtime_factor, 2),
            "audio_seconds_processed_per_second": round(realtime_factor, 2),
            "approximate_peak_memory_mb": round(peak_mem, 1),
            "number_of_motorcycle_candidate_frames": n_frames_20,
            "number_of_merged_motorcycle_events": len(events_20),
            "n_chunks": ext_result.n_chunks,
        }
        pd.DataFrame([extended_row]).to_csv(args.results_dir / "benchmark_timings_extended.csv", index=False)
        frame_dfs_by_duration[("extended", best_chunk_duration)] = ext_result.frame_df
        print(f"  extended run: total={ext_result.total_seconds:.2f}s realtime_factor={realtime_factor:.1f}x")

    best_frame_df = frame_dfs_by_duration.get(("extended", best_chunk_duration), frame_dfs_by_duration[best_chunk_duration])
    best_frame_df.to_parquet(args.results_dir / "frame_scores_best_chunk.parquet", index=False)
    best_frame_df.to_csv(args.results_dir / "frame_scores_best_chunk.csv", index=False)
    print(f"\nWrote frame-level scores ({len(best_frame_df)} frames, "
          f"hop~{measured_frame_hop:.4f}s) at chunk_duration={best_chunk_duration}s")

    supporting_names = [labels[i] for i in class_indices["supporting"] if labels[i] in best_frame_df.columns]
    sweep_rows = []
    events_by_threshold = {}
    for th in thresholds:
        direct_events = merge_events(best_frame_df, DIRECT_CLASS_NAME, th, args.gap_seconds, supporting_names)
        n_direct_frames = int((best_frame_df[DIRECT_CLASS_NAME] >= th).sum()) if DIRECT_CLASS_NAME in best_frame_df.columns else 0
        events_by_threshold[th] = direct_events
        sweep_rows.append({"threshold": th, "n_direct_motorcycle_frames": n_direct_frames,
                            "n_direct_motorcycle_events": len(direct_events)})
    pd.DataFrame(sweep_rows).to_csv(args.results_dir / "threshold_sweep.csv", index=False)
    print("\nThreshold sweep (direct 'Motorcycle' class):")
    for r in sweep_rows:
        print(f"  threshold={r['threshold']:.2f}  frames={r['n_direct_motorcycle_frames']}  "
              f"events={r['n_direct_motorcycle_events']}")

    primary_threshold = 0.20
    primary_events = events_by_threshold[primary_threshold]
    pd.DataFrame(primary_events).to_csv(
        args.results_dir / f"motorcycle_events_threshold_{primary_threshold}.csv", index=False
    )

    clip_source_events = primary_events
    if not clip_source_events:
        lowest_th = min(thresholds)
        clip_source_events = events_by_threshold[lowest_th]
        print(f"\nNo events at threshold={primary_threshold}; falling back to "
              f"threshold={lowest_th} for review clips ({len(clip_source_events)} events).")

    written_clips = write_review_clips(
        args.excerpt_path, clip_source_events, args.results_dir / "clips",
        pad_seconds=3.0, max_clips=args.max_clips,
    )
    pd.DataFrame(written_clips).to_csv(args.results_dir / "clips_manifest.csv", index=False)
    print(f"\nWrote {len(written_clips)} review clips to {args.results_dir / 'clips'}")

    steady_state_realtime_factor = args.test_window_seconds / medians.min()
    projections = {}
    seconds_per_hour = 3600.0 / steady_state_realtime_factor
    for label, hours in [("1_hour", 1), ("8_hours", 8), ("24_hours", 24), ("7_days", 24 * 7)]:
        projections[label] = round(seconds_per_hour * hours, 1)
    projections["steady_state_realtime_factor"] = round(steady_state_realtime_factor, 2)
    projections["best_chunk_duration_seconds"] = float(best_chunk_duration)
    projections["_note"] = (
        f"Excludes one-off checkpoint download ({download_seconds:.1f}s) and "
        f"one-off model load/warm-up (load={model_load_seconds:.2f}s, "
        f"warmup={warmup_seconds:.2f}s)."
    )
    with open(args.results_dir / "processing_time_projections.json", "w") as f:
        json.dump(projections, f, indent=2)
    print("\nProcessing time projections (steady state, excl. one-off download/load):")
    for k, v in projections.items():
        print(f"  {k}: {v}")

    mem.stop()
    print(f"\nApproximate overall peak memory: {mem.peak_overall():.1f} MB")
    print(f"\nAll outputs saved under: {args.results_dir}")


if __name__ == "__main__":
    main()
