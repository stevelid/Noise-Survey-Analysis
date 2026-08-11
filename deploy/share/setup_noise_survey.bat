@echo off
REM Noise Survey Analysis - one-time setup. Double-click this file.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_noise_survey.ps1" %*
if errorlevel 1 pause
