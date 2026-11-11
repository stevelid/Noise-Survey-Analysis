@echo off
setlocal DisableDelayedExpansion
call "%~dp0setup_noise_survey.bat" %*
exit /b %ERRORLEVEL%
