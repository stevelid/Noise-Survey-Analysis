# PANNs (Cnn14_DecisionLevelMax) local-processing benchmark

Second-model benchmark, mirroring `tools/yamnet_benchmark/` for a direct,
like-for-like comparison against YAMNet on the same job 6461 audio excerpt.
Proof of concept only — does not modify the dashboard or the YAMNet
benchmark. See
`G:\My Drive\Venta AI\skills\classify-survey-audio\references\panns-benchmark-report.md`
for the retained findings and how it compares to YAMNet.

## Isolated environment

A separate venv from the YAMNet benchmark (PyTorch, not TensorFlow — kept
apart deliberately):

```
C:\Users\steve\.venv-panns-benchmark
```

Recreate from scratch:

```powershell
python -m venv "$HOME\.venv-panns-benchmark"
& "$HOME\.venv-panns-benchmark\Scripts\Activate.ps1"
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install panns_inference numpy pandas soundfile scipy pyarrow psutil
```

Python 3.13.14 (only interpreter on this machine); PyTorch 2.13.0+cpu has a
working `cp313` Windows wheel, so no alternate interpreter was needed.

**`panns_inference`'s label-file and checkpoint auto-download both shell out
to `wget`, which Windows doesn't ship by default.** The label CSV was
fetched manually once with `curl.exe` into `%USERPROFILE%\panns_data\` (a
one-off, outside this repo, matching where the package expects it); the
model checkpoint is downloaded by `benchmark_panns.py` itself via Python's
stdlib `urllib` (no extra dependency), which also lets the download be
timed the same way the YAMNet benchmark timed the TF-Hub download.

If starting completely fresh, run once before the benchmark:

```powershell
New-Item -ItemType Directory -Force "$HOME\panns_data" | Out-Null
curl.exe -sL -o "$HOME\panns_data\class_labels_indices.csv" `
  "http://storage.googleapis.com/us_audioset/youtube_corpus/v1/csv/class_labels_indices.csv"
```

## Data

Reuses the **exact same 60-minute excerpt** the YAMNet benchmark extracted
from job 6461, R14.WAV (2026-07-01 08:00–09:00 local). The excerpt is a
generated local input and is not retained in this repository. Same audio
in both benchmarks means the results are directly comparable, not just
similar.

## Exact rerun command

```powershell
cd "G:\My Drive\Programing\Noise Survey Analysis"
& "$HOME\.venv-panns-benchmark\Scripts\Activate.ps1"
python tools\panns_benchmark\benchmark_panns.py `
  --test-window-seconds 1800 --chunk-durations 30,120,300,600 --repeats 3 `
  --thresholds 0.05,0.10,0.20,0.30,0.50 --extend-60min `
  --results-dir tools\panns_benchmark\results
```

All paths/parameters are CLI flags (`--help` for the full list). The
checkpoint (~312 MB) is cached at `%USERPROFILE%\panns_data\` and reused on
rerun; delete it to re-time a fresh download.

## Folder contents

```
README.md
benchmark_panns.py
requirements.txt
results/
  system_info.json
  benchmark_timings.csv                  — chunk-duration x repeat timing matrix
  benchmark_timings_extended.csv          — single extended ~60-min run
  frame_scores_best_chunk.csv / .parquet  — full per-frame raw PANNs scores
  threshold_sweep.csv                     — frame/event counts per threshold (no re-inference)
  motorcycle_events_threshold_0.2.csv     — merged direct "Motorcycle" events
  processing_time_projections.json        — 1h/8h/24h/7-day projections
  clips_manifest.csv, clips/*.wav         — review clips for the top candidates
  benchmark_report.md                     — findings, including the YAMNet comparison
```

The `results/` directory is generated, ignored by Git, and disposable. The
retained benchmark report lives in the `classify-survey-audio` skill references.
