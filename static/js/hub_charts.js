/* ═══════════════════════════════════════════════════════════════════════════
   HUB_CHARTS.JS — Dark-themed Plotly chart renderer for Overview section
   ═══════════════════════════════════════════════════════════════════════════ */

const HubCharts = (() => {
  const CFG = { responsive: true, displayModeBar: false };

  function base(overrides = {}) {
    const isLight = typeof Hub !== 'undefined' && Hub.getTheme && Hub.getTheme() === 'light';
    const textColor = isLight ? '#334155' : '#94a3b8';
    const gridColor = isLight ? 'rgba(0,0,0,0.06)' : 'rgba(148,163,184,0.08)';
    const zeroColor = isLight ? 'rgba(0,0,0,0.12)' : 'rgba(148,163,184,0.15)';
    const hoverBg = isLight ? '#ffffff' : '#1e293b';
    const hoverBorder = isLight ? '#e2e8f0' : '#334155';
    const hoverText = isLight ? '#0f172a' : '#f1f5f9';
    return {
      paper_bgcolor: 'transparent',
      plot_bgcolor: 'transparent',
      margin: { l: 50, r: 20, t: 14, b: 34 },
      font: { family: "'Inter', sans-serif", size: 11, color: textColor },
      hoverlabel: { bgcolor: hoverBg, bordercolor: hoverBorder, font: { color: hoverText, size: 11 } },
      xaxis: { gridcolor: gridColor, zerolinecolor: zeroColor },
      yaxis: { gridcolor: gridColor, zerolinecolor: zeroColor },
      ...overrides,
    };
  }

  function fmtQty(v) { return Number(v || 0).toLocaleString('en-IN'); }
  function fmtShortageKg(v) {
    const n = Math.abs(Number(v) || 0);
    return n.toLocaleString('en-IN', { maximumFractionDigits: 0 });
  }
  function trunc(s, m = 26) { const t = String(s ?? ''); return t.length <= m ? t : t.slice(0, m - 1) + '\u2026'; }
  function chartTextColor() {
    return (typeof Hub !== 'undefined' && Hub.getTheme && Hub.getTheme() === 'light') ? '#334155' : '#94a3b8';
  }
  function el(id) { const e = document.getElementById(id); return e && window.Plotly ? e : null; }

  const BLUE = 'rgba(59,130,246,0.85)';
  const GREEN = 'rgba(16,185,129,0.82)';
  const RED = 'rgba(239,68,68,0.82)';
  const AMBER = 'rgba(245,158,11,0.85)';
  const DIM = 'rgba(100,116,139,0.5)';

  let lastRmChartData = null;

  function wireRmShortageMode(data) {
    const sel = document.getElementById('chart-rm-shortage-mode');
    if (!sel || sel.dataset.wired === '1') return;
    sel.dataset.wired = '1';
    sel.addEventListener('change', () => {
      if (lastRmChartData) renderRmShortageByMaterial(lastRmChartData, sel.value);
    });
  }

  // ── RM Charts (from dashboard-charts.js, dark-themed) ──────────────
  function renderRmShortageByMaterial(data, mode) {
    lastRmChartData = data;
    wireRmShortageMode(data);
    const e = el('chart-rm-shortage-by-material'); if (!e) return;
    const items = data.rm_shortage_by_material || [];
    const shortages = items.filter(r => Number(r.rm_shortage_actual) < 0);
    if (!shortages.length) {
      e.innerHTML = '<div class="ti-placeholder">No actual RM shortages (stock meets or exceeds requirement)</div>';
      return;
    }

    const showAll = mode === 'all';
    const sorted = [...shortages].sort(
      (a, b) => Number(a.rm_shortage_actual) - Number(b.rm_shortage_actual)
    );
    const limited = showAll ? sorted : sorted.slice(0, 15);

    const displayVals = limited.map(r => Math.abs(Number(r.rm_shortage_actual) || 0));
    const hovers = limited.map(r => `<b>${r.rm_rawmt_part_no || '–'}</b><br>Stock: ${fmtQty(r.current_acceptedqty)} kgs<br>Required: ${fmtQty(r.total_rm_production_requirement)} kgs<br><b>Shortage: ${fmtQty(r.rm_shortage_actual)} kgs</b>`);

    if (window.Plotly && window.Plotly.purge) window.Plotly.purge(e);

    const barTrace = {
      type: 'bar',
      marker: {
        color: 'rgba(239, 68, 68, 0.88)',
        line: { color: 'rgba(185, 28, 28, 0.45)', width: 1 },
        cornerradius: 4,
      },
      text: displayVals.map(fmtShortageKg),
      textposition: 'outside',
      textfont: { size: 11, color: chartTextColor() },
      cliponaxis: false,
      hoverinfo: 'text',
      hovertext: hovers,
    };

    const yAxisCommon = {
      title: 'Shortage (kgs)',
      rangemode: 'tozero',
      tickformat: ',.0f',
      gridcolor: 'rgba(148,163,184,0.08)',
      zeroline: true,
      zerolinecolor: 'rgba(148,163,184,0.15)',
    };

    if (showAll) {
      const labels = limited.map(r => trunc(r.rm_rawmt_part_no, 28));
      Plotly.newPlot(e, [{
        ...barTrace,
        orientation: 'h',
        y: labels,
        x: displayVals,
      }], base({
        margin: { l: 148, r: 48, t: 52, b: 24 },
        xaxis: { ...yAxisCommon, side: 'top' },
        yaxis: { automargin: true, tickfont: { size: 11 }, autorange: 'reversed' },
        height: Math.min(900, Math.max(360, limited.length * 30)),
        bargap: 0.28,
      }), CFG);
    } else {
      const labels = limited.map(r => trunc(r.rm_rawmt_part_no, 14));
      Plotly.newPlot(e, [{
        ...barTrace,
        x: labels,
        y: displayVals,
      }], base({
        margin: { l: 56, r: 24, t: 28, b: 88 },
        yaxis: yAxisCommon,
        xaxis: {
          automargin: true,
          tickfont: { size: 11 },
          tickangle: 0,
        },
        height: 400,
        bargap: 0.35,
      }), CFG);
    }
  }

  function renderTopRmRequirement(data) {
    const e = el('chart-top-rm-requirement'); if (!e) return;
    const parts = (data.top_rm_parts||[]).filter(r=>r.rm_requirement!==0).sort((a,b)=>a.rm_requirement-b.rm_requirement);
    if (!parts.length) { e.innerHTML = '<div class="ti-placeholder">No RM data</div>'; return; }
    Plotly.newPlot(e, [{ type:'bar', orientation:'h', y:parts.map(r=>r.part_no), x:parts.map(r=>r.rm_requirement), marker:{color:BLUE,cornerradius:4}, hoverinfo:'text', hovertext:parts.map(r=>`<b>${r.part_no}</b><br>RM Req: ${fmtQty(r.rm_requirement)}<br>RM: ${r.rm_rawmt_part_no||'–'}`) }],
      base({ margin:{l:100,r:20,t:10,b:34}, xaxis:{title:'RM Requirement',gridcolor:'rgba(148,163,184,0.08)'}, yaxis:{automargin:true}, height:Math.max(250,parts.length*26) }), CFG);
  }

  function renderRmReqVsInward(data) {
    const e = el('chart-rm-req-vs-inward'); if (!e) return;
    const parts = (data.top_rm_parts||[]).filter(r=>r.rm_requirement!==0||r.rm_inward_accepted_qty>0).sort((a,b)=>Math.max(Math.abs(b.rm_requirement),b.rm_inward_accepted_qty||0)-Math.max(Math.abs(a.rm_requirement),a.rm_inward_accepted_qty||0)).slice(0,12);
    if (!parts.length) { e.innerHTML = '<div class="ti-placeholder">No RM data</div>'; return; }
    const labels = parts.map(r=>trunc(r.part_no,18));
    Plotly.newPlot(e, [
      { type:'bar', name:'RM Requirement', x:labels, y:parts.map(r=>r.rm_requirement), marker:{color:BLUE,cornerradius:4} },
      { type:'bar', name:'RM Inward', x:labels, y:parts.map(r=>r.rm_inward_accepted_qty), marker:{color:GREEN,cornerradius:4} }
    ], base({ barmode:'group', xaxis:{tickangle:-35,automargin:true,tickfont:{size:10}}, yaxis:{title:'Quantity',gridcolor:'rgba(148,163,184,0.08)'}, legend:{orientation:'h',y:1.12,x:0.5,xanchor:'center',font:{color:'#94a3b8'}}, margin:{l:56,r:16,t:36,b:120} }), CFG);
  }

  function renderMaterialMix(data) {
    const e = el('chart-material-mix'); if (!e) return;
    const mix = data.material_mix||{}; const labels = mix.labels||[]; const values = mix.values||[];
    if (!labels.length) { e.innerHTML = '<div class="ti-placeholder">No material data</div>'; return; }
    const pairs = labels.map((l,i)=>({label:String(l||''),value:Math.abs(Number(values[i])||0)})).filter(p=>p.value>0&&p.label).sort((a,b)=>b.value-a.value);
    let rows = pairs.slice(0,12); const rest = pairs.slice(12);
    if (rest.length) { const s = rest.reduce((a,p)=>a+p.value,0); if (s>0) rows.push({label:`Other (${rest.length})`,value:s}); }
    Plotly.newPlot(e, [{ type:'bar', orientation:'h', y:rows.map(r=>trunc(r.label,22)), x:rows.map(r=>r.value), marker:{color:BLUE,cornerradius:3}, hovertemplate:'<b>%{y}</b><br>RM Req: %{x:,.0f}<extra></extra>' }],
      base({ margin:{l:160,r:24,t:8,b:48}, xaxis:{title:'RM requirement',gridcolor:'rgba(148,163,184,0.08)'}, yaxis:{automargin:true,tickfont:{size:10},autorange:'reversed'}, height:Math.min(480,Math.max(250,rows.length*30)) }), CFG);
  }

  function renderStockVsReq(data) {
    const e = el('chart-rm-stock-vs-req'); if (!e) return;
    const items = data.material_stock_vs_req||[];
    if (!items.length) { e.innerHTML = '<div class="ti-placeholder">No data</div>'; return; }
    const labels = items.map(r=>trunc(r.rm_code,18));
    Plotly.newPlot(e, [
      { type:'bar', name:'Current Stock', x:labels, y:items.map(r=>Number(r.current_stock)||0), marker:{color:GREEN,cornerradius:3} },
      { type:'bar', name:'Production Req.', x:labels, y:items.map(r=>Number(r.total_production_req)||0), marker:{color:BLUE,cornerradius:3} }
    ], base({ barmode:'group', xaxis:{tickangle:-35,automargin:true,tickfont:{size:10}}, yaxis:{title:'Qty (kgs)',gridcolor:'rgba(148,163,184,0.08)'}, legend:{orientation:'h',y:1.1,x:0.5,xanchor:'center',font:{color:'#94a3b8'}}, margin:{l:52,r:16,t:40,b:120} }), CFG);
  }

  function renderRmUtilized(data) {
    const e = el('chart-material-rm-utilized'); if (!e) return;
    const mu = data.material_utilized||{}; const labels = (mu.labels||[]).map(l=>trunc(l,22)); const values = mu.values||[];
    if (!labels.length) { e.innerHTML = '<div class="ti-placeholder">No utilization data</div>'; return; }
    Plotly.newPlot(e, [{ type:'bar', orientation:'h', y:labels, x:values, marker:{color:AMBER,cornerradius:3}, hovertemplate:'<b>%{y}</b><br>Utilized: %{x:,.2f}<extra></extra>' }],
      base({ margin:{l:150,r:20,t:10,b:40}, xaxis:{title:'RM utilized (kgs)',gridcolor:'rgba(148,163,184,0.08)'}, yaxis:{automargin:true,tickfont:{size:10},autorange:'reversed'}, height:Math.min(450,Math.max(250,labels.length*28)) }), CFG);
  }

  function renderRmShortageActual(data) {
    const e = el('chart-rm-shortage-actual'); if (!e) return;
    const parts = data.rm_shortage_by_part||[];
    if (!parts.length) { e.innerHTML = '<div class="ti-placeholder">No data</div>'; return; }
    const sorted = [...parts].sort((a,b)=>Math.abs(Number(b.rm_shortage_actual)||0)-Math.abs(Number(a.rm_shortage_actual)||0)).slice(0,15);
    const vals = sorted.map(r=>Number(r.rm_shortage_actual)||0);
    const colors = vals.map(v=>v<0?RED:v>0?GREEN:DIM);
    Plotly.newPlot(e, [{ type:'bar', orientation:'h', y:sorted.map(r=>trunc(r.part_no,16)), x:vals, marker:{color:colors,cornerradius:3}, hoverinfo:'text', hovertext:sorted.map(r=>`<b>${r.part_no}</b><br>RM: ${r.rm_rawmt_part_no||'–'}<br>Shortage: ${fmtQty(r.rm_shortage_actual)}`) }],
      base({ margin:{l:100,r:20,t:10,b:40}, xaxis:{title:'Shortage By Parts (kgs)',gridcolor:'rgba(148,163,184,0.08)',zeroline:true,zerolinecolor:'rgba(148,163,184,0.15)'}, yaxis:{automargin:true,tickfont:{size:10},autorange:'reversed'}, height:Math.min(480,Math.max(250,sorted.length*28)) }), CFG);
  }

  function renderTopRmBalance(data) {
    const e = el('chart-top-rm-balance'); if (!e) return;
    const parts = data.top_rm_balance_parts||[];
    if (!parts.length) { e.innerHTML = '<div class="ti-placeholder">No balance data</div>'; return; }
    const sorted = [...parts].sort((a,b)=>Math.abs(b.rm_balance_kgs)-Math.abs(a.rm_balance_kgs)).slice(0,15);
    Plotly.newPlot(e, [{ type:'bar', orientation:'h', y:sorted.map(r=>trunc(r.part_no,16)), x:sorted.map(r=>r.rm_balance_kgs||0), marker:{color:BLUE,cornerradius:3}, hoverinfo:'text', hovertext:sorted.map(r=>`<b>${r.part_no}</b><br>Balance: ${fmtQty(r.rm_balance_kgs)} kgs`) }],
      base({ margin:{l:100,r:20,t:10,b:40}, xaxis:{title:'RM Balance (kgs)',gridcolor:'rgba(148,163,184,0.08)',zeroline:true,zerolinecolor:'rgba(148,163,184,0.15)'}, yaxis:{automargin:true,tickfont:{size:10},autorange:'reversed'}, height:Math.min(480,Math.max(250,sorted.length*28)) }), CFG);
  }

  // ── Reports charts (production vs req, completion, pending treemap) ─
  function renderProductionVsReq(data) {
    const e = el('chart-production-vs-req'); if (!e) return;
    const items = data.items || [];
    if (!items.length) { e.innerHTML = '<div class="ti-placeholder">No production data</div>'; return; }
    const labels = items.map(r => trunc(r.part_no, 16));
    Plotly.newPlot(e, [
      { type:'bar', name:'Pending', y:labels, x:items.map(r=>r.pending_qty), orientation:'h', marker:{color:RED,cornerradius:3} },
      { type:'bar', name:'Excess', y:labels, x:items.map(r=>r.excess_qty), orientation:'h', marker:{color:GREEN,cornerradius:3} }
    ], base({ barmode:'group', margin:{l:100,r:20,t:10,b:40}, xaxis:{title:'Qty',gridcolor:'rgba(148,163,184,0.08)'}, yaxis:{automargin:true,tickfont:{size:10},autorange:'reversed'}, legend:{orientation:'h',y:1.1,x:0.5,xanchor:'center',font:{color:'#94a3b8'}}, height:Math.min(500,Math.max(300,items.length*24)) }), CFG);
  }

  function renderCompletionBuckets(data) {
    const e = el('chart-completion-buckets'); if (!e) return;
    const buckets = data.buckets || [];
    if (!buckets.length) { e.innerHTML = '<div class="ti-placeholder">No data</div>'; return; }
    const labels = buckets.map(b => b.label);
    const values = buckets.map(b => b.count);
    const colors = ['#ef4444', '#f59e0b', '#3b82f6', '#10b981', '#6366f1'];
    Plotly.newPlot(e, [{ type:'pie', labels, values, marker:{colors:colors.slice(0, labels.length)}, hole:0.45, textfont:{color:'#e2e8f0',size:11}, hovertemplate:'<b>%{label}</b><br>Count: %{value}<br>%{percent}<extra></extra>' }],
      base({ margin:{l:20,r:20,t:10,b:10}, legend:{font:{color:'#94a3b8',size:11}}, height:320 }), CFG);
  }

  function renderPendingTreemap(data) {
    const e = el('chart-pending-treemap'); if (!e) return;
    const items = data.items || [];
    if (!items.length) { e.innerHTML = '<div class="ti-placeholder">No pending data</div>'; return; }
    Plotly.newPlot(e, [{ type:'treemap', labels:items.map(i=>i.part_no), parents:items.map(()=>''), values:items.map(i=>Math.abs(i.pending_qty||0)), textfont:{color:'#fff',size:11}, marker:{colorscale:[[0,'#1e40af'],[0.5,'#3b82f6'],[1,'#93c5fd']], line:{width:1, color:'#0f172a'}} }],
      base({ margin:{l:4,r:4,t:4,b:4}, height:340 }), CFG);
  }

  function renderPendingExcess(summary) {
    const e = el('chart-pending-excess'); if (!e) return;
    const pending = Number(summary.total_pending_qty || 0);
    const excess = Number(summary.total_excess_qty || 0);
    if (pending === 0 && excess === 0) { e.innerHTML = '<div class="ti-placeholder">No balance data</div>'; return; }
    Plotly.newPlot(e, [{ 
      type:'pie', 
      labels:['Pending', 'Excess'], 
      values:[pending, excess], 
      marker:{colors:[RED, GREEN], line:{color:'rgba(255,255,255,0.1)', width:1}}, 
      hole:0.5, 
      textfont:{color:'#e2e8f0',size:11}, 
      hovertemplate:'<b>%{label}</b><br>Qty: %{value:,.0f}<br>%{percent}<extra></extra>' 
    }], base({ margin:{l:10,r:10,t:10,b:40}, legend:{orientation:'h',y:-0.1,x:0.5,xanchor:'center'}, height:300 }), CFG);
  }

  function renderTopPending(data) {
    const e = el('chart-top-pending'); if (!e) return;
    const items = (data.items || []).slice(0, 8);
    if (!items.length) { e.innerHTML = '<div class="ti-placeholder">No data</div>'; return; }
    const topMax = Math.max(...items.map(i => i.pending_qty), 1);
    Plotly.newPlot(e, [{ 
      type:'bar', 
      orientation:'h', 
      y:items.map(i => trunc(i.part_no, 14)), 
      x:items.map(i => i.pending_qty), 
      marker:{ 
        color: items.map(i => i.pending_qty / topMax > 0.8 ? RED : AMBER),
        cornerradius:4 
      }, 
      hovertemplate:'<b>%{y}</b><br>Pending: %{x:,.0f}<extra></extra>' 
    }], base({ 
      margin:{l:100,r:20,t:10,b:34}, 
      xaxis:{title:'Pending Qty',gridcolor:'rgba(148,163,184,0.08)'}, 
      yaxis:{automargin:true, autorange:'reversed'}, 
      height:300 
    }), CFG);
  }

  // ── PM Status donut ────────────────────────────────────────────────
  function renderPmDonut(data) {
    const e = el('chart-pm-donut'); if (!e) return;
    if (!Array.isArray(data) || !data.length) { e.innerHTML = '<div class="ti-placeholder">No PM data</div>'; return; }
    const safe = data.filter(d => d.pmPercentage < 80).length;
    const warn = data.filter(d => d.pmPercentage >= 80 && d.pmPercentage < 100).length;
    const crit = data.filter(d => d.pmPercentage >= 100).length;
    Plotly.newPlot(e, [{ type:'pie', labels:['Safe','Warning','Critical'], values:[safe,warn,crit], marker:{colors:[GREEN,AMBER,RED]}, hole:0.55, textfont:{color:'#e2e8f0',size:12}, hovertemplate:'<b>%{label}</b>: %{value} tools<extra></extra>' }],
      base({ margin:{l:10,r:10,t:10,b:10}, legend:{font:{color:'#94a3b8',size:11},orientation:'h',y:-0.05,x:0.5,xanchor:'center'}, height:280 }), CFG);
  }

  // ── Cumulative production vs target (climbing) ─────────────────────
  function fmtCr(v) {
    const cr = (Number(v) || 0) / 1e7;
    if (!Number.isFinite(cr)) return '0';
    if (Math.abs(cr) >= 10) return cr.toFixed(1);
    if (Math.abs(cr) >= 1) return cr.toFixed(2);
    return cr.toFixed(3);
  }

  function renderDailyProdVsTarget(data) {
    const e = el('chart-daily-prod-vs-target'); if (!e) return;
    const days = data.days || [];
    if (!days.length) {
      e.innerHTML = '<div class="ti-placeholder">No daily production data for this month</div>';
      return;
    }

    const scheduledTotal = Number(data.scheduledTotal) || 0;
    const avgDaily = Number(data.avgDailyTarget) || 0;
    const daysInMonth = Number(data.daysInMonth) || days.length;
    const asOfDay = Math.max(0, Math.min(Number(data.asOfDay) || 0, days.length));
    const CR = 1e7;

    const subtitle = document.getElementById('chart-daily-prod-subtitle');
    if (subtitle) {
      subtitle.textContent =
        `Schedule ${fmtQty(scheduledTotal)} (${fmtCr(scheduledTotal)} Cr) ÷ ${daysInMonth} days · target ${fmtCr(avgDaily)} Cr/day`;
    }

    const labels = days.map(d => Number(d.day));
    const targetCum = days.map((d) =>
      Math.min(avgDaily * Number(d.day), scheduledTotal) / CR
    );

    let cumProduced = 0;
    const actualX = [];
    const producedCum = [];
    for (let i = 0; i < asOfDay; i++) {
      cumProduced += Number(days[i].produced) || 0;
      actualX.push(Number(days[i].day));
      producedCum.push(cumProduced / CR);
    }

    const yMax = Math.max(
      scheduledTotal / CR,
      ...(producedCum.length ? producedCum : [0]),
      0.1
    ) * 1.08;

    const traces = [
      {
        type: 'scatter',
        mode: 'lines',
        name: 'Required',
        x: labels,
        y: targetCum,
        line: { color: 'rgba(245,158,11,0.95)', width: 2.5, dash: 'dot' },
        hovertemplate: '<b>Required</b><br>Day %{x}<br>%{customdata}<extra></extra>',
        customdata: days.map((d) => {
          const v = Math.min(avgDaily * Number(d.day), scheduledTotal);
          return `${fmtQty(v)} (${fmtCr(v)} Cr)`;
        }),
      },
    ];
    if (producedCum.length) {
      traces.push({
        type: 'scatter',
        mode: 'lines+markers',
        name: 'Actual',
        x: actualX,
        y: producedCum,
        fill: 'tozeroy',
        fillcolor: 'rgba(59,130,246,0.12)',
        line: { color: 'rgba(59,130,246,0.95)', width: 3, shape: 'spline' },
        marker: {
          size: 7,
          color: '#fff',
          line: { color: 'rgba(59,130,246,0.95)', width: 2 },
        },
        hovertemplate: '<b>Actual</b><br>Day %{x}<br>%{customdata}<extra></extra>',
        customdata: producedCum.map((crVal) => {
          const v = crVal * CR;
          return `${fmtQty(v)} (${fmtCr(v)} Cr)`;
        }),
      });
    }

    Plotly.newPlot(e, traces, base({
      margin: { l: 52, r: 28, t: 20, b: 56 },
      legend: {
        orientation: 'h',
        y: -0.22,
        x: 0.5,
        xanchor: 'center',
        font: { size: 12 },
      },
      xaxis: {
        title: { text: 'Day of month', standoff: 8, font: { size: 11 } },
        tickmode: 'array',
        tickvals: Array.from({ length: daysInMonth }, (_, i) => i + 1)
          .filter((d) => d === 1 || d === daysInMonth || d % 5 === 0),
        range: [0.5, daysInMonth + 0.5],
        showgrid: true,
        gridcolor: 'rgba(148,163,184,0.1)',
        zeroline: false,
      },
      yaxis: {
        title: { text: 'Crores (Cr)', standoff: 10, font: { size: 11 } },
        rangemode: 'tozero',
        range: [0, yMax],
        ticksuffix: ' Cr',
        tickformat: '.1f',
        showgrid: true,
        gridcolor: 'rgba(148,163,184,0.12)',
        zeroline: true,
        zerolinecolor: 'rgba(148,163,184,0.2)',
      },
      height: 380,
      hovermode: 'x unified',
      shapes: scheduledTotal > 0 ? [{
        type: 'line',
        xref: 'paper', x0: 0, x1: 1,
        yref: 'y', y0: scheduledTotal / CR, y1: scheduledTotal / CR,
        line: { color: 'rgba(148,163,184,0.35)', width: 1, dash: 'dash' },
      }] : [],
      annotations: scheduledTotal > 0 ? [{
        xref: 'paper', x: 1, xanchor: 'right',
        y: scheduledTotal / CR,
        yanchor: 'bottom',
        text: `Schedule ${fmtCr(scheduledTotal)} Cr`,
        showarrow: false,
        font: { size: 10, color: chartTextColor() },
        bgcolor: (typeof Hub !== 'undefined' && Hub.getTheme && Hub.getTheme() === 'light')
          ? 'rgba(255,255,255,0.75)'
          : 'rgba(15,23,42,0.45)',
        borderpad: 3,
      }] : [],
    }), CFG);
  }

  // ── Load all overview charts ───────────────────────────────────────
  async function loadOverview() {
    if (!window.Plotly) return;
    try {
      const rmData = await Hub.api.getRmChartData(20);
      renderRmShortageByMaterial(rmData);
      renderTopRmRequirement(rmData);
      renderRmReqVsInward(rmData);
      renderMaterialMix(rmData);
      renderStockVsReq(rmData);
      renderRmUtilized(rmData);
      renderTopRmBalance(rmData);
      renderRmShortageActual(rmData);
    } catch (err) { console.error('RM charts error:', err); }

    try {
      const dailyVsTarget = await Hub.api.getDailyProdVsTarget();
      renderDailyProdVsTarget(dailyVsTarget);
    } catch (err) { console.error('Daily prod vs target chart error:', err); }

    try {
      const pvr = await Hub.api.getProductionVsReq(15);
      renderProductionVsReq(pvr);
      renderTopPending(pvr); // Restored
    } catch (err) { console.error('PvR chart error:', err); }

    try {
      const summary = await Hub.api.getReportSummary();
      renderPendingExcess(summary); // Restored
    } catch (err) { console.error('Summary chart error:', err); }

    try {
      const cb = await Hub.api.getCompletionBuckets();
      renderCompletionBuckets(cb);
    } catch (err) { console.error('Buckets chart error:', err); }

    try {
      const tm = await Hub.api.getPendingTreemap(30);
      renderPendingTreemap(tm);
    } catch (err) { console.error('Treemap error:', err); }

    try {
      const pm = await Hub.api.get('/api/pm/status?mode=all');
      renderPmDonut(pm);
    } catch (err) { console.error('PM donut error:', err); }
  }

  // Resize handler
  let resizeTimer;
  window.addEventListener('resize', () => {
    if (!window.Plotly) return;
    if (resizeTimer) clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      document.querySelectorAll('.js-plotly-plot').forEach(e => Plotly.Plots.resize(e));
    }, 150);
  });

  // Recolor charts when theme changes
  function recolor(theme) {
    const textColor = theme === 'light' ? '#334155' : '#94a3b8';
    const gridColor = theme === 'light' ? 'rgba(0,0,0,0.06)' : 'rgba(148,163,184,0.08)';
    document.querySelectorAll('.js-plotly-plot').forEach(e => {
      try {
        Plotly.relayout(e, {
          'font.color': textColor,
          'xaxis.gridcolor': gridColor,
          'yaxis.gridcolor': gridColor,
          'legend.font.color': textColor,
        });
      } catch { /* skip */ }
    });
  }

  return { loadOverview, renderPmDonut, renderProductionVsReq, renderCompletionBuckets, renderPendingTreemap, recolor };
})();
