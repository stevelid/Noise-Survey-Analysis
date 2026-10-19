@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0export_annotations.ps1" %*
if errorlevel 1 pause
