@echo off
setlocal DisableDelayedExpansion
REM Noise Survey Analysis - start the dashboard. This is the shortcut target.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch_noise_survey.ps1" %*
set "NSA_EXIT=%ERRORLEVEL%"
if not "%NSA_EXIT%"=="0" pause
exit /b %NSA_EXIT%
