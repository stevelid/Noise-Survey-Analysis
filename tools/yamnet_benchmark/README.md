# YAMNet local-processing benchmark (proof of concept)

Standalone benchmark to establish whether local CPU processing with YAMNet
(TensorFlow Hub, `https://tfhub.dev/google/yamnet/1`) is fast enough to
integrate motorcycle-noise (and other audio-event) detection into the
Noise Survey Analysis dashboard. **This is a benchmark only** — it does not
modify `noise_survey_analysis/` or any dashboard config, and it is not
wired into the dashboard's production workflow.

The maintained findings and recommendation are kept with the operational skill at
`G:\My Drive\Venta AI\skills\classify-survey-audio\references\yamnet-benchmark-report.md`.
Generated results, cached audio and model files are deliberately excluded from this
repository; the `results/`, `data/` and `tfhub_cache/` entries below describe
reproducible local working folders only.

## Isolated environment

A dedicated virtual environment was created at:

```
C:\Users\steve\.venv-yamnet-benchmark
```

(outside this repo, so it can't be confused with the dashboard's own
environment). It was **not** created under `tools/yamnet_benchmark/` because
the working directory at creation time was the user's home directory; the
path is otherwise exactly as specified in the task brief. To recreate it
from scratch:

```powershell
python -m venv "$HOME\.venv-yamnet-benchmark"
& "$HOME\.venv-yamnet-benchmark\Scripts\Activate.ps1"
pip install -r "G:\My Drive\Programing\Noise Survey Analysis\tools\yamnet_benchmark\requirements.txt"
```

Python 3.13.14 was the only interpreter available on this machine and
TensorFlow 2.21.0 ships a `cp313`-`win_amd64` wheel, so no alternate
interpreter install was required. `tensorflow-hub` 0.16.1 imports the
deprecated `pkg_resources` module, which setuptools >= 81 no longer
includes by default — `setuptools<81` is pinned in this venv only to work
around that; it is **not** applied anywhere in the main project environment.

## Data

Job 6461 (Bath Road, Bridgwater) audio lives at:

```
G:\Shared drives\Venta\Jobs\6461 Bath Road, Bridgwater\6461 Surveys\971-3\
  R14.WAV, R15.WAV, R16.WAV  (~4.0 GB each, Svantek 971 continuous recording)
  R17.WAV                    (~1.3 GB, final segment)
```

12 kHz, mono, 16-bit PCM, continuous recording split by the meter at the
~4 GB WAV file-size boundary. Combined duration across all four files is
approximately 165 hours (~6.9 days), matching the `L292_log.csv` survey log
(595,159 one-second rows, survey start `2026-06-30 13:30:00`).

**R14.WAV was chosen as the representative recording** — it is the first
and longest continuous segment (covers the survey start through
2026-07-02 15:11), and a benchmark excerpt was cut from it starting
**2026-07-01 08:00:00** (Wednesday weekday morning), chosen to maximise the
likelihood of daytime commuter/leisure motorcycle traffic on Bath Road
while staying well clear of the file's start/end.

The script extracts a local, cached excerpt via a **partial `soundfile`
read** (seeks into the file rather than loading all ~4 GB), so the source
files on the shared drive are read but never copied or modified, and are
never uploaded anywhere — all processing is local.

## Exact rerun command

```powershell
cd "G:\My Drive\Programing\Noise Survey Analysis"
& "$HOME\.venv-yamnet-benchmark\Scripts\Activate.ps1"
python tools\yamnet_benchmark\benchmark_yamnet.py `
  --excerpt-seconds 3600 --test-window-seconds 1800 `
  --chunk-durations 30,120,300,600 --repeats 3 `
  --thresholds 0.05,0.10,0.20,0.30,0.50 `
  --extend-60min `
  --results-dir tools\yamnet_benchmark\results `
  --data-dir tools\yamnet_benchmark\data
```

All paths, offsets, chunk durations, thresholds and repeat counts are CLI
flags (`python tools\yamnet_benchmark\benchmark_yamnet.py --help` for the
full list) — nothing material is hard-coded except the *default* values,
which match the job 6461 data and the chosen test window described above.

Re-running is safe and idempotent: the extracted excerpt WAV is cached under
`data/` and reused if present (delete it to force a fresh extraction); model
files are cached under `tfhub_cache/` (delete to force a fresh download).

## Folder contents

```
README.md                 — this file
benchmark_yamnet.py        — the benchmark / detection script
requirements.txt           — pinned dependency versions for the isolated venv
data/                       — cached local audio excerpt (git-ignorable; not committed)
tfhub_cache/                — cached YAMNet model download (git-ignorable; not committed)
results/
  system_info.json                          — machine/software/GPU info
  source_audio_info.json                    — R14.WAV format details
  benchmark_timings.csv                     — chunk-duration x repeat timing matrix
  benchmark_timings_extended_60min.csv       — single extended 60-min run
  frame_scores_best_chunk.csv / .parquet     — full per-frame raw YAMNet scores
                                                (motorcycle-relevant classes only)
  threshold_sweep.csv                        — frame/event counts at each threshold
                                                (re-uses saved scores, no re-inference)
  motorcycle_events_threshold_0.2.csv        — merged direct "Motorcycle" candidate events
  supporting_vehicle_candidates.csv          — merged supporting-class events
                                                (engine/revving/etc.), excluding periods
                                                already covered by a direct match
  processing_time_projections.json           — 1h/8h/24h/7-day projections
  clips_manifest.csv                         — metadata for the review clips
  clips/*.wav                                 — up to 10 short review clips
  benchmark_report.md                        — findings and recommendation
```

## Full-day detection run (`run_full_day_detection.py`)

Second script, built after the speed benchmark confirmed local processing
is fast enough. Streams a full day (or any window) directly from the
source WAV in 120s chunks (no full-day copy kept in memory or on disk),
runs YAMNet, merges detections of a chosen target class into events, and
writes a **Classifications CSV** in the exact format the dashboard's
existing Classifications panel already imports
(`classificationUtils.js.parseClassificationsCsv` — Side panel ->
Classifications -> Import). No dashboard code was touched; this reuses a
feature that already existed.

**Generalised beyond motorcycles** — `--target-class` accepts any
YAMNet/AudioSet class name (Dog, Music, Aircraft, ...), and
`--survey-start-local`/`--timezone`/`--position-id` let it run against any
job, not just 6461 (all default to the original job 6461 motorcycle values
for backward compatibility). See the
`classify-survey-audio` skill (`G:\My Drive\Venta AI\skills\classify-survey-audio\core.md`)
for the general workflow and flag reference.

```powershell
cd "G:\My Drive\Programing\Noise Survey Analysis"
& "$HOME\.venv-yamnet-benchmark\Scripts\Activate.ps1"
python tools\yamnet_benchmark\run_full_day_detection.py `
  --high-threshold 0.20 --low-threshold 0.10 `
  --include-supporting `
  --results-dir tools\yamnet_benchmark\results\full_day
```

Defaults process 2026-07-01 00:00–24:00 local (Europe/London) from R14.WAV
at position `MP1 - A39 north-west (971-3)` — all overridable via flags
(`--offset-seconds`, `--duration-seconds`, `--position-id`, etc.). Events
scoring >= `--high-threshold` are exported with `state=on`; events between
`--low-threshold` and `--high-threshold` are exported as `state=uncertain`
(a real field in the dashboard's classification schema) so weaker
candidates stay visible without cluttering the primary set.

**Known limitation — chunk-boundary phase.** YAMNet frames each chunk
starting from that chunk's own t=0, so the exact 0.48 s frame grid over a
given moment in the recording depends on where the chunk boundaries happen
to fall for that particular run. Re-running against a different absolute
start offset can shift a borderline event's peak score by several
hundredths (confirmed empirically: an event scoring 0.226 in the original
60-minute test scored 0.174 in the full-day run at the identical
wall-clock instant). This does not appear to affect clearly real events
(peak scores well above 0.30 were stable), but treat the `on`/`uncertain`
threshold boundary as approximate, not an exact reproducible cutoff.

## Notes on results interpretation

- Raw YAMNet scores are retained throughout — they are **not** calibrated
  probabilities. Thresholds were chosen for screening, not as confidence
  levels.
- "Supporting vehicle candidates" (engine/revving/road-traffic classes) are
  never silently treated as confirmed motorcycles — they are a separate,
  explicitly weaker signal, exported to their own file.
- Source audio is 12 kHz; YAMNet requires 16 kHz, so every chunk is
  resampled (`scipy.signal.resample_poly`, exact 4:3 ratio). The original
  12 kHz recording has no content above 6 kHz to begin with, which is a
  genuine limitation for a source like motorcycle acceleration/exhaust
  noise that can carry energy at higher frequencies — see the findings
  report for how this may affect detection reliability.
