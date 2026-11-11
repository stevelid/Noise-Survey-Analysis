@echo off
setlocal DisableDelayedExpansion
REM Noise Survey Analysis - build a dashboard config for a job number.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0generate_config.ps1" %*
set "NSA_EXIT=%ERRORLEVEL%"
if not "%NSA_EXIT%"=="0" pause
exit /b %NSA_EXIT%
