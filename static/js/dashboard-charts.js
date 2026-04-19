const DashboardCharts = (() => {
  const plotlyConfig = {
    responsive: true,
    displayModeBar: false,
    staticPlot: false,
  };

  function baseLayout(overrides = {}) {
    return {
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      margin: { l: 50, r: 20, t: 14, b: 34 },
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

  function formatQty(v) {
    return Number(v || 0).toLocaleString();
  }

  function truncLabel(s, maxLen = 26) {
    const t = String(s ?? "");
    if (t.length <= maxLen) return t;
    return `${t.slice(0, Math.max(0, maxLen - 1))}\u2026`;
  }

  function getPlotlyEl(id) {
    const el = document.getElementById(id);
    return el && window.Plotly ? el : null;
  }

  /** Primary bar color for RM requirement / balance charts */
  const CHART_BLUE = "rgba(42, 142, 255, 0.88)";

  function renderRmShortageByMaterial(data) {
    const el = getPlotlyEl("chart-rm-shortage-by-material");
    if (!el) return;

    const items = data.rm_shortage_by_material || [];
    if (!items.length) {
      el.innerHTML = '<div class="placeholder">No RM shortage data</div>';
      return;
    }

    const sorted = [...items]
      .sort(
        (a, b) =>
          Math.abs(Number(b.rm_shortage_actual) || 0) -
          Math.abs(Number(a.rm_shortage_actual) || 0),
      )
      .slice(0, 15);
    const labels = sorted.map((r) => truncLabel(r.rm_rawmt_part_no, 20));
    const vals = sorted.map((r) => Number(r.rm_shortage_actual) || 0);
    const colors = vals.map((v) =>
      v < 0
        ? "rgba(220, 38, 38, 0.82)"
        : v > 0
          ? "rgba(5, 150, 105, 0.82)"
          : "rgba(100, 116, 139, 0.65)",
    );
    const hovers = sorted.map((r) => {
      const ca = Number(r.current_acceptedqty) || 0;
      const tpr = Number(r.total_rm_production_requirement) || 0;
      const sh = Number(r.rm_shortage_actual) || 0;
      return (
        `<b>${r.rm_rawmt_part_no || "–"}</b><br>` +
        `Actual stock: ${formatQty(ca)}<br>Total RM Prod Req.: ${formatQty(tpr)}<br>` +
        `<b>Shortage (actual − req.): ${formatQty(sh)}</b>`
      );
    });

    const trace = {
      type: "bar",
      orientation: "h",
      y: labels,
      x: vals,
      marker: { color: colors, cornerradius: 3 },
      hoverinfo: "text",
      hovertext: hovers,
    };

    const layout = baseLayout({
      margin: { l: 120, r: 20, t: 10, b: 40 },
      xaxis: {
        title: "Actual RM Shortage (kgs)",
        gridcolor: "rgba(200,215,230,0.4)",
        zeroline: true,
      },
      yaxis: { automargin: true, tickfont: { size: 10 }, autorange: "reversed" },
      height: Math.min(520, Math.max(280, sorted.length * 28)),
    });

    window.Plotly.newPlot(el, [trace], layout, plotlyConfig);
  }

  function renderTopRmRequirement(data) {
    const el = getPlotlyEl("chart-top-rm-requirement");
    if (!el) return;

    const parts = data.top_rm_parts || [];
    if (!parts.length) {
      el.innerHTML = '<div class="placeholder">No RM data available</div>';
      return;
    }

    const sorted = parts
      .filter((r) => r.rm_requirement !== 0)
      .sort((a, b) => a.rm_requirement - b.rm_requirement);
    const labels = sorted.map((r) => r.part_no);
    const values = sorted.map((r) => r.rm_requirement);
    const hoverText = sorted.map(
      (r) =>
        `<b>${r.part_no}</b><br>RM Req: ${formatQty(r.rm_requirement)}<br>RM: ${r.rm_rawmt_part_no || "–"}`,
    );

    const trace = {
      type: "bar",
      orientation: "h",
      y: labels,
      x: values,
      marker: { color: CHART_BLUE, cornerradius: 4 },
      hoverinfo: "text",
      hovertext: hoverText,
    };

    const layout = baseLayout({
      margin: { l: 100, r: 20, t: 10, b: 34 },
      xaxis: { title: "RM Requirement", gridcolor: "rgba(200,215,230,0.4)" },
      yaxis: { automargin: true },
      height: Math.max(280, sorted.length * 26),
    });

    window.Plotly.newPlot(el, [trace], layout, plotlyConfig);
  }

  function renderRmReqVsInward(data) {
    const el = getPlotlyEl("chart-rm-req-vs-inward");
    if (!el) return;

    const parts = data.top_rm_parts || [];
    if (!parts.length) {
      el.innerHTML = '<div class="placeholder">No RM data available</div>';
      return;
    }

    const MAX_PARTS = 12;
    const scored = parts
      .filter((r) => r.rm_requirement !== 0 || r.rm_inward_accepted_qty > 0)
      .map((r) => ({
        ...r,
        _score: Math.max(
          Math.abs(Number(r.rm_requirement) || 0),
          Number(r.rm_inward_accepted_qty) || 0,
        ),
      }))
      .sort((a, b) => b._score - a._score)
      .slice(0, MAX_PARTS);

    const labels = scored.map((r) => truncLabel(r.part_no, 18));
    const reqValues = scored.map((r) => r.rm_requirement);
    const inwardValues = scored.map((r) => r.rm_inward_accepted_qty);
    const hoverParts = scored.map(
      (r) =>
        `<b>${r.part_no}</b><br>RM Req: ${formatQty(r.rm_requirement)}<br>Inward: ${formatQty(r.rm_inward_accepted_qty)}`,
    );

    const traceReq = {
      type: "bar",
      name: "RM Requirement",
      x: labels,
      y: reqValues,
      marker: { color: "rgba(42, 142, 255, 0.82)", cornerradius: 4 },
      hoverinfo: "text",
      hovertext: hoverParts,
    };

    const traceInward = {
      type: "bar",
      name: "RM Inward (Prior Mo.)",
      x: labels,
      y: inwardValues,
      marker: { color: "rgba(5, 150, 105, 0.78)", cornerradius: 4 },
      hoverinfo: "text",
      hovertext: hoverParts,
    };

    const layout = baseLayout({
      barmode: "group",
      xaxis: {
        tickangle: -35,
        automargin: true,
        tickfont: { size: 10 },
      },
      yaxis: { title: "Quantity", gridcolor: "rgba(200,215,230,0.4)" },
      legend: { orientation: "h", y: 1.12, x: 0.5, xanchor: "center" },
      margin: { l: 56, r: 16, t: 36, b: 120 },
    });

    window.Plotly.newPlot(el, [traceReq, traceInward], layout, plotlyConfig);
  }

  function renderMaterialMix(data) {
    const el = getPlotlyEl("chart-material-mix");
    if (!el) return;

    const mix = data.material_mix || {};
    const labels = mix.labels || [];
    const values = mix.values || [];

    if (!labels.length) {
      el.innerHTML = '<div class="placeholder">No material data</div>';
      return;
    }

    const pairs = labels
      .map((lab, i) => ({
        label: String(lab || ""),
        value: Math.abs(Number(values[i]) || 0),
      }))
      .filter((p) => p.value > 0 && p.label)
      .sort((a, b) => b.value - a.value);

    const MAX_BARS = 12;
    let rows = pairs.slice(0, MAX_BARS);
    const rest = pairs.slice(MAX_BARS);
    if (rest.length) {
      const otherSum = rest.reduce((s, p) => s + p.value, 0);
      if (otherSum > 0) {
        rows = rows.concat([
          {
            label: `Other (${rest.length} materials)`,
            value: otherSum,
            fullLabels: rest.map((p) => p.label),
          },
        ]);
      }
    }

    const yDisp = rows.map((r) => truncLabel(r.label, 22));
    const xVals = rows.map((r) => r.value);
    const hoverText = rows.map((r) => {
      if (r.fullLabels && r.fullLabels.length) {
        const sample = r.fullLabels.slice(0, 8).join(", ");
        const more =
          r.fullLabels.length > 8 ? `, \u2026 (+${r.fullLabels.length - 8} more)` : "";
        return `<b>Other materials</b><br>Total RM Req: ${formatQty(r.value)}<br><span style="font-size:10px">${sample}${more}</span>`;
      }
      return `<b>${r.label}</b><br>RM Req (sum): ${formatQty(r.value)}`;
    });

    const trace = {
      type: "bar",
      orientation: "h",
      y: yDisp,
      x: xVals,
      marker: { color: "rgba(42, 142, 255, 0.85)", cornerradius: 3 },
      hoverinfo: "text",
      hovertext: hoverText,
    };

    const layout = baseLayout({
      margin: { l: 160, r: 24, t: 8, b: 48 },
      xaxis: {
        title: "RM requirement (rolled up)",
        gridcolor: "rgba(200,215,230,0.45)",
        automargin: true,
      },
      yaxis: {
        automargin: true,
        tickfont: { size: 10 },
        autorange: "reversed",
      },
      height: Math.min(520, Math.max(280, rows.length * 30)),
    });

    window.Plotly.newPlot(el, [trace], layout, plotlyConfig);
  }

  function renderMaterialStockVsReq(data) {
    const el = getPlotlyEl("chart-rm-stock-vs-req");
    if (!el) return;

    const items = data.material_stock_vs_req || [];
    if (!items.length) {
      el.innerHTML = '<div class="placeholder">No material data</div>';
      return;
    }

    const labels = items.map((r) => truncLabel(r.rm_code, 18));
    const stock = items.map((r) => Number(r.current_stock) || 0);
    const req = items.map((r) => Number(r.total_production_req) || 0);

    const tStock = {
      type: "bar",
      name: "Current stock avail.",
      x: labels,
      y: stock,
      marker: { color: "rgba(5, 150, 105, 0.82)", cornerradius: 3 },
    };
    const tReq = {
      type: "bar",
      name: "Total RM prod. req.",
      x: labels,
      y: req,
      marker: { color: "rgba(42, 142, 255, 0.85)", cornerradius: 3 },
    };

    const layout = baseLayout({
      barmode: "group",
      xaxis: { tickangle: -35, automargin: true, tickfont: { size: 10 } },
      yaxis: { title: "Quantity (kgs)", gridcolor: "rgba(200,215,230,0.4)" },
      legend: { orientation: "h", y: 1.1, x: 0.5, xanchor: "center" },
      margin: { l: 52, r: 16, t: 40, b: 120 },
    });

    window.Plotly.newPlot(el, [tStock, tReq], layout, plotlyConfig);
  }

  function renderMaterialRmUtilized(data) {
    const el = getPlotlyEl("chart-material-rm-utilized");
    if (!el) return;

    const mu = data.material_utilized || {};
    const labels = (mu.labels || []).map((l) => truncLabel(l, 22));
    const values = mu.values || [];

    if (!labels.length) {
      el.innerHTML = '<div class="placeholder">No utilization data</div>';
      return;
    }

    const trace = {
      type: "bar",
      orientation: "h",
      y: labels,
      x: values,
      marker: { color: "rgba(234, 179, 8, 0.88)", cornerradius: 3 },
      hovertemplate: "<b>%{y}</b><br>Total RM utilized: %{x:,.2f}<extra></extra>",
    };

    const layout = baseLayout({
      margin: { l: 150, r: 20, t: 10, b: 40 },
      xaxis: { title: "Total RM utilized (kgs)", gridcolor: "rgba(200,215,230,0.4)" },
      yaxis: { automargin: true, tickfont: { size: 10 }, autorange: "reversed" },
      height: Math.min(480, Math.max(260, labels.length * 28)),
    });

    window.Plotly.newPlot(el, [trace], layout, plotlyConfig);
  }

  function renderRmShortageActual(data) {
    const el = getPlotlyEl("chart-rm-shortage-actual");
    if (!el) return;

    const parts = data.rm_shortage_by_part || [];
    if (!parts.length) {
      el.innerHTML = '<div class="placeholder">No RM shortage data</div>';
      return;
    }

    const sorted = [...parts]
      .sort(
        (a, b) =>
          Math.abs(Number(b.rm_shortage_actual) || 0) -
          Math.abs(Number(a.rm_shortage_actual) || 0),
      )
      .slice(0, 15);
    const labels = sorted.map((r) => truncLabel(r.part_no, 16));
    const vals = sorted.map((r) => Number(r.rm_shortage_actual) || 0);
    const colors = vals.map((v) =>
      v < 0
        ? "rgba(220, 38, 38, 0.82)"
        : v > 0
          ? "rgba(5, 150, 105, 0.82)"
          : "rgba(100, 116, 139, 0.65)",
    );
    const hovers = sorted.map((r) => {
      const ca = Number(r.current_acceptedqty) || 0;
      const tpr = Number(r.rm_requirement) || 0;
      const sh = Number(r.rm_shortage_actual) || 0;
      return (
        `<b>${r.part_no}</b><br>RM: ${r.rm_rawmt_part_no || "–"}<br>` +
        `Actual stock: ${formatQty(ca)}<br>RM Prod Req: ${formatQty(tpr)}<br>` +
        `<b>Shortage (actual − req.): ${formatQty(sh)}</b>`
      );
    });

    const trace = {
      type: "bar",
      orientation: "h",
      y: labels,
      x: vals,
      marker: { color: colors, cornerradius: 3 },
      hoverinfo: "text",
      hovertext: hovers,
    };

    const layout = baseLayout({
      margin: { l: 100, r: 20, t: 10, b: 40 },
      xaxis: {
        title: "Actual RM Shortage By Parts (kgs)",
        gridcolor: "rgba(200,215,230,0.4)",
        zeroline: true,
      },
      yaxis: { automargin: true, tickfont: { size: 10 }, autorange: "reversed" },
      height: Math.min(520, Math.max(280, sorted.length * 28)),
    });

    window.Plotly.newPlot(el, [trace], layout, plotlyConfig);
  }

  function renderTopRmBalance(data) {
    const el = getPlotlyEl("chart-top-rm-balance");
    if (!el) return;

    const parts = data.top_rm_balance_parts || [];
    if (!parts.length) {
      el.innerHTML = '<div class="placeholder">No balance data</div>';
      return;
    }

    const sorted = [...parts]
      .sort((a, b) => Math.abs(b.rm_balance_kgs) - Math.abs(a.rm_balance_kgs))
      .slice(0, 15);
    const labels = sorted.map((r) => truncLabel(r.part_no, 16));
    const vals = sorted.map((r) => Number(r.rm_balance_kgs) || 0);
    const hovers = sorted.map(
      (r) =>
        `<b>${r.part_no}</b><br>RM: ${r.rm_rawmt_part_no || "–"}<br>Balance: ${formatQty(r.rm_balance_kgs)} kgs<br>RM req: ${formatQty(r.rm_requirement)}`,
    );

    const trace = {
      type: "bar",
      orientation: "h",
      y: labels,
      x: vals,
      marker: { color: CHART_BLUE, cornerradius: 3 },
      hoverinfo: "text",
      hovertext: hovers,
    };

    const layout = baseLayout({
      margin: { l: 100, r: 20, t: 10, b: 40 },
      xaxis: { title: "RM balance (kgs)", gridcolor: "rgba(200,215,230,0.4)", zeroline: true },
      yaxis: { automargin: true, tickfont: { size: 10 }, autorange: "reversed" },
      height: Math.min(520, Math.max(280, sorted.length * 28)),
    });

    window.Plotly.newPlot(el, [trace], layout, plotlyConfig);
  }

  async function load() {
    if (!window.Plotly) return;
    try {
      const data = await ApiClient.getRmChartData(20);
      renderRmShortageByMaterial(data);
      renderTopRmRequirement(data);
      renderRmReqVsInward(data);
      renderMaterialMix(data);
      renderMaterialStockVsReq(data);
      renderMaterialRmUtilized(data);
      renderTopRmBalance(data);
      renderRmShortageActual(data);
    } catch (err) {
      console.error("Dashboard charts error:", err);
    }
  }

  const RM_CHART_IDS = [
    "chart-rm-shortage-by-material",
    "chart-top-rm-requirement",
    "chart-rm-req-vs-inward",
    "chart-material-mix",
    "chart-rm-stock-vs-req",
    "chart-material-rm-utilized",
    "chart-top-rm-balance",
    "chart-rm-shortage-actual",
  ];

  let resizeTimer;
  window.addEventListener("resize", () => {
    if (!window.Plotly) return;
    if (resizeTimer) clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      RM_CHART_IDS.forEach((id) => {
        const el = document.getElementById(id);
        if (el) window.Plotly.Plots.resize(el);
      });
    }, 140);
  });

  return { load };
})();
