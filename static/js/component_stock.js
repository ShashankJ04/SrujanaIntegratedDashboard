/**
 * Component Stock — ready / in-progress / QA panels (Hub section).
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
      return String(Math.round(v));
    }
    return v.toLocaleString('en-IN', { maximumFractionDigits: 2 });
  }

  function setHidden(el, hidden) {
    if (!el) return;
    el.hidden = hidden;
  }

  function showError(msg) {
    const err = document.getElementById('cs-error');
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
    setHidden(document.getElementById('cs-loading'), true);
    setHidden(document.getElementById('cs-panels'), true);
    setHidden(document.getElementById('cs-gross-total'), true);
    setHidden(document.getElementById('cs-empty'), false);
    showError('');
  }

  function populatePartsDatalist(parts) {
    const dl = document.getElementById('cs-parts-datalist');
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
        `/api/component-stock/parts?q=${encodeURIComponent(q)}&limit=50`
      );
      partsCache = Array.isArray(res.parts) ? res.parts : [];
      populatePartsDatalist(partsCache);
    } catch (e) {
      console.warn('Part search failed:', e);
    }
  }

  function partMetaFor(partNo) {
    const key = String(partNo || '').trim().toLowerCase();
    return partsCache.find((p) => String(p.partNo || '').trim().toLowerCase() === key) || null;
  }

  function renderReadyRows(rows) {
    const body = document.getElementById('cs-ready-body');
    if (!body) return;
    body.innerHTML = '';
    (rows || []).forEach((row) => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td class="ti-cs-num">${row.slNo ?? ''}</td>
        <td>${row.stage ?? ''}</td>
        <td class="ti-cs-num">${fmtQty(row.stock)}</td>
      `;
      body.appendChild(tr);
    });
  }

  function renderInprogressRows(rows) {
    const body = document.getElementById('cs-inprogress-body');
    if (!body) return;
    body.innerHTML = '';
    (rows || []).forEach((row) => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td class="ti-cs-num">${row.slNo ?? ''}</td>
        <td>${row.stage ?? ''}</td>
        <td class="ti-cs-num">${fmtQty(row.inhouse)}</td>
        <td class="ti-cs-num">${fmtQty(row.supplier)}</td>
      `;
      body.appendChild(tr);
    });
  }

  function renderQaRows(rows) {
    const body = document.getElementById('cs-qa-body');
    if (!body) return;
    body.innerHTML = '';
    (rows || []).forEach((row) => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${row.stage ?? ''}</td>
        <td class="ti-cs-num">${fmtQty(row.inhouse)}</td>
        <td class="ti-cs-num">${fmtQty(row.supplier)}</td>
      `;
      body.appendChild(tr);
    });
  }

  function applyPayload(data) {
    const partNameEl = document.getElementById('cs-partname');
    const classEl = document.getElementById('cs-class');
    if (partNameEl) partNameEl.value = data.partName || '';
    if (classEl) classEl.value = data.className || '';

    const grossEl = document.getElementById('cs-gross-total-value');
    if (grossEl) grossEl.textContent = fmtQty(data.grossTotal);

    const readyTotal = document.getElementById('cs-ready-total');
    const ipTotal = document.getElementById('cs-inprogress-total');
    const qaTotal = document.getElementById('cs-qa-total');
    if (readyTotal) readyTotal.textContent = fmtQty(data.ready?.total);
    if (ipTotal) ipTotal.textContent = fmtQty(data.inProgress?.total);
    if (qaTotal) qaTotal.textContent = fmtQty(data.qa?.total);

    renderReadyRows(data.ready?.rows);
    renderInprogressRows(data.inProgress?.rows);
    renderQaRows(data.qa?.rows);

    setHidden(document.getElementById('cs-empty'), true);
    setHidden(document.getElementById('cs-panels'), false);
    setHidden(document.getElementById('cs-gross-total'), false);
  }

  async function loadStock() {
    const plantEl = document.getElementById('cs-plant');
    const partEl = document.getElementById('cs-partno');
    const plantId = Number(plantEl?.value || 0);
    const partNo = String(partEl?.value || '').trim();

    if (!plantId || !partNo) {
      resetView();
      return;
    }

    const meta = partMetaFor(partNo);
    const partNameEl = document.getElementById('cs-partname');
    if (partNameEl && meta?.partName) partNameEl.value = meta.partName;

    const seq = ++loadSeq;
    setHidden(document.getElementById('cs-empty'), true);
    setHidden(document.getElementById('cs-panels'), true);
    setHidden(document.getElementById('cs-gross-total'), true);
    setHidden(document.getElementById('cs-loading'), false);
    showError('');

    try {
      const data = await apiFetch(
        `/api/component-stock?plantId=${encodeURIComponent(plantId)}&partNo=${encodeURIComponent(partNo)}`
      );
      if (seq !== loadSeq) return;
      applyPayload(data);
    } catch (e) {
      if (seq !== loadSeq) return;
      console.error(e);
      resetView();
      showError(e.message || 'Failed to load component stock.');
    } finally {
      if (seq === loadSeq) {
        setHidden(document.getElementById('cs-loading'), true);
      }
    }
  }

  function scheduleLoad() {
    const partNo = String(document.getElementById('cs-partno')?.value || '').trim();
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

  async function initMeta() {
    const plantEl = document.getElementById('cs-plant');
    if (!plantEl) return;
    try {
      const res = await apiFetch('/api/component-stock/meta');
      const plants = Array.isArray(res.plants) ? res.plants : [];
      plantEl.innerHTML = '';
      plants.forEach((p) => {
        const opt = document.createElement('option');
        opt.value = String(p.id);
        opt.textContent = p.label || `Unit ${p.id}`;
        plantEl.appendChild(opt);
      });
      if (!plants.length) {
        const opt = document.createElement('option');
        opt.value = '1';
        opt.textContent = 'Unit 1';
        plantEl.appendChild(opt);
      }
    } catch (e) {
      console.error(e);
      plantEl.innerHTML = '<option value="1">Unit 1</option>';
    }
  }

  async function init() {
    if (!document.getElementById('cs-plant')) return;
    resetView();
    await initMeta();
    await loadParts('');

    const plantEl = document.getElementById('cs-plant');
    const partEl = document.getElementById('cs-partno');

    if (plantEl) plantEl.addEventListener('change', () => scheduleLoad());
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

  window.ComponentStockPage = { init };
})();
