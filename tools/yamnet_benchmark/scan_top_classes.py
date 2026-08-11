"""
Open-set YAMNet scan: report the top-scoring AudioSet classes over a survey
audio window, without requiring a pre-chosen --target-class.

Complements run_full_day_detection.py (which needs you to already know what
you're looking for). Use this first when you don't know what's driving an
elevated period and want a ranked shortlist of candidate sound classes to
then investigate/confirm — by ear, and optionally with a follow-up
run_full_day_detection.py pass for whichever classes look promising.

Does not modify the dashboard or the noise_survey_analysis package. Reuses
model loading / resampling from benchmark_yamnet.py.

Run inside the same isolated .venv-yamnet-benchmark environment used for
run_full_day_detection.py.
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
except ImportError:
    import benchmark_yamnet as bm

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_RESULTS_DIR = SCRIPT_DIR / "results" / "scan"
DEFAULT_TFHUB_CACHE = SCRIPT_DIR / "tfhub_cache"

# AudioSet classes commonly associated with narrowband/tonal, high-frequency,
# or mechanical-plant sounds — flagged separately in the summary since these
# are the usual suspects for a persistent "tone" a human notices but a
# broad-class model may only weakly score.
TONE_LIKE_KEYWORDS = [
    "buzz", "hum", "whine", "whistl", "beep", "bleep", "alarm", "siren",
    "smoke detector", "fire alarm", "ring", "electronic", "static",
    "mechanical fan", "air conditioning", "hvac", "vacuum cleaner",
    "chirp", "tuning fork", "sine wave", "single-tone",
]


def iter_source_chunks(source_path, offset_seconds, duration_seconds, chunk_seconds, overlap_seconds):
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
        data, read_sr = sf.read(str(source_path), start=pos, frames=n, dtype="float32", always_2d=True)
        data = data.mean(axis=1) if data.shape[1] > 1 else data[:, 0]
        chunk_offset_seconds = (pos - start_frame_abs) / sr
        yield data, read_sr, chunk_offset_seconds
        if pos + n >= end_frame_abs:
            break
        pos += step_frames


def local_offset_to_epoch_ms(offset_seconds, survey_start_local, tz_name):
    local_dt = survey_start_local + timedelta(seconds=offset_seconds)
    aware = local_dt.replace(tzinfo=ZoneInfo(tz_name))
    return int(round(aware.astimezone(timezone.utc).timestamp() * 1000))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-audio", type=Path, required=True)
    p.add_argument("--offset-seconds", type=float, required=True)
    p.add_argument("--duration-seconds", type=float, required=True)
    p.add_argument("--chunk-seconds", type=float, default=120.0)
    p.add_argument("--overlap-seconds", type=float, default=1.0)
    p.add_argument("--survey-start-local", type=str, required=True)
    p.add_argument("--timezone", type=str, default="Europe/London")
    p.add_argument("--position-id", type=str, required=True)
    p.add_argument("--top-n", type=int, default=25)
    p.add_argument("--bin-minutes", type=float, default=30.0)
    p.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    p.add_argument("--tfhub-cache-dir", type=Path, default=DEFAULT_TFHUB_CACHE)
    p.add_argument("--label", type=str, default="scan")
    args = p.parse_args()

    args.results_dir.mkdir(parents=True, exist_ok=True)
    survey_start_local = datetime.fromisoformat(args.survey_start_local)
    window_start_local = survey_start_local + timedelta(seconds=args.offset_seconds)
    window_end_local = window_start_local + timedelta(seconds=args.duration_seconds)

    print(f"Scanning {args.source_audio.name}: {window_start_local.isoformat()} to "
          f"{window_end_local.isoformat()} ({args.timezone} local), "
          f"{args.duration_seconds / 3600:.2f} h, position {args.position_id!r}")

    print("Loading YAMNet ...")
    model, class_names, model_load_s, cached = bm.load_yamnet(args.tfhub_cache_dir)
    print(f"  model_load_seconds={model_load_s:.2f} (cached={cached}); {len(class_names)} classes")

    dummy = np.zeros(int(2 * bm.YAMNET_SAMPLE_RATE), dtype=np.float32)
    _ = model(dummy)

    t_start = time.perf_counter()
    score_chunks = []
    time_chunks = []
    n_chunks = 0
    for waveform, orig_sr, chunk_offset_s in iter_source_chunks(
        args.source_audio, args.offset_seconds, args.duration_seconds,
        args.chunk_seconds, args.overlap_seconds,
    ):
        waveform_16k = bm.resample_to_16k(waveform, orig_sr)
        scores, _emb, _mel = model(waveform_16k)
        scores_np = scores.numpy().astype(np.float32)
        n_frames = scores_np.shape[0]
        frame_times = chunk_offset_s + np.arange(n_frames) * bm.YAMNET_FRAME_HOP_SECONDS
        score_chunks.append(scores_np)
        time_chunks.append(frame_times)
        n_chunks += 1
        if n_chunks % 60 == 0:
            elapsed = time.perf_counter() - t_start
            print(f"  ... {chunk_offset_s / 3600:.2f}h processed ({elapsed:.1f}s wall time)")

    inference_wall_seconds = time.perf_counter() - t_start
    all_scores = np.concatenate(score_chunks, axis=0)
    all_times = np.concatenate(time_chunks, axis=0)
    print(f"Done: {n_chunks} chunks, {len(all_times)} frames (pre-dedupe), "
          f"{inference_wall_seconds:.1f}s wall time "
          f"({args.duration_seconds / inference_wall_seconds:.0f}x realtime)")

    # dedupe overlapping frame times (keep first occurrence)
    order = np.argsort(all_times, kind="stable")
    all_times = all_times[order]
    all_scores = all_scores[order]
    _, unique_idx = np.unique(all_times, return_index=True)
    all_times = all_times[unique_idx]
    all_scores = all_scores[unique_idx]
    print(f"After dedupe: {len(all_times)} frames")

    class_names_arr = np.array(class_names)

    # --- overall ranking by mean and by max score across the whole window ---
    mean_scores = all_scores.mean(axis=0)
    max_scores = all_scores.max(axis=0)
    top_mean_idx = np.argsort(mean_scores)[::-1][: args.top_n]
    top_max_idx = np.argsort(max_scores)[::-1][: args.top_n]

    overall_df = pd.DataFrame({
        "rank": range(1, args.top_n + 1),
        "class_by_mean": class_names_arr[top_mean_idx],
        "mean_score": mean_scores[top_mean_idx].round(4),
        "class_by_max": class_names_arr[top_max_idx],
        "max_score": max_scores[top_max_idx].round(4),
    })
    overall_path = args.results_dir / f"{args.label}_overall_top_classes.csv"
    overall_df.to_csv(overall_path, index=False)
    print(f"\nTop {args.top_n} classes by mean score over the window:")
    for i in range(min(15, args.top_n)):
        print(f"  {i+1:2d}. {overall_df['class_by_mean'][i]:<35s} mean={overall_df['mean_score'][i]:.3f}")

    # --- tone-like keyword flag ---
    tone_mask = np.array([
        any(k in n.lower() for k in TONE_LIKE_KEYWORDS) for n in class_names
    ])
    tone_idx = np.where(tone_mask)[0]
    tone_df = pd.DataFrame({
        "class": class_names_arr[tone_idx],
        "mean_score": mean_scores[tone_idx].round(4),
        "max_score": max_scores[tone_idx].round(4),
    }).sort_values("max_score", ascending=False)
    tone_path = args.results_dir / f"{args.label}_tone_like_classes.csv"
    tone_df.to_csv(tone_path, index=False)
    print(f"\nTone/alarm/mechanical-plant-like classes (by max score), top 10:")
    for _, row in tone_df.head(10).iterrows():
        print(f"  {row['class']:<35s} max={row['max_score']:.3f} mean={row['mean_score']:.3f}")

    # --- time-binned top-3 classes, to see which sound dominates when ---
    bin_seconds = args.bin_minutes * 60.0
    bin_idx = (all_times // bin_seconds).astype(int)
    n_bins = bin_idx.max() + 1
    bin_rows = []
    for b in range(n_bins):
        sel = bin_idx == b
        if not sel.any():
            continue
        bin_mean = all_scores[sel].mean(axis=0)
        top3 = np.argsort(bin_mean)[::-1][:3]
        bin_start_s = args.offset_seconds + b * bin_seconds
        bin_start_local = survey_start_local + timedelta(seconds=bin_start_s)
        bin_rows.append({
            "bin_start_local": bin_start_local.isoformat(),
            "bin_start_epoch_ms": local_offset_to_epoch_ms(bin_start_s, survey_start_local, args.timezone),
            "top1_class": class_names[top3[0]], "top1_mean": round(float(bin_mean[top3[0]]), 4),
            "top2_class": class_names[top3[1]], "top2_mean": round(float(bin_mean[top3[1]]), 4),
            "top3_class": class_names[top3[2]], "top3_mean": round(float(bin_mean[top3[2]]), 4),
        })
    bin_df = pd.DataFrame(bin_rows)
    bin_path = args.results_dir / f"{args.label}_bin_top_classes.csv"
    bin_df.to_csv(bin_path, index=False)
    print(f"\nPer-{args.bin_minutes:.0f}-min-bin top classes written to {bin_path}")
    print(bin_df.to_string(index=False))

    summary = {
        "source_audio": str(args.source_audio),
        "window_local_start": window_start_local.isoformat(),
        "window_local_end": window_end_local.isoformat(),
        "timezone": args.timezone,
        "position_id": args.position_id,
        "n_frames": int(len(all_times)),
        "inference_wall_seconds": round(inference_wall_seconds, 1),
        "realtime_factor": round(args.duration_seconds / inference_wall_seconds, 1),
    }
    with open(args.results_dir / f"{args.label}_run_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nAll outputs saved under: {args.results_dir}")


if __name__ == "__main__":
    main()
