@echo off
setlocal enabledelayedexpansion

REM == Deployment Script for Noise Survey Analysis ==
REM This script deploys only the necessary production files to the shared drive,
REM excluding development files, tests, documentation, and build artifacts.

REM --- Configuration ---

REM Set the source directory (the location of this script).
set "SOURCE_DIR=%~dp0"
REM Remove trailing backslash from source directory path to avoid issues with quotes
if "%SOURCE_DIR:~-1%"=="\" set "SOURCE_DIR=%SOURCE_DIR:~0,-1%"

REM Set the destination directory.
set "DEST_DIR=G:\Shared drives\Venta\Software\Noise Survey Analysis\Noise Survey Analysis"

REM --- Pre-deployment Checks ---

echo ========================================
echo Noise Survey Analysis - Deployment
echo ========================================
echo.
echo Source: %SOURCE_DIR%
echo Destination: %DEST_DIR%
echo.

REM Check if destination exists
if not exist "%DEST_DIR%" (
    echo ERROR: Destination directory does not exist.
    echo Please verify the path: %DEST_DIR%
    pause
    exit /b 1
)

REM Check for uncommitted changes
echo Checking for uncommitted changes...
git status --porcelain > nul 2>&1
if %ERRORLEVEL% EQU 0 (
    for /f %%i in ('git status --porcelain ^| find /c /v ""') do set CHANGES=%%i
    if not "!CHANGES!"=="0" (
        echo.
        echo WARNING: You have uncommitted changes in your repository.
        echo It is recommended to commit all changes before deploying.
        echo.
        git status --short
        echo.
        set /p CONTINUE="Continue anyway? (y/N): "
        if /i not "!CONTINUE!"=="y" (
            echo Deployment cancelled.
            exit /b 1
        )
    )
)

echo.
echo Starting deployment...
echo.

REM --- Robocopy Execution ---

REM Deploy the noise_survey_analysis package (production code only)
echo [1/3] Syncing noise_survey_analysis package...
robocopy "%SOURCE_DIR%\noise_survey_analysis" "%DEST_DIR%\noise_survey_analysis" /MIR /XD __pycache__ /XF *.pyc /R:2 /W:5 /NFL /NDL

REM Check the exit code from robocopy (0-7 are success codes)
if %ERRORLEVEL% GEQ 8 (
    echo.
    echo ERROR: Failed to sync noise_survey_analysis package.
    exit /b 1
)

REM Deploy requirements.txt
echo [2/3] Syncing requirements.txt...
robocopy "%SOURCE_DIR%" "%DEST_DIR%" requirements.txt /R:2 /W:5 /NFL /NDL

REM Check the exit code from robocopy
if %ERRORLEVEL% GEQ 8 (
    echo.
    echo ERROR: Failed to sync requirements.txt.
    exit /b 1
)

REM Deploy USER_GUIDE.txt
echo [3/3] Syncing USER_GUIDE.txt...
robocopy "%SOURCE_DIR%" "%DEST_DIR%" USER_GUIDE.txt /R:2 /W:5 /NFL /NDL

REM Check the exit code from robocopy
if %ERRORLEVEL% GEQ 8 (
    echo.
    echo ERROR: Failed to sync USER_GUIDE.txt.
    exit /b 1
)

REM --- Post-deployment Summary ---

echo.
echo ========================================
echo Deployment completed successfully!
echo ========================================
echo.
echo Deployed files:
echo   - noise_survey_analysis/ (Python package)
echo   - requirements.txt
echo   - USER_GUIDE.txt
echo.
echo Excluded from deployment:
echo   - Development files (.git, .vscode, etc.)
echo   - Tests and test documentation
echo   - Documentation (README, AGENTS.md, etc.)
echo   - Build artifacts (node_modules, __pycache__, etc.)
echo   - Generated HTML dashboards
echo   - Configuration files (package.json, etc.)
echo.
echo NOTE: The config.json in the shared drive is preserved
echo       and NOT overwritten by this deployment.
echo.

pause
exit /b 0

endlocal
