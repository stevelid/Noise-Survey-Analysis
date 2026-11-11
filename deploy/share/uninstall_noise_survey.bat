@echo off
setlocal DisableDelayedExpansion
REM Noise Survey Analysis - remove the local install from this computer.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0uninstall_noise_survey.ps1" %*
set "NSA_EXIT=%ERRORLEVEL%"
if not "%NSA_EXIT%"=="0" pause
exit /b %NSA_EXIT%
