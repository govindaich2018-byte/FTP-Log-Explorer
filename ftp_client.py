"""FTP client wrapper using Python's ftplib.

All public functions accept explicit host/port/directory parameters
so that multiple FTP servers can be queried in the same session.
"""

import ftplib
import io
from datetime import datetime
from typing import Generator, Optional

from cache import FileEntry
from utils import format_size, get_extension, load_config


# ---------------------------------------------------------------------------
# Internal parsing helpers
# ---------------------------------------------------------------------------

def _parse_mlsd_facts(facts: dict) -> tuple[int, Optional[datetime], str]:
    """Extract size and modification time from an MLSD fact dictionary."""
    size = int(facts.get("size", 0))
    modify_str = facts.get("modify", "")
    modified: Optional[datetime] = None
    modified_display = ""

    if modify_str:
        try:
            modified = datetime.strptime(modify_str[:14], "%Y%m%d%H%M%S")
            modified_display = modified.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass

    return size, modified, modified_display


def _parse_list_line(line: str) -> Optional[tuple[str, int, Optional[datetime], str]]:
    """
    Parse a Unix-format LIST response line.
    Returns (name, size, modified, modified_display) or None if unparseable.
    """
    parts = line.split(None, 8)
    if len(parts) < 9:
        return None

    try:
        size = int(parts[4])
    except ValueError:
        return None

    name = parts[8]
    month_abbr = parts[5]
    day = parts[6]
    year_or_time = parts[7]

    month_map = {
        "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
        "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
    }
    month = month_map.get(month_abbr)
    if month is None:
        return name, size, None, ""

    try:
        if ":" in year_or_time:
            year = datetime.now().year
            hour, minute = map(int, year_or_time.split(":"))
            modified = datetime(year, month, int(day), hour, minute)
        else:
            modified = datetime(int(year_or_time), month, int(day))
    except (ValueError, TypeError):
        return name, size, None, ""

    modified_display = modified.strftime("%Y-%m-%d %H:%M:%S")
    return name, size, modified, modified_display


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

def connect(username: str, password: str, host: str, port: int, directory: str) -> ftplib.FTP:
    """Open and return an authenticated FTP connection to the given host."""
    cfg = load_config()
    ftp = ftplib.FTP(timeout=cfg["timeout"])
    ftp.connect(host, port)
    ftp.login(user=username, passwd=password)
    ftp.cwd(directory)
    return ftp


# ---------------------------------------------------------------------------
# Directory listing
# ---------------------------------------------------------------------------

def list_files(
    username: str,
    password: str,
    host: str,
    port: int,
    directory: str,
    host_key: str,
) -> list[FileEntry]:
    """
    List all .log and .gz files on a single host.
    Tries MLSD first; falls back to LIST if the server does not support it.
    Each FileEntry is tagged with host and host_key for display and routing.
    """
    ftp = connect(username, password, host, port, directory)
    entries: list[FileEntry] = []

    try:
        mlsd_entries = list(ftp.mlsd(facts=["size", "modify", "type"]))
        for name, facts in mlsd_entries:
            if facts.get("type", "file") != "file":
                continue
            ext = get_extension(name)
            if ext not in (".log", ".gz"):
                continue
            size, modified, modified_display = _parse_mlsd_facts(facts)
            entries.append(FileEntry(
                name=name,
                extension=ext,
                size=size,
                modified=modified,
                modified_str=modified_display,
                size_str=format_size(size),
                host=host,
                host_key=host_key,
            ))
    except ftplib.error_perm:
        # Server does not support MLSD; fall back to LIST
        lines: list[str] = []
        ftp.retrlines("LIST", lines.append)
        for line in lines:
            parsed = _parse_list_line(line)
            if parsed is None:
                continue
            name, size, modified, modified_display = parsed
            ext = get_extension(name)
            if ext not in (".log", ".gz"):
                continue
            entries.append(FileEntry(
                name=name,
                extension=ext,
                size=size,
                modified=modified,
                modified_str=modified_display,
                size_str=format_size(size),
                host=host,
                host_key=host_key,
            ))
    finally:
        try:
            ftp.quit()
        except Exception:
            ftp.close()

    return entries


# ---------------------------------------------------------------------------
# Streaming download
# ---------------------------------------------------------------------------

def stream_file_true(
    username: str,
    password: str,
    host: str,
    port: int,
    directory: str,
    filename: str,
) -> Generator[bytes, None, None]:
    """
    True streaming: opens a raw FTP data socket and yields 64 KB chunks.
    The entire file is never held in server RAM.
    """
    cfg = load_config()
    ftp = ftplib.FTP(timeout=cfg["timeout"])
    ftp.connect(host, port)
    ftp.login(user=username, passwd=password)
    ftp.cwd(directory)
    ftp.voidcmd("TYPE I")

    conn, _ = ftp.ntransfercmd(f"RETR {filename}")
    try:
        while True:
            chunk = conn.recv(65536)
            if not chunk:
                break
            yield chunk
    finally:
        conn.close()
        try:
            ftp.quit()
        except Exception:
            ftp.close()


# ---------------------------------------------------------------------------
# Log preview
# ---------------------------------------------------------------------------

def read_log_preview(
    username: str,
    password: str,
    host: str,
    port: int,
    directory: str,
    filename: str,
    max_bytes: int,
) -> str:
    """
    Read up to max_bytes of a .log file and return it decoded as UTF-8.
    Bad bytes are replaced rather than raising an exception.
    """
    ftp = connect(username, password, host, port, directory)
    buf = io.BytesIO()
    collected = [0]

    def handle_chunk(data: bytes) -> None:
        remaining = max_bytes - collected[0]
        if remaining <= 0:
            return
        take = min(len(data), remaining)
        buf.write(data[:take])
        collected[0] += take

    try:
        ftp.retrbinary(f"RETR {filename}", handle_chunk, blocksize=65536)
    finally:
        try:
            ftp.quit()
        except Exception:
            ftp.close()

    buf.seek(0)
    return buf.read().decode("utf-8", errors="replace")
