"""
Understanding the shape of a job folder before anything is parsed.

Job folders follow a consistent three-level shape in practice:

    <job>/<job> Surveys/[visit]/[position]/<files>

The `Surveys` folder is a hard boundary - the rest of a job is admin, correspondence
and reports. The optional visit folder is a campaign (``july 2026``,
``250829 Glazing Tests``, ``Verification Monitoring``); the position folder is
usually the recorder or meter token (``971-2``, ``L350``, ``6145-3 - front``).

Roles within a position are recoverable from the filename alone. NTi in particular
follows an exact grammar, so no size-threshold guessing is needed:

    <date>_SLM_<nnn>_<123|RTA_3rd>_<Log|Report|Rpt_Report>.txt
                        |                |
              broadband / third-octave   time history / summary

This module answers only what can be known cheaply - filenames, folder structure and
an ~8 KB read from each end of a file. Nothing here parses a whole file.
"""

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# The folder inside a job that actually holds survey data.
SURVEY_FOLDER_SUFFIX = 'surveys'

# Job folders are full of analysis spreadsheets - cost calculators, raw-data extracts,
# per-position calc sheets. They never reach the picker, because the parser factory
# claims no parser for them, so they need no filtering here.
#
# The exception is "*overview.xlsx", which SvanFileParser does claim and which IS
# instrument output. So a spreadsheet that gets this far is data, and is flagged for
# display only - it must not be demoted.
ANALYSIS_EXTENSIONS = ('.xlsx', '.xls')
_INSTRUMENT_WORKBOOK_MARKER = 'overview'

# A measurement shorter than this is a spot/manual reading rather than an unattended
# survey. Judged on measured span, not on folder naming, so it holds even when the
# folder is not called something helpful like "Manuals".
SPOT_MEASUREMENT_MAX_SECONDS = 60 * 60

# Folder names that mark a campaign rather than a position.
VISIT_FOLDER_HINTS = (
    'verification', 'monitoring', 'testing', 'test', 'glazing', 'manuals',
    'manual', 'survey', 'visit', 'phase', 'round',
)
# Complete words only. A prefix match would read "Marlow Gardens" as March and
# "summary" as March too - a site name is not a date.
_MONTH_NAMES = (
    'jan', 'january', 'feb', 'february', 'mar', 'march', 'apr', 'april',
    'may', 'jun', 'june', 'jul', 'july', 'aug', 'august',
    'sep', 'sept', 'september', 'oct', 'october', 'nov', 'november',
    'dec', 'december',
)

# <date>_SLM_<nnn>[_<band>_<kind>].txt
NTI_SESSION_RE = re.compile(
    r'^(?P<session>\d{4}-\d{2}-\d{2}_SLM_\d{3})'
    r'(?:_(?P<band>123|RTA_3rd))?'
    r'(?:_(?P<kind>Rpt_Report|Report|Log|VoiceNote))?'
    r'\.(?P<ext>txt|xl2)$',
    re.IGNORECASE,
)

# SvanFileParser accepts _LOG.CSV and _LOG_*.CSV (data_parsers.py: "_log_1s.csv,
# _log_10s.csv"). Without the optional rate suffix those files miss the role entirely
# and split away from their own summary into a separate, wrongly named position.
SVAN_ROLE_RE = re.compile(
    r'^(?P<stem>.+?)[_\s-]*(?P<role>log|summary)(?P<rate>_\d+[a-z]*)?\.csv$',
    re.IGNORECASE,
)


@dataclass
class FileFacts:
    """What we can say about one candidate file without parsing it."""
    path: str
    relative_path: str
    size_bytes: int = 0
    instrument: str = ''          # 'NTi' | 'Svan' | ''
    role: str = ''                # 'log' | 'summary' | 'report' | 'raw' | 'voice_note' | ''
    has_spectral: Optional[bool] = None
    session: str = ''             # NTi session key, so its files collapse into one row
    is_analysis_workbook: bool = False


@dataclass
class SurveyGroup:
    """
    A candidate position: one recorder, in one place, during one visit.

    This is the unit the picker should present. A single NTi session emits about 5.5
    files and a Svan position 2-3, so listing files makes the user do the grouping by
    hand; listing groups does not.
    """
    key: str
    label: str
    visit: str = ''
    sources: List[Dict] = field(default_factory=list)
    instrument: str = ''
    roles: List[str] = field(default_factory=list)
    has_spectral: bool = False
    start_time: str = ''
    end_time: str = ''
    duration_seconds: Optional[float] = None
    total_size_bytes: int = 0
    is_spot_measurement: bool = False
    recommended: bool = False

    @property
    def file_count(self) -> int:
        return len(self.sources)

    def describe_contents(self) -> str:
        """e.g. 'log + summary + audio' - what this position actually offers."""
        ordered = [role for role in ('log', 'summary', 'audio', 'raw', 'voice_note')
                   if role in self.roles]
        extras = sorted(r for r in self.roles if r and r not in ordered)
        return ' + '.join(ordered + extras) or 'data'


def find_survey_root(job_dir: str) -> str:
    """
    Return the folder inside `job_dir` that holds survey data.

    Falls back to the job folder itself when there is no Surveys folder, so nothing is
    hidden from jobs that do not follow the convention.
    """
    if not job_dir or not os.path.isdir(job_dir):
        return job_dir

    try:
        entries = sorted(os.listdir(job_dir))
    except OSError as exc:
        logger.warning("Could not list job directory '%s': %s", job_dir, exc)
        return job_dir

    for entry in entries:
        candidate = os.path.join(job_dir, entry)
        if os.path.isdir(candidate) and entry.strip().lower().endswith(SURVEY_FOLDER_SUFFIX):
            logger.info("Survey root for '%s': %s", os.path.basename(job_dir), entry)
            return candidate

    logger.info(
        "No '<job> Surveys' folder under '%s'; scanning the job folder itself.",
        os.path.basename(job_dir),
    )
    return job_dir


def looks_like_visit_folder(name: str) -> bool:
    """
    True when a folder name reads as a campaign rather than a position.

    Positions are recorder tokens (``971-2``, ``L350``); visits are dated or purposeful
    (``july 2026``, ``250829 Glazing Tests``, ``Verification Monitoring``).
    """
    if not name:
        return False

    # Match whole words only. Substring matching is a trap here: "summary" contains
    # "mar", "Contest" contains "test". Separators are normalised to spaces first so
    # that "july_2026" still yields a "july" token.
    lowered = re.sub(r'[_\-.]+', ' ', name.strip().lower())

    if re.search(r'\b(?:%s)s?\b' % '|'.join(VISIT_FOLDER_HINTS), lowered):
        return True
    if re.search(r'\b(?:%s)\b' % '|'.join(_MONTH_NAMES), lowered):
        return True
    # A bare or embedded 4-digit year, e.g. "2026 works".
    if re.search(r'(?:^|\D)(19|20)\d{2}(?:\D|$)', lowered):
        return True
    return False


def classify_file(path: str, relative_path: str, size_bytes: int = 0) -> FileFacts:
    """Derive instrument, role and spectral content from a filename."""
    facts = FileFacts(path=path, relative_path=relative_path, size_bytes=size_bytes)
    filename = os.path.basename(relative_path or path)
    lowered = filename.lower()

    if lowered.endswith(ANALYSIS_EXTENSIONS) and _INSTRUMENT_WORKBOOK_MARKER not in lowered:
        facts.is_analysis_workbook = True
        return facts

    nti = NTI_SESSION_RE.match(filename)
    if nti:
        facts.instrument = 'NTi'
        facts.session = nti.group('session')
        band = (nti.group('band') or '').lower()
        kind = (nti.group('kind') or '').lower()
        # '123' is broadband, 'rta_3rd' is third-octave.
        facts.has_spectral = band == 'rta_3rd' if band else None
        if nti.group('ext').lower() == 'xl2':
            facts.role = 'raw'
        elif kind == 'log':
            facts.role = 'log'
        elif kind in ('report', 'rpt_report'):
            facts.role = 'summary'
        elif kind == 'voicenote':
            facts.role = 'voice_note'
        return facts

    svan = SVAN_ROLE_RE.match(filename)
    if svan:
        facts.instrument = 'Svan'
        facts.role = svan.group('role').lower()
        return facts

    if lowered.endswith('.svl'):
        facts.instrument = 'Svan'
        facts.role = 'raw'
        return facts

    return facts


def derive_group(relative_path: str, survey_root_name: str = '') -> Dict[str, str]:
    """
    Work out which visit and position a file belongs to, from its path.

    Returns a dict with 'visit' and 'position'. Either may be empty when the layout is
    flat, in which case the caller falls back to the filename.
    """
    parts = [p for p in (relative_path or '').replace('\\', '/').split('/') if p]
    folders = parts[:-1]  # drop the filename

    if survey_root_name and folders and folders[0].strip().lower() == survey_root_name.strip().lower():
        folders = folders[1:]

    if not folders:
        return {'visit': '', 'position': ''}

    if len(folders) == 1:
        # One level: a visit folder on its own means the files sit loose in a campaign;
        # otherwise treat it as the position.
        if looks_like_visit_folder(folders[0]):
            return {'visit': folders[0], 'position': ''}
        return {'visit': '', 'position': folders[0]}

    # Two or more levels: the last folder is the position, and the first visit-looking
    # folder above it is the campaign.
    position = folders[-1]
    visit = ''
    for folder in folders[:-1]:
        if looks_like_visit_folder(folder):
            visit = folder
            break
    if not visit:
        visit = folders[0]
    return {'visit': visit, 'position': position}


def position_label_from_filename(filename: str) -> str:
    """
    Fall back to a position label when the folder layout is flat.

    Meter/recorder tokens are what these are called in practice, and are a fine
    starting label - positions get renamed in the dashboard afterwards.
    """
    stem = os.path.splitext(os.path.basename(filename or ''))[0]

    nti = NTI_SESSION_RE.match(os.path.basename(filename or ''))
    if nti:
        return nti.group('session')

    svan = SVAN_ROLE_RE.match(os.path.basename(filename or ''))
    if svan:
        stem = svan.group('stem')

    cleaned = re.sub(r'[_\s-]*(log|summary|report|rpt_report)(_\d+[a-z]*)?$', '', stem,
                     flags=re.IGNORECASE)
    return cleaned.strip(' _-') or stem


# --- Cheap time-span probing -------------------------------------------------------
#
# Reading ~8 KB from each end of a file is enough to recover its measurement span.
# On a 71 MB, 4-day, 1 s log that costs ~4.5 ms against ~2.5 s for a full parse, so it
# is affordable for every candidate in a job folder.

_PROBE_BYTES = 8192
# The separator between date and time must allow tabs: NTiFileParser reads its table
# with sep='\t' and keeps Date and Time as separate columns, so real rows look like
# "2025-04-28<TAB>11:00:00". Newlines are deliberately excluded so a date on one line
# is never paired with a time on the next.
_DATE_TOKEN_RE = re.compile(
    r'\d{4}[-/]\d{2}[-/]\d{2}[ \tT]+\d{2}:\d{2}(?::\d{2})?'
    r'|\d{2}[-/]\d{2}[-/]\d{4}[ \tT]+\d{2}:\d{2}(?::\d{2})?'
)


def _first_timestamp_in(text: str):
    """Return the first parseable timestamp in a block of text, or None."""
    import pandas as pd

    for match in _DATE_TOKEN_RE.finditer(text):
        try:
            return pd.Timestamp(match.group(0))
        except (ValueError, TypeError):
            continue
    return None


def _last_timestamp_in(text: str):
    import pandas as pd

    for match in reversed(list(_DATE_TOKEN_RE.finditer(text))):
        try:
            return pd.Timestamp(match.group(0))
        except (ValueError, TypeError):
            continue
    return None


def peek_time_span(path: str):
    """
    Recover a file's measurement span by reading only its head and tail.

    Returns (start, end) as pandas Timestamps, either of which may be None. Never
    raises: an unreadable or unrecognised file simply yields (None, None), and the
    caller treats span as unknown rather than failing the scan.
    """
    try:
        with open(path, 'rb') as handle:
            head = handle.read(_PROBE_BYTES).decode('utf-8', 'replace')
            size = handle.seek(0, 2)
            if size > _PROBE_BYTES:
                handle.seek(max(0, size - _PROBE_BYTES))
                tail = handle.read().decode('utf-8', 'replace')
            else:
                tail = head
    except OSError as exc:
        logger.debug("Could not probe '%s': %s", path, exc)
        return None, None

    start = _first_timestamp_in(head)
    end = _last_timestamp_in(tail)
    if start is not None and end is not None and end < start:
        start, end = end, start
    return start, end


def span_seconds(start, end) -> Optional[float]:
    """Duration in seconds, or None when either end is unknown."""
    if start is None or end is None:
        return None
    try:
        return max(0.0, (end - start).total_seconds())
    except (TypeError, AttributeError):
        return None


def is_spot_measurement(duration_seconds: Optional[float]) -> bool:
    """
    True for a short manual reading rather than an unattended survey.

    Unknown duration is treated as not-spot: better to offer a file the user does not
    want than to hide one they do.
    """
    if duration_seconds is None:
        return False
    return duration_seconds < SPOT_MEASUREMENT_MAX_SECONDS


# --- Grouping scanned files into candidate positions --------------------------------

def _group_key(source: Dict) -> tuple:
    """
    Identify the position a scanned source belongs to.

    NTi emits ~5.5 files per session, so the session token is part of the key: without
    it a folder of 13 manual readings presents as 70-odd rows. Svan files in one
    position folder share a key and collapse to a single row.
    """
    return (
        source.get('visit') or '',
        source.get('group_label') or source.get('position_name') or '',
        source.get('session') or '',
    )


def _min_iso(values: List[str]) -> str:
    present = [v for v in values if v]
    return min(present) if present else ''


def _max_iso(values: List[str]) -> str:
    present = [v for v in values if v]
    return max(present) if present else ''


def build_groups(sources: List[Dict]) -> List[SurveyGroup]:
    """
    Collapse scanned sources into candidate positions.

    Ordering puts recommended groups first, then by visit and label, so the rows a user
    most likely wants are at the top without them having to sort.
    """
    buckets: Dict[tuple, List[Dict]] = {}
    for source in sources or []:
        # Saved configs are an action, not a position; leave them out of grouping.
        if source.get('parser_type') == 'config':
            continue
        buckets.setdefault(_group_key(source), []).append(source)

    groups: List[SurveyGroup] = []
    for (visit, label, session), members in buckets.items():
        roles = sorted({(m.get('role') or '') for m in members if m.get('role')})
        instruments = sorted({(m.get('instrument') or '') for m in members if m.get('instrument')})
        starts = [m.get('start_time') or '' for m in members]
        ends = [m.get('end_time') or '' for m in members]
        durations = [m.get('duration_seconds') for m in members
                     if isinstance(m.get('duration_seconds'), (int, float))]

        # A position is a spot reading only when everything in it is. One long log
        # alongside short extras still makes this a real measurement.
        measured = [m for m in members if m.get('duration_seconds') is not None]
        is_spot = bool(measured) and all(m.get('is_spot_measurement') for m in measured)

        display_label = label or session or 'Unnamed position'
        groups.append(SurveyGroup(
            key='|'.join((visit, display_label, session)),
            label=display_label,
            visit=visit,
            sources=members,
            instrument=', '.join(instruments),
            roles=roles,
            has_spectral=any(bool(m.get('has_spectral')) for m in members),
            start_time=_min_iso(starts),
            end_time=_max_iso(ends),
            duration_seconds=max(durations) if durations else None,
            total_size_bytes=sum(int(m.get('file_size_bytes') or 0) for m in members),
            is_spot_measurement=is_spot,
            recommended=any(bool(m.get('recommended')) for m in members) and not is_spot,
        ))

    groups.sort(key=lambda g: (not g.recommended, g.visit, g.label))
    return groups


def list_visits(groups: List[SurveyGroup]) -> List[Dict]:
    """
    Summarise the visits present, newest first.

    Multiple visits per job are the norm rather than the exception - a structural
    survey found 16 of 20 jobs had several - so choosing one is the natural first
    question the picker should ask.
    """
    summary: Dict[str, Dict] = {}
    for group in groups:
        entry = summary.setdefault(group.visit, {
            'visit': group.visit,
            'label': group.visit or 'Main survey',
            'position_count': 0,
            'recommended_count': 0,
            'start_time': '',
            'end_time': '',
        })
        entry['position_count'] += 1
        if group.recommended:
            entry['recommended_count'] += 1
        entry['start_time'] = _min_iso([entry['start_time'], group.start_time])
        entry['end_time'] = _max_iso([entry['end_time'], group.end_time])

    # Newest first: the visit a user opens the picker for is usually the recent one.
    return sorted(summary.values(), key=lambda e: (e['start_time'] or '', e['label']), reverse=True)


def format_duration(seconds: Optional[float]) -> str:
    """Human-readable span for a table cell."""
    if seconds is None:
        return ''
    if seconds < 90:
        return f"{seconds:.0f} s"
    if seconds < 90 * 60:
        return f"{seconds / 60:.0f} min"
    if seconds < 48 * 3600:
        return f"{seconds / 3600:.1f} h"
    return f"{seconds / 86400:.1f} d"
