(() => {
  const chartIds = [
    "chart-top-rm-requirement",
    "chart-rm-req-vs-inward",
    "chart-material-mix",
    "chart-rm-stock-vs-req",
    "chart-material-rm-utilized",
    "chart-top-rm-balance",
    "chart-completion-buckets",
    "chart-pending-treemap",
    "chart-production-vs-req",
    "chart-pending-excess",
    "chart-top-pending",
  ];

  const plotlyConfig = {
    responsive: true,
    displayModeBar: false,
    staticPlot: false,
  };

  function statusColor(ratio, alpha = 0.82) {
    const r = Math.max(0, Math.min(1, Number(ratio) || 0));
    const hue = 136 * (1 - r);
    const sat = 80 + r * 14;
    const lit = 46 + (1 - Math.abs(r - 0.5) * 2) * 10;
    return `hsla(${hue}, ${sat}%, ${lit}%, ${alpha})`;
  }

  const BUCKET_PALETTE = [
    "rgba(220, 38, 38, 0.92)",
    "rgba(239, 120, 24, 0.90)",
    "rgba(234, 179, 8, 0.90)",
    "rgba(52, 211, 102, 0.90)",
    "rgba(5, 150, 105, 0.92)",
  ];

  function getPlotlyEl(id) {
    const el = document.getElementById(id);
    return el && window.Plotly ? el : null;
  }

  function formatQty(value) {
    return Number(value || 0).toLocaleString();
  }

  function formatPct(value, digits = 0) {
    const n = Number(value || 0);
    return `${n.toFixed(digits)}%`;
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function getHoverMetaEl(plotHostEl, defaultText) {
    const host = plotHostEl?.parentElement;
    if (!host) return null;
    let meta = host.querySelector(".chart-hover-meta");
    if (!meta) {
      meta = document.createElement("div");
      meta.className = "chart-hover-meta";
      host.appendChild(meta);
    }
    meta.textContent = defaultText;
    return meta;
  }

  function setHoverMeta(metaEl, text, fallback) {
    if (!metaEl) return;
    metaEl.textContent = text || fallback || "";
  }

  function init() {
    initHeaderDate();
    initResizeHandling();
    loadReports();
  }

  function initResizeHandling() {
    let resizeTimer;
    window.addEventListener("resize", () => {
      if (!window.Plotly) return;
      if (resizeTimer) clearTimeout(resizeTimer);
      resizeTimer = setTimeout(() => {
        chartIds.forEach((id) => {
          const el = document.getElementById(id);
          if (el) {
            window.Plotly.Plots.resize(el);
          }
        });
      }, 140);
    });
  }

  function baseLayout(overrides = {}) {
    return {
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      margin: { l: 40, r: 20, t: 14, b: 34 },
      font: {
        family: 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
        size: 11,
        color: "#344a60",
      },
      hoverlabel: {
        bgcolor: "#ffffff",
        bordercolor: "#c5d2e1",
        font: { color: "#0e2039", size: 11 },
      },
      transition: { duration: 350, easing: "cubic-in-out" },
      ...overrides,
    };
  }

  function initHeaderDate() {
    const headerDateEl = document.getElementById("header-date");
    if (!headerDateEl) return;
    const now = new Date();
    headerDateEl.textContent = now.toLocaleDateString(undefined, {
      weekday: "short",
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  }

  async function loadReports() {
    if (!window.Plotly) {
      throw new Error("Plotly failed to load.");
    }

    try {
      const [summary, completionBuckets, pendingTreemap, prodVsReq, shortfalls] =
        await Promise.all([
          ApiClient.getReportSummary(),
          ApiClient.getCompletionBuckets(),
          ApiClient.getPendingTreemap(35),
          ApiClient.getProductionVsRequirement(15),
          ApiClient.getTopShortfalls(20),
        ]);

      renderSummary(summary);
      renderCompletionBuckets(completionBuckets);
      renderPendingTreemap(pendingTreemap);
      renderProductionVsRequirement(prodVsReq);
      renderPendingExcess(summary);
      renderTopPending(prodVsReq);
      renderShortfalls(shortfalls);
      if (
        typeof DashboardCharts !== "undefined" &&
        typeof DashboardCharts.load === "function"
      ) {
        await DashboardCharts.load();
      }
    } catch (err) {
      console.error(err);
      showErrorState();
    }
  }

  function renderSummary(summary) {
    const {
      total_so_qty,
      total_pending_qty,
      total_excess_qty,
      parts_total,
      parts_completed,
      parts_pending,
    } = summary;
    const fmt = (v) =>
      typeof v === "number"
        ? v.toLocaleString(undefined, { maximumFractionDigits: 0 })
        : "\u2013";

    const el = (id) => document.getElementById(id);
    if (el("kpi-total-so")) el("kpi-total-so").textContent = fmt(total_so_qty);
    if (el("kpi-pending-qty"))
      el("kpi-pending-qty").textContent = fmt(total_pending_qty);
    if (el("kpi-excess-qty"))
      el("kpi-excess-qty").textContent = fmt(total_excess_qty);
    if (el("kpi-parts-total"))
      el("kpi-parts-total").textContent = fmt(parts_total);
    if (el("kpi-parts-completed"))
      el("kpi-parts-completed").textContent = fmt(parts_completed);
    if (el("kpi-parts-pending"))
      el("kpi-parts-pending").textContent = fmt(parts_pending);

    const qtyPct =
      total_so_qty > 0
        ? Math.max(
            0,
            Math.min(
              100,
              Math.round(
                ((total_so_qty - total_pending_qty) / total_so_qty) * 100,
              ),
            ),
          )
        : 0;
    const totalParts =
      parts_total || (parts_completed || 0) + (parts_pending || 0);
    const partsPct =
      totalParts > 0
        ? Math.max(
            0,
            Math.min(100, Math.round((parts_completed / totalParts) * 100)),
          )
        : 0;

    if (el("kpi-qty-pct")) el("kpi-qty-pct").textContent = `${qtyPct}%`;
    if (el("kpi-parts-pct")) el("kpi-parts-pct").textContent = `${partsPct}%`;

    [
      ["kpi-qty-bar", qtyPct],
      ["kpi-parts-bar", partsPct],
    ].forEach(([id, pct]) => {
      const bar = el(id);
      if (!bar) return;
      bar.style.setProperty("--kpi-progress", `${pct}%`);
      bar.style.setProperty("--kpi-hue", `${Math.round(pct * 1.2)}`);
      bar.setAttribute("aria-valuenow", String(pct));
    });
  }

  function renderCompletionBuckets(data) {
    const el = getPlotlyEl("chart-completion-buckets");
    if (!el) return;

    const labels = data.labels || [];
    const counts = data.counts || [];
    const total = counts.reduce((a, v) => a + Number(v || 0), 0);
    const n = labels.length;
    const colors = labels.map(
      (_, i) =>
        BUCKET_PALETTE[i] || statusColor(1 - i / Math.max(1, n - 1), 0.9),
    );
    const defaultMeta = "Hover a segment to inspect bucket details";
    const hoverMeta = getHoverMetaEl(el, defaultMeta);
    const pull = labels.map(() => 0);

    window.Plotly.react(
      el,
      [
        {
          type: "pie",
          labels,
          values: counts,
          hole: 0.58,
          sort: false,
          direction: "clockwise",
          marker: {
            colors,
            line: { color: "rgba(255, 255, 255, 0.96)", width: 2 },
          },
          pull,
          textinfo: "label+percent",
          textfont: { color: "#fff", size: 11, family: "Inter, sans-serif" },
          insidetextorientation: "auto",
          hovertemplate:
            "<b>%{label}</b><br>Parts: %{value:,}<br>Share: %{percent}<extra></extra>",
        },
      ],
      baseLayout({
        margin: { l: 10, r: 10, t: 12, b: 42 },
        legend: {
          orientation: "h",
          x: 0.5,
          xanchor: "center",
          y: -0.08,
          font: { color: "#344a60", size: 10.5 },
        },
      }),
      plotlyConfig,
    );

    el.on("plotly_hover", (evt) => {
      const point = evt?.points?.[0];
      if (!point) return;
      const idx = point.pointNumber;
      const value = Number(counts[idx] || 0);
      const pct = total > 0 ? (value / total) * 100 : 0;
      setHoverMeta(
        hoverMeta,
        `${labels[idx] || `Bucket ${idx + 1}`}: ${formatQty(value)} parts (${formatPct(pct, 1)})`,
        defaultMeta,
      );

      const hoverPull = labels.map((_, i) => (i === idx ? 0.08 : 0));
      window.Plotly.restyle(el, { pull: [hoverPull] });
    });

    el.on("plotly_unhover", () => {
      setHoverMeta(hoverMeta, "", defaultMeta);
      window.Plotly.restyle(el, { pull: [pull] });
    });
  }

  function renderPendingTreemap(items) {
    const el = getPlotlyEl("chart-pending-treemap");
    if (!el) return;

    const tree = (items || []).map((item) => ({
      partNo: item.part_no,
      partName: item.part_name,
      pending: item.pending_qty,
    }));
    if (!tree.length) return;

    const maxPending = Math.max(...tree.map((t) => Number(t.pending || 0)));
    const totalPending = tree.reduce(
      (a, t) => a + Number(t.pending || 0),
      0,
    );
    const defaultMeta =
      "Hover a block to inspect component pending details";
    const hoverMeta = getHoverMetaEl(el, defaultMeta);
    const labels = tree.map((t) => t.partNo);
    const parents = labels.map(() => "");
    const values = tree.map((t) => Number(t.pending || 0));
    const customdata = tree.map((t) => [t.partName || "", t.pending || 0]);
    const colors = values.map((v) =>
      statusColor(v / Math.max(1, maxPending), 0.96),
    );

    window.Plotly.react(
      el,
      [
        {
          type: "treemap",
          labels,
          parents,
          values,
          customdata,
          texttemplate: "<b>%{label}</b><br>%{value:,}",
          textfont: {
            color: "#ffffff",
            size: 12,
            family: "Inter, sans-serif",
          },
          marker: {
            colors,
            line: { width: 2, color: "rgba(255,255,255,0.96)" },
          },
          pathbar: { visible: false },
          hovertemplate:
            "<b>%{label}</b><br>%{customdata[0]}<br>Pending: %{value:,}<extra></extra>",
        },
      ],
      baseLayout({
        margin: { l: 4, r: 4, t: 8, b: 10 },
      }),
      plotlyConfig,
    );

    el.on("plotly_hover", (evt) => {
      const point = evt?.points?.[0];
      if (!point) return;
      const value = Number(point.value || 0);
      const pct = totalPending > 0 ? (value / totalPending) * 100 : 0;
      setHoverMeta(
        hoverMeta,
        `${point.label || "Component"} - Pending ${formatQty(value)} (${formatPct(pct, 1)} of total)`,
        defaultMeta,
      );
    });

    el.on("plotly_unhover", () => {
      setHoverMeta(hoverMeta, "", defaultMeta);
    });
  }

  function renderProductionVsRequirement(data) {
    const el = getPlotlyEl("chart-production-vs-req");
    if (!el) return;

    const labels = data.labels || [];
    const required = data.required || [];
    const pending = data.pending || [];
    const excess = data.excess || [];
    const defaultMeta = "Hover any bar for component-level status details";
    const hoverMeta = getHoverMetaEl(el, defaultMeta);
    const barColors = {
      req: labels.map((_, i) => {
        const ratio =
          required[i] > 0 ? (required[i] - pending[i]) / required[i] : 1;
        return statusColor(1 - Math.max(0, Math.min(1, ratio)), 0.7);
      }),
      pen: "rgba(220, 38, 38, 0.88)",
      exc: "rgba(5, 170, 105, 0.88)",
    };

    const traces = [
      {
        type: "bar",
        name: "Required",
        x: labels,
        y: required,
        marker: {
          color: barColors.req,
          line: { color: "rgba(255,255,255,0.8)", width: 0.8 },
          opacity: 0.92,
        },
        hovertemplate: "Required: %{y:,}<extra></extra>",
      },
      {
        type: "bar",
        name: "Pending",
        x: labels,
        y: pending,
        marker: {
          color: barColors.pen,
          line: { color: "rgba(255,255,255,0.8)", width: 0.8 },
          opacity: 0.92,
        },
        hovertemplate: "Pending: %{y:,}<extra></extra>",
      },
      {
        type: "bar",
        name: "Excess",
        x: labels,
        y: excess,
        marker: {
          color: barColors.exc,
          line: { color: "rgba(255,255,255,0.8)", width: 0.8 },
          opacity: 0.92,
        },
        hovertemplate: "Excess: %{y:,}<extra></extra>",
      },
    ];

    window.Plotly.react(
      el,
      traces,
      baseLayout({
        margin: { l: 48, r: 16, t: 14, b: 60 },
        barmode: "group",
        bargap: 0.22,
        bargroupgap: 0.08,
        hovermode: "x unified",
        legend: {
          orientation: "h",
          x: 0.5,
          xanchor: "center",
          y: -0.22,
          font: { color: "#344a60", size: 11 },
        },
        xaxis: {
          tickangle: -30,
          tickfont: { color: "#445d78", size: 10.5 },
          gridcolor: "rgba(0, 0, 0, 0.06)",
          linecolor: "rgba(0, 0, 0, 0.08)",
          automargin: true,
        },
        yaxis: {
          rangemode: "tozero",
          tickfont: { color: "#445d78", size: 10.5 },
          gridcolor: "rgba(0, 0, 0, 0.05)",
          zerolinecolor: "rgba(0, 0, 0, 0.08)",
        },
      }),
      plotlyConfig,
    );

    el.on("plotly_hover", (evt) => {
      const point = evt?.points?.[0];
      if (!point) return;
      const idx = point.pointNumber;
      const req = Number(required[idx] || 0);
      const pen = Number(pending[idx] || 0);
      const ex = Number(excess[idx] || 0);
      const gap = Math.max(0, pen - ex);
      const coverage =
        req > 0 ? Math.max(0, ((req - pen) / req) * 100) : 0;
      setHoverMeta(
        hoverMeta,
        `${labels[idx] || "Component"} | Coverage ${formatPct(coverage, 1)} | Pending ${formatQty(pen)} | Excess ${formatQty(ex)} | Net Shortfall ${formatQty(gap)}`,
        defaultMeta,
      );

      const highlight = labels.map((_, i) => (i === idx ? 1 : 0.34));
      window.Plotly.restyle(el, { "marker.opacity": [highlight] }, [0]);
      window.Plotly.restyle(el, { "marker.opacity": [highlight] }, [1]);
      window.Plotly.restyle(el, { "marker.opacity": [highlight] }, [2]);
    });

    el.on("plotly_unhover", () => {
      setHoverMeta(hoverMeta, "", defaultMeta);
      window.Plotly.restyle(el, { "marker.opacity": [0.9] }, [0]);
      window.Plotly.restyle(el, { "marker.opacity": [0.9] }, [1]);
      window.Plotly.restyle(el, { "marker.opacity": [0.9] }, [2]);
    });
  }

  function renderPendingExcess(summary) {
    const el = getPlotlyEl("chart-pending-excess");
    if (!el) return;

    const pending = Number(summary.total_pending_qty || 0);
    const excess = Number(summary.total_excess_qty || 0);
    const total = pending + excess;
    const defaultMeta =
      "Hover a segment to compare pending and excess composition";
    const hoverMeta = getHoverMetaEl(el, defaultMeta);
    const pull = [0, 0];
    const labels = ["Pending", "Excess"];
    const values = [pending, excess];

    window.Plotly.react(
      el,
      [
        {
          type: "pie",
          labels,
          values,
          hole: 0.58,
          sort: false,
          marker: {
            colors: [
              "rgba(220, 38, 38, 0.94)",
              "rgba(5, 170, 105, 0.94)",
            ],
            line: { color: "rgba(255,255,255,0.96)", width: 2 },
          },
          pull,
          textinfo: "label+percent",
          textfont: {
            color: "#fff",
            size: 12,
            family: "Inter, sans-serif",
          },
          hovertemplate:
            "<b>%{label}</b><br>Qty: %{value:,}<br>Share: %{percent}<extra></extra>",
        },
      ],
      baseLayout({
        margin: { l: 10, r: 10, t: 10, b: 36 },
        legend: {
          orientation: "h",
          x: 0.5,
          xanchor: "center",
          y: -0.08,
          font: { color: "#344a60", size: 10.5 },
        },
      }),
      plotlyConfig,
    );

    el.on("plotly_hover", (evt) => {
      const point = evt?.points?.[0];
      if (!point) return;
      const idx = point.pointNumber;
      const value = Number(values[idx] || 0);
      const pct = total > 0 ? (value / total) * 100 : 0;
      setHoverMeta(
        hoverMeta,
        `${labels[idx]}: ${formatQty(value)} (${formatPct(pct, 1)}) of total ${formatQty(total)}`,
        defaultMeta,
      );
      const hoverPull = [0, 0];
      hoverPull[idx] = 0.08;
      window.Plotly.restyle(el, { pull: [hoverPull] });
    });

    el.on("plotly_unhover", () => {
      setHoverMeta(hoverMeta, "", defaultMeta);
      window.Plotly.restyle(el, { pull: [pull] });
    });
  }

  function renderTopPending(data) {
    const el = getPlotlyEl("chart-top-pending");
    if (!el) return;

    const labels = (data.labels || []).slice(0, 8);
    const pending = (data.pending || []).slice(0, 8);
    const required = (data.required || []).slice(0, 8);
    const excess = (data.excess || []).slice(0, 8);
    const topMax = Math.max(...pending.map(Number), 1);
    const topTotal = pending.reduce((a, v) => a + Number(v || 0), 0);
    const defaultMeta =
      "Hover a bar to inspect top pending component details";
    const hoverMeta = getHoverMetaEl(el, defaultMeta);
    const colors = pending.map((v) =>
      statusColor(Number(v || 0) / topMax, 0.9),
    );

    window.Plotly.react(
      el,
      [
        {
          type: "bar",
          orientation: "h",
          y: labels,
          x: pending,
          marker: {
            color: colors,
            line: { color: "rgba(255,255,255,0.88)", width: 1.4 },
            opacity: 0.94,
          },
          hovertemplate:
            "<b>%{y}</b><br>Pending: %{x:,}<extra></extra>",
        },
      ],
      baseLayout({
        margin: { l: 110, r: 22, t: 12, b: 30 },
        xaxis: {
          rangemode: "tozero",
          gridcolor: "rgba(0, 0, 0, 0.05)",
          tickfont: { color: "#445d78", size: 10.5 },
          zerolinecolor: "rgba(0, 0, 0, 0.08)",
        },
        yaxis: {
          tickfont: { color: "#344a60", size: 11 },
          automargin: true,
          autorange: "reversed",
        },
      }),
      plotlyConfig,
    );

    el.on("plotly_hover", (evt) => {
      const point = evt?.points?.[0];
      if (!point) return;
      const idx = point.pointNumber;
      const val = Number(pending[idx] || 0);
      const pct = topTotal > 0 ? (val / topTotal) * 100 : 0;
      const req = Number(required[idx] || 0);
      const ex = Number(excess[idx] || 0);
      setHoverMeta(
        hoverMeta,
        `#${idx + 1} ${labels[idx] || "Component"} | Pending ${formatQty(val)} (${formatPct(pct, 1)}) | Required ${formatQty(req)} | Excess ${formatQty(ex)}`,
        defaultMeta,
      );

      const opacities = pending.map((_, i) => (i === idx ? 1 : 0.33));
      window.Plotly.restyle(el, { "marker.opacity": [opacities] });
    });

    el.on("plotly_unhover", () => {
      setHoverMeta(hoverMeta, "", defaultMeta);
      window.Plotly.restyle(el, { "marker.opacity": [0.92] });
    });
  }

  function renderShortfalls(items) {
    const tbody = document.getElementById("shortfalls-body");
    if (!tbody) return;

    if (!items || !items.length) {
      tbody.innerHTML =
        '<tr><td colspan="5" class="reports-table-placeholder">No shortfalls found.</td></tr>';
      return;
    }

    const fmt = (v) =>
      typeof v === "number"
        ? v.toLocaleString(undefined, { maximumFractionDigits: 0 })
        : "\u2013";

    tbody.innerHTML = items
      .map(
        (row) => `<tr>
          <td>${escapeHtml(row.part_no)}</td>
          <td>${escapeHtml(row.part_name)}</td>
          <td class="num">${fmt(row.required_qty)}</td>
          <td class="num num--alert">${fmt(row.pending_qty)}</td>
          <td class="num">${fmt(row.excess_qty)}</td>
        </tr>`,
      )
      .join("");
  }

  function showErrorState() {
    document
      .querySelectorAll(".reports-table-placeholder")
      .forEach((cell) => {
        cell.textContent =
          "Failed to load reports. Please try refreshing.";
      });
  }

  document.addEventListener("DOMContentLoaded", init);
})();
