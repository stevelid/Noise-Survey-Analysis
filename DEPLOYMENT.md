# Deployment Guide

## Overview

This document describes how to deploy the Noise Survey Analysis application to the shared drive for production use.

## Deployment Locations

- **Development**: `G:\My Drive\Programing\Noise Survey Analysis`
- **Production**: `G:\Shared drives\Venta\Software\Noise Survey Analysis\Noise Survey Analysis`

## Deployment Script

Use the `deploy_to_shared.bat` script to deploy the application to the shared drive.

### What Gets Deployed

The deployment script syncs **only production-ready files**:

- ✅ `noise_survey_analysis/` - Complete Python package including:
  - Core application code (`core/`, `ui/`, `visualization/`, `export/`)
  - Static assets (`static/js/`, `static/css/`)
  - Main entry point (`main.py`)
- ✅ `requirements.txt` - Python dependencies
- ✅ `USER_GUIDE.txt` - User documentation

### What Does NOT Get Deployed

The following files are **excluded** from deployment to keep the production environment clean:

- ❌ Development files (`.git/`, `.vscode/`, `.gitignore`)
- ❌ Tests and test documentation (`tests/`, `MANUAL_TEST_CHECKLIST.md`, `STATIC_HTML_TEST_REPORT.md`)
- ❌ Documentation (`README.md`, `AGENTS.md`, `ANNOTATION_GUIDE.md`, `TODO.txt`, `DEPLOYMENT.md`)
- ❌ Build artifacts (`__pycache__/`, `*.pyc`, `node_modules/`, `coverage/`)
- ❌ Generated HTML dashboards (`*.html`)
- ❌ Development configuration (`package.json`, `package-lock.json`, `vitest.config.js`, `playwright.config.ts`)
- ❌ Sync scripts (`sync_to_gdrive.bat`)
- ❌ Other development files (`repomix-output.xml`, `GEMINI.md`)

### Config File Handling

**IMPORTANT**: The `config.json` file in the shared drive is **NOT overwritten** during deployment. This allows the production environment to maintain its own configuration independently of the development environment.

## Pre-Deployment Checklist

Before deploying, ensure:

1. ✅ All changes are committed to git
2. ✅ All automated tests pass (run `npm test` if available)
3. ✅ Manual testing has been performed (see `tests/MANUAL_TEST_CHECKLIST.md`)
4. ✅ No TODO comments or debug code in production files
5. ✅ Version number updated if applicable

## Deployment Steps

1. **Open Command Prompt** in the project directory:
   ```
   G:\My Drive\Programing\Noise Survey Analysis
   ```

2. **Run the deployment script**:
   ```batch
   deploy_to_shared.bat
   ```

3. **Review the pre-deployment checks**:
   - The script will warn if you have uncommitted changes
   - You can choose to continue or cancel

4. **Wait for completion**:
   - The script will sync the `noise_survey_analysis` package
   - Then sync `requirements.txt`
   - A summary will be displayed upon completion

## Post-Deployment Verification

After deployment, verify the production environment:

1. **Check the shared drive** has the updated files:
   ```
   G:\Shared drives\Venta\Software\Noise Survey Analysis\Noise Survey Analysis
   ```

2. **Verify the config.json** is still appropriate for production use

3. **Test the application** by generating a dashboard:
   ```batch
   cd "G:\Shared drives\Venta\Software\Noise Survey Analysis\Noise Survey Analysis"
   python -m noise_survey_analysis.main
   ```

## Rollback Procedure

If issues are discovered after deployment:

1. The shared drive location is version-controlled via Git
2. You can revert to a previous commit:
   ```batch
   cd "G:\Shared drives\Venta\Software\Noise Survey Analysis\Noise Survey Analysis"
   git log --oneline
   git checkout <commit-hash>
   ```

3. Or re-run the deployment script from a previous commit in your development environment

## Troubleshooting

### "Destination directory does not exist"
- Verify you have access to the shared drive
- Check the path in `deploy_to_shared.bat` is correct

### "Robocopy encountered serious errors"
- Check you have write permissions to the shared drive
- Ensure no files are locked/in-use in the destination

### Changes not appearing in production
- Verify the files were actually modified in your development environment
- Check the deployment script output for errors
- Manually compare file timestamps between dev and prod

## Notes

- The deployment uses `robocopy` with `/MIR` (mirror) mode for the package directory
- Python cache files (`__pycache__/`, `*.pyc`) are automatically excluded
- The deployment preserves the production `config.json` to avoid overwriting production settings
