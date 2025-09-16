@echo off
setlocal

REM == Sync Script for Noise Survey Analysis ==
REM This script uses robocopy to synchronize the project directory to a destination,
REM excluding temporary files, build artifacts, and node modules.

REM --- Configuration ---

REM Set the source directory (the location of this script).
set "SOURCE_DIR=%~dp0"
REM Remove trailing backslash from source directory path to avoid issues with quotes
if "%SOURCE_DIR:~-1%"=="\" set "SOURCE_DIR=%SOURCE_DIR:~0,-1%"

REM Set the destination directory.
set "DEST_DIR=G:\My Drive\Programing\Noise Survey Analysis"

REM --- Robocopy Execution ---

echo Syncing project to Google Drive...
echo Source: %SOURCE_DIR%
echo Destination: %DEST_DIR%
echo.

robocopy "%SOURCE_DIR%" "%DEST_DIR%" /MIR /XD node_modules coverage /XF test-output.txt test-output.ans repomix-output.xml /R:2 /W:5 /NFL /NDL /NJH /NJS

REM Check the exit code from robocopy
if %ERRORLEVEL% GEQ 8 (
    echo.
    echo ERROR: Robocopy encountered serious errors. Sync may have failed.
    exit /b 1
) else (
    echo.
    echo Sync completed successfully.
    exit /b 0
)

endlocal
