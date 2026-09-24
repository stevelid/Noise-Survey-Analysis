"""
Benchmark Parquet codecs for the all-class YAMNet score cache.

Needs NO inference and no audio — it reuses a frame_scores_all_classes.parquet
that a previous detection run already produced, so it is cheap to run anywhere
(local or Colab) and measures exactly the data shape this pipeline writes:
~521 float32 class columns plus frame_time/chunk_index.

Why size matters as much as write speed: in the Colab workflow every result is
copied to Google Drive afterwards, so a codec that writes fast but produces a
bigger file can lose the time again on upload. The report therefore shows write
time, file size, read-back time, and a combined estimate at an assumed upload
rate — decide on the "write + upload" column, not write time alone.

Usage
-----
    python benchmark_parquet_compression.py \
        --source "<...>/R13/frame_scores_all_classes.parquet" \
        --codecs zstd,snappy,none,lz4,gzip --repeats 3 --upload-mbps 40

Run it against a full-length file's parquet if you can — a short excerpt will
under-state the differences.
"""

from __future__ import annotations

import argparse
import statistics
import tempfile
import time
from pathlib import Path

import pandas as pd


def bench_codec(df: pd.DataFrame, codec: str, repeats: int, workdir: Path):
    """Write/read the frame `repeats` times with one codec; return medians."""
    compression = None if codec.lower() == "none" else codec
    write_times, read_times, sizes = [], [], []
    for i in range(repeats):
        target = workdir / f"bench_{codec}_{i}.parquet"
        t0 = time.perf_counter()
        df.to_parquet(target, index=False, compression=compression)
        write_times.append(time.perf_counter() - t0)
        sizes.append(target.stat().st_size)

        t0 = time.perf_counter()
        _ = pd.read_parquet(target)
        read_times.append(time.perf_counter() - t0)
        target.unlink()
    return {
        "codec": codec,
        "write_s": statistics.median(write_times),
        "read_s": statistics.median(read_times),
        "size_mb": statistics.median(sizes) / 1e6,
        "write_spread_pct": (
            (max(write_times) - min(write_times)) / statistics.median(write_times) * 100
            if statistics.median(write_times) else 0.0
        ),
    }


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--source", type=Path, required=True,
                    help="An existing frame_scores_all_classes.parquet to re-encode.")
    p.add_argument("--codecs", type=str, default="zstd,snappy,none",
                    help="Comma-separated codecs to compare. lz4 and gzip also work if the "
                         "installed pyarrow supports them.")
    p.add_argument("--repeats", type=int, default=3)
    p.add_argument("--max-rows", type=int, default=None,
                    help="Truncate to N rows for a quick smoke test. Omit for the real "
                         "measurement — a short excerpt under-states the differences.")
    p.add_argument("--upload-mbps", type=float, default=40.0,
                    help="Assumed Drive upload rate (megabytes/s) used for the combined "
                         "write+upload estimate. Colab to Drive is typically tens of MB/s.")
    p.add_argument("--workdir", type=Path, default=None,
                    help="Where to write temp files. Use LOCAL disk (e.g. /content on Colab), "
                         "never a Drive mount, or you are timing the network instead.")
    args = p.parse_args()

    print(f"Loading {args.source} ...")
    t0 = time.perf_counter()
    df = pd.read_parquet(args.source)
    print(f"  {len(df)} frames x {len(df.columns)} columns in {time.perf_counter()-t0:.1f}s")
    if args.max_rows:
        df = df.head(args.max_rows)
        print(f"  truncated to {len(df)} rows (smoke test — not a real measurement)")

    hours = len(df) * 0.48 / 3600  # YAMNet hop is 0.48 s per frame
    print(f"  represents ~{hours:.1f} h of audio\n")

    workdir = args.workdir or Path(tempfile.gettempdir())
    workdir.mkdir(parents=True, exist_ok=True)
    print(f"Writing test files to: {workdir}")
    print(f"Repeats per codec: {args.repeats}\n")

    rows = []
    for codec in [c.strip() for c in args.codecs.split(",") if c.strip()]:
        print(f"  benchmarking {codec} ...", flush=True)
        try:
            rows.append(bench_codec(df, codec, args.repeats, workdir))
        except Exception as e:
            print(f"    skipped ({type(e).__name__}: {e})")

    if not rows:
        raise SystemExit("No codec completed successfully.")

    for r in rows:
        r["upload_s"] = r["size_mb"] / args.upload_mbps
        r["write_plus_upload_s"] = r["write_s"] + r["upload_s"]

    best_total = min(r["write_plus_upload_s"] for r in rows)
    best_write = min(r["write_s"] for r in rows)
    best_size = min(r["size_mb"] for r in rows)

    print(f"\n{'codec':<10}{'write s':>9}{'±%':>6}{'size MB':>10}{'read s':>9}"
          f"{'upload s':>10}{'write+upload':>14}")
    print("-" * 68)
    for r in sorted(rows, key=lambda x: x["write_plus_upload_s"]):
        flag = "  <-- best overall" if r["write_plus_upload_s"] == best_total else ""
        print(f"{r['codec']:<10}{r['write_s']:>9.2f}{r['write_spread_pct']:>6.1f}"
              f"{r['size_mb']:>10.1f}{r['read_s']:>9.2f}{r['upload_s']:>10.2f}"
              f"{r['write_plus_upload_s']:>14.2f}{flag}")

    print(f"\nAssumed upload rate: {args.upload_mbps:.0f} MB/s "
          f"(change with --upload-mbps; the ranking can flip if your real rate differs).")
    print(f"Fastest write alone: {best_write:.2f}s. Smallest file: {best_size:.1f} MB.")

    # Scale to a realistic full survey so the numbers mean something operationally.
    if hours > 0:
        print(f"\nExtrapolated to a 7-day survey (168 h), per position:")
        scale = 168 / hours
        for r in sorted(rows, key=lambda x: x["write_plus_upload_s"]):
            print(f"  {r['codec']:<8} {r['size_mb']*scale/1000:>6.1f} GB cache, "
                  f"{r['write_plus_upload_s']*scale/60:>5.1f} min write+upload")

    print("\nNote: the cache is kept so any AudioSet class can be screened later without "
          "re-inference, so size is a standing storage cost on Drive, not just a transfer cost.")


if __name__ == "__main__":
    main()
