/**
 * FTP Log Explorer – Log Viewer JavaScript
 *
 * Responsibilities:
 *  - Configure and load Monaco Editor
 *  - Fetch log content from /api/preview/<filename>?host=<host_key>
 *  - Provide word-wrap toggle
 *  - Manage loading bar state
 *
 * Globals injected by viewer.html:
 *   FILENAME   – the log filename
 *   HOST_KEY   – the "host:port" string identifying the source FTP server
 */

'use strict';

require.config({
  paths: { vs: 'https://cdn.jsdelivr.net/npm/monaco-editor@0.45.0/min/vs' },
});

/* ============================================================
   Loading bar
   ============================================================ */
const loadingBar = document.getElementById('loadingBar');

function loadingDone() {
  loadingBar.classList.add('done');
  setTimeout(() => loadingBar.classList.add('hidden'), 400);
}

/* ============================================================
   Error display
   ============================================================ */
function showViewerError(message) {
  document.getElementById('viewerAlertMsg').textContent = message;
  document.getElementById('viewerAlert').classList.remove('d-none');
}

/* ============================================================
   Monaco initialisation + content fetch
   ============================================================ */
require(['vs/editor/editor.main'], async function () {

  const editor = monaco.editor.create(document.getElementById('editorContainer'), {
    value:               '',
    language:            'plaintext',
    theme:               'vs-dark',
    readOnly:            true,
    lineNumbers:         'on',
    wordWrap:            'off',
    minimap:             { enabled: true },
    scrollBeyondLastLine: false,
    fontSize:            13,
    fontFamily:          "'JetBrains Mono', 'Cascadia Code', 'Fira Code', monospace",
    fontLigatures:       true,
    renderWhitespace:    'none',
    automaticLayout:     true,
  });

  /* ---------- Word-wrap toggle ---------- */
  let wrapEnabled = false;
  document.getElementById('wrapBtn').addEventListener('click', () => {
    wrapEnabled = !wrapEnabled;
    editor.updateOptions({ wordWrap: wrapEnabled ? 'on' : 'off' });
    document.getElementById('wrapBtn').classList.toggle('btn-outline-secondary', !wrapEnabled);
    document.getElementById('wrapBtn').classList.toggle('btn-secondary', wrapEnabled);
  });

  /* ---------- Responsive resize ---------- */
  window.addEventListener('resize', () => editor.layout());

  /* ---------- Fetch log content from the correct host ---------- */
  try {
    const url = `/api/preview/${encodeURIComponent(FILENAME)}?host=${encodeURIComponent(HOST_KEY)}`;
    const res  = await fetch(url);
    const json = await res.json();

    if (!res.ok) {
      loadingDone();
      showViewerError(json.error || 'Failed to load log content.');
      return;
    }

    editor.setValue(json.content);

    // Best-effort syntax highlighting by extension
    const ext = FILENAME.split('.').pop().toLowerCase();
    const langMap = {
      log: 'plaintext', txt: 'plaintext',
      json: 'json', xml: 'xml',
      yaml: 'yaml', yml: 'yaml',
      ini: 'ini', conf: 'ini',
    };
    monaco.editor.setModelLanguage(editor.getModel(), langMap[ext] || 'plaintext');

    loadingDone();
  } catch (err) {
    loadingDone();
    showViewerError('Network error: ' + err.message);
  }
});
