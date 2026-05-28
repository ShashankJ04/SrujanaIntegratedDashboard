/**
 * DPR — Daily Production Review (Hub)
 * Ported from Original Dashboard dpr.js: 24-machine seed rows, debounced auto-save,
 * /api/dpr/qr-list QR map, column drag/pin/sort, version polling.
 *
 * `window.DPR_POLL_INTERVAL_MS` is set in hub.html from server config (see `dpr_poll_interval_ms`).
 * hub_dpr.html does not set it — the Hub shell loads first. Fallback matches `DPR_POLL_INTERVAL_MS_DEFAULT` in backend/config.py.
 */
window.DprPage = (() => {
  const BASE = "/api";
  /** @see backend/config.py DPR_POLL_INTERVAL_MS_DEFAULT */
  const DPR_POLL_FALLBACK_MS = 500000;
  let machines = [];
  let parts = [];
  let pendingRows = [];
  let monthlyKpi = null;
  let deriveTimer = null;
  let deriveIdx = null;
  let snapshotSaveTimer = null;
  let dprPollTimer = null;
  let dprFullscreenMode = false;
  let dprFullscreenKeyHandlerBound = false;
  let breakdownOperators = [];
  let breakdownOperatorByLabel = new Map();
  let breakdownModalState = null;
  const DPR_POLL_MS = Number(
    window.DPR_POLL_INTERVAL_MS != null ? window.DPR_POLL_INTERVAL_MS : DPR_POLL_FALLBACK_MS
  );
  const breakdownAccess = Array.isArray(window.CURRENT_PERMISSIONS?.plusAccess)
    ? window.CURRENT_PERMISSIONS.plusAccess.includes("edit_dpr")
    : false;
  let suppressRealtimeReloadUntil = 0;
  let lastVersionToken = null;
  const rowAutoSaveTimers = new WeakMap();
  const DPR_PARTS_DATALIST_ID = "dpr-parts-datalist";
  const DPR_LAYOUT_STORAGE_KEY = "dpr_layout_v1";
  let dprDragCol = null;
  /** machineId -> { machineId, machineLabel, pngUrl, scanUrl } */
  let qrByMachine = new Map();
  /** Optional client-side sort (like generic report tables). */
  let dprSortBy = null;
  let dprSortDir = "asc";

  const SORTABLE_COLS = new Set([
    "machine",
    "part_no",
    "part_name",
    "planned_qty",
    "produced_qty",
    "produced_pct",
    "remarks",
    "rm_issued",
    "rm_available",
    "rm_code",
    "rm_coverage_nos",
    "rm_allocated",
    "tool_no",
    "strokes_consumed",
    "pm_due",
  ]);

  const DPR_DEFAULT_COL_ORDER = [
    "actions",
    "machine",
    "qr",
    "part_no",
    "part_name",
    "planned_qty",
    "produced_qty",
    "produced_pct",
    "remarks",
    "rm_issued",
    "rm_available",
    "rm_code",
    "rm_coverage_nos",
    "rm_allocated",
    "tool_no",
    "strokes_consumed",
    "pm_due",
  ];

  let dprLayout = { order: [...DPR_DEFAULT_COL_ORDER], pinnedLeft: [], widths: {} };

  /** @type {{ col: string, startX: number, origW: number } | null} */
  let dprResizeDrag = null;

  function qs(o) {
    const s = new URLSearchParams();
    Object.entries(o).forEach(([k, v]) => {
      if (v != null && v !== "") s.set(k, String(v));
    });
    return s.toString();
  }

  async function apiFetch(url, opts) {
    const r = await fetch(url, opts);
    if (r.status === 401) {
      window.location.href = "/login";
      throw new Error("Session expired");
    }
    if (!r.ok) {
      let m = `Error ${r.status}`;
      try {
        const b = await r.json();
        if (b.error) m = b.error;
      } catch (_) {}
      throw new Error(m);
    }
    return r.json();
  }

  const Api = {
    options: () => apiFetch(`${BASE}/dpr/options`),
    derived: (partNo, plannedQty, date) =>
      apiFetch(`${BASE}/dpr/derived?${qs({ partNo, plannedQty, date })}`),
    summary: (date) => apiFetch(`${BASE}/dpr/summary?${qs({ date })}`),
    rows: (date) => apiFetch(`${BASE}/dpr/rows?${qs({ date })}`),
    save: (payload) =>
      apiFetch(`${BASE}/dpr/rows`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }),
    del: (id) => apiFetch(`${BASE}/dpr/rows/${encodeURIComponent(id)}`, { method: "DELETE" }),
    saveSnapshot: (payload) =>
      apiFetch(`${BASE}/dpr/snapshot`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }),
    version: (date) => apiFetch(`${BASE}/dpr/version?${qs({ date })}`),
    qrList: () => apiFetch(`${BASE}/dpr/qr-list`),
    breakdownOperators: () => apiFetch(`${BASE}/tool-breakdowns/operators/dpr`),
    breakdownList: (params) => apiFetch(`${BASE}/tool-breakdowns?${qs(params || {})}`),
    breakdownCreate: (payload) =>
      apiFetch(`${BASE}/tool-breakdowns`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }),
  };

  function openQrModal(info) {
    const modal = document.getElementById("dpr-qr-modal");
    const img = document.getElementById("dpr-qr-modal-img");
    const title = document.getElementById("dpr-qr-modal-title");
    const link = document.getElementById("dpr-qr-modal-link");
    if (!modal || !img || !title || !link) return;
    title.textContent = `${info.machineLabel || info.machineId || "Machine"} — QR`;
    img.src = info.pngUrl;
    img.alt = "Machine QR code";
    link.href = info.scanUrl;
    modal.classList.remove("dpr-hidden");
  }

  function closeQrModal() {
    const modal = document.getElementById("dpr-qr-modal");
    if (modal) modal.classList.add("dpr-hidden");
  }

  async function refreshQrMap() {
    try {
      const res = await Api.qrList();
      qrByMachine = new Map();
      (res.items || []).forEach((it) => {
        qrByMachine.set(String(it.machineId), it);
      });
    } catch (e) {
      console.warn(e);
      qrByMachine = new Map();
    }
  }

  function isBackdated(dateValue) {
    const d = String(dateValue || "").trim();
    if (!d) return false;
    const today = new Date();
    const y = today.getFullYear();
    const m = String(today.getMonth() + 1).padStart(2, "0");
    const day = String(today.getDate()).padStart(2, "0");
    return d < `${y}-${m}-${day}`;
  }

  function todayIso() {
    const d = new Date();
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  }

  function formatCellNumber(value) {
    if (value === null || value === undefined) return "—";
    const n = Number(value);
    if (Number.isNaN(n)) return String(value);
    return n.toLocaleString("en-IN", {
      minimumFractionDigits: 0,
      maximumFractionDigits: 4,
    });
  }

  function notify(msg, isError) {
    if (typeof window.showSnackbar === "function") {
      window.showSnackbar(msg || (isError ? "Something went wrong" : "Done"));
    } else if (msg) {
      console.log(msg);
    }
  }

  function formatDateTimeLocal(d) {
    if (!(d instanceof Date) || Number.isNaN(d.getTime())) return "—";
    return d.toLocaleString("en-IN", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  function breakdownUserLabel(user) {
    if (!user) return "";
    const label = String(user.label || "").trim();
    if (label) return label;
    const first = String(user.firstName || "").trim();
    const last = String(user.lastName || "").trim();
    const name = [first, last].filter(Boolean).join(" ").trim();
    const login = String(user.login || "").trim();
    if (name && login && name.toLowerCase() !== login.toLowerCase()) {
      return `${name} (${login})`;
    }
    return name || login;
  }

  function hasDprProducedQty(row) {
    const q = row?.producedQty;
    if (q === null || q === undefined || q === "") return false;
    return Number.isFinite(Number(q));
  }

  function syncBreakdownButton(tr, row) {
    if (!tr || !breakdownAccess) return;
    const brBtn = tr.querySelector(".dpr-breakdown-btn");
    if (!brBtn) return;
    const ok = hasDprProducedQty(row);
    brBtn.disabled = !ok;
    brBtn.title = ok
      ? "Raise tool breakdown"
      : "Enter Produced Qty on this line first (0 is allowed)";
  }

  function refreshBreakdownOperators() {
    const dl = document.getElementById("dpr-breakdown-operators");
    if (!dl) return;
    dl.innerHTML = "";
    breakdownOperatorByLabel = new Map();
    (breakdownOperators || []).forEach((u) => {
      const label = breakdownUserLabel(u);
      if (!label) return;
      breakdownOperatorByLabel.set(label, u);
      const opt = document.createElement("option");
      opt.value = label;
      dl.appendChild(opt);
    });
  }

  async function loadBreakdownOperators() {
    try {
      breakdownOperators = await Api.breakdownOperators();
    } catch (e) {
      console.warn("Failed to load breakdown operators:", e);
      breakdownOperators = [];
    }
    refreshBreakdownOperators();
  }

  function setBreakdownWarning(text) {
    const warn = document.getElementById("dpr-breakdown-warning");
    if (!warn) return;
    if (text) {
      warn.textContent = text;
      warn.style.display = "block";
    } else {
      warn.textContent = "";
      warn.style.display = "none";
    }
  }

  function setBreakdownModalSuccess(isSuccess) {
    const title = document.getElementById("dpr-breakdown-title");
    const form = document.getElementById("dpr-breakdown-form");
    const success = document.getElementById("dpr-breakdown-success");
    const cancelBtn = document.getElementById("dpr-breakdown-cancel");
    const submitBtn = document.getElementById("dpr-breakdown-submit");
    if (title) title.textContent = isSuccess ? "Request Raised Successfully" : "Raise Tool Breakdown";
    if (form) form.style.display = isSuccess ? "none" : "flex";
    if (success) success.style.display = "none";
    if (cancelBtn) cancelBtn.textContent = isSuccess ? "Close" : "Cancel";
    if (submitBtn) submitBtn.style.display = isSuccess ? "none" : "";
  }

  async function checkOpenBreakdown(toolNo) {
    if (!toolNo) return false;
    try {
      const rows = await Api.breakdownList({ status: "active", toolNo, limit: 1 });
      return Array.isArray(rows) && rows.length > 0;
    } catch (e) {
      console.warn("Breakdown check failed:", e);
      return false;
    }
  }

  function closeBreakdownModal() {
    const modal = document.getElementById("dpr-breakdown-modal");
    if (modal) modal.classList.remove("open");
    breakdownModalState = null;
    setBreakdownWarning("");
  }

  async function openBreakdownModal(row) {
    const modal = document.getElementById("dpr-breakdown-modal");
    if (!modal) return;
    if (!hasDprProducedQty(row)) {
      notify("Enter Produced Qty on this line before raising a breakdown (0 is allowed).", true);
      return;
    }
    const rowIdx = pendingRows.indexOf(row);
    const dateVal = document.getElementById("dpr-date")?.value || "";
    if (rowIdx >= 0 && dateVal) {
      await saveRow(rowIdx, dateVal, { silent: true });
      row = pendingRows[rowIdx];
      if (!hasDprProducedQty(row)) {
        notify("Enter Produced Qty on this line before raising a breakdown (0 is allowed).", true);
        return;
      }
    }
    const toolNo = String(row?.toolNo || "").trim();
    if (!toolNo) {
      notify("Tool number is missing for this line.", true);
      return;
    }
    const machineLabel = row?.machineLabel || labelByMachineId(row?.machineId) || row?.machineId || "";
    const partNo = row?.partNo || "";
    const partName = row?.partName || "";
    const issueInput = document.getElementById("dpr-breakdown-issue");
    const priorityInput = document.getElementById("dpr-breakdown-priority");
    const operatorInput = document.getElementById("dpr-breakdown-operator");
    const submitBtn = document.getElementById("dpr-breakdown-submit");
    const now = new Date();

    setBreakdownModalSuccess(false);
    const machineEl = document.getElementById("dpr-breakdown-machine");
    const partNoEl = document.getElementById("dpr-breakdown-partno");
    const partNameEl = document.getElementById("dpr-breakdown-partname");
    const toolNoEl = document.getElementById("dpr-breakdown-toolno");
    const downtimeEl = document.getElementById("dpr-breakdown-downtime");
    const producedEl = document.getElementById("dpr-breakdown-produced");
    if (machineEl) machineEl.value = String(machineLabel || "");
    if (partNoEl) partNoEl.value = String(partNo || "");
    if (partNameEl) partNameEl.value = String(partName || "");
    if (toolNoEl) toolNoEl.value = String(toolNo || "");
    if (downtimeEl) downtimeEl.value = formatDateTimeLocal(now);
    if (producedEl) producedEl.value = formatCellNumber(row?.producedQty);
    if (issueInput) issueInput.value = "";
    if (priorityInput) priorityInput.value = "Immediate";
    if (operatorInput) operatorInput.value = "";
    if (submitBtn) submitBtn.disabled = true;
    setBreakdownWarning("Checking for existing open breakdowns...");

    breakdownModalState = {
      row,
      toolNo,
      partNo,
      partName,
      machineId: row?.machineId || "",
      machineName: machineLabel,
      dprRowId: row?.id || null,
      dprProducedQty: row?.producedQty ?? null,
    };

    modal.classList.add("open");

    const hasOpen = await checkOpenBreakdown(toolNo);
    if (submitBtn) submitBtn.disabled = hasOpen;
    setBreakdownWarning(
      hasOpen ? "An open breakdown already exists for this tool." : ""
    );
    if (submitBtn && !hasOpen) submitBtn.disabled = false;
  }

  function formatKpiQty(value) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
    return Number(value).toLocaleString("en-IN", {
      minimumFractionDigits: 0,
      maximumFractionDigits: 2,
    });
  }

  function formatProducedPercent(planned, produced) {
    const p = Number(planned);
    if (!Number.isFinite(p) || p <= 0) return "—";
    if (produced === null || produced === undefined || produced === "") return "—";
    const q = Number(produced);
    if (!Number.isFinite(q)) return "—";
    const pct = (100 * q) / p;
    return `${pct.toLocaleString("en-IN", { maximumFractionDigits: 2, minimumFractionDigits: 0 })}%`;
  }

  function formatPercentValue(value) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
    return `${Number(value).toLocaleString("en-IN", {
      minimumFractionDigits: 0,
      maximumFractionDigits: 2,
    })}%`;
  }

  function setSnapshotValue(id, value) {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = value === null || value === undefined || String(value).trim() === "" ? "—" : String(value);
  }

  function renderBottleneckGrid(text) {
    const grid = document.getElementById("dpr-bottleneck-grid");
    if (!grid) return;
    const lines = String(text || "")
      .split(/\r?\n/)
      .map((s) => s.trim())
      .filter((s) => s.length > 0);
    grid.innerHTML = "";
    if (lines.length === 0) {
      const empty = document.createElement("div");
      empty.className = "ti-dpr-bottleneck-empty";
      empty.textContent = "—";
      grid.appendChild(empty);
      return;
    }
    lines.forEach((line, i) => {
      const cell = document.createElement("div");
      cell.className = "ti-dpr-bottleneck-chip";
      const num = document.createElement("span");
      num.className = "ti-dpr-bottleneck-num";
      num.textContent = `${i + 1}.`;
      const tx = document.createElement("span");
      tx.className = "ti-dpr-bottleneck-text";
      tx.textContent = line;
      cell.appendChild(num);
      cell.appendChild(tx);
      grid.appendChild(cell);
    });
  }

  function wireSnapshotEditors() {
    const root = document.getElementById("section-dpr");
    const canEdit = !!window.DPR_EDIT_ALLOWED && !dprFullscreenMode;
    const readOperators = document.getElementById("dpr-operators-read");
    const editOperators = document.getElementById("dpr-operators-edit");
    const bottleneckReadWrap = document.getElementById("dpr-board-bottleneck-read-wrap");
    const bottleneckInput = document.getElementById("dpr-board-bottleneck-input");
    if (canEdit) {
      if (readOperators) readOperators.style.display = "none";
      if (editOperators) editOperators.style.display = "inline-flex";
      if (bottleneckReadWrap) bottleneckReadWrap.style.display = "none";
      if (bottleneckInput) bottleneckInput.style.display = "block";
    } else {
      if (readOperators) readOperators.style.display = "";
      if (editOperators) editOperators.style.display = "none";
      if (bottleneckReadWrap) bottleneckReadWrap.style.display = "";
      if (bottleneckInput) bottleneckInput.style.display = "none";
    }
    if (root && !root.dataset.snapshotWired) {
      root.dataset.snapshotWired = "1";
      const scheduleSave = () => {
        if (!window.DPR_EDIT_ALLOWED || dprFullscreenMode) return;
        if (snapshotSaveTimer) clearTimeout(snapshotSaveTimer);
        snapshotSaveTimer = setTimeout(saveSnapshot, 300);
      };
      const opPlanned = document.getElementById("dpr-op-planned-input");
      const opActual = document.getElementById("dpr-op-actual-input");
      const bIn = document.getElementById("dpr-board-bottleneck-input");
      if (opPlanned) opPlanned.addEventListener("input", scheduleSave);
      if (opActual) opActual.addEventListener("input", scheduleSave);
      if (bIn) bIn.addEventListener("input", scheduleSave);
    }
  }

  async function saveSnapshot() {
    if (!window.DPR_EDIT_ALLOWED || dprFullscreenMode) return;
    const reviewDate = document.getElementById("dpr-date")?.value || "";
    if (!reviewDate) return;
    const opPlanned = document.getElementById("dpr-op-planned-input")?.value ?? "";
    const opActual = document.getElementById("dpr-op-actual-input")?.value ?? "";
    const bottleneck = document.getElementById("dpr-board-bottleneck-input")?.value ?? "";
    try {
      await Api.saveSnapshot({
        reviewDate,
        operatorPlanned: opPlanned === "" ? null : Number(opPlanned),
        operatorActual: opActual === "" ? null : Number(opActual),
        bottleneckPending: bottleneck,
      });
    } catch (e) {
      setStatus(e.message || "Snapshot save failed", true);
    }
  }

  function setKpiProducedPctEl(id, value) {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = formatPercentValue(value);
    el.classList.remove("dpr-kpi-value--pct-low", "dpr-kpi-value--pct-good", "ti-dpr-kpi--neg", "ti-dpr-kpi--pos");
    if (value === null || value === undefined || Number.isNaN(Number(value))) return;
    const v = Number(value);
    if (v < 70) el.classList.add("dpr-kpi-value--pct-low", "ti-dpr-kpi--neg");
    else el.classList.add("dpr-kpi-value--pct-good", "ti-dpr-kpi--pos");
  }

  function updateKpiStrip() {
    let dailyPlanned = 0;
    let dailyProduced = 0;
    pendingRows.forEach((row) => {
      dailyPlanned += Number(row.plannedQty || 0);
      const pq = row.producedQty;
      dailyProduced += pq === null || pq === undefined ? 0 : Number(pq);
    });

    const setText = (id, text) => {
      const el = document.getElementById(id);
      if (el) el.textContent = text;
    };

    setText("dpr-kpi-daily-planned", formatKpiQty(dailyPlanned));
    setText("dpr-kpi-daily-produced", formatKpiQty(dailyProduced));
    const dailyProducedPct = dailyPlanned > 0 ? (100 * dailyProduced) / dailyPlanned : null;
    setKpiProducedPctEl("dpr-kpi-daily-produced-pct", dailyProducedPct);

    if (monthlyKpi && typeof monthlyKpi === "object") {
      setText("dpr-kpi-monthly-planned", formatKpiQty(monthlyKpi.monthlyPlanned));
      setText("dpr-kpi-monthly-produced", formatKpiQty(monthlyKpi.monthlyProduced));
      setKpiProducedPctEl("dpr-kpi-monthly-produced-pct", monthlyKpi.monthlyProducedPct);
      const opPlannedText = formatCellNumber(monthlyKpi.operatorPlanned);
      const opActualText = formatCellNumber(monthlyKpi.operatorActual);
      setSnapshotValue("dpr-operators-read", `${opPlannedText} / ${opActualText}`);
      const opPlannedInput = document.getElementById("dpr-op-planned-input");
      const opActualInput = document.getElementById("dpr-op-actual-input");
      if (opPlannedInput && document.activeElement !== opPlannedInput) {
        opPlannedInput.value =
          monthlyKpi.operatorPlanned === null || monthlyKpi.operatorPlanned === undefined
            ? ""
            : String(monthlyKpi.operatorPlanned);
      }
      if (opActualInput && document.activeElement !== opActualInput) {
        opActualInput.value =
          monthlyKpi.operatorActual === null || monthlyKpi.operatorActual === undefined
            ? ""
            : String(monthlyKpi.operatorActual);
      }
      setSnapshotValue(
        "dpr-machines-read",
        `${formatCellNumber(monthlyKpi.plannedMachines)} / ${formatCellNumber(monthlyKpi.totalMachines)}`,
      );
      setSnapshotValue("dpr-board-last-planned", formatKpiQty(monthlyKpi.lastDayPlanned));
      setSnapshotValue("dpr-board-last-produced", formatKpiQty(monthlyKpi.lastDayProduced));
      setKpiProducedPctEl("dpr-board-last-achievement", monthlyKpi.lastDayAchievementPct);
      const bottleneckText = String(monthlyKpi.bottleneckPending || "").trim();
      renderBottleneckGrid(bottleneckText);
      const bottleneckInput = document.getElementById("dpr-board-bottleneck-input");
      if (bottleneckInput && document.activeElement !== bottleneckInput) {
        bottleneckInput.value = bottleneckText;
      }
    } else {
      setText("dpr-kpi-monthly-planned", "—");
      setText("dpr-kpi-monthly-produced", "—");
      setKpiProducedPctEl("dpr-kpi-monthly-produced-pct", null);
      setSnapshotValue("dpr-operators-read", "—");
      setSnapshotValue("dpr-machines-read", "—");
      setSnapshotValue("dpr-board-last-planned", "—");
      setSnapshotValue("dpr-board-last-produced", "—");
      setKpiProducedPctEl("dpr-board-last-achievement", null);
      renderBottleneckGrid("");
    }

    const sumEl = document.getElementById("dpr-table-summary");
    if (sumEl) {
      const n = pendingRows.length;
      sumEl.textContent = n ? `${n.toLocaleString("en-IN")} line${n === 1 ? "" : "s"}` : "No lines";
    }
  }

  function setStatus(msg, isError) {
    const el = document.getElementById("dpr-status");
    if (!el) return;
    el.textContent = msg || "";
    el.style.color = isError ? "var(--clr-danger, #ef4444)" : "";
  }

  function applyDprFullscreenState() {
    document.body.classList.toggle("dpr-fullscreen-mode", dprFullscreenMode);
    const btn = document.getElementById("dpr-fullscreen-toggle");
    if (btn) {
      btn.textContent = dprFullscreenMode ? "🡽 Exit full screen" : "⛶ Full screen";
      btn.setAttribute("aria-pressed", dprFullscreenMode ? "true" : "false");
      btn.title = dprFullscreenMode ? "Exit DPR fullscreen view" : "Toggle DPR fullscreen view";
    }
    wireSnapshotEditors();
  }

  function applyEditabilityForDate(dateVal) {
    const addBtn = document.getElementById("dpr-add-row");
    const canEdit =
      !!window.DPR_EDIT_ALLOWED && !isBackdated(dateVal) && !dprFullscreenMode;
    if (addBtn) addBtn.style.display = canEdit ? "" : "none";
    const th = document.getElementById("dpr-th-actions");
    if (th) th.classList.toggle("dpr-layout-hidden", !canEdit);
    return canEdit;
  }

  function partNameFor(partNo) {
    const key = String(partNo || "").trim();
    const keyLc = key.toLowerCase();
    const p = parts.find((x) => String(x.part_no || "").trim().toLowerCase() === keyLc);
    return p ? String(p.part_name || "").trim() : "";
  }

  function ensurePartDatalist() {
    let dl = document.getElementById(DPR_PARTS_DATALIST_ID);
    if (!dl) {
      dl = document.createElement("datalist");
      dl.id = DPR_PARTS_DATALIST_ID;
      document.body.appendChild(dl);
    }
    dl.innerHTML = "";
    parts.forEach((p) => {
      const partNo = String(p.part_no || "").trim();
      if (!partNo) return;
      const opt = document.createElement("option");
      opt.value = partNo;
      dl.appendChild(opt);
    });
  }

  function loadDprLayout() {
    try {
      const raw = window.localStorage.getItem(DPR_LAYOUT_STORAGE_KEY);
      if (!raw) return;
      const parsed = JSON.parse(raw);
      if (!parsed || typeof parsed !== "object") return;
      if (Array.isArray(parsed.order)) {
        dprLayout.order = parsed.order.map((x) => String(x || "").trim()).filter(Boolean);
      }
      if (Array.isArray(parsed.pinnedLeft)) {
        dprLayout.pinnedLeft = parsed.pinnedLeft.map((x) => String(x || "").trim()).filter(Boolean);
      }
      if (parsed.widths && typeof parsed.widths === "object") {
        dprLayout.widths = { ...parsed.widths };
      }
    } catch (_) {
      /* ignore */
    }
  }

  function resetDprLayout(editable) {
    dprLayout = {
      order: editable
        ? [...DPR_DEFAULT_COL_ORDER]
        : DPR_DEFAULT_COL_ORDER.filter((c) => c !== "actions"),
      pinnedLeft: [],
      widths: {},
    };
    saveDprLayout();
    applyDprColumnLayout(editable);
    wireDprHeaderControls(editable);
    wireDprColumnSort(editable);
  }

  function saveDprLayout() {
    try {
      window.localStorage.setItem(DPR_LAYOUT_STORAGE_KEY, JSON.stringify(dprLayout));
    } catch (_) {
      /* ignore */
    }
  }

  /** Earliest created first within a machine; new unsaved lines last. */
  function createdSortKey(row) {
    const raw = row.createdAt || row.created_at || "";
    if (raw) {
      const t = Date.parse(String(raw).trim().replace(" ", "T"));
      if (!Number.isNaN(t)) {
        const id = Number(row.id);
        return [t, Number.isFinite(id) ? id : 0];
      }
    }
    const id = Number(row.id);
    if (Number.isFinite(id) && id > 0) return [id, id];
    return [Number.MAX_SAFE_INTEGER, 0];
  }

  function compareCreatedSort(a, b) {
    const ca = createdSortKey(a);
    const cb = createdSortKey(b);
    if (ca[0] !== cb[0]) return ca[0] - cb[0];
    return ca[1] - cb[1];
  }

  function sortPendingRowsByMachine() {
    const labelById = new Map(machines.map((m) => [String(m.id), String(m.label || m.id)]));
    pendingRows.sort((a, b) => {
      const al = String(a.machineLabel || labelById.get(String(a.machineId || "")) || a.machineId || "")
        .trim()
        .toLowerCase();
      const bl = String(b.machineLabel || labelById.get(String(b.machineId || "")) || b.machineId || "")
        .trim()
        .toLowerCase();
      if (al !== bl) return al.localeCompare(bl);
      return compareCreatedSort(a, b);
    });
  }

  function labelByMachineId(mid) {
    const m = machines.find((x) => String(x.id) === String(mid));
    return String(m?.label || mid || "");
  }

  const COL_TO_ROW_KEY = {
    rm_issued: "rmIssued",
    rm_available: "rmAvailable",
    rm_code: "rmCode",
    rm_coverage_nos: "rmCoverageNos",
    rm_allocated: "rmAllocated",
    tool_no: "toolNo",
    strokes_consumed: "strokesConsumed",
    pm_due: "pmDue",
  };

  function sortValueForColumn(row, col) {
    const p = Number(row.plannedQty);
    const q = row.producedQty;
    switch (col) {
      case "machine":
        return (row.machineLabel || labelByMachineId(row.machineId) || row.machineId || "").toLowerCase();
      case "part_no":
        return String(row.partNo || "").toLowerCase();
      case "part_name":
        return String(row.partName || partNameFor(row.partNo) || "").toLowerCase();
      case "planned_qty":
        return Number.isFinite(p) ? p : -Infinity;
      case "produced_qty":
        return q === null || q === undefined || q === "" ? -Infinity : Number(q);
      case "produced_pct": {
        if (!Number.isFinite(p) || p <= 0) return -Infinity;
        const qq = Number(q);
        if (!Number.isFinite(qq)) return -Infinity;
        return (100 * qq) / p;
      }
      case "remarks":
        return String(row.remarks || "").toLowerCase();
      default: {
        const rk = COL_TO_ROW_KEY[col];
        if (!rk) return "";
        const v = row[rk];
        if (v === null || v === undefined) return -Infinity;
        const n = Number(v);
        if (Number.isFinite(n)) return n;
        return String(v).toLowerCase();
      }
    }
  }

  function applyPendingSort() {
    if (!dprSortBy || !SORTABLE_COLS.has(dprSortBy)) return;
    const dir = dprSortDir === "desc" ? -1 : 1;
    const col = dprSortBy;
    pendingRows.sort((a, b) => {
      const va = sortValueForColumn(a, col);
      const vb = sortValueForColumn(b, col);
      if (typeof va === "number" && typeof vb === "number") {
        if (va !== vb) return dir * (va - vb);
      } else {
        const sa = String(va);
        const sb = String(vb);
        if (sa !== sb) return dir * sa.localeCompare(sb);
      }
      const ma = sortValueForColumn(a, "machine").localeCompare(sortValueForColumn(b, "machine"));
      if (ma !== 0) return ma;
      return compareCreatedSort(a, b);
    });
  }

  function updateDprSortIndicators() {
    const table = document.getElementById("dpr-table");
    if (!table) return;
    table.querySelectorAll("thead th[data-col-name]").forEach((th) => {
      const c = th.dataset.colName;
      th.classList.remove("dpr-th-sorted-asc", "dpr-th-sorted-desc");
      let ind = th.querySelector(".dpr-sort-ind");
      if (!SORTABLE_COLS.has(c)) {
        if (ind) ind.textContent = "";
        return;
      }
      if (!ind) {
        ind = document.createElement("span");
        ind.className = "dpr-sort-ind";
        ind.setAttribute("aria-hidden", "true");
        th.appendChild(ind);
      }
      if (dprSortBy === c) {
        th.classList.add(dprSortDir === "desc" ? "dpr-th-sorted-desc" : "dpr-th-sorted-asc");
        ind.textContent = dprSortDir === "desc" ? " ▼" : " ▲";
      } else {
        ind.textContent = "";
      }
    });
  }

  function applyColumnWidths(table) {
    if (!table) return;
    const wmap = dprLayout.widths && typeof dprLayout.widths === "object" ? dprLayout.widths : {};
    table.querySelectorAll("[data-col-name]").forEach((cell) => {
      const k = String(cell.dataset.colName || "");
      const n = wmap[k];
      if (n != null && Number.isFinite(Number(n)) && Number(n) >= 40) {
        const px = `${Math.round(Number(n))}px`;
        cell.style.width = px;
        cell.style.minWidth = px;
        cell.style.maxWidth = px;
      } else {
        cell.style.width = "";
        cell.style.minWidth = "";
        cell.style.maxWidth = "";
      }
    });
  }

  function attachDprResizeGlobals() {
    if (attachDprResizeGlobals._done) return;
    attachDprResizeGlobals._done = true;
    document.addEventListener("mousemove", (e) => {
      if (!dprResizeDrag) return;
      const table = document.getElementById("dpr-table");
      if (!table) return;
      const th = table.querySelector(`thead th[data-col-name="${dprResizeDrag.col}"]`);
      if (!th) return;
      const delta = e.pageX - dprResizeDrag.startX;
      const newW = Math.max(60, dprResizeDrag.origW + delta);
      if (!dprLayout.widths || typeof dprLayout.widths !== "object") dprLayout.widths = {};
      dprLayout.widths[dprResizeDrag.col] = newW;
      applyColumnWidths(table);
      applyDprPinnedStyles(table);
    });
    document.addEventListener("mouseup", () => {
      if (!dprResizeDrag) return;
      dprResizeDrag = null;
      document.body.classList.remove("dpr-col-resizing");
      saveDprLayout();
      const table = document.getElementById("dpr-table");
      if (table) applyDprPinnedStyles(table);
    });
  }

  function applyDprPinnedStyles(table) {
    if (!table) return;
    const all = table.querySelectorAll("[data-col-name]");
    all.forEach((el) => {
      el.classList.remove("is-pinned-left", "is-pinned-left-last");
      el.style.left = "";
      el.style.zIndex = "";
    });

    const headerPinned = Array.from(table.querySelectorAll("thead th[data-col-name]")).filter((th) =>
      dprLayout.pinnedLeft.includes(String(th.dataset.colName || "")),
    );
    let left = 0;
    headerPinned.forEach((th, i) => {
      const name = String(th.dataset.colName || "");
      const w = th.offsetWidth || 0;
      const cells = table.querySelectorAll(`[data-col-name="${name}"]`);
      cells.forEach((c) => {
        c.classList.add("is-pinned-left");
        c.style.left = `${left}px`;
        c.style.zIndex = c.tagName === "TH" ? String(80 - i) : String(20 - i);
      });
      left += w;
    });
    const last = headerPinned[headerPinned.length - 1];
    if (last) {
      const name = String(last.dataset.colName || "");
      table.querySelectorAll(`[data-col-name="${name}"]`).forEach((c) => c.classList.add("is-pinned-left-last"));
    }
  }

  function applyDprColumnLayout(editable) {
    const table = document.getElementById("dpr-table");
    if (!table) return;
    const headerRow = table.querySelector("thead tr");
    if (!headerRow) return;
    const ths = Array.from(headerRow.querySelectorAll("th[data-col-name]"));
    const available = ths.map((th) => String(th.dataset.colName || ""));
    if (!editable) dprLayout.order = dprLayout.order.filter((c) => c !== "actions");
    let order = [
      ...dprLayout.order.filter((c) => available.includes(c)),
      ...available.filter((c) => !dprLayout.order.includes(c)),
    ];
    const pinned = order.filter((c) => dprLayout.pinnedLeft.includes(c));
    const unpinned = order.filter((c) => !dprLayout.pinnedLeft.includes(c));
    order = [...pinned, ...unpinned];
    dprLayout.order = order;
    headerRow.innerHTML = "";
    order.forEach((name) => {
      const th = ths.find((x) => String(x.dataset.colName || "") === name);
      if (th) headerRow.appendChild(th);
    });

    const bodyRows = Array.from(table.querySelectorAll("tbody tr"));
    bodyRows.forEach((tr) => {
      if (tr.querySelector(".ti-dpr-empty")) return;
      const tds = Array.from(tr.querySelectorAll("td[data-col-name]"));
      const map = new Map(tds.map((td) => [String(td.dataset.colName || ""), td]));
      tds.forEach((td) => td.remove());
      order.forEach((name) => {
        const td = map.get(name);
        if (td) tr.appendChild(td);
      });
    });
    applyColumnWidths(table);
    applyDprPinnedStyles(table);
    saveDprLayout();
  }

  function wireDprHeaderControls(editable) {
    const table = document.getElementById("dpr-table");
    if (!table) return;
    const headers = Array.from(table.querySelectorAll("thead th[data-col-name]"));
    headers.forEach((th) => {
      const col = String(th.dataset.colName || "");
      if (!col) return;
      th.setAttribute("draggable", "true");

      if (!th.querySelector(".pin-toggle-btn")) {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "pin-toggle-btn";
        btn.title = "Pin column to left";
        btn.setAttribute("aria-label", "Pin column to left");
        btn.innerHTML = `
          <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
            <path d="M9 3h6v3l2 3v3H7V9l2-3V3zM12 12v9" />
          </svg>
        `;
        btn.addEventListener("click", (e) => {
          e.preventDefault();
          e.stopPropagation();
          const pinned = dprLayout.pinnedLeft.includes(col);
          dprLayout.pinnedLeft = pinned
            ? dprLayout.pinnedLeft.filter((x) => x !== col)
            : [...dprLayout.pinnedLeft, col];
          applyDprColumnLayout(editable);
          wireDprHeaderControls(editable);
          wireDprColumnSort(editable);
        });
        th.insertBefore(btn, th.firstChild);
      }

      if (!th.querySelector(".dpr-col-resize")) {
        const rz = document.createElement("div");
        rz.className = "dpr-col-resize";
        rz.dataset.col = col;
        rz.title = "Drag to resize column";
        rz.addEventListener("mousedown", (e) => {
          e.preventDefault();
          e.stopPropagation();
          const w = th.offsetWidth || 120;
          dprResizeDrag = { col, startX: e.pageX, origW: w };
          document.body.classList.add("dpr-col-resizing");
        });
        th.appendChild(rz);
      }

      const pinBtn = th.querySelector(".pin-toggle-btn");
      if (pinBtn) {
        pinBtn.classList.toggle("is-pinned", dprLayout.pinnedLeft.includes(col));
      }

      th.ondragstart = (e) => {
        if (e.target && e.target.closest && e.target.closest(".pin-toggle-btn")) return;
        if (e.target && e.target.closest && e.target.closest(".dpr-col-resize")) {
          e.preventDefault();
          return;
        }
        dprDragCol = col;
        th.classList.add("is-dragging");
        if (e.dataTransfer) e.dataTransfer.effectAllowed = "move";
      };
      th.ondragend = () => {
        dprDragCol = null;
        th.classList.remove("is-dragging");
        table.querySelectorAll("th").forEach((h) => h.classList.remove("drag-over"));
      };
      th.ondragover = (e) => {
        if (!dprDragCol || dprDragCol === col) return;
        e.preventDefault();
        th.classList.add("drag-over");
      };
      th.ondragleave = () => th.classList.remove("drag-over");
      th.ondrop = (e) => {
        if (!dprDragCol || dprDragCol === col) return;
        e.preventDefault();
        th.classList.remove("drag-over");
        const order = [...dprLayout.order];
        const from = order.indexOf(dprDragCol);
        const to = order.indexOf(col);
        if (from < 0 || to < 0 || from === to) return;
        const [item] = order.splice(from, 1);
        order.splice(to, 0, item);
        dprLayout.order = order;
        applyDprColumnLayout(editable);
        wireDprHeaderControls(editable);
        wireDprColumnSort(editable);
      };
    });
  }

  function wireDprColumnSort(editable) {
    const table = document.getElementById("dpr-table");
    if (!table) return;
    table.querySelectorAll("thead th[data-col-name]").forEach((th) => {
      const col = String(th.dataset.colName || "");
      if (!SORTABLE_COLS.has(col)) return;
      th.dataset.dprSortWired = th.dataset.dprSortWired || "";
      if (th.dataset.dprSortWired === "1") return;
      th.dataset.dprSortWired = "1";
      th.addEventListener("click", (e) => {
        if (e.target.closest && e.target.closest(".pin-toggle-btn")) return;
        if (e.target.closest && e.target.closest(".dpr-col-resize")) return;
        e.preventDefault();
        if (dprSortBy === col) {
          if (dprSortDir === "asc") dprSortDir = "desc";
          else {
            dprSortBy = null;
            dprSortDir = "asc";
          }
        } else {
          dprSortBy = col;
          dprSortDir = "asc";
        }
        applyPendingSort();
        render();
      });
    });
  }

  function blankEditorRow(machineId = "", machineLabel = "") {
    return {
      id: null,
      machineId: machineId || "",
      machineLabel: machineLabel || machineId || "",
      partNo: "",
      partName: "",
      plannedQty: null,
      producedQty: null,
      producedPct: null,
      rmIssued: null,
      rmAvailable: null,
      rmCode: null,
      rmCoverageNos: null,
      rmAllocated: null,
      toolNo: null,
      strokesConsumed: null,
      pmDue: null,
      remarks: "",
    };
  }

  function buildEditorRows(savedRows) {
    const rows = Array.isArray(savedRows) ? [...savedRows] : [];
    const byMachine = new Map();
    const extras = [];
    rows.forEach((r) => {
      const mid = String(r.machineId || "").trim();
      if (mid && !byMachine.has(mid)) {
        byMachine.set(mid, r);
      } else {
        extras.push(r);
      }
    });
    const seeded = [];
    machines.forEach((m) => {
      const mid = String(m.id || "").trim();
      if (!mid) return;
      seeded.push(byMachine.get(mid) || blankEditorRow(mid, m.label || mid));
    });
    const combined = seeded.length === 0 ? rows : [...seeded, ...extras];
    const labelById = new Map(machines.map((m) => [String(m.id || ""), String(m.label || m.id || "")]));
    combined.sort((a, b) => {
      const al = String(a.machineLabel || labelById.get(String(a.machineId || "")) || a.machineId || "")
        .trim()
        .toLowerCase();
      const bl = String(b.machineLabel || labelById.get(String(b.machineId || "")) || b.machineId || "")
        .trim()
        .toLowerCase();
      if (al !== bl) return al.localeCompare(bl);
      return compareCreatedSort(a, b);
    });
    return combined;
  }

  async function refreshDerived(index) {
    const row = pendingRows[index];
    if (!row) return;
    const dateInput = document.getElementById("dpr-date");
    const dateVal = dateInput ? dateInput.value : "";
    if (!String(row.partNo || "").trim()) {
      row.toolNo = null;
      row.rmIssued = null;
      row.rmAvailable = null;
      row.rmCode = null;
      row.rmCoverageNos = null;
      row.rmAllocated = null;
      row.strokesConsumed = null;
      row.pmDue = null;
      return;
    }
    try {
      const pq = row.plannedQty === null || row.plannedQty === undefined ? 0 : row.plannedQty;
      const res = await Api.derived(row.partNo, pq, dateVal);
      row.toolNo = res.toolNo ?? null;
      row.rmIssued = res.rmIssued ?? null;
      row.rmAvailable = res.rmAvailable ?? null;
      row.rmCode = res.rmCode ?? null;
      row.rmCoverageNos = res.rmCoverageNos ?? null;
      row.rmAllocated = res.rmAllocated ?? null;
      row.strokesConsumed = res.strokesConsumed ?? null;
      row.pmDue = res.pmDue ?? null;
      setStatus("");
    } catch (e) {
      console.error(e);
      row.toolNo = null;
      row.rmIssued = null;
      row.rmAvailable = null;
      row.rmCode = null;
      row.rmCoverageNos = null;
      row.rmAllocated = null;
      row.strokesConsumed = null;
      row.pmDue = null;
      setStatus(e.message || "Could not load tool / RM data", true);
    }
  }

  function scheduleRefreshDerived(index) {
    if (deriveTimer) clearTimeout(deriveTimer);
    deriveIdx = index;
    deriveTimer = setTimeout(async () => {
      deriveTimer = null;
      const idx = deriveIdx;
      await refreshDerived(idx);
      const tbody = document.getElementById("dpr-tbody");
      if (!tbody) return;
      const tr = tbody.children[idx];
      if (!tr) return;
      const row = pendingRows[idx];
      if (!row) return;
      const setCell = (colName, value) => {
        const td = tr.querySelector(`[data-col-name="${colName}"]`);
        if (td) td.textContent = formatCellNumber(value);
      };
      setCell("rm_issued", row.rmIssued);
      setCell("rm_available", row.rmAvailable);
      setCell("rm_code", row.rmCode);
      setCell("rm_coverage_nos", row.rmCoverageNos);
      setCell("rm_allocated", row.rmAllocated);
      setCell("tool_no", row.toolNo);
      setCell("strokes_consumed", row.strokesConsumed);
      setCell("pm_due", row.pmDue);
    }, 200);
  }

  function render() {
    const tbody = document.getElementById("dpr-tbody");
    if (!tbody) return;

    const dateInput = document.getElementById("dpr-date");
    const dateVal = dateInput ? dateInput.value : "";
    const editable = applyEditabilityForDate(dateVal);
    applyPendingSort();
    const allRows = [...pendingRows];
    const colActions = editable ? 1 : 0;
    const numCols = 16 + colActions;

    tbody.innerHTML = "";

    allRows.forEach((row, idx) => {
      const tr = document.createElement("tr");
      if (row.id) tr.dataset.rowId = String(row.id);

      const machineCell = document.createElement("td");
      machineCell.dataset.colName = "machine";
      if (editable) {
        const sel = document.createElement("select");
        sel.className = "ti-dpr-select dpr-select";
        sel.dataset.field = "machineId";
        const opt0 = document.createElement("option");
        opt0.value = "";
        opt0.textContent = machines.length ? "Select machine" : "No machines (set DPR_MACHINE_LIST_SQL)";
        sel.appendChild(opt0);
        machines.forEach((m) => {
          const o = document.createElement("option");
          o.value = m.id;
          o.textContent = m.label || m.id;
          sel.appendChild(o);
        });
        sel.value = row.machineId || "";
        sel.addEventListener("change", async () => {
          pendingRows[idx].machineId = sel.value;
          await autoSaveReadyRow(idx, dateVal);
        });
        machineCell.appendChild(sel);
      } else {
        machineCell.textContent = row.machineLabel || row.machineId || "—";
      }

      const qrCell = document.createElement("td");
      qrCell.dataset.colName = "qr";
      const mid = String(row.machineId || "");
      const qinfo = qrByMachine.get(mid);
      if (qinfo) {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "ti-btn ti-btn-outline ti-btn-xs dpr-qr-cell-btn";
        btn.textContent = "Show";
        btn.title = "Show machine QR code";
        btn.addEventListener("click", () => openQrModal(qinfo));
        qrCell.appendChild(btn);
      } else {
        qrCell.textContent = "—";
      }

      const partNoCell = document.createElement("td");
      partNoCell.dataset.colName = "part_no";
      if (editable) {
        const inp = document.createElement("input");
        inp.type = "text";
        inp.className = "ti-dpr-input-text dpr-input-text";
        inp.dataset.field = "partNo";
        inp.setAttribute("list", DPR_PARTS_DATALIST_ID);
        inp.placeholder = "Type part no";
        inp.value = row.partNo || "";
        inp.addEventListener("change", async () => {
          const partNo = String(inp.value || "").trim();
          pendingRows[idx].partNo = partNo;
          pendingRows[idx].partName = partNameFor(partNo);
          await refreshDerived(idx);
          await autoSaveReadyRow(idx, dateVal);
          render();
        });
        partNoCell.appendChild(inp);
      } else {
        partNoCell.textContent = row.partNo || "—";
      }

      const partNameCell = document.createElement("td");
      partNameCell.dataset.colName = "part_name";
      partNameCell.textContent = row.partName || partNameFor(row.partNo) || "—";

      const plannedCell = document.createElement("td");
      plannedCell.dataset.colName = "planned_qty";
      if (editable) {
        const inp = document.createElement("input");
        inp.type = "number";
        inp.step = "any";
        inp.className = "ti-dpr-input-num dpr-input-num";
        inp.value =
          row.plannedQty === null || row.plannedQty === undefined ? "" : String(row.plannedQty);
        inp.addEventListener("input", () => {
          pendingRows[idx].plannedQty = inp.value === "" ? null : Number(inp.value);
          const tr = inp.closest("tr");
          const pcel = tr?.querySelector('[data-col-name="produced_pct"]');
          if (pcel) {
            pcel.textContent = formatProducedPercent(
              pendingRows[idx].plannedQty,
              pendingRows[idx].producedQty,
            );
          }
          updateKpiStrip();
          scheduleRefreshDerived(idx);
        });
        inp.addEventListener("change", async () => {
          pendingRows[idx].plannedQty = inp.value === "" ? null : Number(inp.value);
          await autoSaveReadyRow(idx, dateVal);
        });
        plannedCell.appendChild(inp);
      } else {
        plannedCell.textContent = formatCellNumber(row.plannedQty);
      }

      const producedCell = document.createElement("td");
      producedCell.dataset.colName = "produced_qty";
      if (editable) {
        const inp = document.createElement("input");
        inp.type = "number";
        inp.step = "any";
        inp.className = "ti-dpr-input-num dpr-input-num";
        inp.value =
          row.producedQty === null || row.producedQty === undefined ? "" : String(row.producedQty);
        producedCell.appendChild(inp);
      } else {
        producedCell.textContent = formatCellNumber(row.producedQty);
      }

      const pctCell = document.createElement("td");
      pctCell.dataset.colName = "produced_pct";
      pctCell.textContent = formatProducedPercent(row.plannedQty, row.producedQty);
      const initialPct = Number(row.producedPct);
      if (Number.isFinite(initialPct)) {
        pctCell.classList.toggle("dpr-produced-pct-low", initialPct < 70);
        pctCell.classList.toggle("dpr-produced-pct-good", initialPct >= 70);
      }
      if (editable) {
        const inpP = producedCell.querySelector("input");
        if (inpP) {
          inpP.addEventListener("input", () => {
            pendingRows[idx].producedQty = inpP.value === "" ? null : Number(inpP.value);
            pctCell.textContent = formatProducedPercent(
              pendingRows[idx].plannedQty,
              pendingRows[idx].producedQty,
            );
            const p = Number(pendingRows[idx].plannedQty);
            const q = Number(pendingRows[idx].producedQty);
            const calcPct = Number.isFinite(p) && p > 0 && Number.isFinite(q) ? (100 * q) / p : null;
            pctCell.classList.toggle("dpr-produced-pct-low", Number.isFinite(calcPct) && calcPct < 70);
            pctCell.classList.toggle("dpr-produced-pct-good", Number.isFinite(calcPct) && calcPct >= 70);
            syncBreakdownButton(tr, pendingRows[idx]);
            updateKpiStrip();
          });
          inpP.addEventListener("change", () => scheduleRowAutoSave(row, dateVal, 120));
        }
      }

      const remarksCell = document.createElement("td");
      remarksCell.dataset.colName = "remarks";
      if (editable) {
        const inp = document.createElement("input");
        inp.type = "text";
        inp.className = "ti-dpr-input-text dpr-input-text";
        inp.value = row.remarks || "";
        inp.addEventListener("input", () => {
          pendingRows[idx].remarks = inp.value;
        });
        inp.addEventListener("change", () => scheduleRowAutoSave(row, dateVal, 120));
        remarksCell.appendChild(inp);
      } else {
        remarksCell.textContent = row.remarks || "—";
      }

      const mkDerived = (key, val) => {
        const td = document.createElement("td");
        td.dataset.colName = key;
        td.textContent = formatCellNumber(val);
        return td;
      };

      if (editable) {
        const actionCell = document.createElement("td");
        actionCell.dataset.colName = "actions";
        actionCell.className = "dpr-col-actions";
        if (breakdownAccess) {
          const brBtn = document.createElement("button");
          brBtn.type = "button";
          brBtn.className = "ti-btn ti-btn--xs ti-btn--ghost dpr-breakdown-btn";
          brBtn.textContent = "Breakdown";
          brBtn.addEventListener("click", () => openBreakdownModal(pendingRows[idx]));
          syncBreakdownButton(tr, row);
          actionCell.appendChild(brBtn);
        }
        const delBtn = document.createElement("button");
        delBtn.type = "button";
        delBtn.className = "ti-btn ti-btn--xs ti-btn--ghost";
        delBtn.textContent = "Delete";
        delBtn.addEventListener("click", () => deleteRow(idx, row.id));
        actionCell.appendChild(delBtn);
        tr.appendChild(actionCell);
      }

      tr.appendChild(machineCell);
      tr.appendChild(qrCell);
      tr.appendChild(partNoCell);
      tr.appendChild(partNameCell);
      tr.appendChild(plannedCell);
      tr.appendChild(producedCell);
      tr.appendChild(pctCell);
      tr.appendChild(remarksCell);
      tr.appendChild(mkDerived("rm_issued", row.rmIssued));
      tr.appendChild(mkDerived("rm_available", row.rmAvailable));
      tr.appendChild(mkDerived("rm_code", row.rmCode));
      tr.appendChild(mkDerived("rm_coverage_nos", row.rmCoverageNos));
      tr.appendChild(mkDerived("rm_allocated", row.rmAllocated));
      tr.appendChild(mkDerived("tool_no", row.toolNo));
      tr.appendChild(mkDerived("strokes_consumed", row.strokesConsumed));
      tr.appendChild(mkDerived("pm_due", row.pmDue));

      tbody.appendChild(tr);
    });

    if (allRows.length === 0) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = numCols;
      td.className = "ti-dpr-empty";
      td.textContent = editable
        ? "No lines for this date. Click Add line to create one."
        : "No lines for this date.";
      tr.appendChild(td);
      tbody.appendChild(tr);
    }

    applyDprColumnLayout(editable);
    wireDprHeaderControls(editable);
    wireDprColumnSort(editable);
    updateDprSortIndicators();
    updateKpiStrip();
  }

  async function saveRow(index, dateVal, opts = {}) {
    const silent = !!opts.silent;
    const row = pendingRows[index];
    if (!row) return;
    if (!silent) setStatus("");
    try {
      const payload = {
        id: row.id || null,
        reviewDate: dateVal,
        machineId: row.machineId || "",
        partNo: row.partNo || "",
        plannedQty: row.plannedQty === null || row.plannedQty === undefined ? 0 : row.plannedQty,
        producedQty:
          row.producedQty === null || row.producedQty === undefined ? null : row.producedQty,
        remarks: row.remarks || "",
      };
      const res = await Api.save(payload);
      if (res.row) {
        Object.assign(row, res.row);
      } else if (res.id) {
        row.id = res.id;
      }
      sortPendingRowsByMachine();
      suppressRealtimeReloadUntil = Date.now() + 1500;
      setStatus(silent ? "Auto-saved." : "Saved.");
      if (!silent) {
        await loadRows(dateVal);
      } else {
        render();
      }
    } catch (e) {
      console.error(e);
      setStatus(e.message || (silent ? "Auto-save failed" : "Save failed"), true);
    }
  }

  async function autoSaveReadyRow(index, dateVal) {
    const row = pendingRows[index];
    if (!row) return;
    const machineId = String(row.machineId || "").trim();
    const partNo = String(row.partNo || "").trim();
    const planned = row.plannedQty;
    const hasPlanned =
      planned !== null &&
      planned !== undefined &&
      planned !== "" &&
      Number.isFinite(Number(planned));
    if (!machineId || !partNo || !hasPlanned) return;
    await saveRow(index, dateVal, { silent: true });
  }

  function scheduleRowAutoSave(rowRef, dateVal, delayMs = 500) {
    if (!rowRef) return;
    const prev = rowAutoSaveTimers.get(rowRef);
    if (prev) window.clearTimeout(prev);
    const timer = window.setTimeout(async () => {
      rowAutoSaveTimers.delete(rowRef);
      const idx = pendingRows.indexOf(rowRef);
      if (idx < 0) return;
      await autoSaveReadyRow(idx, dateVal);
    }, delayMs);
    rowAutoSaveTimers.set(rowRef, timer);
  }

  async function deleteRow(index, id) {
    const dateVal = document.getElementById("dpr-date")?.value || "";
    if (!id) {
      pendingRows.splice(index, 1);
      render();
      return;
    }
    if (!window.confirm("Delete this line?")) return;
    setStatus("");
    try {
      await Api.del(id);
      await loadRows(dateVal);
      setStatus("Deleted.");
    } catch (e) {
      console.error(e);
      setStatus(e.message || "Delete failed", true);
    }
  }

  function stopDprPolling() {
    if (dprPollTimer) {
      clearInterval(dprPollTimer);
      dprPollTimer = null;
    }
  }

  function startDprPollingFallback(dateVal) {
    stopDprPolling();
    let isRefreshing = false;
    dprPollTimer = window.setInterval(async () => {
      const currentDate = document.getElementById("dpr-date")?.value;
      if (!currentDate || currentDate !== dateVal) return;
      if (isRefreshing) return;
      try {
        const ver = await Api.version(currentDate);
        const token = ver && ver.version ? String(ver.version) : "";
        if (!token) return;
        if (lastVersionToken === null) {
          lastVersionToken = token;
          return;
        }
        if (token !== lastVersionToken) {
          lastVersionToken = token;
          isRefreshing = true;
          await loadRows(currentDate);
        }
      } catch (e) {
        console.warn("DPR version poll failed:", e);
      } finally {
        isRefreshing = false;
      }
    }, DPR_POLL_MS);
  }

  async function loadRows(dateVal) {
    const container = document.getElementById("dpr-table-container");
    if (container) container.classList.add("loading");
    setStatus("Loading…");
    dprSortBy = null;
    dprSortDir = "asc";
    try {
      const res = await Api.rows(dateVal);
      const savedRows = res.rows || [];
      const editable = applyEditabilityForDate(dateVal);
      pendingRows = editable ? buildEditorRows(savedRows) : savedRows;
      try {
        monthlyKpi = await Api.summary(dateVal);
      } catch (sumErr) {
        console.warn(sumErr);
        monthlyKpi = null;
      }
      render();
      setStatus("");
    } catch (e) {
      console.error(e);
      pendingRows = [];
      monthlyKpi = null;
      render();
      setStatus("Failed to load rows.", true);
    } finally {
      if (container) container.classList.remove("loading");
    }
  }

  async function init() {
    loadDprLayout();
    attachDprResizeGlobals();
    window.DPR_EDIT_ALLOWED = typeof window.DPR_EDIT_ALLOWED === "boolean" ? window.DPR_EDIT_ALLOWED : false;

    const dateInput = document.getElementById("dpr-date");
    if (!dateInput) return;
    dateInput.value = todayIso();
    applyEditabilityForDate(dateInput.value);
    wireSnapshotEditors();

    try {
      const opt = await Api.options();
      machines = opt.machines || [];
      parts = opt.parts || [];
      ensurePartDatalist();
    } catch (e) {
      console.error(e);
      setStatus("Could not load picklists.", true);
    }
    if (breakdownAccess) {
      await loadBreakdownOperators();
    }

    dateInput.addEventListener("change", () => {
      lastVersionToken = null;
      applyEditabilityForDate(dateInput.value);
      loadRows(dateInput.value);
      startDprPollingFallback(dateInput.value);
    });

    const addBtn = document.getElementById("dpr-add-row");
    if (addBtn) {
      addBtn.addEventListener("click", () => {
        pendingRows.push(blankEditorRow());
        render();
      });
    }

    const resetColsBtn = document.getElementById("dpr-reset-columns");
    if (resetColsBtn) {
      resetColsBtn.addEventListener("click", () => {
        const d = document.getElementById("dpr-date")?.value || "";
        const editable = applyEditabilityForDate(d);
        resetDprLayout(editable);
      });
    }

    const fsBtn = document.getElementById("dpr-fullscreen-toggle");
    if (fsBtn) {
      dprFullscreenMode = document.body.classList.contains("dpr-fullscreen-mode");
      applyDprFullscreenState();
      fsBtn.addEventListener("click", () => {
        dprFullscreenMode = !dprFullscreenMode;
        applyDprFullscreenState();
        render();
      });
    }

    if (!dprFullscreenKeyHandlerBound) {
      dprFullscreenKeyHandlerBound = true;
      document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && dprFullscreenMode) {
          dprFullscreenMode = false;
          applyDprFullscreenState();
          render();
        }
      });
    }

    await refreshQrMap();
    await loadRows(dateInput.value);
    startDprPollingFallback(dateInput.value);

    const qrClose = document.getElementById("dpr-qr-modal-close");
    const qrBackdrop = document.getElementById("dpr-qr-modal-backdrop");
    if (qrClose) qrClose.addEventListener("click", closeQrModal);
    if (qrBackdrop) qrBackdrop.addEventListener("click", closeQrModal);

    if (breakdownAccess) {
      const brCancel = document.getElementById("dpr-breakdown-cancel");
      if (brCancel) brCancel.addEventListener("click", closeBreakdownModal);
      const brSubmit = document.getElementById("dpr-breakdown-submit");
      if (brSubmit) {
        brSubmit.addEventListener("click", async () => {
          if (!breakdownModalState) return;
          const liveRow =
            pendingRows.find((r) => r.id && r.id === breakdownModalState.dprRowId) ||
            breakdownModalState.row;
          if (!hasDprProducedQty(liveRow)) {
            notify("Enter Produced Qty on this line before raising a breakdown (0 is allowed).", true);
            return;
          }
          const issueInput = document.getElementById("dpr-breakdown-issue");
          const priorityInput = document.getElementById("dpr-breakdown-priority");
          const operatorInput = document.getElementById("dpr-breakdown-operator");
          const issue = String(issueInput?.value || "").trim();
          if (!issue) {
            notify("Please enter the issue/problem.", true);
            return;
          }
          const priority = String(priorityInput?.value || "Immediate").trim();
          const operatorLabel = String(operatorInput?.value || "").trim();
          const operator = breakdownOperatorByLabel.get(operatorLabel);
          if (!operator) {
            notify("Please select a valid operator.", true);
            return;
          }
          brSubmit.disabled = true;
          try {
            const dateVal = document.getElementById("dpr-date")?.value || "";
            await Api.breakdownCreate({
              toolNo: breakdownModalState.toolNo,
              partNo: breakdownModalState.partNo,
              partName: breakdownModalState.partName,
              machineId: breakdownModalState.machineId,
              machineName: breakdownModalState.machineName,
              issue,
              priority,
              operatorId: operator.id,
              dprRowId: breakdownModalState.dprRowId,
              dprProducedQty: liveRow.producedQty,
              dprReviewDate: dateVal || null,
            });
            breakdownModalState = null;
            setBreakdownWarning("");
            setBreakdownModalSuccess(true);
          } catch (e) {
            console.error(e);
            notify(e.message || "Failed to raise breakdown.", true);
            brSubmit.disabled = false;
          }
        });
      }
    }
  }

  return { init, loadRows };
})();
