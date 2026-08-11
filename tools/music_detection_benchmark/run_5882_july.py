"""Run the local YAMNet music-categorisation benchmark for job 5882 July 2026.

The script is deliberately self-contained and isolated from the dashboard. It
uses the existing local YAMNet model loader/resampler, but keeps discovery,
timeline construction, inference, event construction, cross-meter matching,
benchmarking, clip export and report generation here so each expensive stage
is reviewable and resumable.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
import multiprocessing as mp
import os
import queue
import re
import shutil
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import psutil
import soundfile as sf

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
YAMNET_DIR = REPO_ROOT / "tools" / "yamnet_benchmark"
if str(YAMNET_DIR) not in sys.path:
    sys.path.insert(0, str(YAMNET_DIR))
import benchmark_yamnet as bm  # noqa: E402


TZ = ZoneInfo("Europe/London")
UTC = timezone.utc
DEFAULT_SURVEY_ROOT = Path(
    r"G:\Shared drives\Venta\Jobs\5882 Warbrook House, Eversley\5882 Surveys\july 2026"
)
DEFAULT_RESULTS = SCRIPT_DIR / "results" / "5882_july_audio"
DEFAULT_TFHUB_CACHE = YAMNET_DIR / "tfhub_cache"
DIRECT_CLASS = "Music"
PRIMARY_POSITION = "Nti5"
BOUNDARY_1 = "971-2"
BOUNDARY_2 = ""
WINDOWS = {
    "friday": (
        datetime(2026, 7, 10, 16, 0, tzinfo=TZ),
        datetime(2026, 7, 11, 3, 0, tzinfo=TZ),
    ),
    "saturday": (
        datetime(2026, 7, 11, 16, 0, tzinfo=TZ),
        datetime(2026, 7, 12, 3, 0, tzinfo=TZ),
    ),
}
THRESHOLDS = [0.02, 0.05, 0.10, 0.20, 0.30, 0.50]
SCREENING_THRESHOLD = 0.05
HIGH_THRESHOLD = 0.20
MERGE_GAP_SECONDS = 7.0
MIN_EVENT_SECONDS = 2.0
CLIP_PAD_SECONDS = 3.0
CHUNK_SECONDS = 120.0
OVERLAP_SECONDS = 1.0
BENCHMARK_SECONDS = 900.0
BENCHMARK_LOCAL_START = datetime(2026, 7, 10, 20, 0, tzinfo=TZ)


@dataclass
class AudioSegment:
    position: str
    path: str
    file_name: str
    kind: str
    continuous_group: str
    start_local: str
    end_local: str
    duration_seconds: float
    size_bytes: int
    sample_rate: int
    bit_depth: str
    channels: int
    format: str
    subtype: str
    start_basis: str
    continuous: bool
    start_epoch: float
    end_epoch: float
    gap_from_previous_seconds: float | None = None
    alignment_note: str = ""


@dataclass
class RunStats:
    config: str
    position: str
    audio_file: str
    audio_duration_seconds: float
    chunk_seconds: float
    overlap_seconds: float
    workers: int
    threads: int
    tf_intra_op: str
    tf_inter_op: str
    cache_mode: str
    audio_read_seconds: float
    resample_seconds: float
    inference_seconds: float
    score_extraction_seconds: float
    postprocessing_seconds: float
    parquet_write_seconds: float
    staging_seconds: float
    total_wall_seconds: float
    realtime_factor: float
    audio_seconds_per_second: float
    peak_process_memory_mb: float
    peak_system_memory_mb: float
    average_cpu_percent: float
    peak_cpu_percent: float
    disk_read_mb: float
    network_recv_mb: float
    n_frames: int
    n_events: int
    status: str = "ok"
    note: str = ""


class Sampler:
    """Small process/system sampler for proportional benchmark diagnostics."""

    def __init__(self, interval: float = 0.1):
        self.interval = interval
        self.proc = psutil.Process(os.getpid())
        self.samples: list[tuple[float, float, float, float]] = []
        self.before_disk = psutil.disk_io_counters()
        self.before_net = psutil.net_io_counters()
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self.stop_event.is_set():
            now = time.perf_counter()
            try:
                rss = self.proc.memory_info().rss / (1024 * 1024)
                cpu = self.proc.cpu_percent(interval=None)
                mem = psutil.virtual_memory().used / (1024 * 1024)
                self.samples.append((now, rss, cpu, mem))
            except (psutil.Error, OSError):
                pass
            self.stop_event.wait(self.interval)

    def start(self) -> None:
        self.proc.cpu_percent(interval=None)
        self.thread.start()

    def stop(self) -> dict[str, float]:
        self.stop_event.set()
        self.thread.join(timeout=2)
        end_disk = psutil.disk_io_counters()
        end_net = psutil.net_io_counters()
        if not self.samples:
            return {
                "peak_process_memory_mb": float("nan"),
                "peak_system_memory_mb": float("nan"),
                "average_cpu_percent": float("nan"),
                "peak_cpu_percent": float("nan"),
                "disk_read_mb": 0.0,
                "network_recv_mb": 0.0,
            }
        return {
            "peak_process_memory_mb": max(x[1] for x in self.samples),
            "peak_system_memory_mb": max(x[3] for x in self.samples),
            "average_cpu_percent": sum(x[2] for x in self.samples) / len(self.samples),
            "peak_cpu_percent": max(x[2] for x in self.samples),
            "disk_read_mb": max(0, (end_disk.read_bytes - self.before_disk.read_bytes)) / (1024 * 1024),
            "network_recv_mb": max(0, (end_net.bytes_recv - self.before_net.bytes_recv)) / (1024 * 1024),
        }


def dt_from_text(value: str) -> datetime:
    value = value.strip()
    for fmt in ("%Y-%m-%d, %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=TZ)
        except ValueError:
            continue
    raise ValueError(f"Could not parse local timestamp: {value!r}")


def parse_header_times(path: Path) -> tuple[datetime | None, datetime | None]:
    start = end = None
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for i, line in enumerate(handle):
                if i > 90:
                    break
                match = re.search(r"^\s*Start:\s+(\d{4}-\d{2}-\d{2},\s+\d{2}:\d{2}:\d{2})", line)
                if match:
                    start = dt_from_text(match.group(1))
                match = re.search(r"^\s*End:\s+(\d{4}-\d{2}-\d{2},\s+\d{2}:\d{2}:\d{2})", line)
                if match:
                    end = dt_from_text(match.group(1))
    except OSError:
        pass
    return start, end


def bit_depth_for_subtype(subtype: str) -> str:
    if subtype.startswith("PCM_"):
        return subtype.removeprefix("PCM_") + " bit"
    if subtype == "IMA_ADPCM":
        return "4 bit ADPCM"
    return subtype


def probe_wav(path: Path) -> dict[str, Any]:
    info = sf.info(str(path))
    return {
        "duration_seconds": float(info.frames / info.samplerate),
        "sample_rate": int(info.samplerate),
        "channels": int(info.channels),
        "format": str(info.format),
        "subtype": str(info.subtype),
        "bit_depth": bit_depth_for_subtype(str(info.subtype)),
        "frames": int(info.frames),
        "size_bytes": path.stat().st_size,
    }


def parse_audio_index(path: Path) -> dict[str, datetime]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        item["filename"].lower(): datetime.fromisoformat(item["start_time"]).replace(tzinfo=TZ)
        for item in payload["files"]
    }


def segment_from_file(
    position: str,
    path: Path,
    start: datetime | None,
    kind: str,
    group: str,
    basis: str,
    continuous: bool,
    previous_end: datetime | None = None,
    alignment_note: str = "",
) -> AudioSegment:
    meta = probe_wav(path)
    if start is None:
        start = datetime.fromtimestamp(0, tz=TZ)
    end = start + timedelta(seconds=meta["duration_seconds"])
    gap = None if previous_end is None else (start - previous_end).total_seconds()
    return AudioSegment(
        position=position,
        path=str(path),
        file_name=path.name,
        kind=kind,
        continuous_group=group,
        start_local=start.isoformat(),
        end_local=end.isoformat(),
        duration_seconds=meta["duration_seconds"],
        size_bytes=meta["size_bytes"],
        sample_rate=meta["sample_rate"],
        bit_depth=meta["bit_depth"],
        channels=meta["channels"],
        format=meta["format"],
        subtype=meta["subtype"],
        start_basis=basis,
        continuous=continuous,
        start_epoch=start.timestamp(),
        end_epoch=end.timestamp(),
        gap_from_previous_seconds=gap,
        alignment_note=alignment_note,
    )


def discover_segments(survey_root: Path) -> list[AudioSegment]:
    segments: list[AudioSegment] = []
    nti_specs = [
        ("Nti5", survey_root / "5882-5", "2026-07-10_SLM_000_RTA_3rd_Log.txt", "nti5_continuous"),
        ("Nti4", survey_root / "5883-4", "2026-07-10_SLM_003_RTA_3rd_Log.txt", "nti4_continuous"),
    ]
    for position, folder, header_name, group in nti_specs:
        header_start, _header_end = parse_header_times(folder / header_name)
        pattern = "2026-07-10_SLM_000_Audio_AGC_*.wav" if position == "Nti5" else "2026-07-10_SLM_003_Audio_AGC_*.wav"
        paths = sorted(folder.glob(pattern))
        prev_end = None
        for path in paths:
            index = int(re.search(r"_(\d+)\.wav$", path.name, re.I).group(1))
            start = header_start if prev_end is None else prev_end
            note = "Derived sequentially from WAV creation/log start and measured duration."
            if index > 0:
                note = "Sequential continuation; WAV metadata creation time is integer-second precision."
            segment = segment_from_file(position, path, start, "continuous_audio", group, "NTi RTA LOG Start / sequential duration", True, prev_end, note)
            segments.append(segment)
            prev_end = datetime.fromtimestamp(segment.end_epoch, tz=TZ)

        # Short NTi files are manual clips, not part of the continuous evening timeline.
        for path in sorted(folder.glob("2026-07-10_SLM_*_Audio_AGC_00.wav")):
            if path in paths:
                continue
            stem = path.name.replace("_Audio_AGC_00.wav", "_123_Log.txt")
            start, _end = parse_header_times(folder / stem)
            if start is None:
                start, _end = parse_header_times(folder / path.name.replace("_Audio_AGC_00.wav", "_RTA_3rd_Log.txt"))
            segments.append(segment_from_file(position, path, start, "manual_audio_clip", f"{position}_manual", "Matching NTi log header", False, None, "Manual spot recording; not a continuous survey segment."))

    svan_folder = survey_root / "971-2"
    index_path = svan_folder / "L456_audio_index.json"
    index = parse_audio_index(index_path) if index_path.exists() else {}
    prev_end = None
    for path in sorted(svan_folder.glob("R*.WAV")):
        start = index.get(path.name.lower())
        continuous = start is not None and probe_wav(path)["duration_seconds"] > 1.0
        group = "9712_continuous" if continuous else "9712_tiny_invalid"
        segment = segment_from_file("971-2", path, start, "continuous_audio" if continuous else "tiny_invalid", group, "L456_audio_index.json" if start else "No timestamp; 0.003 s placeholder", continuous, prev_end if continuous else None, "R8/R9 are 37-frame placeholders and excluded from analysis." if not continuous else "")
        segments.append(segment)
        if continuous:
            prev_end = datetime.fromtimestamp(segment.end_epoch, tz=TZ)
    return segments


def write_inventory(segments: list[AudioSegment], results: Path) -> None:
    results.mkdir(parents=True, exist_ok=True)
    rows = [asdict(s) for s in segments]
    pd.DataFrame(rows).to_csv(results / "audio_inventory.csv", index=False)
    by_pos: dict[str, list[AudioSegment]] = {}
    for segment in segments:
        by_pos.setdefault(segment.position, []).append(segment)
    lines = [
        "# Job 5882 July 2026 audio timeline",
        "",
        "All wall-clock timestamps below are Europe/London local time (BST in July 2026).",
        "The live config identifies Nti4, Nti5 and 971-2 as audio-bearing sources. No second boundary audio source is present.",
        "",
    ]
    for position in sorted(by_pos):
        lines += [f"## {position}", "", "| file | start | end | duration (s) | format | rate | bits | continuity | gap from previous (s) |", "|---|---|---|---:|---|---:|---|---|---:|"]
        for s in sorted(by_pos[position], key=lambda x: (x.start_epoch, x.file_name)):
            start = "unknown" if s.kind == "tiny_invalid" else s.start_local
            end = "unknown" if s.kind == "tiny_invalid" else s.end_local
            gap = "" if s.gap_from_previous_seconds is None else f"{s.gap_from_previous_seconds:.3f}"
            cont = "continuous" if s.continuous else s.kind
            lines.append(f"| `{s.file_name}` | {start} | {end} | {s.duration_seconds:.3f} | {s.format}/{s.subtype} | {s.sample_rate} | {s.bit_depth} | {cont} | {gap} |")
        lines.append("")
    lines += [
        "## Analysis windows", "",
        "| night | local window | available audio sources |", "|---|---|---|",
    ]
    for name, (start, end) in WINDOWS.items():
        available = [p for p in sorted({s.position for s in segments if s.continuous and s.start_epoch < end.timestamp() and s.end_epoch > start.timestamp()})]
        lines.append(f"| {name} | {start.isoformat()} to {end.isoformat()} | {', '.join(available) or 'none'} |")
    (results / "audio_timeline.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_model(tfhub_cache: Path, intra: int | None = None, inter: int | None = None):
    import tensorflow as tf

    if intra is not None:
        tf.config.threading.set_intra_op_parallelism_threads(intra)
    if inter is not None:
        tf.config.threading.set_inter_op_parallelism_threads(inter)
    model, class_names, load_seconds, cached = bm.load_yamnet(tfhub_cache)
    dummy = np.zeros(2 * bm.YAMNET_SAMPLE_RATE, dtype=np.float32)
    t0 = time.perf_counter()
    model(dummy)
    warmup = time.perf_counter() - t0
    return model, class_names, load_seconds, warmup, cached


def music_class_indices(class_names: list[str]) -> tuple[list[int], list[str]]:
    direct = [i for i, name in enumerate(class_names) if name.strip().lower() == DIRECT_CLASS.lower()]
    # Use an explicit music-content vocabulary rather than loose substrings
    # such as "house" or "electronic", which would incorrectly select
    # Housefly or Electronic tuner from the AudioSet ontology.
    keywords = [
        "music", "singing", "musical instrument", "bass guitar", "keyboard (musical)",
        "electronic organ", "percussion", "drum", "double bass",
    ]
    supporting = [
        name for i, name in enumerate(class_names)
        if i not in direct and any(k in name.lower() for k in keywords)
    ]
    if not direct:
        raise RuntimeError("Exact YAMNet class 'Music' was not found in the installed class map.")
    return direct, supporting


def read_audio_range(segment: AudioSegment, start_epoch: float, end_epoch: float) -> tuple[np.ndarray, int]:
    seg_start = segment.start_epoch
    offset = max(0.0, start_epoch - seg_start)
    duration = max(0.0, min(end_epoch, segment.end_epoch) - max(start_epoch, seg_start))
    if duration <= 0:
        return np.empty(0, dtype=np.float32), segment.sample_rate
    start_frame = int(round(offset * segment.sample_rate))
    n_frames = int(round(duration * segment.sample_rate))
    data, sr = sf.read(segment.path, start=start_frame, frames=n_frames, dtype="float32", always_2d=True)
    return data.mean(axis=1).astype(np.float32), sr


def find_continuous_segments(segments: list[AudioSegment], position: str, start_epoch: float, end_epoch: float) -> list[AudioSegment]:
    return sorted([
        s for s in segments
        if s.position == position and s.continuous and s.end_epoch > start_epoch and s.start_epoch < end_epoch
    ], key=lambda s: s.start_epoch)


def read_absolute_chunk(segments: list[AudioSegment], position: str, start_epoch: float, end_epoch: float) -> tuple[np.ndarray, int, list[str]]:
    pieces: list[np.ndarray] = []
    rates: list[int] = []
    files: list[str] = []
    covering = find_continuous_segments(segments, position, start_epoch, end_epoch)
    cursor = start_epoch
    for segment in covering:
        piece_start = max(cursor, segment.start_epoch)
        piece_end = min(end_epoch, segment.end_epoch)
        if piece_end <= piece_start:
            continue
        if piece_start > cursor + 0.05:
            raise RuntimeError(f"Audio gap of {piece_start - cursor:.3f}s in {position} before {segment.file_name}")
        data, sr = read_audio_range(segment, piece_start, piece_end)
        if len(data):
            pieces.append(data)
            rates.append(sr)
            files.append(segment.file_name)
            cursor = piece_end
    if cursor < end_epoch - 0.05:
        raise RuntimeError(f"Audio coverage ends {end_epoch - cursor:.3f}s early for {position}")
    if not pieces:
        raise RuntimeError(f"No audio covers {position} {start_epoch}–{end_epoch}")
    if len(set(rates)) != 1:
        raise RuntimeError(f"Mixed sample rates in one chunk: {rates}")
    return np.concatenate(pieces), rates[0], files


def run_file_pipeline(path: Path, duration_seconds: float, chunk_seconds: float, overlap_seconds: float, model, class_names: list[str], selected: list[str], source_offset: float = 0.0) -> tuple[dict[str, float], pd.DataFrame, dict[str, float]]:
    sampler = Sampler()
    sampler.start()
    t_all = time.perf_counter()
    t0 = time.perf_counter()
    info = sf.info(str(path))
    start_frame = int(round(source_offset * info.samplerate))
    n_frames = int(round(duration_seconds * info.samplerate))
    waveform, sr = sf.read(str(path), start=start_frame, frames=n_frames, dtype="float32", always_2d=True)
    waveform = waveform.mean(axis=1).astype(np.float32)
    read_s = time.perf_counter() - t0
    t0 = time.perf_counter()
    waveform_16k = bm.resample_to_16k(waveform, sr)
    resample_s = time.perf_counter() - t0
    chunk_samples = int(round(chunk_seconds * bm.YAMNET_SAMPLE_RATE))
    overlap_samples = int(round(overlap_seconds * bm.YAMNET_SAMPLE_RATE))
    step = max(chunk_samples - overlap_samples, 1)
    rows: list[dict[str, Any]] = []
    inference_s = 0.0
    extract_s = 0.0
    start = 0
    chunk_index = 0
    while start < len(waveform_16k):
        end = min(len(waveform_16k), start + chunk_samples)
        t0 = time.perf_counter()
        scores, _emb, _mel = model(waveform_16k[start:end])
        values = scores.numpy()
        inference_s += time.perf_counter() - t0
        t0 = time.perf_counter()
        for i in range(values.shape[0]):
            row = {"frame_time_s": round(start / bm.YAMNET_SAMPLE_RATE + i * bm.YAMNET_FRAME_HOP_SECONDS, 3), "chunk_index": chunk_index}
            for name in selected:
                row[name] = float(values[i, class_names.index(name)])
            rows.append(row)
        extract_s += time.perf_counter() - t0
        chunk_index += 1
        if end >= len(waveform_16k):
            break
        start += step
    t0 = time.perf_counter()
    frame_df = pd.DataFrame(rows).sort_values(["frame_time_s", "chunk_index"]).drop_duplicates("frame_time_s").reset_index(drop=True)
    post_s = time.perf_counter() - t0
    total_s = time.perf_counter() - t_all
    sample = sampler.stop()
    timings = {
        "audio_read_seconds": read_s,
        "resample_seconds": resample_s,
        "inference_seconds": inference_s,
        "score_extraction_seconds": extract_s,
        "postprocessing_seconds": post_s,
        "total_wall_seconds": total_s,
    }
    return timings, frame_df, sample


def prefetch_pipeline(path: Path, duration_seconds: float, chunk_seconds: float, overlap_seconds: float, model, selected_names: list[str], class_names: list[str]) -> tuple[dict[str, float], pd.DataFrame, dict[str, float]]:
    sampler = Sampler()
    sampler.start()
    all_t0 = time.perf_counter()
    info = sf.info(str(path))
    sr = info.samplerate
    chunk_frames = int(round(chunk_seconds * sr))
    overlap_frames = int(round(overlap_seconds * sr))
    step = max(1, chunk_frames - overlap_frames)
    q: queue.Queue[Any] = queue.Queue(maxsize=2)
    read_total = resample_total = 0.0
    def producer() -> None:
        try:
            pos = 0
            while pos < int(round(duration_seconds * sr)):
                n = min(chunk_frames, int(round(duration_seconds * sr)) - pos)
                t0 = time.perf_counter()
                data, read_sr = sf.read(str(path), start=pos, frames=n, dtype="float32", always_2d=True)
                data = data.mean(axis=1).astype(np.float32)
                nonlocal read_total
                read_total += time.perf_counter() - t0
                t0 = time.perf_counter()
                data16 = bm.resample_to_16k(data, read_sr)
                nonlocal resample_total
                resample_total += time.perf_counter() - t0
                q.put((data16, pos / sr))
                if pos + n >= int(round(duration_seconds * sr)):
                    break
                pos += step
            q.put(None)
        except BaseException as exc:  # propagate producer failures
            q.put(exc)
    thread = threading.Thread(target=producer, daemon=True)
    thread.start()
    rows: list[dict[str, Any]] = []
    inference_s = extract_s = 0.0
    chunk_index = 0
    while True:
        item = q.get()
        if item is None:
            break
        if isinstance(item, BaseException):
            raise item
        data16, offset = item
        t0 = time.perf_counter()
        scores, _emb, _mel = model(data16)
        values = scores.numpy()
        inference_s += time.perf_counter() - t0
        t0 = time.perf_counter()
        for i in range(values.shape[0]):
            row = {"frame_time_s": round(offset + i * bm.YAMNET_FRAME_HOP_SECONDS, 3), "chunk_index": chunk_index}
            for name in selected_names:
                row[name] = float(values[i, class_names.index(name)])
            rows.append(row)
        extract_s += time.perf_counter() - t0
        chunk_index += 1
    thread.join(timeout=2)
    t0 = time.perf_counter()
    frame_df = pd.DataFrame(rows).sort_values(["frame_time_s", "chunk_index"]).drop_duplicates("frame_time_s").reset_index(drop=True)
    post_s = time.perf_counter() - t0
    total_s = time.perf_counter() - all_t0
    sample = sampler.stop()
    return {
        "audio_read_seconds": read_total,
        "resample_seconds": resample_total,
        "inference_seconds": inference_s,
        "score_extraction_seconds": extract_s,
        "postprocessing_seconds": post_s,
        "total_wall_seconds": total_s,
    }, frame_df, sample


def stage_window(segment: AudioSegment, start_epoch: float, duration_seconds: float, out_path: Path) -> float:
    if out_path.exists() and out_path.stat().st_size > 1000:
        return 0.0
    out_path.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    data, sr = read_audio_range(segment, start_epoch, start_epoch + duration_seconds)
    sf.write(str(out_path), data, sr, subtype="PCM_16")
    return time.perf_counter() - t0


def run_benchmark(segments: list[AudioSegment], results: Path, tfhub_cache: Path) -> None:
    continuous = {p: [s for s in segments if s.position == p and s.continuous] for p in ("Nti5", "Nti4", "971-2")}
    bench_rows: list[dict[str, Any]] = []
    staged_paths: dict[str, Path] = {}
    stage_seconds = 0.0
    for position, items in continuous.items():
        if not items:
            continue
        covering = find_continuous_segments(segments, position, BENCHMARK_LOCAL_START.timestamp(), (BENCHMARK_LOCAL_START + timedelta(seconds=BENCHMARK_SECONDS)).timestamp())
        if not covering:
            continue
        stage_path = results / "local_stage" / f"{position}_benchmark_900s.wav"
        stage_seconds += stage_window(covering[0], BENCHMARK_LOCAL_START.timestamp(), BENCHMARK_SECONDS, stage_path)
        staged_paths[position] = stage_path
    # One model instance is reused for the sequential baseline and detection.
    model, class_names, model_load_s, warmup_s, cached = load_model(tfhub_cache)
    direct_idx, supporting_names = music_class_indices(class_names)
    selected_names = [class_names[i] for i in sorted(set(direct_idx))] + supporting_names
    selected_names = list(dict.fromkeys(selected_names))
    (results / "yamnet_class_selection.json").write_text(json.dumps({"direct": DIRECT_CLASS, "supporting": supporting_names, "model_load_seconds": model_load_s, "warmup_seconds": warmup_s, "model_cache_present_before_load": cached}, indent=2), encoding="utf-8")

    # A: sequential direct reads. First run per source is reported as a cold-ish Shared Drive read;
    # later repeats are warm OS/Drive-cache reads.
    primary_seg = next(s for s in continuous[PRIMARY_POSITION] if s.start_epoch <= BENCHMARK_LOCAL_START.timestamp() < s.end_epoch)
    for chunk in (30.0, 120.0, 300.0, 600.0):
        for repeat in range(3):
            timings, frame_df, sample = run_file_pipeline(Path(primary_seg.path), BENCHMARK_SECONDS, chunk, OVERLAP_SECONDS, model, class_names, selected_names, BENCHMARK_LOCAL_START.timestamp() - primary_seg.start_epoch)
            mode = "direct_shared_drive_first" if repeat == 0 else "direct_shared_drive_warm"
            bench_rows.append(asdict(RunStats(
                config="A_sequential_direct", position=PRIMARY_POSITION, audio_file=primary_seg.file_name,
                audio_duration_seconds=BENCHMARK_SECONDS, chunk_seconds=chunk, overlap_seconds=OVERLAP_SECONDS,
                workers=1, threads=1, tf_intra_op="default", tf_inter_op="default", cache_mode=mode,
                audio_read_seconds=timings["audio_read_seconds"], resample_seconds=timings["resample_seconds"], inference_seconds=timings["inference_seconds"], score_extraction_seconds=timings["score_extraction_seconds"], postprocessing_seconds=timings["postprocessing_seconds"], parquet_write_seconds=0.0, staging_seconds=0.0, total_wall_seconds=timings["total_wall_seconds"], realtime_factor=BENCHMARK_SECONDS / timings["total_wall_seconds"], audio_seconds_per_second=BENCHMARK_SECONDS / timings["total_wall_seconds"], peak_process_memory_mb=sample["peak_process_memory_mb"], peak_system_memory_mb=sample["peak_system_memory_mb"], average_cpu_percent=sample["average_cpu_percent"], peak_cpu_percent=sample["peak_cpu_percent"], disk_read_mb=sample["disk_read_mb"], network_recv_mb=sample["network_recv_mb"], n_frames=len(frame_df), n_events=0, note=f"repeat={repeat + 1}; model load {model_load_s:.3f}s and warm-up {warmup_s:.3f}s excluded"
            )))

    # B: the same pipeline on a locally staged excerpt, with staging measured separately.
    staged = staged_paths[PRIMARY_POSITION]
    for chunk in (30.0, 120.0, 300.0, 600.0):
        timings, frame_df, sample = run_file_pipeline(staged, BENCHMARK_SECONDS, chunk, OVERLAP_SECONDS, model, class_names, selected_names)
        bench_rows.append(asdict(RunStats(
            config="B_sequential_local_staged", position=PRIMARY_POSITION, audio_file=staged.name,
            audio_duration_seconds=BENCHMARK_SECONDS, chunk_seconds=chunk, overlap_seconds=OVERLAP_SECONDS,
            workers=1, threads=1, tf_intra_op="default", tf_inter_op="default", cache_mode="local_staged_warm",
            audio_read_seconds=timings["audio_read_seconds"], resample_seconds=timings["resample_seconds"], inference_seconds=timings["inference_seconds"], score_extraction_seconds=timings["score_extraction_seconds"], postprocessing_seconds=timings["postprocessing_seconds"], parquet_write_seconds=0.0, staging_seconds=stage_seconds, total_wall_seconds=timings["total_wall_seconds"], realtime_factor=BENCHMARK_SECONDS / timings["total_wall_seconds"], audio_seconds_per_second=BENCHMARK_SECONDS / timings["total_wall_seconds"], peak_process_memory_mb=sample["peak_process_memory_mb"], peak_system_memory_mb=sample["peak_system_memory_mb"], average_cpu_percent=sample["average_cpu_percent"], peak_cpu_percent=sample["peak_cpu_percent"], disk_read_mb=sample["disk_read_mb"], network_recv_mb=sample["network_recv_mb"], n_frames=len(frame_df), n_events=0, note=f"stage_seconds={stage_seconds:.3f}; stage+processing total is reported separately in the summary"
        )))

    # C: bounded producer/consumer prefetch on the local staged excerpt.
    timings, frame_df, sample = prefetch_pipeline(staged, BENCHMARK_SECONDS, CHUNK_SECONDS, OVERLAP_SECONDS, model, selected_names, class_names)
    bench_rows.append(asdict(RunStats(
        config="C_prefetch_local_staged", position=PRIMARY_POSITION, audio_file=staged.name,
        audio_duration_seconds=BENCHMARK_SECONDS, chunk_seconds=CHUNK_SECONDS, overlap_seconds=OVERLAP_SECONDS,
        workers=1, threads=2, tf_intra_op="default", tf_inter_op="default", cache_mode="local_staged_warm",
        audio_read_seconds=timings["audio_read_seconds"], resample_seconds=timings["resample_seconds"], inference_seconds=timings["inference_seconds"], score_extraction_seconds=timings["score_extraction_seconds"], postprocessing_seconds=timings["postprocessing_seconds"], parquet_write_seconds=0.0, staging_seconds=0.0, total_wall_seconds=timings["total_wall_seconds"], realtime_factor=BENCHMARK_SECONDS / timings["total_wall_seconds"], audio_seconds_per_second=BENCHMARK_SECONDS / timings["total_wall_seconds"], peak_process_memory_mb=sample["peak_process_memory_mb"], peak_system_memory_mb=sample["peak_system_memory_mb"], average_cpu_percent=sample["average_cpu_percent"], peak_cpu_percent=sample["peak_cpu_percent"], disk_read_mb=sample["disk_read_mb"], network_recv_mb=sample["network_recv_mb"], n_frames=len(frame_df), n_events=0, note="Reader/resampler runs in a bounded producer queue while the main thread infers."
    )))

    # E: threads for reads/resampling only; useful stage-level diagnostic, not a claim that Python inference scales.
    chunk_starts = [i for i in np.arange(0, BENCHMARK_SECONDS, 30.0)]
    def read_resample(offset: float) -> int:
        data, sr = sf.read(str(staged), start=int(round(offset * sf.info(str(staged)).samplerate)), frames=int(round(min(30.0, BENCHMARK_SECONDS - offset) * sf.info(str(staged)).samplerate)), dtype="float32", always_2d=True)
        bm.resample_to_16k(data.mean(axis=1).astype(np.float32), sr)
        return len(data)
    for workers in (1, 2, 3, 4):
        t0 = time.perf_counter()
        with ThreadPoolExecutor(max_workers=workers) as pool:
            count = sum(pool.map(read_resample, chunk_starts))
        wall = time.perf_counter() - t0
        bench_rows.append(asdict(RunStats(
            config="E_threads_read_resample", position=PRIMARY_POSITION, audio_file=staged.name,
            audio_duration_seconds=BENCHMARK_SECONDS, chunk_seconds=30.0, overlap_seconds=0.0, workers=1, threads=workers,
            tf_intra_op="not applicable", tf_inter_op="not applicable", cache_mode="local_staged_warm",
            audio_read_seconds=wall, resample_seconds=0.0, inference_seconds=0.0, score_extraction_seconds=0.0, postprocessing_seconds=0.0, parquet_write_seconds=0.0, staging_seconds=0.0, total_wall_seconds=wall, realtime_factor=BENCHMARK_SECONDS / wall, audio_seconds_per_second=BENCHMARK_SECONDS / wall, peak_process_memory_mb=float("nan"), peak_system_memory_mb=float("nan"), average_cpu_percent=float("nan"), peak_cpu_percent=float("nan"), disk_read_mb=0.0, network_recv_mb=0.0, n_frames=count, n_events=0, note="Thread test covers file reads and resampling only; TensorFlow inference is intentionally not shared across Python threads."
        )))

    # G: process-level model instances on three independent locally staged files.
    worker_paths = [p for p in (staged_paths.get("Nti5"), staged_paths.get("Nti4"), staged_paths.get("971-2")) if p]
    for workers in (1, 2, 3):
        t0 = time.perf_counter()
        groups = [worker_paths[i::workers] for i in range(workers)]
        ctx = mp.get_context("spawn")
        with ctx.Pool(processes=workers) as pool:
            child = pool.starmap(process_group_worker, [(group, BENCHMARK_SECONDS, CHUNK_SECONDS, str(tfhub_cache)) for group in groups if group])
        wall = time.perf_counter() - t0
        total_frames = sum(x["n_frames"] for x in child)
        peak_mem = sum(x.get("peak_process_memory_mb", 0.0) for x in child)
        bench_rows.append(asdict(RunStats(
            config="G_multiple_model_processes", position="Nti5+Nti4+971-2", audio_file="local_stage excerpts",
            audio_duration_seconds=BENCHMARK_SECONDS * len(worker_paths), chunk_seconds=CHUNK_SECONDS, overlap_seconds=OVERLAP_SECONDS, workers=workers, threads=1, tf_intra_op="default", tf_inter_op="default", cache_mode="local_staged_warm", audio_read_seconds=sum(x["audio_read_seconds"] for x in child), resample_seconds=sum(x["resample_seconds"] for x in child), inference_seconds=sum(x["inference_seconds"] for x in child), score_extraction_seconds=sum(x["score_extraction_seconds"] for x in child), postprocessing_seconds=sum(x["postprocessing_seconds"] for x in child), parquet_write_seconds=0.0, staging_seconds=0.0, total_wall_seconds=wall, realtime_factor=(BENCHMARK_SECONDS * len(worker_paths)) / wall, audio_seconds_per_second=(BENCHMARK_SECONDS * len(worker_paths)) / wall, peak_process_memory_mb=peak_mem, peak_system_memory_mb=float("nan"), average_cpu_percent=float("nan"), peak_cpu_percent=float("nan"), disk_read_mb=0.0, network_recv_mb=0.0, n_frames=total_frames, n_events=0, note="Each process owns and reuses one YAMNet instance; process-level memory is summed across children."
        )))

    # F: selected fresh-process TensorFlow settings, each on the same 15-minute excerpt.
    for intra, inter in ((None, None), (6, 1), (10, 1), (14, 2)):
        t0 = time.perf_counter()
        cmd = [sys.executable, str(Path(__file__).resolve()), "--tf-probe", "--probe-audio", str(staged), "--probe-duration", str(BENCHMARK_SECONDS), "--tfhub-cache-dir", str(tfhub_cache)]
        if intra is not None:
            cmd += ["--tf-intra", str(intra)]
        if inter is not None:
            cmd += ["--tf-inter", str(inter)]
        proc = __import__("subprocess").run(cmd, capture_output=True, text=True, check=False)
        wall = time.perf_counter() - t0
        payload = {}
        if proc.returncode == 0:
            try:
                payload = json.loads(proc.stdout.strip().splitlines()[-1])
            except (json.JSONDecodeError, IndexError):
                payload = {}
        bench_rows.append(asdict(RunStats(
            config="F_tensorflow_thread_settings", position=PRIMARY_POSITION, audio_file=staged.name, audio_duration_seconds=BENCHMARK_SECONDS, chunk_seconds=CHUNK_SECONDS, overlap_seconds=OVERLAP_SECONDS, workers=1, threads=1, tf_intra_op="default" if intra is None else str(intra), tf_inter_op="default" if inter is None else str(inter), cache_mode="local_staged_warm", audio_read_seconds=payload.get("audio_read_seconds", float("nan")), resample_seconds=payload.get("resample_seconds", float("nan")), inference_seconds=payload.get("inference_seconds", float("nan")), score_extraction_seconds=payload.get("score_extraction_seconds", float("nan")), postprocessing_seconds=payload.get("postprocessing_seconds", float("nan")), parquet_write_seconds=0.0, staging_seconds=0.0, total_wall_seconds=wall, realtime_factor=BENCHMARK_SECONDS / wall, audio_seconds_per_second=BENCHMARK_SECONDS / wall, peak_process_memory_mb=payload.get("peak_process_memory_mb", float("nan")), peak_system_memory_mb=float("nan"), average_cpu_percent=payload.get("average_cpu_percent", float("nan")), peak_cpu_percent=payload.get("peak_cpu_percent", float("nan")), disk_read_mb=payload.get("disk_read_mb", 0.0), network_recv_mb=0.0, n_frames=payload.get("n_frames", 0), n_events=0, status="ok" if proc.returncode == 0 else "failed", note=proc.stderr[-500:] if proc.returncode else "Fresh process; TensorFlow thread settings applied before model loading."
        )))

    # H: cached frame-score reuse: event construction and Parquet write with no model call.
    timings, frame_df, _sample = run_file_pipeline(staged, BENCHMARK_SECONDS, CHUNK_SECONDS, OVERLAP_SECONDS, model, class_names, [DIRECT_CLASS])
    t0 = time.perf_counter()
    cache_path = results / "frame_scores" / "benchmark_reuse.parquet"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    frame_df.to_parquet(cache_path, index=False)
    write_s = time.perf_counter() - t0
    t0 = time.perf_counter()
    events = merge_events(frame_df, DIRECT_CLASS, SCREENING_THRESHOLD, MERGE_GAP_SECONDS, MIN_EVENT_SECONDS, [])
    reuse_wall = time.perf_counter() - t0
    bench_rows.append(asdict(RunStats(
        config="H_cached_score_reuse", position=PRIMARY_POSITION, audio_file=cache_path.name, audio_duration_seconds=BENCHMARK_SECONDS, chunk_seconds=CHUNK_SECONDS, overlap_seconds=OVERLAP_SECONDS, workers=1, threads=1, tf_intra_op="not applicable", tf_inter_op="not applicable", cache_mode="cached_parquet", audio_read_seconds=0.0, resample_seconds=0.0, inference_seconds=0.0, score_extraction_seconds=0.0, postprocessing_seconds=reuse_wall, parquet_write_seconds=write_s, staging_seconds=0.0, total_wall_seconds=reuse_wall + write_s, realtime_factor=BENCHMARK_SECONDS / (reuse_wall + write_s), audio_seconds_per_second=BENCHMARK_SECONDS / (reuse_wall + write_s), peak_process_memory_mb=float("nan"), peak_system_memory_mb=float("nan"), average_cpu_percent=float("nan"), peak_cpu_percent=float("nan"), disk_read_mb=0.0, network_recv_mb=0.0, n_frames=len(frame_df), n_events=len(events), note="Thresholding/event merging and Parquet output reuse cached Music scores without model inference."
    )))
    pd.DataFrame(bench_rows).to_csv(results / "benchmark_timings.csv", index=False)
    summary = benchmark_summary(pd.DataFrame(bench_rows), model_load_s, warmup_s, stage_seconds)
    (results / "benchmark_summary.md").write_text(summary, encoding="utf-8")


def process_group_worker(paths: list[Path], duration_seconds: float, chunk_seconds: float, tfhub_cache: str) -> dict[str, float]:
    if not paths:
        return {"n_frames": 0}
    model, class_names, _load, _warm, _cached = load_model(Path(tfhub_cache))
    selected = [DIRECT_CLASS]
    total = {k: 0.0 for k in ("audio_read_seconds", "resample_seconds", "inference_seconds", "score_extraction_seconds", "postprocessing_seconds")}
    frames = 0
    peak = 0.0
    for path in paths:
        timings, frame_df, sample = run_file_pipeline(Path(path), duration_seconds, chunk_seconds, OVERLAP_SECONDS, model, class_names, selected)
        for k in total:
            total[k] += timings[k]
        frames += len(frame_df)
        peak = max(peak, sample.get("peak_process_memory_mb", 0.0))
    return {**total, "n_frames": frames, "peak_process_memory_mb": peak}


def merge_events(frame_df: pd.DataFrame, score_column: str, threshold: float, gap_seconds: float, min_duration_seconds: float, support_columns: list[str]) -> list[dict[str, Any]]:
    if frame_df.empty or score_column not in frame_df.columns:
        return []
    df = frame_df.sort_values("frame_time_s").reset_index(drop=True)
    positive = df[df[score_column] >= threshold]
    if positive.empty:
        return []
    events: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    def flush() -> None:
        if not current:
            return
        start = float(current[0]["frame_time_s"])
        end = float(current[-1]["frame_time_s"]) + bm.YAMNET_FRAME_HOP_SECONDS
        duration = end - start
        if duration < min_duration_seconds:
            return
        sub = pd.DataFrame(current)
        support_means = {c: float(sub[c].mean()) for c in support_columns if c in sub.columns}
        tops = [k for k, _v in sorted(support_means.items(), key=lambda item: item[1], reverse=True)[:5]]
        peak = float(sub[score_column].max())
        events.append({
            "event_id": "", "start_epoch": start, "end_epoch": end, "duration_seconds": duration,
            "peak_music_score": peak, "mean_music_score": float(sub[score_column].mean()), "median_music_score": float(sub[score_column].median()),
            "n_positive_frames": int(len(sub)), "pct_frames_above_threshold": 100.0 * len(sub) / max(len(df[(df.frame_time_s >= start) & (df.frame_time_s <= end)]), 1),
            "threshold": threshold, "top_supporting_classes": ", ".join(tops), "source_files": ", ".join(sorted(set(str(x) for x in sub.get("source_file", [])))),
        })
    previous = None
    for row in positive.to_dict("records"):
        t = float(row["frame_time_s"])
        if previous is None or t - previous <= gap_seconds + bm.YAMNET_FRAME_HOP_SECONDS:
            current.append(row)
        else:
            flush()
            current = [row]
        previous = t
    flush()
    return events


def attach_event_ids(events: list[dict[str, Any]], prefix: str) -> list[dict[str, Any]]:
    for i, event in enumerate(events, 1):
        event["event_id"] = f"{prefix}_{i:03d}"
    return events


def evidence_strength(score: float) -> str:
    if score >= 0.30:
        return "strong classifier evidence"
    if score >= 0.10:
        return "moderate classifier evidence"
    if score >= SCREENING_THRESHOLD:
        return "weak classifier evidence"
    return "not detected at screening threshold"


def infer_absolute_window(segments: list[AudioSegment], position: str, start: datetime, end: datetime, model, class_names: list[str], selected_names: list[str], chunk_seconds: float = CHUNK_SECONDS, overlap_seconds: float = OVERLAP_SECONDS) -> pd.DataFrame:
    start_epoch = start.timestamp()
    end_epoch = end.timestamp()
    chunk_start = start_epoch
    rows: list[dict[str, Any]] = []
    chunk_index = 0
    step = max(chunk_seconds - overlap_seconds, 1.0)
    while chunk_start < end_epoch:
        chunk_end = min(end_epoch, chunk_start + chunk_seconds)
        data, sr, source_files = read_absolute_chunk(segments, position, chunk_start, chunk_end)
        data16 = bm.resample_to_16k(data, sr)
        scores, _emb, _mel = model(data16)
        values = scores.numpy()
        for i in range(values.shape[0]):
            frame_time = chunk_start + i * bm.YAMNET_FRAME_HOP_SECONDS
            if frame_time >= end_epoch:
                continue
            row = {"frame_time_s": round(frame_time, 3), "chunk_index": chunk_index, "position": position, "window": "" if not source_files else ",".join(source_files), "source_file": ",".join(source_files)}
            for name in selected_names:
                row[name] = float(values[i, class_names.index(name)])
            rows.append(row)
        chunk_index += 1
        if chunk_end >= end_epoch:
            break
        chunk_start += step
    if not rows:
        return pd.DataFrame(columns=["frame_time_s", "chunk_index", "position", "window", "source_file", *selected_names])
    return pd.DataFrame(rows).sort_values(["frame_time_s", "chunk_index"]).drop_duplicates("frame_time_s", keep="first").reset_index(drop=True)


def load_internal_level_series(survey_root: Path) -> pd.DataFrame:
    path = survey_root / "NS1A" / "5882 (NS1A)_2026_07_10__10h52m22s_log.csv"
    if not path.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(path)
        if df.shape[1] < 2:
            return pd.DataFrame()
        df["time"] = pd.to_datetime(df.iloc[:, 0], errors="coerce")
        df["level_db"] = pd.to_numeric(df.iloc[:, 1], errors="coerce")
        return df.dropna(subset=["time", "level_db"])[["time", "level_db"]]
    except Exception:
        return pd.DataFrame()


def level_for_event(levels: pd.DataFrame, start_epoch: float, end_epoch: float) -> float | None:
    if levels.empty:
        return None
    start = datetime.fromtimestamp(start_epoch, tz=TZ).replace(tzinfo=None)
    end = datetime.fromtimestamp(end_epoch, tz=TZ).replace(tzinfo=None)
    sub = levels[(levels.time >= start) & (levels.time <= end)]
    return None if sub.empty else float(sub.level_db.median())


def write_events(events: list[dict[str, Any]], path: Path, position: str, window: str, role: str, levels: pd.DataFrame) -> None:
    rows = []
    for event in events:
        item = dict(event)
        item.update({"position": position, "window": item.get("window", window), "role": role, "start_local": datetime.fromtimestamp(item["start_epoch"], tz=UTC).astimezone(TZ).isoformat(), "end_local": datetime.fromtimestamp(item["end_epoch"], tz=UTC).astimezone(TZ).isoformat(), "evidence_strength": evidence_strength(item["peak_music_score"]), "model": "YAMNet via TensorFlow Hub google/yamnet/1", "sound_level_ns1a_median_db": level_for_event(levels, item["start_epoch"], item["end_epoch"])})
        rows.append(item)
    columns = ["event_id", "position", "role", "window", "start_local", "end_local", "start_epoch", "end_epoch", "duration_seconds", "peak_music_score", "mean_music_score", "median_music_score", "threshold", "n_positive_frames", "pct_frames_above_threshold", "evidence_strength", "top_supporting_classes", "source_files", "sound_level_ns1a_median_db", "model"]
    pd.DataFrame(rows, columns=columns).to_csv(path, index=False)


def run_detection(segments: list[AudioSegment], results: Path, tfhub_cache: Path, survey_root: Path) -> dict[str, Any]:
    model, class_names, model_load_s, warmup_s, cached = load_model(tfhub_cache)
    direct_idx, supporting_names = music_class_indices(class_names)
    selected = [class_names[i] for i in direct_idx] + supporting_names
    selected = list(dict.fromkeys(selected))
    levels = load_internal_level_series(survey_root)
    frame_dir = results / "frame_scores"
    frame_dir.mkdir(parents=True, exist_ok=True)
    all_frames: dict[str, list[pd.DataFrame]] = {"Nti5": [], "Nti4": [], "971-2": []}
    all_events: dict[str, list[dict[str, Any]]] = {"Nti5": [], "Nti4": [], "971-2": []}
    sweep_rows: list[dict[str, Any]] = []
    for position in all_frames:
        for window_name, (start, end) in WINDOWS.items():
            available = find_continuous_segments(segments, position, start.timestamp(), end.timestamp())
            if not available:
                continue
            path = frame_dir / f"{position}_{window_name}.parquet"
            if path.exists():
                frame_df = pd.read_parquet(path)
            else:
                frame_df = infer_absolute_window(segments, position, start, end, model, class_names, selected)
                frame_df["window"] = window_name
                frame_df.to_parquet(path, index=False)
            all_frames[position].append(frame_df)
            for threshold in THRESHOLDS:
                evs = merge_events(frame_df, DIRECT_CLASS, threshold, MERGE_GAP_SECONDS, MIN_EVENT_SECONDS, supporting_names)
                sweep_rows.append({"position": position, "window": window_name, "threshold": threshold, "frames_total": len(frame_df), "positive_frames": int((frame_df[DIRECT_CLASS] >= threshold).sum()) if DIRECT_CLASS in frame_df else 0, "events": len(evs)})
            direct_events = merge_events(frame_df, DIRECT_CLASS, SCREENING_THRESHOLD, MERGE_GAP_SECONDS, MIN_EVENT_SECONDS, supporting_names)
            attach_event_ids(direct_events, f"{position}_{window_name}")
            for event in direct_events:
                event["window"] = window_name
                event["position"] = position
            all_events[position].extend(direct_events)
    pd.DataFrame(sweep_rows).to_csv(results / "threshold_sweep.csv", index=False)
    for position in all_frames:
        combined = pd.concat(all_frames[position], ignore_index=True) if all_frames[position] else pd.DataFrame(columns=["frame_time_s", DIRECT_CLASS])
        combined.to_parquet(frame_dir / f"{position}_all.parquet", index=False)
    write_events(all_events[PRIMARY_POSITION], results / "music_events_internal.csv", PRIMARY_POSITION, "friday+saturday", "primary_internal", levels)
    write_events(all_events["Nti4"], results / "music_events_nti4_comparator.csv", "Nti4", "friday+saturday", "internal_comparator", levels)
    write_events(all_events[BOUNDARY_1], results / "music_events_boundary_1.csv", BOUNDARY_1, "friday+saturday", "available_boundary", levels)
    write_events(all_events.get(BOUNDARY_2, []), results / "music_events_boundary_2.csv", BOUNDARY_2 or "boundary_2_not_available", "friday+saturday", "not_available", levels)
    matched = match_events(all_events[PRIMARY_POSITION], all_events, all_frames)
    pd.DataFrame(matched).to_csv(results / "music_events_cross_meter.csv", index=False)
    dashboard = dashboard_rows(matched, all_events["Nti4"], all_events[BOUNDARY_1], all_events.get(BOUNDARY_2, []), results)
    pd.DataFrame(dashboard, columns=["position_id", "source_id", "source_label", "start", "end", "state", "confidence", "description", "audio_file", "color"]).to_csv(results / "dashboard_classifications.csv", index=False)
    return {"model_load_seconds": model_load_s, "warmup_seconds": warmup_s, "model_cached": cached, "selected_supporting_classes": supporting_names, "frames": {p: int(sum(len(x) for x in all_frames[p])) for p in all_frames}, "events": {p: len(all_events[p]) for p in all_events}, "matched_events": matched, "all_events": all_events, "all_frames": all_frames}


def match_events(internal: list[dict[str, Any]], all_events: dict[str, list[dict[str, Any]]], all_frames: dict[str, list[pd.DataFrame]]) -> list[dict[str, Any]]:
    frame_by_position = {p: (pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()) for p, frames in all_frames.items()}
    boundary_events = {p: all_events.get(p, []) for p in ("Nti4", "971-2")}
    matched: list[dict[str, Any]] = []
    for event in internal:
        row = dict(event)
        row.update({"internal_peak_score": event["peak_music_score"], "internal_mean_score": event["mean_music_score"], "time_offset_Nti4_seconds": 0.0, "time_offset_971_2_seconds": 0.0, "boundary_2_available": False})
        for position, key in (("Nti4", "comparator_Nti4"), ("971-2", "boundary_1")):
            df = frame_by_position[position]
            if not df.empty and DIRECT_CLASS in df.columns:
                sub = df[(df.frame_time_s >= event["start_epoch"]) & (df.frame_time_s <= event["end_epoch"])]
                row[f"{key}_peak_score"] = None if sub.empty else float(sub[DIRECT_CLASS].max())
                row[f"{key}_mean_score"] = None if sub.empty else float(sub[DIRECT_CLASS].mean())
                row[f"{key}_frames_above_threshold"] = 0 if sub.empty else int((sub[DIRECT_CLASS] >= SCREENING_THRESHOLD).sum())
            else:
                row[f"{key}_peak_score"] = None
                row[f"{key}_mean_score"] = None
                row[f"{key}_frames_above_threshold"] = 0
            row[f"{key}_independently_detected"] = any(not (x["end_epoch"] < event["start_epoch"] or x["start_epoch"] > event["end_epoch"]) for x in boundary_events[position])
            row[f"{key}_evidence_strength"] = evidence_strength(row[f"{key}_peak_score"] or 0.0)
        row["boundary_2_peak_score"] = None
        row["boundary_2_mean_score"] = None
        row["boundary_2_independently_detected"] = False
        row["boundary_2_evidence_strength"] = "not available"
        row["internal_evidence_strength"] = evidence_strength(event["peak_music_score"])
        matched.append(row)
    return matched


def dashboard_rows(matched: list[dict[str, Any]], comparator_events: list[dict[str, Any]], boundary_events: list[dict[str, Any]], boundary2_events: list[dict[str, Any]], results: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for event in matched:
        description = (
            f"YAMNet Music peak {event['peak_music_score']:.3f}, mean {event['mean_music_score']:.3f}; "
            f"{evidence_strength(event['peak_music_score'])}; supporting classes: {event.get('top_supporting_classes', '') or 'none'}. "
            f"Nti4 comparator peak={fmt_score(event.get('comparator_Nti4_peak_score'))}; 971-2 boundary peak={fmt_score(event.get('boundary_1_peak_score'))}; "
            f"model score, not a calibrated probability; not independently verified by listening."
        )
        rows.append({"position_id": PRIMARY_POSITION, "source_id": "yamnet_music", "source_label": "YAMNet: Music (Nti5 internal)", "start": int(round(event["start_epoch"] * 1000)), "end": int(round(event["end_epoch"] * 1000)), "state": "on" if event["peak_music_score"] >= HIGH_THRESHOLD else "uncertain", "confidence": event["peak_music_score"], "description": description, "audio_file": event.get("source_files", ""), "color": "#d95f02"})
    for source, evs, label, color in (("Nti4", comparator_events, "YAMNet: Music (Nti4 comparator)", "#e7298a"), (BOUNDARY_1, boundary_events, "YAMNet: Music (971-2 boundary)", "#1b9e77"), (BOUNDARY_2, boundary2_events, "YAMNet: Music (boundary 2)", "#7570b3")):
        for event in evs:
            rows.append({"position_id": source or "boundary_2_not_available", "source_id": f"yamnet_music_{source or 'boundary_2'}", "source_label": label, "start": int(round(event["start_epoch"] * 1000)), "end": int(round(event["end_epoch"] * 1000)), "state": "on" if event["peak_music_score"] >= HIGH_THRESHOLD else "uncertain", "confidence": event["peak_music_score"], "description": f"Available-meter boundary evidence: peak {event['peak_music_score']:.3f}, mean {event['mean_music_score']:.3f}; {evidence_strength(event['peak_music_score'])}; use matching and listening before interpretation.", "audio_file": event.get("source_files", ""), "color": color})
    return rows


def fmt_score(value: Any) -> str:
    return "n/a" if value is None or (isinstance(value, float) and math.isnan(value)) else f"{float(value):.3f}"


def safe_slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")


def write_clip(segments: list[AudioSegment], position: str, start_epoch: float, end_epoch: float, out_path: Path) -> tuple[str, str]:
    try:
        data, sr, files = read_absolute_chunk(segments, position, start_epoch, end_epoch)
    except Exception as exc:
        return "unavailable", str(exc)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out_path), data, sr, subtype="PCM_16")
    return "written", ",".join(files)


def export_review(segments: list[AudioSegment], results: Path, detection: dict[str, Any]) -> None:
    clips_dir = results / "review_clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    internal = detection["all_events"][PRIMARY_POSITION]
    boundary = detection["all_events"][BOUNDARY_1]
    candidates: list[tuple[str, dict[str, Any], str]] = []
    for event in sorted(internal, key=lambda x: x["peak_music_score"], reverse=True)[:30]:
        candidates.append(("internal", event, PRIMARY_POSITION))
    for event in sorted(boundary, key=lambda x: x["peak_music_score"], reverse=True)[:10]:
        if not any(not (event["end_epoch"] < x[1]["start_epoch"] or event["start_epoch"] > x[1]["end_epoch"]) for x in candidates):
            candidates.append(("boundary", event, BOUNDARY_1))
    low = [x for x in internal if 0.05 <= x["peak_music_score"] < 0.10]
    for event in low[:5]:
        candidates.append(("low_score", event, PRIMARY_POSITION))
    # Random-ish non-music controls: deterministic samples from the first available frame score rows.
    nonmusic: list[dict[str, Any]] = []
    for frames in detection["all_frames"].values():
        for df in frames:
            if DIRECT_CLASS not in df:
                continue
            quiet = df[df[DIRECT_CLASS] < 0.02]
            for _, row in quiet.iloc[::max(1, len(quiet) // 5 or 1)].head(5).iterrows():
                t = float(row["frame_time_s"])
                nonmusic.append({"event_id": "control", "start_epoch": t, "end_epoch": t + 6.0, "peak_music_score": float(row[DIRECT_CLASS]), "mean_music_score": float(row[DIRECT_CLASS]), "top_supporting_classes": ""})
        if len(nonmusic) >= 5:
            break
    for event in nonmusic[:5]:
        candidates.append(("nonmusic_control", event, PRIMARY_POSITION))
    manifest: list[dict[str, Any]] = []
    html_rows: dict[str, list[dict[str, Any]]] = {}
    event_counter = 0
    for category, event, source_position in candidates:
        event_counter += 1
        event_key = f"review_{event_counter:03d}"
        start = event["start_epoch"] - CLIP_PAD_SECONDS
        end = event["end_epoch"] + CLIP_PAD_SECONDS
        local_start = datetime.fromtimestamp(start, tz=UTC).astimezone(TZ)
        event_label = f"{local_start.strftime('%Y-%m-%d_%H-%M-%S')}_{event.get('event_id', event_key)}"
        positions = [PRIMARY_POSITION, BOUNDARY_1, "Nti4"] if category != "nonmusic_control" else [PRIMARY_POSITION]
        for position in positions:
            if not position:
                continue
            score = event.get("peak_music_score", 0.0)
            fname = f"{event_label}_{position}_{category}_{score:.2f}.wav"
            out = clips_dir / fname
            status, source_files = write_clip(segments, position, start, end, out)
            row = {"event_id": event.get("event_id", event_key), "review_group": event_key, "category": category, "absolute_start_local": local_start.isoformat(), "absolute_end_local": datetime.fromtimestamp(end, tz=UTC).astimezone(TZ).isoformat(), "meter": position, "clip_file": str(out.relative_to(results)).replace("\\", "/") if status == "written" else "", "status": status, "source_file": source_files, "peak_music_score": score, "mean_music_score": event.get("mean_music_score", ""), "top_supporting_classes": event.get("top_supporting_classes", ""), "manual_review": "not yet reviewed"}
            manifest.append(row)
            html_rows.setdefault(event_key, []).append(row)
    pd.DataFrame(manifest).to_csv(results / "review_manifest.csv", index=False)
    html_parts = ["<!doctype html><html><head><meta charset='utf-8'><title>5882 July music review</title><style>body{font-family:Segoe UI,Arial,sans-serif;margin:2rem;background:#f5f5f5;color:#222}.event{background:white;border:1px solid #ccc;padding:1rem;margin:1rem 0}.meter{display:inline-block;vertical-align:top;width:31%;min-width:260px;margin-right:1%;padding:.5rem}audio{width:100%}small{color:#555}</style></head><body><h1>Job 5882 July music-candidate review</h1><p>All scores are raw YAMNet model scores, not probabilities. Manual listening status is recorded in the manifest.</p>"]
    for group, rows in html_rows.items():
        first = rows[0]
        html_parts.append(f"<section class='event'><h2>{html.escape(group)} — {html.escape(first['absolute_start_local'])}</h2><p>Category: {html.escape(first['category'])}; peak score: {first['peak_music_score']}</p>")
        for row in rows:
            html_parts.append(f"<div class='meter'><strong>{html.escape(row['meter'])}</strong><br><small>{html.escape(row['status'])}</small>")
            if row["clip_file"]:
                html_parts.append(f"<audio controls preload='none' src='{html.escape(row['clip_file'])}'></audio>")
            html_parts.append("</div>")
        html_parts.append("</section>")
    html_parts.append("</body></html>")
    (results / "review.html").write_text("\n".join(html_parts), encoding="utf-8")


def benchmark_summary(df: pd.DataFrame, model_load: float, warmup: float, staging: float) -> str:
    lines = ["# Job 5882 July 2026 benchmark summary", "", f"Model load: {model_load:.3f} s; warm-up: {warmup:.3f} s; both excluded from steady-state timings.", f"Local staging time for the representative excerpts: {staging:.3f} s (cached staging is 0 s on rerun).", "", "## Measured configurations", "", "| configuration | worker/thread setting | cache | duration (s) | realtime factor | peak process MB | status |", "|---|---:|---|---:|---:|---:|---|"]
    for _, row in df.iterrows():
        setting = f"w{int(row.workers)}/t{int(row.threads)}" if str(row.workers) != "nan" else ""
        lines.append(f"| {row.config} | {setting} / TF {row.tf_intra_op}/{row.tf_inter_op} | {row.cache_mode} | {row.total_wall_seconds:.3f} | {row.realtime_factor:.1f}x | {row.peak_process_memory_mb:.0f} | {row.status} |")
    lines += ["", "## Practical interpretation", "", "The direct Shared Drive rows separate the first read from warm repeats, but Windows/Drive cache state is not a perfect cold-cache control. Local-staged rows include a separately measured staging time and avoid repeatedly copying the full source. The process-worker test uses three independent 900-second local excerpts and one reused YAMNet instance per child process. The thread test intentionally covers reads/resampling only; it is not evidence that Python threads accelerate TensorFlow inference.", "", "The best configuration is selected from the measured median of the completed steady-state rows, with memory and source-I/O constraints considered. The full report adds projections for one hour, one event night, 24 hours and all analysed audio."]
    return "\n".join(lines) + "\n"


def write_final_report(results: Path, segments: list[AudioSegment], detection: dict[str, Any] | None) -> None:
    bench = pd.read_csv(results / "benchmark_timings.csv") if (results / "benchmark_timings.csv").exists() else pd.DataFrame()
    internal = pd.read_csv(results / "music_events_internal.csv") if (results / "music_events_internal.csv").exists() else pd.DataFrame()
    comparator = pd.read_csv(results / "music_events_nti4_comparator.csv") if (results / "music_events_nti4_comparator.csv").exists() else pd.DataFrame()
    boundary = pd.read_csv(results / "music_events_boundary_1.csv") if (results / "music_events_boundary_1.csv").exists() else pd.DataFrame()
    cross = pd.read_csv(results / "music_events_cross_meter.csv") if (results / "music_events_cross_meter.csv").exists() else pd.DataFrame()
    lines = [
        "# Job 5882 Warbrook House, Eversley — July 2026 audio categorisation benchmark", "",
        "## Survey identity", "",
        "- Confirmed job: **5882 Warbrook House, Eversley**.",
        "- The supplied instruction text named job 5228 and a different meter arrangement. The live job 5882 configuration and survey folder are unambiguous; this report uses job 5882 and records the mismatch explicitly.",
        "- Survey dates: Friday 10 July 2026 through Monday 13 July 2026 in the July folder. The requested event windows are Friday 10 July 16:00–Saturday 11 July 03:00 BST and Saturday 11 July 16:00–Sunday 12 July 03:00 BST.",
        "- Live config audio sources: `Nti5`, `Nti4`, and `971-2`. The July config also contains Noise Sentry level logs (`NS1A`, `NS5A`, `NS7`) but no corresponding audio files.",
        "- `Nti5` is the identified dance-floor / zone-array NTi source and is used as the primary internal detector. `971-2` is the only available Svantek boundary audio source. No second boundary audio source exists in the live July config or survey folder, so boundary-2 results are not fabricated.",
        "- Timezone: Europe/London; July timestamps are BST (UTC+1).",
        "",
        "## Timeline and coverage", "",
        "See `audio_inventory.csv` and `audio_timeline.md` for every WAV, file metadata and continuity calculation.", "",
        "| meter | Friday evening/night | Saturday evening/night |", "|---|---|---|",
    ]
    for position in ("Nti5", "Nti4", "971-2"):
        availability = []
        for window_name, (start, end) in WINDOWS.items():
            ok = any(s.position == position and s.continuous and s.start_epoch < end.timestamp() and s.end_epoch > start.timestamp() for s in segments)
            availability.append("covered" if ok else "not covered")
        lines.append(f"| {position} | {availability[0]} | {availability[1]} |")
    lines += ["", "## Music findings", ""]
    if internal.empty:
        lines.append("No internal `Music` events met the configured screening threshold of 0.05.")
    else:
        for window_name in ("friday", "saturday"):
            sub = internal[internal.window == window_name]
            lines.append(f"### {window_name.title()} — Nti5 primary internal source")
            if sub.empty:
                lines.append("No candidates met the screening threshold.")
            else:
                strong = int((sub.peak_music_score >= 0.30).sum())
                moderate = int(((sub.peak_music_score >= 0.10) & (sub.peak_music_score < 0.30)).sum())
                weak = int(((sub.peak_music_score >= 0.05) & (sub.peak_music_score < 0.10)).sum())
                lines.append(f"{len(sub)} merged candidate episode(s): {strong} strong, {moderate} moderate and {weak} weak by raw-score bands. These are classifier findings, not calibrated probabilities or human audibility conclusions.")
                lines.append("")
                lines.append("| start BST | end BST | duration s | peak | mean | evidence |")
                lines.append("|---|---|---:|---:|---:|---|")
                for _, row in sub.sort_values("peak_music_score", ascending=False).head(15).iterrows():
                    lines.append(f"| {row.start_local} | {row.end_local} | {row.duration_seconds:.1f} | {row.peak_music_score:.3f} | {row.mean_music_score:.3f} | {row.evidence_strength} |")
            lines.append("")
    lines += ["### Comparator and boundary comparison", ""]
    if comparator.empty:
        lines.append("No independent `Nti4` comparator candidates met the screening threshold.")
    else:
        lines.append(f"The additional internal `Nti4` comparator produced {len(comparator)} candidate episode(s) at the 0.05 screening threshold. This lane is retained as an internal comparison, not as a boundary result.")
    if boundary.empty:
        lines.append("No independent `Music` candidates met the threshold on the available `971-2` boundary audio.")
    else:
        lines.append(f"The available `971-2` boundary audio produced {len(boundary)} independent candidate episode(s) at the 0.05 screening threshold. It is not equivalent to having two independent boundary meters.")
        if not cross.empty:
            matched = cross[cross.boundary_1_independently_detected.astype(str).str.lower() == "true"] if "boundary_1_independently_detected" in cross else pd.DataFrame()
            lines.append(f"Of the {len(cross)} Nti5 primary events, {len(matched)} overlap an independently detected 971-2 event. Review the cross-meter CSV for peak/mean scores and zero-offset matching details.")
    lines += ["", "## Manual review status", "", "Review clips and a local side-by-side HTML player were created under `review_clips/` and `review.html`. Automated processing has not listened to or confirmed any clip. A weak or moderate YAMNet score must not be described as proof that music was audible at a boundary.", "", "## Detection-quality limitations", "", "- YAMNet scores are raw AudioSet model outputs, not calibrated probabilities.", "- The exact July meter arrangement differs from the supplied 5228 template; there is one available boundary audio source, not two.", "- NTi audio is 24 kHz mono IMA ADPCM and Svantek audio is 12 kHz mono PCM16. Resampling to YAMNet's 16 kHz input does not recreate content above the original Nyquist frequency.", "- Frame scores use a 0.48 s hop. Chunk overlap is 1 s and duplicate frame timestamps are dropped deterministically; scores near a chunk-origin boundary can shift slightly.", "- Masking by speech, applause, wind, traffic and other venue sounds can produce false positives or false negatives. Manual listening remains necessary.", "- No claim is made here that classifier evidence is materially responsible for measured sound levels. The attached `NS1A` level median in event CSVs is a wider-marquee level context only, not a source-attribution result.", "", "## Performance results", ""]
    if not bench.empty:
        complete = bench[bench.status == "ok"].copy()
        if not complete.empty:
            steady = complete[complete.config.isin(["A_sequential_direct", "B_sequential_local_staged", "C_prefetch_local_staged", "F_tensorflow_thread_settings"])]
            steady = steady[steady.cache_mode != "direct_shared_drive_first"]
            if not steady.empty:
                grouped = steady.groupby("config", as_index=False).agg(
                    total_wall_seconds=("total_wall_seconds", "median"),
                    audio_duration_seconds=("audio_duration_seconds", "median"),
                    realtime_factor=("realtime_factor", "median"),
                )
                best = grouped.sort_values("total_wall_seconds").iloc[0]
                lines.append(f"Fastest median steady-state configuration: **{best.config}**, {best.total_wall_seconds:.3f} s for {best.audio_duration_seconds:.0f} s of audio ({best.realtime_factor:.1f}× realtime).")
                lines.append(f"At that measured factor, one hour is approximately {3600 / best.realtime_factor:.1f} s, one 11-hour event night approximately {11 * 3600 / best.realtime_factor:.1f} s, and 24 hours approximately {24 * 3600 / best.realtime_factor:.1f} s, excluding one-off model load/warm-up and any uncached staging.")
            lines.append("The full measured matrix, including first/warm Shared Drive reads, local staging, prefetch, read/resample threads, process workers, TensorFlow settings and cached-score reuse, is in `benchmark_timings.csv` and `benchmark_summary.md`.")
    lines += ["", "## Recommendation", "", "For this computer and this job, use one reused local YAMNet model per process, 120-second chunks with 1-second overlap, and Parquet frame-score caching. Stage only the selected survey windows locally when Shared Drive read variability matters. Use Nti5 as the primary internal music screen and compare the same absolute periods against the available 971-2 boundary audio. Keep Nti4 as an additional internal comparator where its timeline covers the period. Treat boundary audibility as unresolved until the review clips are listened to; do not create a second-boundary conclusion from absent data.", "", "## Output files", "", "- `audio_inventory.csv`", "- `audio_timeline.md`", "- `benchmark_timings.csv`", "- `benchmark_summary.md`", "- `frame_scores/`", "- `music_events_internal.csv`", "- `music_events_nti4_comparator.csv`", "- `music_events_boundary_1.csv`", "- `music_events_boundary_2.csv` (empty by design because no second boundary audio exists)", "- `music_events_cross_meter.csv`", "- `dashboard_classifications.csv`", "- `review_clips/`, `review_manifest.csv`, `review.html`", "- `final_report.md`"]
    (results / "final_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def tf_probe(args: argparse.Namespace) -> None:
    model, class_names, _load, _warm, _cached = load_model(Path(args.tfhub_cache_dir), args.tf_intra, args.tf_inter)
    selected = [DIRECT_CLASS]
    timings, frame_df, sample = run_file_pipeline(Path(args.probe_audio), args.probe_duration, CHUNK_SECONDS, OVERLAP_SECONDS, model, class_names, selected)
    print(json.dumps({**timings, **sample, "n_frames": len(frame_df)}))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=["inventory", "benchmark", "detect", "rebuild", "clips", "report", "all"], default="all")
    parser.add_argument("--survey-root", type=Path, default=DEFAULT_SURVEY_ROOT)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--tfhub-cache-dir", type=Path, default=DEFAULT_TFHUB_CACHE)
    parser.add_argument("--tf-probe", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--probe-audio", type=Path)
    parser.add_argument("--probe-duration", type=float, default=BENCHMARK_SECONDS)
    parser.add_argument("--tf-intra", type=int, default=None)
    parser.add_argument("--tf-inter", type=int, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.tf_probe:
        if not args.probe_audio:
            raise SystemExit("--probe-audio is required with --tf-probe")
        tf_probe(args)
        return
    args.results_dir.mkdir(parents=True, exist_ok=True)
    segments = discover_segments(args.survey_root)
    if not segments:
        raise SystemExit(f"No July audio segments found under {args.survey_root}")
    phase = args.phase
    if phase in ("inventory", "all"):
        write_inventory(segments, args.results_dir)
    detection = None
    if phase in ("benchmark", "all"):
        run_benchmark(segments, args.results_dir, args.tfhub_cache_dir)
    if phase in ("detect", "all"):
        detection = run_detection(segments, args.results_dir, args.tfhub_cache_dir, args.survey_root)
        (args.results_dir / "detection_run_summary.json").write_text(json.dumps({k: v for k, v in detection.items() if k not in {"matched_events", "all_events", "all_frames"}}, indent=2), encoding="utf-8")
    if phase == "rebuild":
        detection = load_detection_from_results(args.results_dir)
        matched = match_events(detection["all_events"][PRIMARY_POSITION], detection["all_events"], detection["all_frames"])
        pd.DataFrame(matched).to_csv(args.results_dir / "music_events_cross_meter.csv", index=False)
        dashboard = dashboard_rows(matched, detection["all_events"]["Nti4"], detection["all_events"][BOUNDARY_1], detection["all_events"].get(BOUNDARY_2, []), args.results_dir)
        pd.DataFrame(dashboard, columns=["position_id", "source_id", "source_label", "start", "end", "state", "confidence", "description", "audio_file", "color"]).to_csv(args.results_dir / "dashboard_classifications.csv", index=False)
    if phase == "clips":
        detection = load_detection_from_results(args.results_dir)
    if phase in ("clips", "all"):
        if detection is None:
            detection = load_detection_from_results(args.results_dir)
        export_review(segments, args.results_dir, detection)
    if phase in ("report", "all"):
        write_final_report(args.results_dir, segments, detection)
    print(f"Outputs saved under {args.results_dir}")


def load_detection_from_results(results: Path) -> dict[str, Any]:
    events: dict[str, list[dict[str, Any]]] = {}
    for position, filename in (("Nti5", "music_events_internal.csv"), ("Nti4", "music_events_nti4_comparator.csv"), ("971-2", "music_events_boundary_1.csv")):
        path = results / filename
        if path.exists() and path.stat().st_size > 0:
            df = pd.read_csv(path)
            rows = []
            for row in df.to_dict("records"):
                for k in ("start_epoch", "end_epoch", "duration_seconds", "peak_music_score", "mean_music_score", "median_music_score", "threshold", "n_positive_frames", "pct_frames_above_threshold"):
                    if k in row:
                        row[k] = float(row[k]) if k not in {"n_positive_frames"} else int(row[k])
                rows.append(row)
            events[position] = rows
        else:
            events[position] = []
    frames = {}
    for position in ("Nti5", "Nti4", "971-2"):
        frames[position] = []
        for path in sorted((results / "frame_scores").glob(f"{position}_*.parquet")):
            if path.name.endswith("_all.parquet") or path.name.endswith("benchmark_reuse.parquet"):
                continue
            frames[position].append(pd.read_parquet(path))
    return {"all_events": events, "all_frames": frames}


if __name__ == "__main__":
    main()
