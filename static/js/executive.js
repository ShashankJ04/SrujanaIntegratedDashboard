/**
 * Executive Dashboard — 4-Pillar War Room (Hub Module)
 */
window.ExecPage = (() => {
  const WH = "/api/wh";

  function fmt(v) {
    if (v == null) return "—";
    const n = Number(v);
    return Number.isNaN(n) ? String(v) : n.toLocaleString("en-IN");
  }

  function statusDot(s) {
    const map = { healthy: "🟢", warning: "🟡", critical: "🔴" };
    return map[s] || "⚪";
  }

  async function api(url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error(`${r.status}`);
    return r.json();
  }

  function renderPillars(data) {
    const p = data.pillars || {};
    const upd = document.getElementById("exec-updated");
    if (upd) upd.textContent = `Last updated: ${data.last_updated || "—"}`;

    // Customer Parts
    const cp = p.customer_parts || {};
    document.getElementById("exec-cp-required").textContent = fmt(cp.required);
    document.getElementById("exec-cp-produced").textContent = fmt(cp.produced);
    document.getElementById("exec-cp-balance").textContent = fmt(cp.balance);
    document.getElementById("exec-cp-status").textContent = statusDot(cp.status);
    document.querySelector('[data-pillar="customer_parts"]').dataset.status = cp.status || "healthy";

    // Raw Material
    const rm = p.raw_material || {};
    document.getElementById("exec-rm-required").textContent = rm.required || "—";
    document.getElementById("exec-rm-status").textContent = statusDot(rm.status);
    document.querySelector('[data-pillar="raw_material"]').dataset.status = rm.status || "healthy";

    // Tools
    const tl = p.tools || {};
    document.getElementById("exec-tl-total").textContent = fmt(tl.required);
    document.getElementById("exec-tl-critical").textContent = fmt(tl.balance);
    document.getElementById("exec-tl-status").textContent = statusDot(tl.status);
    document.querySelector('[data-pillar="tools"]').dataset.status = tl.status || "healthy";

    // Machines
    const mc = p.machines || {};
    document.getElementById("exec-mc-active").textContent = fmt(mc.produced);
    document.getElementById("exec-mc-status").textContent = statusDot(mc.status);
    document.querySelector('[data-pillar="machines"]').dataset.status = mc.status || "healthy";
  }

  function renderDrillList(containerId, rows, columns) {
    const el = document.getElementById(containerId);
    if (!el) return;
    if (!rows || rows.length === 0) {
      el.innerHTML = '<em class="ti-text-dim">All clear — no critical items.</em>';
      return;
    }
    let html = '<table class="ti-dpr-table"><thead><tr>';
    columns.forEach(c => { html += `<th>${c.label}</th>`; });
    html += '</tr></thead><tbody>';
    rows.forEach(r => {
      html += '<tr>';
      columns.forEach(c => {
        const v = r[c.key];
        const cls = c.key === 'status' ? ` class="ti-exec-status-${(v||'').toLowerCase()}"` : '';
        html += `<td${cls}>${v != null ? v : '—'}</td>`;
      });
      html += '</tr>';
    });
    html += '</tbody></table>';
    el.innerHTML = html;
  }

  async function load() {
    try {
      const data = await api(`${WH}/master_kpis`);
      renderPillars(data);
    } catch (e) {
      console.error("Executive KPIs failed:", e);
    }

    try {
      const tools = await api(`${WH}/drilldown/tools`);
      renderDrillList("exec-tools-list", tools, [
        { key: "TL_tool_number", label: "Tool No" },
        { key: "current_strokes", label: "Current Strokes" },
        { key: "PM_next_stroke", label: "PM Due At" },
        { key: "status", label: "Status" },
      ]);
    } catch (e) {
      document.getElementById("exec-tools-list").innerHTML = '<em class="ti-text-dim">Could not load tool data.</em>';
    }

    try {
      const rm = await api(`${WH}/drilldown/raw_materials`);
      renderDrillList("exec-rm-list", rm, [
        { key: "item_code", label: "Item Code" },
        { key: "total_rm_needed", label: "Needed" },
        { key: "total_rm_available", label: "Available" },
        { key: "status", label: "Status" },
      ]);
    } catch (e) {
      document.getElementById("exec-rm-list").innerHTML = '<em class="ti-text-dim">Could not load RM data.</em>';
    }
  }

  function init() { load(); }
  return { init };
})();
