@echo off
setlocal DisableDelayedExpansion
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0import_sd_card.ps1" %*
set "NSA_EXIT=%ERRORLEVEL%"
if not "%NSA_EXIT%"=="0" pause
exit /b %NSA_EXIT%
