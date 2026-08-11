"""Small, source-validated cache for completed audio-alignment metadata."""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import os
import pickle
import tempfile
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)

AUDIO_ALIGNMENT_CACHE_VERSION = "audio-alignment-v1"
_AUDIO_SUFFIXES = {".wav"}


def _normalise_json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _normalise_json_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, set):
        normalised = [_normalise_json_value(item) for item in value]
        return sorted(normalised, key=lambda item: json.dumps(item, sort_keys=True, default=str))
    if isinstance(value, (tuple, list)):
        return [_normalise_json_value(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


def _file_signature(path: str) -> dict[str, Any]:
    normalised_path = os.path.normcase(os.path.normpath(os.path.abspath(path)))
    try:
        stat = os.stat(path)
    except OSError:
        return {"path": normalised_path, "state": "missing"}

    return {
        "path": normalised_path,
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


def _audio_directory_signature(path: str) -> dict[str, Any]:
    normalised_path = os.path.normcase(os.path.normpath(os.path.abspath(path)))
    try:
        entries = []
        with os.scandir(path) as directory_entries:
            for entry in directory_entries:
                if not entry.is_file():
                    continue
                name_lower = entry.name.casefold()
                is_audio_file = Path(name_lower).suffix in _AUDIO_SUFFIXES
                is_audio_index = name_lower.endswith("_audio_index.json")
                if not is_audio_file and not is_audio_index:
                    continue
                stat = entry.stat()
                entries.append(
                    {
                        "name": name_lower,
                        "size": stat.st_size,
                        "mtime_ns": stat.st_mtime_ns,
                    }
                )
        entries.sort(key=lambda item: item["name"])
        return {"path": normalised_path, "entries": entries}
    except OSError:
        return {"path": normalised_path, "state": "missing"}


def build_source_fingerprint(source_configs: list[dict[str, Any]]) -> str | None:
    """Fingerprint source options plus file and audio-directory state."""
    if not source_configs:
        return None

    canonical_configs = []
    for config in source_configs:
        parser_type = str(
            config.get("parser_type") or config.get("parser_type_hint") or "auto"
        ).casefold()
        raw_paths = config.get("file_paths", config.get("file_path", []))
        if isinstance(raw_paths, str):
            paths = [raw_paths]
        elif isinstance(raw_paths, (set, tuple, list)):
            paths = [str(path) for path in raw_paths]
        else:
            paths = []

        signatures = []
        for path in sorted(paths, key=lambda item: os.path.normcase(os.path.abspath(item))):
            if parser_type in {"audio", "wav"} and os.path.isdir(path):
                signatures.append(_audio_directory_signature(path))
            else:
                signatures.append(_file_signature(path))

        options = {
            key: value
            for key, value in config.items()
            if key not in {"file_path", "file_paths"}
        }
        canonical_configs.append(
            {
                "options": _normalise_json_value(options),
                "sources": signatures,
            }
        )

    canonical_configs.sort(
        key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":"), default=str)
    )
    payload = {"configs": canonical_configs}
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
    return f"sources-v1:{digest}"


def build_audio_alignment_cache_key(
    source_configs: list[dict[str, Any]],
    alignment_settings: dict[str, Any],
) -> str | None:
    """Fingerprint every input that can affect the audio-alignment result."""
    source_fingerprint = build_source_fingerprint(source_configs)
    if source_fingerprint is None:
        return None

    payload = {
        "version": AUDIO_ALIGNMENT_CACHE_VERSION,
        "settings": _normalise_json_value(alignment_settings),
        "source_fingerprint": source_fingerprint,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
    return f"{AUDIO_ALIGNMENT_CACHE_VERSION}:{digest}"


def capture_audio_alignment(app_data: Any) -> dict[str, Any]:
    """Copy the small per-position audio tables modified by alignment."""
    snapshot = {}
    for position_name in app_data.positions():
        position_data = app_data[position_name]
        if not getattr(position_data, "has_audio_files", False):
            continue
        snapshot[position_name] = copy.deepcopy(getattr(position_data, "audio_files_list", None))
    return snapshot


def restore_audio_alignment(app_data: Any, snapshot: dict[str, Any]) -> bool:
    """Restore a complete alignment snapshot, returning False if it is incomplete."""
    audio_positions = {
        position_name
        for position_name in app_data.positions()
        if getattr(app_data[position_name], "has_audio_files", False)
    }
    if not audio_positions or set(snapshot) != audio_positions:
        return False

    for position_name in audio_positions:
        app_data[position_name].audio_files_list = copy.deepcopy(snapshot[position_name])
    return True


class AudioAlignmentCache:
    """Disk-backed cache containing only completed audio-alignment tables."""

    def __init__(self, cache_file: str | Path | None = None) -> None:
        self._cache_file = Path(cache_file) if cache_file else (
            Path(tempfile.gettempdir()) / "noise_survey_audio_alignment_cache.pkl"
        )
        self._data: dict[str, dict[str, Any]] = {}
        self._load_from_disk()

    def _load_from_disk(self) -> None:
        try:
            if not self._cache_file.exists():
                return
            with self._cache_file.open("rb") as cache_stream:
                loaded = pickle.load(cache_stream)
            if isinstance(loaded, dict):
                self._data = {
                    key: value
                    for key, value in loaded.items()
                    if isinstance(key, str) and key.startswith(f"{AUDIO_ALIGNMENT_CACHE_VERSION}:")
                }
        except Exception as exc:
            logger.warning("Failed to load audio-alignment cache: %s", exc)
            self._data = {}

    def _save_to_disk(self) -> None:
        self._cache_file.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self._cache_file.with_name(
            f"{self._cache_file.name}.{os.getpid()}.tmp"
        )
        try:
            with temporary_path.open("wb") as cache_stream:
                pickle.dump(self._data, cache_stream, protocol=pickle.HIGHEST_PROTOCOL)
            os.replace(temporary_path, self._cache_file)
        except Exception as exc:
            logger.warning("Failed to save audio-alignment cache: %s", exc)
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass

    def get(self, key: str | None) -> dict[str, Any] | None:
        if not key or key not in self._data:
            return None
        return copy.deepcopy(self._data[key])

    def put(self, key: str | None, snapshot: dict[str, Any]) -> None:
        if not key:
            return
        self._data[key] = copy.deepcopy(snapshot)
        self._save_to_disk()
