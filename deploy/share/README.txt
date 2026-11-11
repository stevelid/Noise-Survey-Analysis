VENTA NOISE SURVEY TOOLS
=======================

FIRST TIME ON A COMPUTER

1. In Google Drive, right-click this whole Noise Survey Analysis folder and
   choose Offline access > Available offline. Wait for syncing to finish.
2. Double-click START_HERE.bat (setup_noise_survey.bat does the same thing).
3. Wait for "Setup complete". The first run takes several minutes.

Setup supplies its own Python, all required packages and the audio runtime.
You do not need to install Python or VLC, change Windows settings, choose an
environment or use a command prompt. No administrator account is needed.
Once the complete folder is available offline, setup needs no internet.

Supported: standard Intel/AMD 64-bit Windows 10 and 11 computers, using the
Windows PowerShell already supplied with Windows. Windows on ARM and 32-bit
Windows have not been tested or packaged. A browser is needed for the dashboard.
Your organisation's software restrictions may require help from its IT team.

THE THREE DESKTOP SHORTCUTS

Noise Survey Analysis
    Opens the dashboard in your usual browser. Keep its console window open
    while using it. Scan a job's Surveys folder, or right-click an existing
    noise_survey_config_XXXX.json and choose Open in Noise Survey Analysis.
    Large surveys can take a few minutes to load; avoid opening extra sessions.

Import SD Card
    Insert an NTi XL2 or Svantek 971 SD card, then open this shortcut. Check the
    suggested job number and job name. It copies and verifies the data in the
    job's Surveys folder. The original files on the card are kept.
    NTi power-failure recovery files are supported. Other meter card formats
    are not supported by this interactive importer.

Process Meter File
    Choose a copied Svantek or Noise Sentry file. Alternatively right-click it
    and choose Extract TH data. On Windows 11 choose Show more options first.
    Supported: .svl (971), @RES*.svn (958A), .cil, .csv, .xls, .xlsx (Noise Sentry).
    Noise Sentry may ask about installation/retrieval periods; read the prompt.
    Result: _log.csv and _summary.csv beside the input file.

NTi reports are read directly by the dashboard's NTi parser: scan the folder
containing the original report, log, spectral and audio files together.
Generate Config (generate_config.bat) can also build a job's dashboard config.
This package does not create Venta Excel TH workbooks or install Excel add-ins.
USB download software supplied by the meter manufacturers is separate.

UPDATES AND REPAIRS

The code runs from this shared folder. Updates arrive when Drive finishes
syncing. Launching the dashboard or a meter parser checks the local packages
and repairs them when needed. Run START_HERE.bat again after an update to
refresh desktop shortcuts and right-click menus; it is safe to run repeatedly.
If this folder is moved or Drive changes letter, run setup from the new location.
Keep the job folder available offline as well if working without internet.

IF SOMETHING DOES NOT WORK

Close the dashboard's console window. Run START_HERE.bat again.
If that does not fix it, double-click diagnose_noise_survey.bat and send Steve
the report it opens. The report lists software, paths and recent errors.
Do not delete or format a card unless you have checked the imported files.

FILES ON YOUR COMPUTER

%LOCALAPPDATA%\NoiseSurveyAnalysis contains the private Python, environment,
audio runtime, caches and logs. No PATH or administrator settings are changed.
To remove the local software and its shortcuts, run uninstall_noise_survey.bat.
Your survey files, shared software and other Python/VLC installations are kept.
