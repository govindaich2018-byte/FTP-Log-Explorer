/**
 * FTP Log Explorer – Dashboard JavaScript (multi-host edition)
 *
 * Responsibilities:
 *  - Fetch the merged file listing from /api/files (all hosts in parallel on server)
 *  - Initialise DataTables
 *  - Drive host filter, extension filter, and sort dropdown entirely locally
 *  - Handle Refresh button
 */

'use strict';

/* ============================================================
   State
   ============================================================ */
let dataTable = null;

/* ============================================================
   Utility
   ============================================================ */
function escapeHtml(str) {
  return String(str || '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function showAlert(message, type = 'danger') {
  const container = document.getElementById('alertContainer');
  const id = 'alert-' + Date.now();
  const icon = type === 'danger'   ? 'exclamation-triangle-fill'
             : type === 'success'  ? 'check-circle-fill'
             : type === 'warning'  ? 'exclamation-triangle-fill'
             :                       'info-circle-fill';
  container.insertAdjacentHTML('beforeend', `
    <div id="${id}" class="alert alert-${type} alert-dismissible d-flex align-items-start gap-2 py-2 px-3 mb-2" role="alert">
      <i class="bi bi-${icon} flex-shrink-0 mt-1"></i>
      <span>${message}</span>
      <button type="button" class="btn-close btn-close-white ms-auto" data-bs-dismiss="alert"></button>
    </div>
  `);
  if (type !== 'danger') {
    setTimeout(() => document.getElementById(id)?.remove(), 6000);
  }
}

/* ============================================================
   Stats display
   ============================================================ */
function updateStats(stats) {
  document.getElementById('statTotal').textContent  = stats.total.toLocaleString();
  document.getElementById('statLog').textContent    = stats.log.toLocaleString();
  document.getElementById('statGz').textContent     = stats.gz.toLocaleString();
  document.getElementById('statLoaded').textContent = stats.loaded_at || '–';
}

/* ============================================================
   Row builder
   ============================================================ */
function buildRow(file) {
  const extClass = file.extension === '.log' ? 'ext-log' : 'ext-gz';
  const isLog    = file.extension === '.log';
  const hk       = encodeURIComponent(file.host_key);
  const fn       = encodeURIComponent(file.name);

  const viewBtn = isLog
    ? `<a href="/view/${fn}?host=${hk}"
          class="btn btn-sm btn-outline-primary action-btn me-1"
          title="Open in Monaco viewer">
         <i class="bi bi-eye me-1"></i>View
       </a>`
    : '';

  const dlBtn = `<a href="/download/${fn}?host=${hk}"
                    class="btn btn-sm btn-outline-success action-btn"
                    title="Download file">
                   <i class="bi bi-download me-1"></i>Download
                 </a>`;

  const hostBadge = `<span class="host-badge" data-host="${escapeHtml(file.host_key)}"
                           title="${escapeHtml(file.host_key)}">${escapeHtml(file.host_key)}</span>`;

  return [
    `<span class="filename-cell">${escapeHtml(file.name)}</span>`,
    `<span class="ext-badge ${extClass}">${escapeHtml(file.extension)}</span>`,
    // data-order carries the raw byte count for numeric sort
    `<span class="size-cell" data-order="${file.size}">${escapeHtml(file.size_str)}</span>`,
    `<span class="date-cell" data-order="${escapeHtml(file.modified)}">${escapeHtml(file.modified_str || '–')}</span>`,
    hostBadge,
    `<div class="d-flex justify-content-center">${viewBtn}${dlBtn}</div>`,
  ];
}

/* ============================================================
   DataTable initialisation
   ============================================================ */
function initDataTable(files) {
  const rows = files.map(buildRow);

  if (dataTable) {
    dataTable.clear().rows.add(rows).draw();
    return;
  }

  // Register a custom search function for the host column (col 4)
  // so the host-filter radio buttons can drive it independently of
  // the DataTables global search box.
  $.fn.dataTable.ext.search.push(function (_settings, rowData) {
    const activeHost = document.querySelector('input[name="hostFilter"]:checked')?.value || 'all';
    if (activeHost === 'all') return true;
    // rowData[4] is the raw HTML of the host cell
    const tmp = document.createElement('div');
    tmp.innerHTML = rowData[4];
    const span = tmp.querySelector('[data-host]');
    return span && span.getAttribute('data-host') === activeHost;
  });

  dataTable = $('#filesTable').DataTable({
    data: rows,
    columns: [
      { title: 'Filename' },
      { title: 'Ext',      orderable: false, className: 'text-center' },
      { title: 'Size',     type: 'num' },
      { title: 'Modified' },
      { title: 'Host',     orderable: false },
      { title: 'Actions',  orderable: false, className: 'text-center' },
    ],
    order: [[3, 'desc']],
    pageLength: 25,
    lengthMenu: [10, 25, 50, 100, 500, -1],
    language: {
      lengthMenu:      'Show _MENU_ files',
      search:          '',
      searchPlaceholder: 'Search filenames…',
      info:            '_START_–_END_ of _TOTAL_ files',
      infoEmpty:       'No files',
      infoFiltered:    '(filtered from _MAX_ total)',
      zeroRecords:     'No files match your search.',
      emptyTable:      'No files found.',
      paginate: { first: '«', last: '»', next: '›', previous: '‹' },
    },
    columnDefs: [
      // Numeric sort on Size: extract data-order from span
      {
        targets: 2,
        render: function (data, type) {
          if (type === 'sort') {
            const tmp = document.createElement('div');
            tmp.innerHTML = data;
            const span = tmp.querySelector('[data-order]');
            return span ? parseInt(span.getAttribute('data-order'), 10) : 0;
          }
          return data;
        },
      },
      // String sort on Modified: extract data-order ISO string
      {
        targets: 3,
        render: function (data, type) {
          if (type === 'sort') {
            const tmp = document.createElement('div');
            tmp.innerHTML = data;
            const span = tmp.querySelector('[data-order]');
            return span ? span.getAttribute('data-order') : '';
          }
          return data;
        },
      },
    ],
    dom: "<'row align-items-center pt-3 pb-2'<'col-sm-6'l><'col-sm-6'f>>rt<'row align-items-center pt-2'<'col-sm-5'i><'col-sm-7'p>>",
    autoWidth: false,
  });
}

/* ============================================================
   Sort control
   ============================================================ */
function applySortFromDropdown(value) {
  if (!dataTable) return;
  const map = {
    name_asc:  [0, 'asc'],  name_desc: [0, 'desc'],
    date_desc: [3, 'desc'], date_asc:  [3, 'asc'],
    size_desc: [2, 'desc'], size_asc:  [2, 'asc'],
  };
  const [col, dir] = map[value] || [3, 'desc'];
  dataTable.order([col, dir]).draw();
}

/* ============================================================
   Extension filter (uses DataTables column search on col 1)
   ============================================================ */
function applyExtensionFilter(value) {
  if (!dataTable) return;
  if (value === 'all') {
    dataTable.column(1).search('').draw();
  } else {
    dataTable.column(1).search('\\' + value, true, false).draw();
  }
}

/* ============================================================
   Host filter (uses the custom search function registered above)
   ============================================================ */
function applyHostFilter() {
  if (!dataTable) return;
  dataTable.draw();   // triggers the custom search function
}

/* ============================================================
   Load files
   ============================================================ */
async function loadFiles() {
  try {
    const res  = await fetch('/api/files');
    const json = await res.json();

    if (!res.ok) {
      showAlert(escapeHtml(json.error || 'Failed to load file listing.'));
      return;
    }

    // Show per-host errors as warnings (non-blocking)
    if (json.errors && json.errors.length) {
      json.errors.forEach(e => showAlert(escapeHtml(e), 'warning'));
    }

    updateStats(json.stats);

    document.getElementById('tableLoading').classList.add('d-none');
    document.getElementById('tableWrapper').classList.remove('d-none');

    initDataTable(json.files);

    // Re-apply current control state
    applyExtensionFilter(
      document.querySelector('input[name="extFilter"]:checked')?.value || 'all'
    );
    applyHostFilter();
    applySortFromDropdown(document.getElementById('sortSelect').value);

  } catch (err) {
    showAlert('Network error: ' + escapeHtml(err.message));
  }
}

/* ============================================================
   Refresh
   ============================================================ */
async function refreshListing() {
  const btn  = document.getElementById('refreshBtn');
  const orig = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>Refreshing…`;

  try {
    const res  = await fetch('/api/refresh', { method: 'POST' });
    const json = await res.json();

    if (!res.ok) {
      showAlert(escapeHtml(json.error || 'Refresh failed.'));
      return;
    }

    if (json.errors && json.errors.length) {
      json.errors.forEach(e => showAlert(escapeHtml(e), 'warning'));
    }

    await loadFiles();
    showAlert('Directory listings refreshed across all hosts.', 'success');
  } catch (err) {
    showAlert('Network error during refresh: ' + escapeHtml(err.message));
  } finally {
    btn.disabled = false;
    btn.innerHTML = orig;
  }
}

/* ============================================================
   Bootstrap
   ============================================================ */
document.addEventListener('DOMContentLoaded', () => {
  loadFiles();

  document.getElementById('refreshBtn').addEventListener('click', refreshListing);

  document.getElementById('sortSelect').addEventListener('change', (e) => {
    applySortFromDropdown(e.target.value);
  });

  document.querySelectorAll('input[name="extFilter"]').forEach((r) => {
    r.addEventListener('change', (e) => applyExtensionFilter(e.target.value));
  });

  document.querySelectorAll('input[name="hostFilter"]').forEach((r) => {
    r.addEventListener('change', () => applyHostFilter());
  });

  // Hide the host filter widget entirely if only one host was configured
  const hostRadios = document.querySelectorAll('input[name="hostFilter"]');
  if (hostRadios.length <= 2) {   // "All" + one host = no point showing it
    const wrapper = document.getElementById('hostFilterWrapper');
    if (wrapper) wrapper.classList.add('d-none');
  }
});
