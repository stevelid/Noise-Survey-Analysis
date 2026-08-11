@echo off
REM Noise Survey Analysis - remove the local install from this computer.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0uninstall_noise_survey.ps1" %*
if errorlevel 1 pause
