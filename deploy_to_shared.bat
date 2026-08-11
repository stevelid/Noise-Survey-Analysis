@echo off
REM Publish this development tree to the team's shared-drive copy.
REM The real work is in deploy\deploy_to_shared.ps1 - see DEPLOYMENT.md.
REM
REM   deploy_to_shared.bat                     code and scripts
REM   deploy_to_shared.bat -RebuildWheelhouse  also refresh the offline packages
REM   deploy_to_shared.bat -WhatIf             show what would happen

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy\deploy_to_shared.ps1" %*
pause
