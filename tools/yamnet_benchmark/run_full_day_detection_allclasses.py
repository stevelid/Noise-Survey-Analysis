"""
Full-day YAMNet detection, capturing ALL AudioSet class scores per frame
(not just the classes relevant to one target), then post-processing one or
more target classes from that single cached pass.

Rationale: the expensive step is running the model over the audio
(inference); extracting extra score columns from output already computed is
essentially free, and storage for the resulting frame-score parquet is
cheap. So the standard going-forward practice (per Steve, 2026-08-20) is to
capture full-class scores whenever YAMNet is run over survey audio, so any
other sound class can be screened later from the same cached pass with zero
re-inference cost. Use this script instead of `run_full_day_detection.py`
(single-target, partial-class capture) for any new job.

Reuses model-loading / resampling / event-merging code from
benchmark_yamnet.py, and the chunked-streaming/timestamp helpers from
run_full_day_detection.py, rather than duplicating them.

Run inside the `.venv-yamnet-benchmark` environment — and make sure
PYTHONPATH is not set to a stale global site-packages dir first (has been
seen to shadow the venv's own tensorflow install and break the import;
`env -u PYTHONPATH ...` or unset it in the shell first).

Output per run:
  frame_scores_all_classes.parquet   — every frame x every AudioSet class
                                        (521 cols + frame_time + chunk_index)
  classifications_<slug>.csv          — one per --target, dashboard-importable
  run_summary.json                    — config, counts and per-stage timings

--from-cache
  Skips inference entirely and regenerates classification CSVs from an
  existing frame_scores_all_classes.parquet in --results-dir. This is the
  payoff of the all-class capture: screening a sound class nobody asked for
  at survey time costs seconds instead of re-running the model over days of
  audio. Timestamps are reproduced exactly, since they derive from
  frame_time in the cached parquet plus the same --survey-start-local /
  --offset-seconds arithmetic used on the original run.

Chunk size note: DEFAULT_CHUNK_SECONDS stays 120 s, which is the benchmarked
best for CPU runs on Steve's desktop/laptop. The Colab T4 production setting
is 250 s and is passed explicitly by the Colab notebook — do not change the
default here to a GPU-tuned value, the two environments want different sizes.
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

try:
    from . import benchmark_yamnet as bm
    from .run_full_day_detection import iter_source_chunks, local_offset_to_epoch_ms, _slugify
except ImportError:  # Direct script execution: this directory is on sys.path.
    import benchmark_yamnet as bm
    from run_full_day_detection import iter_source_chunks, local_offset_to_epoch_ms, _slugify

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_RESULTS_DIR = SCRIPT_DIR / "results" / "full_day_allclasses"
DEFAULT_TFHUB_CACHE = SCRIPT_DIR / "tfhub_cache"

# 120 s is the CPU-benchmarked optimum (desktop/laptop). The Colab T4
# production value is 250 s, passed explicitly by the notebook.
DEFAULT_CHUNK_SECONDS = 120
DEFAULT_OVERLAP_SECONDS = 1.0
DEFAULT_HIGH_THRESHOLD = 0.20
DEFAULT_LOW_THRESHOLD = 0.10
DEFAULT_GAP_SECONDS = 1.5

SCORES_FILENAME = "frame_scores_all_classes.parquet"
SUMMARY_FILENAME = "run_summary.json"


def parse_target_spec(spec: str) -> tuple[str, list[str]]:
    """'Dog' or 'Dog:Bark,Howl,Whimper (dog)' -> (class_name, [supporting...])."""
    if ":" in spec:
        name, kw = spec.split(":", 1)
        keywords = [k.strip() for k in kw.split(",") if k.strip()]
        return name.strip(), keywords
    return spec.strip(), []


def run_inference(args, timings: dict):
    """Stream the audio window through YAMNet, returning the deduplicated
    per-frame all-class score frame. Accumulates per-stage timings."""
    print("Loading YAMNet ...")
    model, class_names, model_load_s, cached = bm.load_yamnet(args.tfhub_cache_dir)
    timings["model_load_seconds"] = model_load_s
    print(f"  model_load_seconds={model_load_s:.2f} (cached={cached}), "
          f"{len(class_names)} classes")

    dummy = np.zeros(int(2 * bm.YAMNET_SAMPLE_RATE), dtype=np.float32)
    t0 = time.perf_counter()
    _ = model(dummy)
    timings["warmup_seconds"] = time.perf_counter() - t0
    print(f"  warmup_seconds={timings['warmup_seconds']:.2f}")

    print(f"Streaming audio in {args.chunk_seconds:.0f}s chunks from source "
          f"(no full-day file kept in memory) ...")
    t_start = time.perf_counter()
    timings["audio_read_seconds"] = 0.0
    timings["resample_seconds"] = 0.0
    timings["model_call_seconds"] = 0.0

    time_blocks, chunk_id_blocks, score_blocks = [], [], []
    n_chunks = 0
    for waveform, orig_sr, chunk_offset_s in iter_source_chunks(
        args.source_audio, args.offset_seconds, args.duration_seconds,
        args.chunk_seconds, args.overlap_seconds, timings,
    ):
        t = time.perf_counter()
        waveform_16k = bm.resample_to_16k(waveform, orig_sr)
        timings["resample_seconds"] += time.perf_counter() - t

        # model() is async on GPU; .numpy() forces the device sync, so timing
        # the pair is the honest "model call + fetch result" cost.
        t = time.perf_counter()
        scores, _emb, _mel = model(waveform_16k)
        scores_np = scores.numpy().astype(np.float32)
        timings["model_call_seconds"] += time.perf_counter() - t

        n_frames = scores_np.shape[0]
        times = chunk_offset_s + np.arange(n_frames) * bm.YAMNET_FRAME_HOP_SECONDS
        time_blocks.append(times)
        chunk_id_blocks.append(np.full(n_frames, n_chunks, dtype=np.int32))
        score_blocks.append(scores_np)
        n_chunks += 1
        if n_chunks % 60 == 0:
            elapsed = time.perf_counter() - t_start
            processed_h = chunk_offset_s / 3600
            print(f"  ... {processed_h:.2f}h of audio processed ({elapsed:.1f}s wall time so far)")

    timings["stream_loop_seconds"] = time.perf_counter() - t_start

    t = time.perf_counter()
    all_times = np.concatenate(time_blocks)
    all_chunks = np.concatenate(chunk_id_blocks)
    all_scores = np.vstack(score_blocks)
    timings["concat_seconds"] = time.perf_counter() - t
    del time_blocks, chunk_id_blocks, score_blocks

    print(f"Done streaming: {n_chunks} chunks, {len(all_times)} frames, "
          f"{timings['stream_loop_seconds']:.1f}s stream-loop wall time "
          f"({args.duration_seconds / timings['stream_loop_seconds']:.0f}x realtime end-to-end "
          f"in-loop; model call alone "
          f"{args.duration_seconds / max(timings['model_call_seconds'], 1e-9):.0f}x)")

    # De-duplicate overlap regions between chunks: keep first occurrence in
    # chunk order (matches merge behaviour of run_full_day_detection.py).
    # UNCHANGED semantics — exported timestamps depend on this exactly.
    t = time.perf_counter()
    order = np.argsort(all_times, kind="stable")
    all_times = all_times[order]
    all_chunks = all_chunks[order]
    all_scores = all_scores[order]
    rounded = np.round(all_times, 3)
    _, first_idx = np.unique(rounded, return_index=True)
    first_idx = np.sort(first_idx)
    all_times = rounded[first_idx]
    all_chunks = all_chunks[first_idx]
    all_scores = all_scores[first_idx]
    timings["dedup_sort_seconds"] = time.perf_counter() - t

    t = time.perf_counter()
    frame_df = pd.DataFrame(all_scores, columns=class_names)
    frame_df.insert(0, "chunk_index", all_chunks)
    frame_df.insert(0, "frame_time", all_times)
    timings["dataframe_seconds"] = time.perf_counter() - t

    return frame_df, class_names, n_chunks


def load_cached(args, timings: dict):
    """--from-cache: reload a previous run's all-class parquet instead of inferring."""
    scores_path = args.results_dir / SCORES_FILENAME
    if not scores_path.exists():
        raise SystemExit(
            f"--from-cache needs {scores_path} to exist; no cached scores found. "
            f"Run without --from-cache first."
        )
    t = time.perf_counter()
    frame_df = pd.read_parquet(scores_path)
    timings["parquet_read_seconds"] = time.perf_counter() - t
    class_names = [c for c in frame_df.columns if c not in ("frame_time", "chunk_index")]
    n_chunks = int(frame_df["chunk_index"].max()) + 1 if "chunk_index" in frame_df else 0
    print(f"Loaded cached scores from {scores_path} "
          f"({len(frame_df)} frames x {len(class_names)} classes, "
          f"{timings['parquet_read_seconds']:.1f}s) — no inference run.")
    return frame_df, class_names, n_chunks


def export_targets(frame_df, args, survey_start_local, tz_name, timings, run_summary,
                    audio_file_name):
    """Merge frames into events per target class and write dashboard CSVs.
    Semantics unchanged from the original implementation.

    `audio_file_name` fills the CSV's audio_file column, which the dashboard uses
    to find the recording for playback. It is passed in rather than taken from
    args.source_audio because a --from-cache run may not have the real WAV to
    hand, and must still name the file the scores actually came from."""
    t_events = time.perf_counter()
    for spec in args.targets:
        target_class, supporting_keywords = parse_target_spec(spec)
        slug = _slugify(target_class)
        if target_class not in frame_df.columns:
            # case-insensitive fallback
            match = next((c for c in frame_df.columns if c.lower() == target_class.lower()), None)
            if match is None:
                raise ValueError(
                    f"--target {target_class!r} does not exactly match any YAMNet class name."
                )
            target_class = match
        supporting_names = [
            c for c in frame_df.columns
            if c != target_class and any(k.lower() in c.lower() for k in supporting_keywords)
        ]

        events = bm.merge_events(frame_df, target_class, args.low_threshold,
                                  args.gap_seconds, supporting_names or None)
        for ev in events:
            ev["state"] = "on" if ev["peak_score"] >= args.high_threshold else "uncertain"

        n_on = sum(1 for e in events if e["state"] == "on")
        n_uncertain = len(events) - n_on
        print(f"[{target_class}] candidate events >= {args.low_threshold}: {len(events)} "
              f"({n_on} 'on' >= {args.high_threshold}, {n_uncertain} 'uncertain')")

        rows = []
        source_id = f"yamnet_{slug}"
        source_label = f"YAMNet: {target_class}"
        for ev in events:
            start_ms = local_offset_to_epoch_ms(args.offset_seconds + ev["start_time"], survey_start_local, tz_name)
            end_ms = local_offset_to_epoch_ms(args.offset_seconds + ev["end_time"], survey_start_local, tz_name)
            rows.append({
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
                "audio_file": audio_file_name,
                "color": "",
            })
        out_path = args.results_dir / f"classifications_{slug}.csv"
        pd.DataFrame(rows, columns=[
            "position_id", "source_id", "source_label", "start", "end",
            "state", "confidence", "description", "audio_file", "color",
        ]).to_csv(out_path, index=False)
        print(f"  -> {out_path} ({len(rows)} rows)")

        run_summary["targets"][target_class] = {
            "source_id": source_id,
            "n_events_on": n_on,
            "n_events_uncertain": n_uncertain,
            "classifications_csv": str(out_path),
        }
    timings["events_seconds"] = time.perf_counter() - t_events


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source-audio", type=Path, required=True)
    parser.add_argument("--offset-seconds", type=float, default=0.0)
    parser.add_argument("--duration-seconds", type=float, required=True)
    parser.add_argument("--chunk-seconds", type=float, default=DEFAULT_CHUNK_SECONDS,
                         help=f"Audio seconds per model call. Default {DEFAULT_CHUNK_SECONDS} is "
                              f"the CPU-benchmarked optimum; the Colab T4 production value is 250 "
                              f"(passed explicitly by the notebook). Above ~300 gives no throughput "
                              f"gain on a T4 but raises GPU memory sharply.")
    parser.add_argument("--overlap-seconds", type=float, default=DEFAULT_OVERLAP_SECONDS)
    parser.add_argument("--target", action="append", dest="targets", default=[],
                         help="Target class to export as a classifications CSV from the "
                              "cached full-class scores. Repeatable. Format: 'ClassName' "
                              "or 'ClassName:supporting,keyword,list' (exact AudioSet class "
                              "name, case-insensitive; supporting keywords are substring "
                              "matches against other class names, tracked but never folded "
                              "into the direct detection). E.g. --target Dog:Bark,Howl "
                              "--target \"Traffic noise, roadway noise:Vehicle,Car,Engine\"")
    parser.add_argument("--high-threshold", type=float, default=DEFAULT_HIGH_THRESHOLD)
    parser.add_argument("--low-threshold", type=float, default=DEFAULT_LOW_THRESHOLD)
    parser.add_argument("--gap-seconds", type=float, default=DEFAULT_GAP_SECONDS)
    parser.add_argument("--survey-start-local", type=str, required=True,
                         help="Naive local wall-clock start of THIS source file, ISO format "
                              "(e.g. 2026-04-14T10:30:00).")
    parser.add_argument("--timezone", type=str, default="Europe/London")
    parser.add_argument("--position-id", type=str, required=True)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--tfhub-cache-dir", type=Path, default=DEFAULT_TFHUB_CACHE)
    parser.add_argument("--parquet-compression", type=str, default="zstd",
                         help="Parquet codec for the all-class score cache: zstd (default, "
                              "best size), snappy (faster write, larger), or none.")
    parser.add_argument("--from-cache", action="store_true",
                         help="Skip inference; regenerate classification CSVs from the existing "
                              f"{SCORES_FILENAME} in --results-dir. Use to screen an additional "
                              "sound class without re-running the model over the audio.")
    args = parser.parse_args()

    if not args.targets:
        raise SystemExit("Pass at least one --target (e.g. --target Dog).")

    survey_start_local = datetime.fromisoformat(args.survey_start_local)
    tz_name = args.timezone
    args.results_dir.mkdir(parents=True, exist_ok=True)

    t_local_total = time.perf_counter()
    timings: dict = {}

    day_start_local = survey_start_local + timedelta(seconds=args.offset_seconds)
    day_end_local = day_start_local + timedelta(seconds=args.duration_seconds)
    print(f"Processing {args.source_audio.name}: "
          f"{day_start_local.isoformat()} to {day_end_local.isoformat()} ({tz_name} local), "
          f"{args.duration_seconds / 3600:.1f} h, capturing ALL classes"
          f"{' [FROM CACHE — no inference]' if args.from_cache else ''}")

    # The audio_file column must name the recording the scores came from, so the
    # dashboard can find it for playback. On a --from-cache run the real WAV may
    # not be present, so prefer the source recorded by the run that did the
    # inference; fall back to whatever --source-audio was given.
    resolved_source = str(args.source_audio)
    if args.from_cache:
        prev_summary = args.results_dir / SUMMARY_FILENAME
        if prev_summary.exists():
            try:
                prev_src = json.loads(prev_summary.read_text()).get("source_audio")
                if prev_src:
                    resolved_source = prev_src
            except (json.JSONDecodeError, OSError):
                pass  # fall back to --source-audio
    audio_file_name = Path(resolved_source).name

    if args.from_cache:
        frame_df, class_names, n_chunks = load_cached(args, timings)
        print(f"  audio_file column: {audio_file_name}")
    else:
        frame_df, class_names, n_chunks = run_inference(args, timings)

        scores_path = args.results_dir / SCORES_FILENAME
        compression = None if args.parquet_compression.lower() == "none" else args.parquet_compression
        t = time.perf_counter()
        frame_df.to_parquet(scores_path, index=False, compression=compression)
        timings["parquet_write_seconds"] = time.perf_counter() - t
        size_mb = scores_path.stat().st_size / 1e6
        print(f"Wrote full-class frame scores: {scores_path} "
              f"({len(frame_df)} frames x {len(class_names)} classes, "
              f"{size_mb:.1f} MB, {timings['parquet_write_seconds']:.1f}s, "
              f"codec={args.parquet_compression})")

    run_summary = {
        "source_audio": resolved_source,
        "window_local_start": day_start_local.isoformat(),
        "window_local_end": day_end_local.isoformat(),
        "timezone": tz_name,
        "duration_hours": args.duration_seconds / 3600,
        "chunk_seconds": args.chunk_seconds,
        "overlap_seconds": args.overlap_seconds,
        "parquet_compression": args.parquet_compression,
        "from_cache": bool(args.from_cache),
        "n_chunks": n_chunks,
        "n_frames": len(frame_df),
        "n_classes": len(class_names),
        "position_id": args.position_id,
        "high_threshold": args.high_threshold,
        "low_threshold": args.low_threshold,
        "targets": {},
    }

    export_targets(frame_df, args, survey_start_local, tz_name, timings, run_summary,
                    audio_file_name)

    timings["local_total_seconds"] = time.perf_counter() - t_local_total

    # Realtime factors, explicitly named so nothing gets read as "pure inference".
    dur = args.duration_seconds
    rt = {}
    if timings.get("model_call_seconds"):
        rt["model_call_only"] = round(dur / timings["model_call_seconds"], 1)
    if timings.get("stream_loop_seconds"):
        rt["stream_loop"] = round(dur / timings["stream_loop_seconds"], 1)
    if timings.get("local_total_seconds"):
        rt["local_total"] = round(dur / timings["local_total_seconds"], 1)

    run_summary["timings_seconds"] = {k: round(v, 3) for k, v in sorted(timings.items())}
    run_summary["realtime_factors"] = rt
    run_summary["timings_note"] = (
        "stream_loop_seconds covers the whole read+resample+model+bookkeeping loop, "
        "NOT pure model inference — use model_call_seconds for that (model() plus the "
        ".numpy() device sync). local_total_seconds covers everything this process did, "
        "excluding any upload of results to Drive by the caller."
    )

    with open(args.results_dir / SUMMARY_FILENAME, "w") as f:
        json.dump(run_summary, f, indent=2)

    print("\nStage timings (s):")
    for k, v in sorted(timings.items()):
        print(f"  {k:26s} {v:9.2f}")
    print("Realtime factors: " + ", ".join(f"{k}={v}x" for k, v in rt.items()))

    print(f"\nAll outputs saved under: {args.results_dir}")
    print("To view: dashboard side panel -> Classifications -> Import -> select a "
          "classifications_<slug>.csv. To screen a different class later against this "
          f"same audio window with zero re-inference, rerun with --from-cache (or load "
          f"{SCORES_FILENAME} and call benchmark_yamnet.merge_events() directly).")


if __name__ == "__main__":
    main()
