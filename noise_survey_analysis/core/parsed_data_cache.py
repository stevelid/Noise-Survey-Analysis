"""
parsed_data_cache.py
File-level caching for parsed noise data to avoid redundant file parsing.
"""
import os
import pickle
import hashlib
import logging
from pathlib import Path
from typing import Optional, Dict
from dataclasses import dataclass
from datetime import datetime
import tempfile

logger = logging.getLogger(__name__)

# Bump whenever parser OUTPUT changes (new columns, timezone/DST handling, merge-relevant
# fixes) so stale pickles from an older parser are never served. It is part of the cache key.
PARSER_CACHE_VERSION = 2

# Eviction limits (applied when the cache starts and after writes).
CACHE_MAX_AGE_SECONDS = 30 * 24 * 3600
CACHE_MAX_TOTAL_BYTES = 3 * 1024 ** 3

try:
    from .data_parsers import DEFAULT_TIMEZONE, ParsedData
except ImportError:
    from data_parsers import DEFAULT_TIMEZONE, ParsedData


@dataclass
class CacheEntry:
    """Metadata for a cached parsed file."""
    parsed_data: ParsedData
    file_path: str
    file_mtime: float  # Modification time
    file_size: int
    cache_timestamp: float


class ParsedDataCache:
    """
    Thread-safe file-level cache for ParsedData objects.

    Caches individual file parse results based on file path, mtime, and size.
    This allows reuse of parsed data even when loading different combinations
    of files (unlike caching the entire DataManager).
    """

    _instance = None
    _cache_dir = Path(tempfile.gettempdir()) / 'noise_survey_parsed_cache'

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._cache: Dict[str, CacheEntry] = {}
            cls._instance._ensure_cache_dir()
            cls._instance._evict_disk_entries()
        return cls._instance

    def _ensure_cache_dir(self):
        """Create cache directory if it doesn't exist."""
        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning(f"Failed to create cache directory: {e}")

    def _get_cache_key(
        self,
        file_path: str,
        return_all_columns: bool = False,
        timezone: Optional[str] = None,
    ) -> str:
        """Generate a unique cache key for a file path, parse profile, and timezone."""
        # Use absolute path for consistency
        abs_path = os.path.abspath(file_path)
        # Include parse profile and timezone so parse results are not cross-contaminated.
        profile = 'full' if return_all_columns else 'filtered'
        resolved_timezone = timezone or DEFAULT_TIMEZONE
        key_string = f"v{PARSER_CACHE_VERSION}::{abs_path}::{profile}::{resolved_timezone}"
        # Hash for a shorter key
        return hashlib.md5(key_string.encode('utf-8')).hexdigest()

    def _get_cache_file_path(self, cache_key: str) -> Path:
        """Get the path to the cache file for a given key."""
        return self._cache_dir / f"{cache_key}.pkl"

    def _load_entry_from_disk(self, cache_key: str) -> Optional[CacheEntry]:
        """Load one entry from disk on demand (nothing is unpickled at import)."""
        cache_file = self._get_cache_file_path(cache_key)
        if not cache_file.exists():
            return None
        try:
            with open(cache_file, 'rb') as f:
                entry: CacheEntry = pickle.load(f)
            try:
                os.utime(cache_file, None)  # touch: mtime doubles as last-used for LRU eviction
            except OSError:
                pass
            return entry
        except Exception as e:
            logger.debug(f"Failed to load cache entry {cache_file.name}: {e}")
            try:
                cache_file.unlink()  # corrupted/incompatible pickle
            except OSError:
                pass
            return None

    def _evict_disk_entries(self):
        """Drop entries older than 30 days, then least-recently-used until under the size cap."""
        try:
            files = []
            now = datetime.now().timestamp()
            for cache_file in self._cache_dir.glob("*.pkl"):
                try:
                    st = cache_file.stat()
                except OSError:
                    continue
                if now - st.st_mtime > CACHE_MAX_AGE_SECONDS:
                    self._remove_entry(cache_file.stem)
                    continue
                files.append((st.st_mtime, st.st_size, cache_file))
            total = sum(f[1] for f in files)
            if total > CACHE_MAX_TOTAL_BYTES:
                for mtime, size, cache_file in sorted(files, key=lambda f: f[0]):
                    if total <= CACHE_MAX_TOTAL_BYTES:
                        break
                    self._remove_entry(cache_file.stem)
                    total -= size
            for stale in self._cache_dir.glob("*.pkl.tmp*"):
                if now - stale.stat().st_mtime > 3600:
                    stale.unlink()
        except Exception as e:
            logger.debug(f"Cache eviction skipped: {e}")

    def _save_entry_to_disk(self, cache_key: str, entry: CacheEntry):
        """Save a single cache entry atomically (temp file + os.replace)."""
        cache_file = self._get_cache_file_path(cache_key)
        tmp_file = cache_file.with_name(f"{cache_file.name}.tmp{os.getpid()}")
        try:
            with open(tmp_file, 'wb') as f:
                pickle.dump(entry, f)
            os.replace(tmp_file, cache_file)
        except Exception as e:
            logger.warning(f"Failed to save cache entry to disk: {e}")
            try:
                if tmp_file.exists():
                    tmp_file.unlink()
            except OSError:
                pass

    def _is_file_modified(self, file_path: str, cached_mtime: float, cached_size: int) -> bool:
        """Check if a file has been modified since it was cached."""
        try:
            stat = os.stat(file_path)
            return stat.st_mtime != cached_mtime or stat.st_size != cached_size
        except (OSError, FileNotFoundError):
            # File doesn't exist or can't be accessed
            return True

    def get(
        self,
        file_path: str,
        return_all_columns: bool = False,
        timezone: Optional[str] = None,
    ) -> Optional[ParsedData]:
        """
        Retrieve cached parsed data for a file if available and valid.

        Args:
            file_path: Path to the file
            return_all_columns: Whether all columns were requested during parsing
            timezone: Timezone used to interpret naive datetimes

        Returns:
            ParsedData object if cached and valid, None otherwise
        """
        cache_key = self._get_cache_key(file_path, return_all_columns, timezone)

        entry = self._cache.get(cache_key)
        if entry is None:
            entry = self._load_entry_from_disk(cache_key)
            if entry is None:
                return None
            self._cache[cache_key] = entry

        # Verify the file hasn't been modified
        if self._is_file_modified(file_path, entry.file_mtime, entry.file_size):
            logger.debug(f"Cache miss (file modified): {os.path.basename(file_path)}")
            # Remove stale entry
            self._remove_entry(cache_key)
            return None

        logger.debug(f"Cache hit: {os.path.basename(file_path)}")
        return entry.parsed_data

    def put(
        self,
        file_path: str,
        parsed_data: ParsedData,
        return_all_columns: bool = False,
        timezone: Optional[str] = None,
    ):
        """
        Store parsed data in the cache.

        Args:
            file_path: Path to the file
            parsed_data: Parsed data to cache
            return_all_columns: Whether all columns were requested during parsing
            timezone: Timezone used to interpret naive datetimes
        """
        try:
            stat = os.stat(file_path)
            resolved_timezone = timezone or parsed_data.metadata.get('timezone') or DEFAULT_TIMEZONE
            cache_key = self._get_cache_key(file_path, return_all_columns, resolved_timezone)

            entry = CacheEntry(
                parsed_data=parsed_data,
                file_path=os.path.abspath(file_path),
                file_mtime=stat.st_mtime,
                file_size=stat.st_size,
                cache_timestamp=datetime.now().timestamp()
            )

            self._cache[cache_key] = entry
            self._save_entry_to_disk(cache_key, entry)
            self._evict_disk_entries()
            logger.debug(f"Cached: {os.path.basename(file_path)}")

        except Exception as e:
            logger.warning(f"Failed to cache parsed data for {file_path}: {e}")

    def _remove_entry(self, cache_key: str):
        """Remove a cache entry from memory and disk."""
        if cache_key in self._cache:
            del self._cache[cache_key]

        cache_file = self._get_cache_file_path(cache_key)
        try:
            if cache_file.exists():
                cache_file.unlink()
        except Exception as e:
            logger.debug(f"Failed to remove cache file: {e}")

    def clear(self):
        """Clear all cache entries."""
        self._cache.clear()

        # Remove all cache files (including leftover temp files)
        if self._cache_dir.exists():
            for cache_file in list(self._cache_dir.glob("*.pkl")) + list(self._cache_dir.glob("*.pkl.tmp*")):
                try:
                    cache_file.unlink()
                except Exception as e:
                    logger.debug(f"Failed to remove cache file {cache_file.name}: {e}")

        logger.info("Cleared parsed data cache")

    def get_stats(self) -> Dict:
        """Get cache statistics."""
        total_size = 0
        oldest_timestamp = None
        newest_timestamp = None

        for entry in self._cache.values():
            # Estimate size (this is approximate)
            if entry.parsed_data.totals_df is not None:
                total_size += entry.parsed_data.totals_df.memory_usage(deep=True).sum()
            if entry.parsed_data.spectral_df is not None:
                total_size += entry.parsed_data.spectral_df.memory_usage(deep=True).sum()

            if oldest_timestamp is None or entry.cache_timestamp < oldest_timestamp:
                oldest_timestamp = entry.cache_timestamp
            if newest_timestamp is None or entry.cache_timestamp > newest_timestamp:
                newest_timestamp = entry.cache_timestamp

        try:
            on_disk = {p.stem for p in self._cache_dir.glob("*.pkl")}
        except OSError:
            on_disk = set()
        return {
            'entry_count': len(on_disk | set(self._cache)),
            'estimated_memory_mb': total_size / (1024 * 1024) if total_size > 0 else 0,
            'cache_dir': str(self._cache_dir),
            'oldest_entry': datetime.fromtimestamp(oldest_timestamp) if oldest_timestamp else None,
            'newest_entry': datetime.fromtimestamp(newest_timestamp) if newest_timestamp else None,
        }


# Singleton instance
_parsed_data_cache = ParsedDataCache()


def get_parsed_data_cache() -> ParsedDataCache:
    """Get the singleton ParsedDataCache instance."""
    return _parsed_data_cache
