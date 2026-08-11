# 5882 July audio categorisation benchmark

This folder is isolated from the production dashboard. It reuses the local
YAMNet loader and resampler in `tools/yamnet_benchmark/benchmark_yamnet.py`
but does not import or modify the dashboard application.

Run with the dedicated local environment:

```powershell
$py = 'C:\Users\steve\.venv-yamnet-benchmark\Scripts\python.exe'
& $py tools\music_detection_benchmark\run_5882_july.py --phase inventory
& $py tools\music_detection_benchmark\run_5882_july.py --phase benchmark
& $py tools\music_detection_benchmark\run_5882_july.py --phase detect
& $py tools\music_detection_benchmark\run_5882_july.py --phase clips
& $py tools\music_detection_benchmark\run_5882_july.py --phase report
```

Use `--phase all` to execute the same phases sequentially after a successful
inventory. All source paths and the output directory are command-line options;
the documented defaults point at the synced July 2026 job 5882 survey folder
and this repository's isolated results area.

All audio processing is local. Source audio is read or partially staged only;
original survey files are never changed.
