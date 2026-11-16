"""Autosave of the dashboard workspace beside the job config.

The browser sends the persistable app state a couple of seconds after every annotation, layout or
offset change (``autosave_workspace`` session action).  This module owns the file side of that:

* ``<config_stem>.workspace.json``      the live autosave, rewritten atomically (temp + replace);
* ``<config_stem>.workspace.<yyyymmdd-hhmmss>.bak.json``  the file as it was when a session first
                                         wrote (the newest ``BACKUP_KEEP`` are kept), plus one more
                                         whenever a save would shrink the region+marker count below
                                         what the file holds and no backup of that content exists;
* ``<config_stem>.workspace.corrupt-<timestamp>.json``  an unreadable autosave, moved aside rather
                                         than overwritten.

Two tabs on the same job would silently clobber each other.  Every write carries a revision number
in an ``autosave`` header; a session remembers the revision it started from (``base_rev``) and
refuses to write when the file now holds a newer revision written by a different session.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

WORKSPACE_SUFFIX = '.workspace.json'
BACKUP_KEEP = 10
# Google Drive for desktop briefly locks files while it syncs them.
_REPLACE_ATTEMPTS = 6
_REPLACE_DELAY_S = 0.25
# A newer revision written by a session that has ended (or sent its final pagehide flush) is
# adopted, not treated as a rival tab, when it landed within this long of the new session starting.
ADOPT_WINDOW_S = 60.0

_FILE_LOCKS: Dict[str, threading.RLock] = {}
_FILE_LOCKS_GUARD = threading.Lock()
_ENDED_SESSIONS: set = set()


def _file_lock(config_path: str | os.PathLike) -> threading.RLock:
    """One lock per config file: the restore read and every session's write share it."""
    key = os.path.normcase(os.path.abspath(str(config_path)))
    with _FILE_LOCKS_GUARD:
        return _FILE_LOCKS.setdefault(key, threading.RLock())


def workspace_autosave_path(config_path: str | os.PathLike) -> Path:
    """``<config_stem>.workspace.json`` beside the config."""
    cfg = Path(config_path)
    return cfg.with_name(cfg.stem + WORKSPACE_SUFFIX)


def cfg_stem(config_path: str | os.PathLike) -> str:
    return Path(config_path).stem


def workspace_backup_path(config_path: str | os.PathLike, stamp: str = '') -> Path:
    """``<stem>.workspace.<yyyymmdd-hhmmss>.bak.json`` (``stamp`` defaults to now)."""
    cfg = Path(config_path)
    stamp = stamp or datetime.now().strftime('%Y%m%d-%H%M%S')
    return cfg.with_name(f"{cfg.stem}.workspace.{stamp}.bak.json")


def list_workspace_backups(config_path: str | os.PathLike) -> list:
    """Existing timestamped backups, oldest first."""
    cfg = Path(config_path)
    prefix, suffix = f"{cfg.stem}.workspace.2", '.bak.json'
    try:
        names = [p for p in cfg.parent.iterdir() if p.name.startswith(prefix) and p.name.endswith(suffix)]
    except OSError:
        return []
    return sorted(names, key=lambda p: p.name[:-len(suffix)])


def _annotation_count(document: Any) -> int:
    """Regions + markers in a workspace payload (what a backup is protecting)."""
    app_state = document.get('appState') if isinstance(document, dict) else None
    if not isinstance(app_state, dict):
        return 0
    total = 0
    for key in ('regions', 'markers'):
        block = app_state.get(key)
        by_id = block.get('byId') if isinstance(block, dict) else None
        total += len(by_id) if isinstance(by_id, dict) else 0
    return total


def read_workspace_autosave(config_path: str | os.PathLike | None) -> Optional[Dict[str, Any]]:
    """Return the autosaved workspace payload, or ``None`` when absent or unreadable."""
    if not config_path:
        return None
    path = workspace_autosave_path(config_path)
    try:
        with _file_lock(config_path), open(path, 'r', encoding='utf-8-sig') as handle:
            payload = json.load(handle)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        logger.warning("Autosave %s could not be read (%s); ignoring it.", path, exc)
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get('appState'), dict):
        logger.warning("Autosave %s has no appState; ignoring it.", path)
        return None
    return payload


_LATEST: Dict[str, Dict[str, Any]] = {}


def _latest_key(config_path: str | os.PathLike) -> str:
    return os.path.normcase(os.path.abspath(str(config_path)))


def latest_workspace(config_path: str | os.PathLike | None) -> Optional[Dict[str, Any]]:
    """Newest autosaved workspace for ``config_path``: the last one any session wrote in this
    process, else whatever is on disk.  Works with no browser tab open."""
    if not config_path:
        return None
    return _LATEST.get(_latest_key(config_path)) or read_workspace_autosave(config_path)


def autosave_revision(payload: Optional[Dict[str, Any]]) -> int:
    header = (payload or {}).get('autosave')
    try:
        return int(header.get('rev', 0)) if isinstance(header, dict) else 0
    except (TypeError, ValueError):
        return 0


def _retry_permission(operation, *args) -> None:
    last: Optional[BaseException] = None
    for attempt in range(_REPLACE_ATTEMPTS):
        try:
            operation(*args)
            return
        except PermissionError as exc:
            last = exc
            time.sleep(_REPLACE_DELAY_S * (attempt + 1))
    assert last is not None
    raise last


@dataclass
class AutosaveResult:
    status: str                      # 'ok' | 'conflict' | 'error' | 'unavailable'
    message: str = ''
    rev: int = 0
    saved_at: str = ''
    path: str = ''

    @property
    def ok(self) -> bool:
        return self.status == 'ok'


@dataclass
class WorkspaceAutosave:
    """Per-session writer for one config's autosave file."""

    config_path: Optional[str]
    base_rev: int = 0
    session_id: Optional[str] = None
    # True for a session that did not restore the file (--no-restore / ?fresh=1 / explicit --state):
    # its first write moves the existing autosave to <stem>.workspace.<timestamp>.json instead of
    # replacing it.
    preserve_existing: bool = False
    backup_done: bool = False
    # Region+marker count of the newest backup this session made (the shrink guard compares to it).
    backup_count: int = -1
    created_epoch: float = field(default_factory=time.time, repr=False)
    last_payload: Optional[Dict[str, Any]] = field(default=None, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @classmethod
    def for_config(cls, config_path: str | os.PathLike | None) -> 'WorkspaceAutosave':
        """Create a writer and adopt the revision currently on disk as this session's base."""
        autosave = cls(config_path=str(config_path) if config_path else None)
        existing = read_workspace_autosave(config_path)
        autosave.base_rev = autosave_revision(existing)
        autosave.last_payload = existing
        return autosave

    @property
    def available(self) -> bool:
        return bool(self.config_path)

    @property
    def path(self) -> Optional[Path]:
        return workspace_autosave_path(self.config_path) if self.config_path else None

    def save(self, payload: Any) -> AutosaveResult:
        """Write ``payload`` (a workspace payload with ``appState``). Never raises."""
        if not self.available:
            return AutosaveResult('unavailable', 'No config file is attached to this session, so autosave is off.')
        if not isinstance(payload, dict) or not isinstance(payload.get('appState'), dict):
            return AutosaveResult('error', 'Autosave payload has no appState.')
        with self._lock, _file_lock(self.config_path):
            try:
                return self._save_locked(payload)
            except Exception as exc:  # pragma: no cover - defensive; surfaced as a toast
                logger.error("Autosave failed: %s", exc, exc_info=True)
                return AutosaveResult('error', f'Autosave failed: {exc}', path=str(self.path))

    def end(self) -> None:
        """The browser session is gone; a newer revision it left behind is adoptable."""
        if self.session_id:
            _ENDED_SESSIONS.add(self.session_id)

    def _adoptable(self, header: Any, disk_session: Optional[str]) -> bool:
        if not isinstance(header, dict):
            return False
        if not (header.get('final') is True or (disk_session and disk_session in _ENDED_SESSIONS)):
            return False
        try:
            age = float(header.get('savedEpoch')) - self.created_epoch
        except (TypeError, ValueError):
            return False
        return -1.0 <= age <= ADOPT_WINDOW_S

    def _backup(self, target: Path, content_count: int) -> None:
        """Copy the live file to a new timestamped backup and rotate. Never overwrites a backup."""
        stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        backup = workspace_backup_path(self.config_path, stamp)
        n = 1
        while backup.exists():
            n += 1
            backup = workspace_backup_path(self.config_path, f"{stamp}-{n}")
        try:
            _retry_permission(shutil.copyfile, target, backup)
        except OSError as exc:
            logger.warning("Could not write autosave backup %s: %s", backup, exc)
            return
        self.backup_count = content_count
        for old in list_workspace_backups(self.config_path)[:-BACKUP_KEEP]:
            try:
                old.unlink()
            except OSError:
                pass

    def _save_locked(self, payload: Dict[str, Any]) -> AutosaveResult:
        target = self.path
        assert target is not None
        session_id = str(payload.get('sessionId') or self.session_id or '') or None
        existing_ok = True
        existing: Optional[Dict[str, Any]] = None
        if target.exists():
            try:
                with open(target, 'r', encoding='utf-8-sig') as handle:
                    existing = json.load(handle)
                if not isinstance(existing, dict):
                    existing_ok = False
            except (OSError, ValueError):
                existing_ok = False
            if not existing_ok:
                aside = target.with_name(
                    target.name[:-len('.json')] + f".corrupt-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json")
                try:
                    _retry_permission(os.replace, target, aside)
                    logger.warning("Unreadable autosave moved aside to %s", aside)
                except OSError as exc:
                    logger.warning("Could not move unreadable autosave aside: %s", exc)
                existing = None

        header = (existing or {}).get('autosave') if isinstance(existing, dict) else None
        disk_rev = autosave_revision(existing)
        disk_session = header.get('sessionId') if isinstance(header, dict) else None
        disk_count = _annotation_count(existing)
        adopted = False
        if existing is not None and disk_rev > self.base_rev and disk_session != session_id:
            if not self._adoptable(header, disk_session):
                return AutosaveResult(
                    'conflict',
                    'Another dashboard tab for this job has saved newer annotations. This tab did not '
                    'overwrite them. Reload the page to pick them up.',
                    rev=disk_rev, path=str(target))
            # The previous tab's last flush landed after this tab read the file (page reload). Its
            # writer has ended, so this tab takes over; the flushed copy is kept as a backup first.
            adopted = True
            logger.warning("Autosave rev %s from ended session %s adopted; keeping it as a backup.",
                           disk_rev, disk_session)

        if existing is not None and not self.backup_done and self.preserve_existing:
            kept = target.with_name(cfg_stem(self.config_path) + f".workspace.{datetime.now().strftime('%Y%m%d-%H%M%S')}.json")
            try:
                _retry_permission(os.replace, target, kept)
                logger.info("Existing autosave kept as %s", kept.name)
            except OSError as exc:
                logger.warning("Could not set the existing autosave aside (%s); copying instead.", exc)
                _retry_permission(shutil.copyfile, target, kept)
            self.backup_done = True
        elif existing is not None:
            new_count = _annotation_count(payload)
            shrinking = new_count < disk_count and disk_count > self.backup_count
            if not self.backup_done or adopted or shrinking:
                self._backup(target, disk_count)
            self.backup_done = True
        elif existing is None:
            self.backup_done = True

        new_rev = max(disk_rev, self.base_rev) + 1
        saved_at = datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')
        document = dict(payload)
        document['autosave'] = {
            'rev': new_rev,
            'sessionId': session_id,
            'savedAt': saved_at,
            'savedEpoch': time.time(),
            'config': os.path.basename(self.config_path or ''),
        }
        if payload.get('final') is True:
            document['autosave']['final'] = True  # the page's pagehide flush: a newer tab may adopt it
        document.pop('sessionId', None)
        document.pop('rev', None)
        document.pop('final', None)

        tmp = target.with_name(target.name + '.tmp')
        with open(tmp, 'w', encoding='utf-8') as handle:
            json.dump(document, handle, ensure_ascii=False)
        try:
            _retry_permission(os.replace, tmp, target)
        except OSError:
            try:
                tmp.unlink()
            except OSError:
                pass
            raise
        self.base_rev = new_rev
        self.session_id = session_id
        self.last_payload = document
        _LATEST[_latest_key(self.config_path)] = document
        return AutosaveResult('ok', 'Saved', rev=new_rev, saved_at=saved_at, path=str(target))
