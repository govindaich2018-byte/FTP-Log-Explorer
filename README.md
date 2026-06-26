# FTP Log Explorer

A fast, production-quality web application for browsing and viewing thousands of `.log` and `.gz` files on a single FTP server.

---

## Features

- **One-time directory load** – The server directory is fetched once and cached in memory; all searching, filtering, and sorting happen locally with zero FTP reconnections.
- **DataTables file browser** – Pagination, instant search, column sorting, and 10/25/50/100/500/All page sizes.
- **Monaco Editor viewer** – VS Code–quality log viewer with syntax highlighting, line numbers, minimap, word-wrap toggle, and in-editor search (`Ctrl+F`).
- **Streaming downloads** – Files stream directly from FTP to the browser in 64 KB chunks; the server never loads an entire file into RAM.
- **Secure credentials** – Username and password are stored only in the encrypted Flask session cookie and are never written to disk.
- **Extension filter** – Instantly toggle between All / `.log` / `.gz` views.
- **Sort controls** – Name A→Z / Z→A, Newest/Oldest, Largest/Smallest.
- **Refresh** – Reconnects to FTP and reloads the directory listing without logging out.
- **Friendly errors** – All FTP errors surface as Bootstrap alerts, never as Python tracebacks.

---

## Requirements

| Dependency | Version  |
|------------|----------|
| Python     | 3.12+    |
| Flask      | 3.1.0    |
| Werkzeug   | 3.1.3    |

All other dependencies (Bootstrap 5, DataTables.js, Monaco Editor, jQuery) are loaded from CDN at runtime. No Node.js or build step required.

---

## Installation

```bash
# 1. Clone or unzip the project
cd ftp_log_explorer

# 2. Create and activate a virtual environment (recommended)
python3 -m venv .venv
source .venv/bin/activate      # macOS / Linux
.venv\Scripts\activate.bat     # Windows

# 3. Install Python dependencies
pip install -r requirements.txt
```

---

## Configuration

Edit `config.json` before starting the application:

```json
{
    "host": "ftp.company.com",
    "port": 21,
    "directory": "/logs",
    "timeout": 30,
    "max_preview_mb": 20
}
```

| Key              | Description                                              |
|------------------|----------------------------------------------------------|
| `host`           | FTP server hostname or IP address                        |
| `port`           | FTP port (default `22`)                                  |
| `directory`      | Remote directory that contains the log files             |
| `timeout`        | FTP connection timeout in seconds                        |
| `max_preview_mb` | Maximum megabytes to load for the in-browser log preview |

> **Note:** The FTP URL is never shown to the user. Only a username and password are requested at login.

---

## Running the Application

```bash
python app.py
```

Then open your browser at:

```
http://127.0.0.1:5000
```

Sign in with your FTP credentials. The directory listing loads automatically after login.

---

## Project Structure

```
ftp_log_explorer/
├── app.py            # Flask application factory and entry point
├── routes.py         # All route handlers (login, dashboard, API, viewer, download)
├── ftp_client.py     # FTP operations: connect, list, preview, stream
├── cache.py          # In-memory directory cache (FileEntry dataclass)
├── utils.py          # Config loader, size formatter, extension helpers
├── config.json       # FTP server configuration (edit this)
├── requirements.txt  # Python dependencies
├── README.md         # This file
├── templates/
│   ├── layout.html   # Base template (Bootstrap, DataTables, fonts)
│   ├── login.html    # Login page with spinner and error handling
│   ├── dashboard.html# Main file browser (stats, controls, table)
│   └── viewer.html   # Monaco Editor log viewer
└── static/
    ├── css/
    │   └── style.css # All custom styles (dark theme, tokens, overrides)
    └── js/
        ├── dashboard.js # File loading, DataTable init, filter/sort logic
        └── viewer.js    # Monaco setup, log content fetch, word-wrap toggle
```

---

## Usage

### Searching

Type in the DataTables search box to instantly filter filenames. No FTP request is made — searching is entirely local.

### Viewing a log file

Click **View** next to any `.log` file. The log content loads into Monaco Editor.

- Use `Ctrl+F` (or `Cmd+F` on Mac) for in-editor search.
- Use the **Wrap** button in the top bar to toggle word wrap.
- The preview is capped at `max_preview_mb` (configurable). The file is not pre-loaded — it is only fetched when you open the viewer.

### Downloading files

Click **Download** for any `.log` or `.gz` file. The file streams directly from FTP to your browser without buffering the entire file in server memory.

### Refreshing

Click the **Refresh** button in the top bar to reconnect to the FTP server and reload the directory listing.

---

## Troubleshooting

| Symptom                          | Fix                                                                 |
|----------------------------------|---------------------------------------------------------------------|
| "Could not connect to FTP server" | Check `config.json` host and port. Confirm the FTP server is reachable from your machine. |
| "Invalid username or password"   | Verify your FTP credentials.                                        |
| Directory loads but is empty     | Confirm `config.json` → `directory` points to the correct path and contains `.log` / `.gz` files. |
| Log preview shows replacement characters (�) | The log file contains non-UTF-8 bytes. This is expected; bad bytes are replaced rather than crashing. |
| Download is very slow            | The FTP server or network is the bottleneck. Downloads stream in 64 KB chunks. |
| Monaco editor does not appear    | Check browser console for CDN errors. Ensure you have internet access (Monaco is loaded from a CDN). |
| Session expires unexpectedly     | The Flask secret key is regenerated each time `app.py` starts, which invalidates all sessions. This is intentional for security. |

---

## Security Notes

- Credentials are kept only in a server-side encrypted session cookie (`SESSION_COOKIE_HTTPONLY = True`).
- Credentials are never logged, written to disk, or echoed in responses.
- The Flask secret key is randomly generated at startup (`secrets.token_hex(32)`), so sessions are invalidated whenever the server restarts.
- This application is intended for local/intranet use and does not include HTTPS termination. If exposing over a network, place it behind a reverse proxy (nginx/caddy) with TLS.
