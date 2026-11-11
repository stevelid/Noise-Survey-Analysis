@echo off
setlocal DisableDelayedExpansion
REM Noise Survey Analysis - write a diagnostic report to send to Steve.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0diagnose_noise_survey.ps1" %*
set "NSA_EXIT=%ERRORLEVEL%"
if not "%NSA_EXIT%"=="0" pause
exit /b %NSA_EXIT%
