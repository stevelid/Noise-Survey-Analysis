# Release checks — 4 November 2026

Final publication updates the bundled quickstart/CLI/user-guide front doors;
application and parser code are identical to the browser-tested 12:15 build.

Shared release: `2026.11.04.1222`, built from the current working tree at
`caf470d` (uncommitted annotation/deployment changes included, as requested).
Previous releases are backed up under the shared `runtime/previous-releases/`.

Passed on STEVE_HOME, Windows 11 x64:
- 479 dashboard Python tests; 521 JavaScript tests passed, 3 skipped.
  JavaScript tests ran from a fresh local copy with the correct working directory.
- 8 Noise Sentry/SVAN parser regression tests.
- 8 config generation/portability tests after updating the generated launch instructions.
- Deployment integrity: all 183 release files match their recorded SHA256 values.
- Setup rebuilt the local private Python 3.13.16 environment from the 23-package
  offline wheelhouse; native imports, exact pinned versions and audio checks passed.
- The published parsers processed synthetic Noise Sentry CSV/XLSX into standard
  summaries and loaded them in the dashboard; NTi report parsing and SVAN
  971/958A entry-point imports passed in the rebuilt installed runtime.
- Explorer integration checks passed using isolated registry/shortcut fixtures;
  actual three desktop shortcuts and meter/config menus now target shared launchers.
- Chrome/Playwright loaded the shared application into the data-selection UI with
  no page errors. The dedicated smoke server was then closed; existing sessions
  were not stopped. Screenshot/log: Venta AI workspace/working/nsa-release-2026-11-04/.

The release also contains the seven top-level YAMNet helper/setup files used by
the classification skill. TensorFlow/YAMNet uses its separate optional environment;
inference was not rerun for this publication.

Operational dashboard, classification and meter skill paths use the shared
release. Development/build provenance still names the maintainer's My Drive
repositories; these are not needed to run the published tools. Standalone demo
blocks in the Python parser modules retain developer example-data paths and are
not part of dashboard loading or meter processing.

The Windows 10/second-PC/physical-meter/958A binary-coverage limits from the
previous release below still apply. No physical survey/card data were processed.

---

# Release checks - 21 October 2026

Verified on this Windows 11 x64 PC using Windows PowerShell 5.1, a separate local
release directory and a private installation path containing spaces. No existing
Windows file associations or desktop shortcuts were changed during testing.

Passed:
- Private Python 3.13.16 unpack, venv creation and installation of all 23 pinned
  packages from the offline cp313 wheelhouse (no package download required).
- Runtime/native imports, all pinned versions, wrong-version detection,
  refusal of mutation paths outside the local install, repeat setup without rebuild.
- Portable VLC 3.0.24 unpack, native library load and player creation.
- All three desktop shortcut targets and the generated per-user .cil/meter and
  config context-menu commands, including paths containing spaces.
- Synthetic Svantek SD copy, SHA256 verification, retention of a 101 MB source
  WAV, and NTi empty-project recovery from RESTORE_AFTER_POWERFAIL.
- Noise Sentry CSV and XLSX processing through the published command-line
  dispatcher, then loading the results through the dashboard parser.
- NTi broadband report parsing in the installed runtime; SVAN 971/958A entry
  point imports. Five existing SVAN 971 special-record tests pass.
- Dashboard launches through the packaged launcher, selects an unused port,
  creates a Bokeh session and renders the data-selection screen in Chrome.
  Both localhost/127.0.0.1 origins are permitted. No browser errors on final load.
- Diagnostic report generation.
- Application regression suites: 472 Python tests passed; 513 JavaScript tests
  passed, 3 skipped (39 files), using a local non-synced test copy.

Limits:
- Windows 10 compatibility targets the built-in PowerShell 5.1 APIs; this run
  was on Windows 11. No second physical PC, ARM or 32-bit Windows was tested.
- Synthetic cards were used, not a connected physical meter or removable card.
- The legacy SLM Parsers root test suite cannot run as a complete suite: it
  references the absent Svan.svan958a_totals module and @RES0043.SVN fixture.
  This is pre-existing; no unsupported parser implementation was invented to
  satisfy it. Actual 958A binary coverage remains limited to import checks.
- The Bokeh data selector emits an existing non-blocking jquery-ui warning
  about DataTable column reordering. The selector renders and connects.

The Python Windows installer was tried in the isolated test but failed inside
Windows Installer with 0x80070003. The final package uses the official portable
Python distribution and does not invoke that installer.
