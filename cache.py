"""In-memory cache for FTP directory listings, keyed per host."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class FileEntry:
    name: str
    extension: str
    size: int
    modified: Optional[datetime]
    modified_str: str
    size_str: str
    host: str           # Which FTP host this file came from
    host_key: str       # Normalised "host:port" identifier


@dataclass
class HostCache:
    """Cache for a single FTP host."""
    files: list[FileEntry] = field(default_factory=list)
    loaded_at: Optional[datetime] = None
    error: Optional[str] = None

    def is_loaded(self) -> bool:
        return self.loaded_at is not None

    def clear(self) -> None:
        self.files = []
        self.loaded_at = None
        self.error = None

    def set(self, files: list[FileEntry]) -> None:
        self.files = files
        self.loaded_at = datetime.now()
        self.error = None

    def set_error(self, message: str) -> None:
        self.files = []
        self.loaded_at = datetime.now()   # Mark as "attempted"
        self.error = message


class MultiHostCache:
    """Aggregated cache across all configured hosts."""

    def __init__(self) -> None:
        # host_key -> HostCache
        self._caches: dict[str, HostCache] = {}

    # ------------------------------------------------------------------
    # Per-host operations
    # ------------------------------------------------------------------

    def get_host(self, host_key: str) -> HostCache:
        if host_key not in self._caches:
            self._caches[host_key] = HostCache()
        return self._caches[host_key]

    def clear_host(self, host_key: str) -> None:
        if host_key in self._caches:
            self._caches[host_key].clear()

    # ------------------------------------------------------------------
    # Global operations
    # ------------------------------------------------------------------

    def clear_all(self) -> None:
        self._caches.clear()

    def all_files(self) -> list[FileEntry]:
        result: list[FileEntry] = []
        for hc in self._caches.values():
            result.extend(hc.files)
        return result

    def host_keys(self) -> list[str]:
        return list(self._caches.keys())

    def stats(self) -> dict:
        files = self.all_files()
        total = len(files)
        log_count = sum(1 for f in files if f.extension == ".log")
        gz_count = sum(1 for f in files if f.extension == ".gz")

        host_stats = {}
        for key, hc in self._caches.items():
            host_stats[key] = {
                "total": len(hc.files),
                "loaded_at": hc.loaded_at.strftime("%Y-%m-%d %H:%M:%S") if hc.loaded_at else None,
                "error": hc.error,
            }

        latest = max(
            (hc.loaded_at for hc in self._caches.values() if hc.loaded_at),
            default=None,
        )
        return {
            "total": total,
            "log": log_count,
            "gz": gz_count,
            "loaded_at": latest.strftime("%Y-%m-%d %H:%M:%S") if latest else None,
            "hosts": host_stats,
        }


# Module-level singleton
directory_cache = MultiHostCache()
