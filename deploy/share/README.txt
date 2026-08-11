NOISE SURVEY ANALYSIS
=====================
Venta Acoustics survey dashboard - shared team install


FIRST TIME ON THIS COMPUTER
---------------------------

Double-click:      setup_noise_survey.bat

That is the only step. It will:
  * find Python, and install it for you if it is not already there
  * install everything it needs (from this shared folder, so it works even
    without an internet connection)
  * put a "Noise Survey Analysis" shortcut on your desktop
  * add the right-click menus described below

It takes a few minutes the first time. If it asks for anything, say yes.


EVERY DAY AFTER THAT
--------------------

Double-click the "Noise Survey Analysis" shortcut on your desktop.

You never need to run setup again. The application runs from this shared folder,
so you are always on the current version as soon as Steve releases it. The
launcher also checks its own Python environment each time and rebuilds it if
anything has broken or the requirements have changed.


OPENING A SURVEY
----------------

If you already have a config file for the job
    Right-click noise_survey_config_XXXX.json  ->  "Open in Noise Survey Analysis"

If you do not have one yet
    Double-click generate_config.bat, type the job number, and it will build
    one from the survey data in the job folder.

If you just want to browse
    Use the desktop shortcut. The dashboard opens with a file picker, already
    pointed at G:\Shared drives\Venta\Jobs. Type the job number and click
    "Scan Job Directory".

The first load of a big survey (lots of audio, or a long log file) can take a
couple of minutes. The page says "Initializing Dashboard..." while it works.
That is normal - do not reload the page, and do not open the address a second
time. Each time you open it you start a separate session, which makes it
slower, not faster.


PROCESSING METER FILES
----------------------

Right-click a meter file  ->  "Extract TH data"

Works on:
    .svl              SVAN 971
    .svn              SVAN 958A (@RES*.SVN)
    .csv .xls .xlsx   Noise Sentry


AUDIO PLAYBACK
--------------

Audio needs VLC media player (the 64-bit version) installed. Setup offers to
install it. Everything else - charts, data, spectra, export - works without it.


WHEN SOMETHING GOES WRONG
-------------------------

1. Close the dashboard window and open it again from the desktop shortcut.
   Most problems fix themselves at this point, because the launcher repairs
   the installation automatically.

2. Still not working? Double-click:

       diagnose_noise_survey.bat

   It writes a report and opens it in Notepad. Send that file to Steve. It
   contains no survey data - just what is installed on your computer and the
   last error.

3. To force a full rebuild of the installation:

       Right-click launch_noise_survey.ps1 -> Run with PowerShell
       (or run:  launch_noise_survey.bat -Repair)


WHAT GOES WHERE
---------------

On this shared drive
    Noise Survey Analysis\   the application, run directly from here
    SLM Parsers\             the meter file parsers
    runtime\                 offline package store and version information
    *.bat / *.ps1            the scripts you double-click

On your computer
    %LOCALAPPDATA%\NoiseSurveyAnalysis\
        venv\     the private Python environment the dashboard runs in
        pycache\  Python's bytecode cache, kept off the shared drive
        logs\     setup and launch logs

Nothing is installed system-wide and nothing needs administrator rights.
To remove it all again, run uninstall_noise_survey.bat.
