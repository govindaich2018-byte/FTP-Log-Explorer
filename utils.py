"""Utility helpers for the FTP Log Explorer."""

import json
import os
from typing import Any


CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")


def load_config() -> dict[str, Any]:
    """Load and return the application configuration."""
    with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def format_size(size_bytes: int) -> str:
    """Convert a byte count to a human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 ** 2:
        return f"{size_bytes / 1024:.1f} KB"
    if size_bytes < 1024 ** 3:
        return f"{size_bytes / 1024 ** 2:.1f} MB"
    return f"{size_bytes / 1024 ** 3:.1f} GB"


def get_extension(filename: str) -> str:
    """Return the lowercase file extension including the dot."""
    _, ext = os.path.splitext(filename)
    return ext.lower()


def parse_host_string(raw: str) -> list[tuple[str, int]]:
    """
    Parse a newline- or comma-separated list of host strings.

    Accepted formats per entry:
      hostname
      hostname:port
      1.2.3.4
      1.2.3.4:2222

    Returns a list of (host, port) tuples.
    Duplicate entries are deduplicated while preserving order.
    """
    cfg = load_config()
    default_port: int = cfg.get("port", 22)

    seen: set[tuple[str, int]] = set()
    results: list[tuple[str, int]] = []

    # Split on newlines first, then commas
    raw_entries = []
    for line in raw.splitlines():
        raw_entries.extend(line.split(","))

    for entry in raw_entries:
        entry = entry.strip()
        if not entry:
            continue

        if ":" in entry:
            host_part, _, port_part = entry.rpartition(":")
            try:
                port = int(port_part)
            except ValueError:
                # Malformed – treat the whole thing as the hostname
                host_part = entry
                port = default_port
        else:
            host_part = entry
            port = default_port

        host_part = host_part.strip()
        if not host_part:
            continue

        key = (host_part, port)
        if key not in seen:
            seen.add(key)
            results.append(key)

    return results


def host_key(host: str, port: int) -> str:
    """Return a canonical string identifier for a host+port pair."""
    return f"{host}:{port}"
