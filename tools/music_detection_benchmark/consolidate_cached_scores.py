"""Consolidate cached YAMNet frame scores for job 5882 July.

This is deliberately a post-processing-only script. It reads the existing
per-position/per-window Parquet frame scores and never loads or invokes YAMNet.
Raw audio is read only when the optional review phase writes matched listening
clips; that phase also performs no inference.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import soundfile as sf

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import run_5882_july as base  # noqa: E402


SMOOTH_SECONDS = 5.0
HYSTERESIS_HIGH = 0.20
HYSTERESIS_LOW = 0.05
MERGE_GAPS = (3.0, 7.0, 15.0, 30.0)
REVIEW_MERGE_GAP = 7.0
MIN_BLOCK_SECONDS = 2.0
REVIEW_PAD_SECONDS = 3.0
RAW_SCREENING_THRESHOLD = base.SCREENING_THRESHOLD
POSITIONS = (base.PRIMARY_POSITION, "Nti4", base.BOUNDARY_1)


def cached_path(results: Path, position: str, window: str) -> Path:
    return results / "frame_scores" / f"{position}_{window}.parquet"


def load_cached_frame_scores(results: Path, position: str, window: str) -> pd.DataFrame:
    path = cached_path(results, position, window)
    if not path.exists():
        raise FileNotFoundError(f"Required cached frame scores are missing: {path}")
    df = pd.read_parquet(path)
    required = {"frame_time_s", base.DIRECT_CLASS}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{path} is missing cached score columns: {sorted(missing)}")
    df = df.sort_values("frame_time_s").drop_duplicates("frame_time_s", keep="first").reset_index(drop=True)
    if df["frame_time_s"].duplicated().any():
        raise ValueError(f"Duplicate frame timestamps remain in {path}")
    return df


def add_smoothed_state(df: pd.DataFrame) -> pd.DataFrame:
    """Add a centred rolling-median score and high/low hysteresis state."""
    out = df.copy()
    hop = float(base.bm.YAMNET_FRAME_HOP_SECONDS)
    rolling_frames = max(3, int(round(SMOOTH_SECONDS / hop)))
    if rolling_frames % 2 == 0:
        rolling_frames += 1
    out["music_score_smoothed"] = (
        out[base.DIRECT_CLASS]
        .rolling(window=rolling_frames, center=True, min_periods=1)
        .median()
        .astype(float)
    )
    active: list[bool] = []
    state = False
    for score in out["music_score_smoothed"].to_numpy(dtype=float):
        if not state and score >= HYSTERESIS_HIGH:
            state = True
        elif state and score < HYSTERESIS_LOW:
            state = False
        active.append(state)
    out["music_active_hysteresis"] = active
    return out


def _summarise_interval(df: pd.DataFrame, start: float, end: float, prefix: str) -> dict[str, Any]:
    sub = df[(df.frame_time_s >= start) & (df.frame_time_s < end)]
    if sub.empty:
        return {
            f"{prefix}_frames": 0,
            f"{prefix}_raw_music_max": np.nan,
            f"{prefix}_raw_music_mean": np.nan,
            f"{prefix}_raw_music_median": np.nan,
            f"{prefix}_raw_music_p95": np.nan,
            f"{prefix}_raw_frames_ge_{RAW_SCREENING_THRESHOLD:.2f}": 0,
            f"{prefix}_raw_threshold_crossed": False,
            f"{prefix}_raw_pct_frames_ge_{RAW_SCREENING_THRESHOLD:.2f}": 0.0,
            f"{prefix}_smoothed_max": np.nan,
            f"{prefix}_smoothed_high_threshold_crossed": False,
            f"{prefix}_smoothed_pct_ge_{HYSTERESIS_HIGH:.2f}": 0.0,
        }
    raw = sub[base.DIRECT_CLASS].astype(float)
    smooth = sub["music_score_smoothed"].astype(float)
    return {
        f"{prefix}_frames": int(len(sub)),
        f"{prefix}_raw_music_max": float(raw.max()),
        f"{prefix}_raw_music_mean": float(raw.mean()),
        f"{prefix}_raw_music_median": float(raw.median()),
        f"{prefix}_raw_music_p95": float(raw.quantile(0.95)),
        f"{prefix}_raw_frames_ge_{RAW_SCREENING_THRESHOLD:.2f}": int((raw >= RAW_SCREENING_THRESHOLD).sum()),
        f"{prefix}_raw_threshold_crossed": bool((raw >= RAW_SCREENING_THRESHOLD).any()),
        f"{prefix}_raw_pct_frames_ge_{RAW_SCREENING_THRESHOLD:.2f}": float(100.0 * (raw >= RAW_SCREENING_THRESHOLD).mean()),
        f"{prefix}_smoothed_max": float(smooth.max()),
        f"{prefix}_smoothed_high_threshold_crossed": bool((smooth >= HYSTERESIS_HIGH).any()),
        f"{prefix}_smoothed_pct_ge_{HYSTERESIS_HIGH:.2f}": float(100.0 * (smooth >= HYSTERESIS_HIGH).mean()),
    }


def _initial_blocks(df: pd.DataFrame) -> list[dict[str, Any]]:
    hop = float(base.bm.YAMNET_FRAME_HOP_SECONDS)
    blocks: list[dict[str, Any]] = []
    start_idx: int | None = None
    for i, is_active in enumerate(df["music_active_hysteresis"].to_numpy(dtype=bool)):
        if is_active and start_idx is None:
            start_idx = i
        if (not is_active or i == len(df) - 1) and start_idx is not None:
            end_idx = i if not is_active else i + 1
            start = float(df.iloc[start_idx].frame_time_s)
            end = float(df.iloc[end_idx - 1].frame_time_s) + hop
            if end - start >= MIN_BLOCK_SECONDS:
                blocks.append({"start_epoch": start, "end_epoch": end, "initial_active_frames": int(df.iloc[start_idx:end_idx]["music_active_hysteresis"].sum())})
            start_idx = None
    return blocks


def _merge_blocks(df: pd.DataFrame, blocks: list[dict[str, Any]], gap_seconds: float) -> list[dict[str, Any]]:
    if not blocks:
        return []
    merged: list[dict[str, Any]] = []
    for block in blocks:
        if not merged or block["start_epoch"] - merged[-1]["end_epoch"] > gap_seconds:
            merged.append(dict(block))
        else:
            merged[-1]["end_epoch"] = max(merged[-1]["end_epoch"], block["end_epoch"])
            merged[-1]["initial_active_frames"] += block["initial_active_frames"]
    hop = float(base.bm.YAMNET_FRAME_HOP_SECONDS)
    output: list[dict[str, Any]] = []
    for number, block in enumerate(merged, 1):
        start = float(block["start_epoch"])
        end = float(block["end_epoch"])
        sub = df[(df.frame_time_s >= start) & (df.frame_time_s < end)]
        active_seconds = float(block["initial_active_frames"] * hop)
        row: dict[str, Any] = {
            "block_number": number,
            "start_epoch": start,
            "end_epoch": end,
            "duration_seconds": end - start,
            "initial_hysteresis_blocks": 0,
            "hysteresis_active_seconds": active_seconds,
            "merge_gap_filled_seconds": max(0.0, (end - start) - active_seconds),
            "frames_in_interval": int(len(sub)),
            "raw_music_peak": np.nan if sub.empty else float(sub[base.DIRECT_CLASS].max()),
            "raw_music_mean": np.nan if sub.empty else float(sub[base.DIRECT_CLASS].mean()),
            "smoothed_music_peak": np.nan if sub.empty else float(sub["music_score_smoothed"].max()),
            "smoothed_music_mean": np.nan if sub.empty else float(sub["music_score_smoothed"].mean()),
            "raw_pct_frames_ge_0.05": 0.0 if sub.empty else float(100.0 * (sub[base.DIRECT_CLASS] >= RAW_SCREENING_THRESHOLD).mean()),
        }
        output.append(row)
    return output


def overlap(block: dict[str, Any], other: dict[str, Any]) -> bool:
    return other["end_epoch"] > block["start_epoch"] and other["start_epoch"] < block["end_epoch"]


def interval_metrics(df: pd.DataFrame, block: dict[str, Any], prefix: str, independent_blocks: list[dict[str, Any]]) -> dict[str, Any]:
    start, end = float(block["start_epoch"]), float(block["end_epoch"])
    result = _summarise_interval(df, start, end, prefix)
    result[f"{prefix}_independent_hysteresis_block_overlap"] = any(overlap(block, other) for other in independent_blocks)
    result[f"{prefix}_independent_block_count_overlapping"] = sum(overlap(block, other) for other in independent_blocks)
    return result


def local_iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).astimezone(base.TZ).isoformat()


def block_rows_for_position(df: pd.DataFrame, position: str, window: str, gap_seconds: float) -> list[dict[str, Any]]:
    smoothed = add_smoothed_state(df)
    initial = _initial_blocks(smoothed)
    rows = _merge_blocks(smoothed, initial, gap_seconds)
    for row in rows:
        row.update({
            "position": position,
            "window": window,
            "merge_gap_seconds": gap_seconds,
            "smoothing_seconds": SMOOTH_SECONDS,
            "hysteresis_high": HYSTERESIS_HIGH,
            "hysteresis_low": HYSTERESIS_LOW,
            "start_local": local_iso(row["start_epoch"]),
            "end_local": local_iso(row["end_epoch"]),
        })
    return rows


def build_cached_consolidation(results: Path) -> dict[str, Any]:
    out_dir = results / "consolidated_cached_scores"
    out_dir.mkdir(parents=True, exist_ok=True)
    cached: dict[tuple[str, str], pd.DataFrame] = {}
    blocks_by_setting: dict[tuple[str, str, float], list[dict[str, Any]]] = {}
    comparison_rows: list[dict[str, Any]] = []
    provenance = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "yamnet_inference_invoked": False,
        "source": "existing frame_scores/*.parquet only",
        "source_files": [],
        "smoothing": {"method": "centred rolling median", "window_seconds": SMOOTH_SECONDS},
        "hysteresis": {"high": HYSTERESIS_HIGH, "low": HYSTERESIS_LOW},
        "merge_gaps_seconds": list(MERGE_GAPS),
        "raw_screening_threshold": RAW_SCREENING_THRESHOLD,
        "review_merge_gap_seconds": REVIEW_MERGE_GAP,
    }
    for position in POSITIONS:
        for window in base.WINDOWS:
            df = load_cached_frame_scores(results, position, window)
            cached[(position, window)] = df
            provenance["source_files"].append(str(cached_path(results, position, window)))
            smoothed = add_smoothed_state(df)
            initial_count = len(_initial_blocks(smoothed))
            for gap in MERGE_GAPS:
                rows = block_rows_for_position(df, position, window, gap)
                blocks_by_setting[(position, window, gap)] = rows
                block_path = out_dir / f"{position}_{window}_blocks_gap_{gap:g}s.csv"
                pd.DataFrame(rows).to_csv(block_path, index=False)
                comparison_rows.append({
                    "position": position,
                    "window": window,
                    "merge_gap_seconds": gap,
                    "smoothing_method": "centred rolling median",
                    "smoothing_seconds": SMOOTH_SECONDS,
                    "hysteresis_high": HYSTERESIS_HIGH,
                    "hysteresis_low": HYSTERESIS_LOW,
                    "initial_hysteresis_block_count": initial_count,
                    "consolidated_block_count": len(rows),
                    "total_music_active_seconds": float(sum(x["duration_seconds"] for x in rows)),
                    "total_hysteresis_active_seconds": float(sum(x["hysteresis_active_seconds"] for x in rows)),
                    "total_merge_gap_filled_seconds": float(sum(x["merge_gap_filled_seconds"] for x in rows)),
                    "active_percent_of_window": float(100.0 * sum(x["duration_seconds"] for x in rows) / 39600.0),
                })
    comparison = pd.DataFrame(comparison_rows)
    comparison.to_csv(out_dir / "music_timeline_comparison.csv", index=False)
    review_blocks: list[dict[str, Any]] = []
    for window in base.WINDOWS:
        n5_df = add_smoothed_state(cached[(base.PRIMARY_POSITION, window)])
        nti4_df = add_smoothed_state(cached[("Nti4", window)])
        boundary_df = add_smoothed_state(cached[(base.BOUNDARY_1, window)])
        n5_blocks = blocks_by_setting[(base.PRIMARY_POSITION, window, REVIEW_MERGE_GAP)]
        nti4_blocks = blocks_by_setting[("Nti4", window, REVIEW_MERGE_GAP)]
        boundary_blocks = blocks_by_setting[(base.BOUNDARY_1, window, REVIEW_MERGE_GAP)]
        for row in n5_blocks:
            record = dict(row)
            record["block_id"] = f"{window}_{int(row['block_number']):03d}"
            record.update(interval_metrics(n5_df, row, "Nti5", n5_blocks))
            record.update(interval_metrics(nti4_df, row, "Nti4", nti4_blocks))
            record.update(interval_metrics(boundary_df, row, "971-2", boundary_blocks))
            record["manual_review_status"] = "not yet reviewed"
            record["boundary_interpretation"] = "not an audibility conclusion; manually review matched clips"
            review_blocks.append(record)
    matched = pd.DataFrame(review_blocks)
    matched.to_csv(out_dir / "Nti5_consolidated_blocks_gap_7s_with_comparators.csv", index=False)
    provenance["cached_frame_counts"] = {f"{p}_{w}": int(len(cached[(p, w)])) for p in POSITIONS for w in base.WINDOWS}
    provenance["consolidated_review_block_count"] = len(matched)
    (out_dir / "provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    write_consolidated_report(out_dir, comparison, matched)
    return {"out_dir": out_dir, "cached": cached, "review_blocks": review_blocks, "comparison": comparison}


def write_consolidated_report(out_dir: Path, comparison: pd.DataFrame, matched: pd.DataFrame) -> None:
    lines = [
        "# Job 5882 July cached-score music-active consolidation",
        "",
        "This post-processing output reads only the six existing `frame_scores/*.parquet` files. YAMNet was not loaded or rerun.",
        "",
        f"Smoothing: centred {SMOOTH_SECONDS:.1f}s rolling median. Hysteresis: enter at `{HYSTERESIS_HIGH:.2f}` and remain active until below `{HYSTERESIS_LOW:.2f}`. Merge gaps tested: {', '.join(f'{x:g}s' for x in MERGE_GAPS)}. Minimum consolidated block: {MIN_BLOCK_SECONDS:.1f}s.",
        "",
        "## Nti5 comparison",
        "",
        "| window | merge gap | blocks | active duration (min) | merge-filled (min) | window coverage |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    n5 = comparison[comparison.position == base.PRIMARY_POSITION]
    for _, row in n5.sort_values(["window", "merge_gap_seconds"]).iterrows():
        lines.append(f"| {row.window} | {row.merge_gap_seconds:g}s | {int(row.consolidated_block_count)} | {row.total_music_active_seconds / 60:.1f} | {row.total_merge_gap_filled_seconds / 60:.1f} | {row.active_percent_of_window:.1f}% |")
    lines += [
        "",
        "## Comparator handling",
        "",
        f"For every one of the {len(matched)} consolidated Nti5 blocks at the {REVIEW_MERGE_GAP:g}s merge setting, Nti4 and 971-2 raw and smoothed Music scores are calculated over the exact same absolute interval. The CSV also records raw-frame threshold crossings and overlap with each meter's independently consolidated hysteresis blocks.",
        "",
        "Boundary fields are classifier comparisons only. They do not state that music was audible at the boundary; manual listening is required.",
        "",
        "## Files",
        "",
        "- `music_timeline_comparison.csv` — event count and duration sensitivity for all three available audio positions.",
        "- `Nti5_consolidated_blocks_gap_7s_with_comparators.csv` — primary blocks plus exact-interval Nti4 and 971-2 metrics.",
        "- `Nti5_friday_blocks_gap_*.csv` and `Nti5_saturday_blocks_gap_*.csv` — consolidated timelines at each merge gap.",
        "- `review.html` — matched three-meter listening page; all clips remain marked not yet reviewed.",
        "- `provenance.json` — cached-only provenance and frame counts.",
    ]
    (out_dir / "consolidated_cached_score_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_consolidated_review(results: Path, consolidation: dict[str, Any], survey_root: Path) -> None:
    out_dir = consolidation["out_dir"]
    clip_dir = out_dir / "review_clips"
    clip_dir.mkdir(parents=True, exist_ok=True)
    segments = base.discover_segments(survey_root)
    manifest: list[dict[str, Any]] = []
    html_parts = [
        "<!doctype html><html><head><meta charset='utf-8'><title>5882 July consolidated cached-score review</title>",
        "<style>body{font-family:Segoe UI,Arial,sans-serif;margin:2rem;background:#f5f5f5;color:#222}.notice{background:#fff8dc;border:1px solid #d8b23c;padding:1rem;margin-bottom:1rem}.index{background:white;border:1px solid #ccc;padding:1rem;margin-bottom:1rem}.event{background:white;border:1px solid #ccc;padding:1rem;margin:1rem 0}.meters{display:grid;grid-template-columns:repeat(3,minmax(260px,1fr));gap:1rem}.meter{border:1px solid #ddd;padding:.75rem}.meter.boundary{background:#f5fbf7}audio{width:100%}small{color:#555}.score{font-family:Consolas,monospace;font-size:.9rem}</style>",
        "</head><body><h1>Job 5882 July consolidated music-active review</h1>",
        "<div class='notice'><strong>Cached-score post-processing only.</strong> The timeline uses a centred rolling median, hysteresis and a 7-second merge gap. These are raw YAMNet classifier scores, not probabilities. Boundary music must not be described as audible until the matched clips have been manually reviewed.</div>",
    ]
    blocks = sorted(consolidation["review_blocks"], key=lambda x: x["start_epoch"])
    html_parts.append("<div class='index'><h2>Index</h2><ul>")
    for block in blocks:
        html_parts.append(f"<li><a href='#{html.escape(block['block_id'])}'>{html.escape(block['block_id'])}</a> — {html.escape(block['start_local'])} to {html.escape(block['end_local'])}</li>")
    html_parts.append("</ul></div>")
    for block in blocks:
        block_id = block["block_id"]
        start = max(base.WINDOWS[block["window"]][0].timestamp(), block["start_epoch"] - REVIEW_PAD_SECONDS)
        end = min(base.WINDOWS[block["window"]][1].timestamp(), block["end_epoch"] + REVIEW_PAD_SECONDS)
        clip_start_local = local_iso(start)
        clip_end_local = local_iso(end)
        html_parts.append(f"<section class='event' id='{html.escape(block_id)}'><h2>{html.escape(block_id)} — {html.escape(block['start_local'])} to {html.escape(block['end_local'])}</h2>")
        html_parts.append(f"<p>Consolidated Nti5 block duration: {block['duration_seconds']:.1f}s; smoothed peak: {block['smoothed_music_peak']:.3f}; raw peak: {block['raw_music_peak']:.3f}. Matched clip interval (with ±{REVIEW_PAD_SECONDS:.0f}s pad): {html.escape(clip_start_local)} to {html.escape(clip_end_local)}.</p>")
        html_parts.append("<div class='meters'>")
        for position, prefix, label, boundary in ((base.PRIMARY_POSITION, "Nti5", "Nti5 primary internal", False), ("Nti4", "Nti4", "Nti4 internal comparator", False), (base.BOUNDARY_1, "971-2", "971-2 available boundary", True)):
            filename = f"{block_id}_{position.replace('-', '_')}.flac"
            out = clip_dir / block["window"] / filename
            try:
                data, sample_rate, source_files_list = base.read_absolute_chunk(segments, position, start, end)
                out.parent.mkdir(parents=True, exist_ok=True)
                sf.write(str(out), data, sample_rate, format="FLAC", subtype="PCM_16")
                status, source_files = "written", ",".join(source_files_list)
            except Exception as exc:
                status, source_files = "unavailable", str(exc)
            relative = str(out.relative_to(results)).replace("\\", "/") if status == "written" else ""
            raw_max = block.get(f"{prefix}_raw_music_max")
            raw_mean = block.get(f"{prefix}_raw_music_mean")
            raw_pct = block.get(f"{prefix}_raw_pct_frames_ge_0.05")
            overlap_value = block.get(f"{prefix}_independent_hysteresis_block_overlap")
            manual = "not yet reviewed"
            manifest.append({
                "block_id": block_id,
                "window": block["window"],
                "meter": position,
                "role": "available boundary comparison only" if boundary else ("primary internal" if position == base.PRIMARY_POSITION else "internal comparator"),
                "block_start_local": block["start_local"],
                "block_end_local": block["end_local"],
                "clip_start_local": clip_start_local,
                "clip_end_local": clip_end_local,
                "clip_file": relative,
                "status": status,
                "source_file": source_files,
                "raw_music_max_same_interval": raw_max,
                "raw_music_mean_same_interval": raw_mean,
                "raw_pct_frames_ge_0.05_same_interval": raw_pct,
                "independent_hysteresis_block_overlap": overlap_value,
                "manual_review": manual,
                "boundary_interpretation": "not audible until manually reviewed" if boundary else "classifier comparison only",
            })
            html_parts.append(f"<div class='meter{' boundary' if boundary else ''}'><h3>{html.escape(label)}</h3><small>{html.escape(status)}; manual review: {manual}</small><p class='score'>same-interval raw max={float(raw_max):.3f} | mean={float(raw_mean):.3f} | raw ≥0.05={float(raw_pct):.1f}%<br>independent hysteresis overlap={html.escape(str(overlap_value))}</p>")
            if relative:
                html_parts.append(f"<audio controls preload='none' src='{html.escape(relative)}'></audio>")
            html_parts.append("</div>")
        html_parts.append("</div><p><strong>Boundary caution:</strong> 971-2 score agreement or disagreement is not an audibility conclusion. Listen to the clip and record the manual review separately.</p></section>")
    html_parts.append("</body></html>")
    pd.DataFrame(manifest).to_csv(out_dir / "review_manifest.csv", index=False)
    page = "\n".join(html_parts)
    (results / "review.html").write_text(page, encoding="utf-8")
    # The root page uses paths relative to the results directory; keep a
    # second copy usable when opened directly from the consolidation folder.
    out_page = page.replace("consolidated_cached_scores/review_clips/", "review_clips/")
    (out_dir / "review.html").write_text(out_page, encoding="utf-8")


def rebuild_review_page_copy(results: Path) -> None:
    out_dir = results / "consolidated_cached_scores"
    source = results / "review.html"
    if not source.exists():
        raise SystemExit(f"The root review page is missing: {source}")
    page = source.read_text(encoding="utf-8")
    (out_dir / "review.html").write_text(page.replace("consolidated_cached_scores/review_clips/", "review_clips/"), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("consolidate", "review", "page", "all"), default="all")
    parser.add_argument("--results-dir", type=Path, default=base.DEFAULT_RESULTS)
    parser.add_argument("--survey-root", type=Path, default=base.DEFAULT_SURVEY_ROOT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.phase in ("consolidate", "all"):
        consolidation = build_cached_consolidation(args.results_dir)
    else:
        out_dir = args.results_dir / "consolidated_cached_scores"
        matched_path = out_dir / "Nti5_consolidated_blocks_gap_7s_with_comparators.csv"
        comparison_path = out_dir / "music_timeline_comparison.csv"
        if not matched_path.exists() or not comparison_path.exists():
            raise SystemExit("Cached consolidation outputs are missing; run --phase consolidate first.")
        consolidation = {
            "out_dir": out_dir,
            "review_blocks": pd.read_csv(matched_path).to_dict("records"),
            "comparison": pd.read_csv(comparison_path),
        }
    if args.phase in ("review", "all"):
        write_consolidated_review(args.results_dir, consolidation, args.survey_root)
    if args.phase == "page":
        rebuild_review_page_copy(args.results_dir)
    print(f"Cached-only consolidation outputs saved under {consolidation['out_dir']}")


if __name__ == "__main__":
    main()
