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

try:
    from .data_parsers import ParsedData
except ImportError:
    from data_parsers import ParsedData


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
            cls._instance._load_from_disk()
        return cls._instance

    def _ensure_cache_dir(self):
        """Create cache directory if it doesn't exist."""
        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning(f"Failed to create cache directory: {e}")

    def _get_cache_key(self, file_path: str) -> str:
        """Generate a unique cache key for a file path."""
        # Use absolute path for consistency
        abs_path = os.path.abspath(file_path)
        # Hash the path for a shorter key
        return hashlib.md5(abs_path.encode('utf-8')).hexdigest()

    def _get_cache_file_path(self, cache_key: str) -> Path:
        """Get the path to the cache file for a given key."""
        return self._cache_dir / f"{cache_key}.pkl"

    def _load_from_disk(self):
        """Load all cache entries from disk."""
        if not self._cache_dir.exists():
            return

        loaded_count = 0
        for cache_file in self._cache_dir.glob("*.pkl"):
            try:
                with open(cache_file, 'rb') as f:
                    entry: CacheEntry = pickle.load(f)
                    cache_key = cache_file.stem
                    self._cache[cache_key] = entry
                    loaded_count += 1
            except Exception as e:
                logger.debug(f"Failed to load cache entry {cache_file.name}: {e}")
                # Remove corrupted cache files
                try:
                    cache_file.unlink()
                except:
                    pass

        if loaded_count > 0:
            logger.info(f"Loaded {loaded_count} cached parsed file(s) from disk")

    def _save_entry_to_disk(self, cache_key: str, entry: CacheEntry):
        """Save a single cache entry to disk."""
        try:
            cache_file = self._get_cache_file_path(cache_key)
            with open(cache_file, 'wb') as f:
                pickle.dump(entry, f)
        except Exception as e:
            logger.warning(f"Failed to save cache entry to disk: {e}")

    def _is_file_modified(self, file_path: str, cached_mtime: float, cached_size: int) -> bool:
        """Check if a file has been modified since it was cached."""
        try:
            stat = os.stat(file_path)
            return stat.st_mtime != cached_mtime or stat.st_size != cached_size
        except (OSError, FileNotFoundError):
            # File doesn't exist or can't be accessed
            return True

    def get(self, file_path: str, return_all_columns: bool = False) -> Optional[ParsedData]:
        """
        Retrieve cached parsed data for a file if available and valid.

        Args:
            file_path: Path to the file
            return_all_columns: Whether all columns were requested during parsing

        Returns:
            ParsedData object if cached and valid, None otherwise
        """
        cache_key = self._get_cache_key(file_path)

        if cache_key not in self._cache:
            return None

        entry = self._cache[cache_key]

        # Verify the file hasn't been modified
        if self._is_file_modified(file_path, entry.file_mtime, entry.file_size):
            logger.debug(f"Cache miss (file modified): {os.path.basename(file_path)}")
            # Remove stale entry
            self._remove_entry(cache_key)
            return None

        # Note: We don't cache based on return_all_columns parameter
        # If this becomes important, we could enhance the cache key
        logger.debug(f"Cache hit: {os.path.basename(file_path)}")
        return entry.parsed_data

    def put(self, file_path: str, parsed_data: ParsedData, return_all_columns: bool = False):
        """
        Store parsed data in the cache.

        Args:
            file_path: Path to the file
            parsed_data: Parsed data to cache
            return_all_columns: Whether all columns were requested during parsing
        """
        try:
            stat = os.stat(file_path)
            cache_key = self._get_cache_key(file_path)

            entry = CacheEntry(
                parsed_data=parsed_data,
                file_path=os.path.abspath(file_path),
                file_mtime=stat.st_mtime,
                file_size=stat.st_size,
                cache_timestamp=datetime.now().timestamp()
            )

            self._cache[cache_key] = entry
            self._save_entry_to_disk(cache_key, entry)
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

        # Remove all cache files
        if self._cache_dir.exists():
            for cache_file in self._cache_dir.glob("*.pkl"):
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

        return {
            'entry_count': len(self._cache),
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
