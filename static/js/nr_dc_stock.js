/**
 * NR DC Stock — transit and supplier stock panels.
 */
(function () {
  'use strict';

  let partsCache = [];
  let loadTimer = null;
  let loadSeq = 0;

  function fmtQty(n) {
    const v = Number(n);
    if (!Number.isFinite(v)) return '0';
    if (Math.abs(v - Math.round(v)) < 1e-9) {
      return String(Math.round(v)).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    }
    return v.toLocaleString('en-IN', { maximumFractionDigits: 2 });
  }

  function setHidden(el, hidden) {
    if (!el) return;
    el.hidden = hidden;
  }

  function showError(msg) {
    const err = document.getElementById('nrdc-error');
    if (!err) return;
    if (msg) {
      err.textContent = msg;
      setHidden(err, false);
    } else {
      err.textContent = '';
      setHidden(err, true);
    }
  }

  function resetView() {
    setHidden(document.getElementById('nrdc-loading'), true);
    setHidden(document.getElementById('nrdc-panels'), true);
    setHidden(document.getElementById('nrdc-srujana-badge'), true);
    setHidden(document.getElementById('nrdc-empty'), false);
    showError('');
  }

  function populatePartsDatalist(parts) {
    const dl = document.getElementById('nrdc-parts-datalist');
    if (!dl) return;
    dl.innerHTML = '';
    parts.forEach((p) => {
      const opt = document.createElement('option');
      opt.value = p.partNo || '';
      opt.label = p.partName ? `${p.partNo} — ${p.partName}` : p.partNo;
      dl.appendChild(opt);
    });
  }

  async function loadParts(query) {
    const q = String(query || '').trim();
    try {
      const res = await apiFetch(
        `/api/nr-dc-stock/parts?q=${encodeURIComponent(q)}&limit=50`
      );
      partsCache = Array.isArray(res.parts) ? res.parts : [];
      populatePartsDatalist(partsCache);
    } catch (e) {
      console.warn('NR DC part search failed:', e);
    }
  }

  function partMetaFor(partNo) {
    const key = String(partNo || '').trim().toLowerCase();
    return partsCache.find((p) => String(p.partNo || '').trim().toLowerCase() === key) || null;
  }

  function renderTransitRows(rows) {
    const body = document.getElementById('nrdc-transit-body');
    if (!body) return;
    body.innerHTML = '';
    let total = 0;
    (rows || []).forEach((row) => {
      total += Number(row.qty) || 0;
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${row.from ?? ''}</td>
        <td>${row.to ?? ''}</td>
        <td class="ti-cs-num">${fmtQty(row.qty)}</td>
        <td>${row.purpose ?? ''}</td>
      `;
      body.appendChild(tr);
    });
    if (!(rows || []).length) {
      const tr = document.createElement('tr');
      tr.innerHTML = '<td colspan="4" style="text-align:center;color:var(--ti-text-muted)">No items in transit</td>';
      body.appendChild(tr);
    }
    const totalEl = document.getElementById('nrdc-transit-total');
    if (totalEl) totalEl.textContent = fmtQty(total);
  }

  function renderSupplierRows(rows) {
    const body = document.getElementById('nrdc-supplier-body');
    if (!body) return;
    body.innerHTML = '';
    let total = 0;
    (rows || []).forEach((row) => {
      total += Number(row.qty) || 0;
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${row.supplier ?? ''}</td>
        <td class="ti-cs-num">${fmtQty(row.qty)}</td>
        <td>${row.readyForStage ?? ''}</td>
      `;
      body.appendChild(tr);
    });
    if (!(rows || []).length) {
      const tr = document.createElement('tr');
      tr.innerHTML = '<td colspan="3" style="text-align:center;color:var(--ti-text-muted)">No supplier stock</td>';
      body.appendChild(tr);
    }
    const totalEl = document.getElementById('nrdc-supplier-total');
    if (totalEl) totalEl.textContent = fmtQty(total);
  }

  function applyPayload(data) {
    const partNameEl = document.getElementById('nrdc-partname');
    if (partNameEl) partNameEl.value = data.partName || '';

    const badgeEl = document.getElementById('nrdc-srujana-badge');
    const qtyEl = document.getElementById('nrdc-srujana-qty');
    if (qtyEl) qtyEl.textContent = fmtQty(data.inSrujana);
    setHidden(badgeEl, false);

    renderTransitRows(data.transit);
    renderSupplierRows(data.suppliers);

    setHidden(document.getElementById('nrdc-empty'), true);
    setHidden(document.getElementById('nrdc-panels'), false);
  }

  async function loadStock() {
    const partEl = document.getElementById('nrdc-partno');
    const partNo = String(partEl?.value || '').trim();

    if (!partNo) {
      resetView();
      return;
    }

    const meta = partMetaFor(partNo);
    const partNameEl = document.getElementById('nrdc-partname');
    if (partNameEl && meta?.partName) partNameEl.value = meta.partName;

    const seq = ++loadSeq;
    setHidden(document.getElementById('nrdc-empty'), true);
    setHidden(document.getElementById('nrdc-panels'), true);
    setHidden(document.getElementById('nrdc-srujana-badge'), true);
    setHidden(document.getElementById('nrdc-loading'), false);
    showError('');

    try {
      const data = await apiFetch(
        `/api/nr-dc-stock?partNo=${encodeURIComponent(partNo)}`
      );
      if (seq !== loadSeq) return;
      applyPayload(data);
    } catch (e) {
      if (seq !== loadSeq) return;
      console.error(e);
      resetView();
      showError(e.message || 'Failed to load NR DC stock.');
    } finally {
      if (seq === loadSeq) {
        setHidden(document.getElementById('nrdc-loading'), true);
      }
    }
  }

  function scheduleLoad() {
    const partNo = String(document.getElementById('nrdc-partno')?.value || '').trim();
    if (!partNo) {
      if (loadTimer) clearTimeout(loadTimer);
      loadTimer = null;
      resetView();
      return;
    }
    if (loadTimer) clearTimeout(loadTimer);
    loadTimer = setTimeout(() => {
      loadTimer = null;
      loadStock();
    }, 300);
  }

  async function init() {
    if (!document.getElementById('nrdc-partno')) return;
    resetView();
    await loadParts('');

    const partEl = document.getElementById('nrdc-partno');

    if (partEl) {
      partEl.addEventListener('focus', () => loadParts(String(partEl.value || '').trim()));
      partEl.addEventListener('input', () => {
        const v = String(partEl.value || '').trim();
        loadParts(v);
        scheduleLoad();
      });
      partEl.addEventListener('change', () => scheduleLoad());
    }
  }

  window.NrDcStockPage = { init };
})();
