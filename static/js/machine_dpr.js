window.MachineDprPage = (() => {
  const token = window.MACHINE_QR_TOKEN || "";

  function todayIso() {
    const t = new Date();
    const y = t.getFullYear();
    const m = String(t.getMonth() + 1).padStart(2, "0");
    const day = String(t.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  }

  function isToday(dateStr) {
    const d = String(dateStr || "").trim();
    return d === todayIso();
  }

  function setStatus(msg, isError) {
    const el = document.getElementById("machine-dpr-status");
    if (!el) return;
    el.textContent = msg || "";
    el.style.color = isError ? "#b91c1c" : "";
  }

  function getSelectedDate() {
    const inp = document.getElementById("mdpr-date");
    const v = inp && inp.value ? String(inp.value).trim() : "";
    return v || todayIso();
  }

  function formatNum(v) {
    if (v === null || v === undefined) return "—";
    const n = Number(v);
    if (Number.isNaN(n)) return "—";
    return n.toLocaleString("en-IN", { maximumFractionDigits: 4, minimumFractionDigits: 0 });
  }

  function formatAny(v) {
    if (v === null || v === undefined) return "—";
    const s = String(v).trim();
    return s === "" ? "—" : s;
  }

  function formatPct(planned, produced) {
    const p = Number(planned);
    if (!Number.isFinite(p) || p <= 0) return { text: "—", low: false, achieved: false };
    if (produced === null || produced === undefined || produced === "")
      return { text: "—", low: false, achieved: false };
    const q = Number(produced);
    if (!Number.isFinite(q)) return { text: "—", low: false, achieved: false };
    const pct = (100 * q) / p;
    const text = `${pct.toLocaleString("en-IN", { maximumFractionDigits: 2, minimumFractionDigits: 0 })}%`;
    const low = pct < 70;
    return { text, low, achieved: !low };
  }

  function renderShiftCard(res) {
    const el = document.createElement("article");
    el.className = "mdpr-card mdpr-card--shift";
    el.innerHTML = `
      <div class="mdpr-card-tag">Machine details</div>
      <div class="mdpr-shift-row">
        <div class="mdpr-shift-ico" aria-hidden="true">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M12 2L4 6v6c0 5 3.5 9.5 8 11 4.5-1.5 8-6 8-11V6l-8-4z" stroke="#2563eb" stroke-width="1.6" fill="#eff6ff"/>
            <circle cx="12" cy="10" r="2.5" fill="#2563eb"/>
          </svg>
        </div>
        <div class="mdpr-shift-text">
          <p class="mdpr-machine-name">Machine: <strong>${escapeHtml(res.machineLabel || res.machineId || "—")}</strong></p>
          <p class="mdpr-operator-name">Operator: <strong>${escapeHtml(res.operatorLabel || "—")}</strong></p>
        </div>
      </div>
    `;
    return el;
  }

  function escapeHtml(s) {
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }

  function render(res) {
    const cards = document.getElementById("machine-dpr-cards");
    if (!cards) return;

    const canEdit = !!window.DPR_EDIT_ALLOWED && isToday(res.date);

    cards.innerHTML = "";
    cards.appendChild(renderShiftCard(res));

    const rows = res.rows || [];
    if (!rows.length) {
      const empty = document.createElement("p");
      empty.className = "mdpr-empty";
      empty.textContent =
        "No production scheduled for this machine on the selected date.";
      cards.appendChild(empty);
      return;
    }

    rows.forEach((row) => {
      const card = document.createElement("article");
      card.className = "mdpr-card mdpr-card--line";

      const titleText = row.partName || "Part";
      const partNoText = row.partNo || "—";

      const top = document.createElement("div");
      top.className = "mdpr-line-top";
      const titleBlock = document.createElement("div");
      titleBlock.className = "mdpr-line-title-wrap";
      const overline = document.createElement("div");
      overline.className = "mdpr-line-overline";
      overline.textContent = "Component";
      const h = document.createElement("h2");
      h.className = "mdpr-line-title";
      h.textContent = titleText;
      const sub = document.createElement("div");
      sub.className = "mdpr-line-subrow";
      const partChip = document.createElement("span");
      partChip.className = "mdpr-line-chip";
      partChip.textContent = partNoText;
      sub.appendChild(partChip);
      titleBlock.appendChild(overline);
      titleBlock.appendChild(h);
      titleBlock.appendChild(sub);

      const badgeRow = document.createElement("div");
      badgeRow.className = "mdpr-badge-row";
      const lbl = document.createElement("span");
      lbl.className = "mdpr-badge-label";
      lbl.textContent = "Produced %";
      const badge = document.createElement("span");
      badge.className = "mdpr-pct-badge";
      badgeRow.appendChild(lbl);
      badgeRow.appendChild(badge);

      top.appendChild(titleBlock);
      top.appendChild(badgeRow);

      function syncBadge() {
        let v = null;
        if (canEdit && prodInp) {
          const raw = prodInp.value.trim();
          v = raw === "" ? null : Number(raw);
        } else {
          v = row.producedQty;
        }
        const pct = formatPct(row.plannedQty, v);
        badge.textContent =
          pct.text === "—"
            ? "—"
            : pct.low
              ? `${pct.text} Below target`
              : `${pct.text} Achieved`;
        badge.className =
          pct.text === "—"
            ? "mdpr-pct-badge mdpr-pct-badge--muted"
            : pct.low
              ? "mdpr-pct-badge mdpr-pct-badge--bad"
              : "mdpr-pct-badge mdpr-pct-badge--ok";
      }

      const primaryMetrics = document.createElement("div");
      primaryMetrics.className = "mdpr-primary-metrics";

      const plannedBox = document.createElement("div");
      plannedBox.className = "mdpr-stat-card mdpr-stat-card--planned";
      plannedBox.innerHTML = `
        <span class="mdpr-stat-label">Planned</span>
        <span class="mdpr-stat-value">${formatNum(row.plannedQty)}</span>
      `;

      const producedBox = document.createElement("div");
      producedBox.className = "mdpr-stat-card mdpr-stat-card--produced";
      const cap = document.createElement("span");
      cap.className = "mdpr-stat-label";
      cap.textContent = "Produced";
      producedBox.appendChild(cap);

      let prodInp = null;
      if (canEdit) {
        prodInp = document.createElement("input");
        prodInp.type = "number";
        prodInp.inputMode = "decimal";
        prodInp.step = "any";
        prodInp.className = "mdpr-input";
        prodInp.value =
          row.producedQty === null || row.producedQty === undefined ? "" : String(row.producedQty);
        prodInp.addEventListener("input", syncBadge);
        producedBox.appendChild(prodInp);
        const note = document.createElement("span");
        note.className = "mdpr-stat-note";
        note.textContent = "Enter actual produced units";
        producedBox.appendChild(note);
      } else {
        const num = document.createElement("span");
        num.className = "mdpr-stat-value";
        num.textContent = formatNum(row.producedQty);
        producedBox.appendChild(num);
      }

      primaryMetrics.appendChild(plannedBox);
      primaryMetrics.appendChild(producedBox);

      const auxMetrics = document.createElement("div");
      auxMetrics.className = "mdpr-detail-grid";
      auxMetrics.innerHTML = `
        <div class="mdpr-detail-card">
          <span class="mdpr-detail-label">RM Code</span>
          <span class="mdpr-detail-value mdpr-detail-value--text">${escapeHtml(formatAny(row.rmCode))}</span>
        </div>
        <div class="mdpr-detail-card">
          <span class="mdpr-detail-label">RM Issued</span>
          <span class="mdpr-detail-value">${escapeHtml(formatNum(row.rmIssued))}</span>
        </div>
        <div class="mdpr-detail-card">
          <span class="mdpr-detail-label">Tool No</span>
          <span class="mdpr-detail-value mdpr-detail-value--text">${escapeHtml(formatAny(row.toolNo))}</span>
        </div>
      `;

      const remWrap = document.createElement("div");
      remWrap.className = "mdpr-remarks-box";
      const remHead = document.createElement("div");
      remHead.className = "mdpr-remarks-head";
      remHead.innerHTML = `<span>Remarks</span><span class="mdpr-pencil" title="Edit">&#9998;</span>`;
      remWrap.appendChild(remHead);

      let remField;
      if (canEdit) {
        remField = document.createElement("textarea");
        remField.className = "mdpr-textarea";
        remField.rows = 2;
        remField.placeholder = "Notes…";
        remField.value = row.remarks ? String(row.remarks) : "";
      } else {
        remField = document.createElement("div");
        remField.className = "mdpr-remarks-read";
        remField.textContent = row.remarks ? String(row.remarks) : "—";
      }
      remWrap.appendChild(remField);

      card.appendChild(top);
      card.appendChild(primaryMetrics);
      card.appendChild(auxMetrics);
      card.appendChild(remWrap);

      if (canEdit) {
        const persistRow = async (opts = {}) => {
          const { reloadAfter = false, saveLabel = "Saved." } = opts;
          setStatus("Saving…");
          let producedQty = null;
          if (prodInp) {
            const t = prodInp.value.trim();
            if (t !== "") {
              const n = Number(t);
              producedQty = Number.isFinite(n) ? n : null;
            }
          }
          try {
            await ApiClient.putMachineProduced(token, {
              reviewDate: res.date,
              rowId: row.id,
              producedQty,
              remarks: remField.value,
            });
            row.producedQty = producedQty;
            row.remarks = remField.value || "";
            setStatus(saveLabel);
            if (reloadAfter) await load();
          } catch (e) {
            console.error(e);
            setStatus(e.message || "Save failed", true);
          }
        };

        const saveBtn = document.createElement("button");
        saveBtn.type = "button";
        saveBtn.className = "mdpr-save";
        saveBtn.textContent = "Save";
        saveBtn.addEventListener("click", async () => persistRow({ reloadAfter: true, saveLabel: "Saved." }));
        card.appendChild(saveBtn);
      }

      syncBadge();
      cards.appendChild(card);
    });
  }

  function applyViewOnlyStatus(res) {
    if (!window.DPR_EDIT_ALLOWED) {
      setStatus("");
      return;
    }
    if (!isToday(res.date)) {
      setStatus("View only — select today’s date to edit production.");
    } else {
      setStatus("");
    }
  }

  async function load() {
    setStatus("Loading…");
    const dateVal = getSelectedDate();
    try {
      const res = await ApiClient.getMachineDprToday(token, dateVal);
      render(res);
      applyViewOnlyStatus(res);
    } catch (e) {
      console.error(e);
      setStatus(e.message || "Failed to load.", true);
    }
  }

  function startMachinePolling() {
    /** @see backend/config.py DPR_POLL_INTERVAL_MS_DEFAULT; machine_dpr.html sets window.DPR_POLL_INTERVAL_MS */
    const FALLBACK_MS = 500000;
    const POLL_MS = Number(
      window.DPR_POLL_INTERVAL_MS != null ? window.DPR_POLL_INTERVAL_MS : FALLBACK_MS
    );
    let pollTimer = null;
    let lastToken = null;
    const loop = async () => {
      const dateVal = getSelectedDate();
      if (!isToday(dateVal)) return;
      try {
        const ver = await ApiClient.getDprVersion(dateVal);
        const token = ver && ver.version ? String(ver.version) : "";
        if (!token) return;
        if (lastToken === null) {
          lastToken = token;
          return;
        }
        if (token !== lastToken) {
          lastToken = token;
          await load();
        }
      } catch (e) {
        console.warn("Machine DPR version poll failed:", e);
      }
    };
    if (pollTimer) window.clearInterval(pollTimer);
    pollTimer = window.setInterval(loop, POLL_MS);
  }

  document.addEventListener("DOMContentLoaded", () => {
    if (!token) return;
    const dateInp = document.getElementById("mdpr-date");
    if (dateInp) {
      dateInp.removeAttribute("max");
      dateInp.value = todayIso();
      dateInp.addEventListener("change", () => {
        load();
      });
    }
    load();
    startMachinePolling();
  });

  return { load };
})();
