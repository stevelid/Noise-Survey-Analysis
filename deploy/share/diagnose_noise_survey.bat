@echo off
REM Noise Survey Analysis - write a diagnostic report to send to Steve.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0diagnose_noise_survey.ps1" %*
if errorlevel 1 pause
