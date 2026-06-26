"""Flask route definitions for FTP Log Explorer."""

import ftplib
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import wraps

from flask import (
    Blueprint,
    Response,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    stream_with_context,
    url_for,
)

import ftp_client
from cache import directory_cache
from utils import get_extension, host_key, load_config, parse_host_string

bp = Blueprint("main", __name__)


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "username" not in session:
            return redirect(url_for("main.login"))
        return f(*args, **kwargs)
    return decorated


def get_credentials() -> tuple[str, str]:
    return session["username"], session["password"]


def get_hosts() -> list[tuple[str, int]]:
    """Return the list of (host, port) pairs stored in the session."""
    return [tuple(h) for h in session.get("hosts", [])]


# ---------------------------------------------------------------------------
# Multi-host loading
# ---------------------------------------------------------------------------

def _load_single_host(
    username: str,
    password: str,
    host: str,
    port: int,
    directory: str,
) -> tuple[str, list, str | None]:
    """
    Worker: connect to one host, list files, return (host_key, files, error).
    Designed to run inside a ThreadPoolExecutor.
    """
    hk = host_key(host, port)
    try:
        files = ftp_client.list_files(username, password, host, port, directory, hk)
        return hk, files, None
    except ftplib.error_perm as exc:
        return hk, [], f"Permission denied on {host}: {exc}"
    except ftplib.all_errors as exc:
        return hk, [], f"FTP error on {host}: {exc}"


def load_all_hosts(username: str, password: str) -> dict:
    """
    Fan out to all configured hosts in parallel threads.
    Populates the multi-host cache and returns a stats dict with any errors.
    """
    hosts = get_hosts()
    cfg = load_config()
    directory = cfg.get("directory", "/")

    results: dict = {"errors": []}

    with ThreadPoolExecutor(max_workers=min(len(hosts), 8)) as pool:
        futures = {
            pool.submit(_load_single_host, username, password, h, p, directory): host_key(h, p)
            for h, p in hosts
        }
        for future in as_completed(futures):
            hk, files, error = future.result()
            hc = directory_cache.get_host(hk)
            if error:
                hc.set_error(error)
                results["errors"].append(error)
            else:
                hc.set(files)

    results["stats"] = directory_cache.stats()
    return results


# ---------------------------------------------------------------------------
# Login / Logout
# ---------------------------------------------------------------------------

@bp.route("/", methods=["GET"])
def index():
    if "username" in session:
        return redirect(url_for("main.dashboard"))
    return redirect(url_for("main.login"))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        if "username" in session:
            return redirect(url_for("main.dashboard"))
        return render_template("login.html")

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    hosts_raw = request.form.get("hosts", "").strip()

    if not username or not password:
        return render_template("login.html", error="Username and password are required.")

    if not hosts_raw:
        return render_template("login.html", error="At least one FTP host is required.")

    hosts = parse_host_string(hosts_raw)
    if not hosts:
        return render_template("login.html", error="No valid hosts found. Use format: hostname or hostname:port")

    cfg = load_config()
    directory = cfg.get("directory", "/")

    # Validate credentials against all hosts; collect errors
    connect_errors: list[str] = []
    valid_hosts: list[tuple[str, int]] = []

    for h, p in hosts:
        try:
            ftp_client.connect(username, password, h, p, directory).quit()
            valid_hosts.append((h, p))
        except ftplib.error_perm as exc:
            msg = str(exc)
            if "530" in msg or "login" in msg.lower():
                connect_errors.append(f"{h}: Invalid credentials")
            else:
                connect_errors.append(f"{h}: {msg}")
        except ftplib.all_errors as exc:
            connect_errors.append(f"{h}: {exc}")

    if not valid_hosts:
        error_summary = "; ".join(connect_errors)
        return render_template("login.html", error=f"Could not connect to any host. {error_summary}", hosts_raw=hosts_raw)

    session["username"] = username
    session["password"] = password
    session["hosts"] = valid_hosts   # stored as list of [host, port] pairs

    directory_cache.clear_all()

    # Surface partial failures as a warning on the dashboard via session flash
    if connect_errors:
        session["login_warnings"] = connect_errors

    return redirect(url_for("main.dashboard"))


@bp.route("/logout")
def logout():
    session.clear()
    directory_cache.clear_all()
    return redirect(url_for("main.login"))


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@bp.route("/dashboard")
@login_required
def dashboard():
    hosts = get_hosts()
    host_labels = [host_key(h, p) for h, p in hosts]
    warnings = session.pop("login_warnings", [])
    return render_template(
        "dashboard.html",
        host_labels=host_labels,
        username=session["username"],
        login_warnings=warnings,
    )


# ---------------------------------------------------------------------------
# API: file listing
# ---------------------------------------------------------------------------

@bp.route("/api/files")
@login_required
def api_files():
    """Return the merged file list across all hosts, loading if not yet cached."""
    username, password = get_credentials()

    # Load any host whose cache is not yet populated
    hosts = get_hosts()
    cfg = load_config()
    directory = cfg.get("directory", "/")
    errors: list[str] = []

    hosts_to_load = [
        (h, p) for h, p in hosts
        if not directory_cache.get_host(host_key(h, p)).is_loaded()
    ]

    if hosts_to_load:
        with ThreadPoolExecutor(max_workers=min(len(hosts_to_load), 8)) as pool:
            futures = {
                pool.submit(_load_single_host, username, password, h, p, directory): host_key(h, p)
                for h, p in hosts_to_load
            }
            for future in as_completed(futures):
                hk, files, error = future.result()
                hc = directory_cache.get_host(hk)
                if error:
                    hc.set_error(error)
                    errors.append(error)
                else:
                    hc.set(files)

    all_files = directory_cache.all_files()
    result = [
        {
            "name": f.name,
            "extension": f.extension,
            "size": f.size,
            "size_str": f.size_str,
            "modified": f.modified.isoformat() if f.modified else "",
            "modified_str": f.modified_str,
            "host": f.host,
            "host_key": f.host_key,
        }
        for f in all_files
    ]
    return jsonify({"files": result, "stats": directory_cache.stats(), "errors": errors})


@bp.route("/api/refresh", methods=["POST"])
@login_required
def api_refresh():
    """Force a full reload of all host caches."""
    directory_cache.clear_all()
    username, password = get_credentials()
    result = load_all_hosts(username, password)
    return jsonify(result)


# ---------------------------------------------------------------------------
# Log viewer
# ---------------------------------------------------------------------------

@bp.route("/view/<path:filename>")
@login_required
def view_file(filename: str):
    """Render the Monaco-based log viewer page."""
    if not filename.lower().endswith(".log"):
        return redirect(url_for("main.dashboard"))

    host_param = request.args.get("host", "")

    # Locate the file in the cache to get its metadata and source host
    entry = next(
        (f for f in directory_cache.all_files()
         if f.name == filename and (not host_param or f.host_key == host_param)),
        None,
    )

    cfg = load_config()
    return render_template(
        "viewer.html",
        filename=filename,
        host_key_param=host_param or (entry.host_key if entry else ""),
        size_str=entry.size_str if entry else "Unknown",
        modified_str=entry.modified_str if entry else "Unknown",
        host_label=entry.host_key if entry else host_param,
        max_preview_mb=cfg.get("max_preview_mb", 20),
    )


@bp.route("/api/preview/<path:filename>")
@login_required
def api_preview(filename: str):
    """Return the text content of a .log file (up to max_preview_mb)."""
    if not filename.lower().endswith(".log"):
        return jsonify({"error": "Preview only available for .log files."}), 400

    host_param = request.args.get("host", "")
    entry = next(
        (f for f in directory_cache.all_files()
         if f.name == filename and (not host_param or f.host_key == host_param)),
        None,
    )

    if entry is None:
        return jsonify({"error": "File not found in cache. Try refreshing."}), 404

    cfg = load_config()
    max_bytes = cfg.get("max_preview_mb", 20) * 1024 * 1024
    directory = cfg.get("directory", "/")

    try:
        username, password = get_credentials()
        # Derive port from host_key ("hostname:port") robustly
        try:
            port = int(entry.host_key.rsplit(":", 1)[-1])
        except (ValueError, IndexError):
            port = load_config().get("port", 22)
        content = ftp_client.read_log_preview(
            username, password,
            entry.host, port,
            directory, filename, max_bytes,
        )
    except ftplib.error_perm as exc:
        return jsonify({"error": f"Permission denied: {exc}"}), 403
    except ftplib.all_errors as exc:
        return jsonify({"error": f"FTP error: {exc}"}), 502

    return jsonify({"content": content})


# ---------------------------------------------------------------------------
# Downloads
# ---------------------------------------------------------------------------

@bp.route("/download/<path:filename>")
@login_required
def download_file(filename: str):
    """Stream a file directly from its source FTP host to the browser."""
    ext = get_extension(filename)
    if ext not in (".log", ".gz"):
        return "Unsupported file type.", 400

    host_param = request.args.get("host", "")
    entry = next(
        (f for f in directory_cache.all_files()
         if f.name == filename and (not host_param or f.host_key == host_param)),
        None,
    )

    if entry is None:
        return "File not found in cache. Try refreshing the dashboard.", 404

    cfg = load_config()
    directory = cfg.get("directory", "/")
    mime = "text/plain" if ext == ".log" else "application/gzip"

    try:
        username, password = get_credentials()
        try:
            port = int(entry.host_key.rsplit(":", 1)[-1])
        except (ValueError, IndexError):
            port = load_config().get("port", 22)
        generator = ftp_client.stream_file_true(
            username, password, entry.host, port, directory, filename
        )
        return Response(
            stream_with_context(generator),
            mimetype=mime,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "X-Accel-Buffering": "no",
            },
        )
    except ftplib.error_perm as exc:
        return f"Permission denied: {exc}", 403
    except ftplib.all_errors as exc:
        return f"FTP error: {exc}", 502
