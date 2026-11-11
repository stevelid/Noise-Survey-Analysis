@echo off
setlocal DisableDelayedExpansion
REM Noise Survey Analysis - one-time setup. Double-click this file.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_noise_survey.ps1" %*
set "NSA_EXIT=%ERRORLEVEL%"
if not "%NSA_EXIT%"=="0" pause
exit /b %NSA_EXIT%
