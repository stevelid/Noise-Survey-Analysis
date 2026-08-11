@echo off
REM Noise Survey Analysis - build a dashboard config for a job number.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0generate_config.ps1" %*
if errorlevel 1 pause
