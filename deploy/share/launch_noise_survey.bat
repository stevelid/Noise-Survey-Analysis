@echo off
REM Noise Survey Analysis - start the dashboard. This is the shortcut target.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch_noise_survey.ps1" %*
if errorlevel 1 pause
