/**
 * portal_machine.js — Digital Twin Machine Portal Logic
 * Real-time telemetry and task routing for floor operators.
 */

(function() {
  const mid = window.MACHINE_ID;
  let pollInterval;

  async function updatePortal() {
    try {
      const resp = await fetch(`/api/wh/machine_portal/${mid}`);
      if (!resp.ok) throw new Error('API unreachable');
      const data = await resp.json();

      renderDashboard(data);
    } catch (err) {
      console.error('Portal sync error:', err);
      document.getElementById('p-status').textContent = '⚠️ Sync Error';
    }
  }

  function renderDashboard(data) {
    // 1. Header & Machine Info
    document.getElementById('p-machine-name').textContent = data.machine.MCM_Name;
    
    // 2. Active Job Info
    if (data.job) {
      document.getElementById('p-part-no').textContent = data.job.part_no;
      document.getElementById('p-part-name').textContent = data.job.part_name;
      document.getElementById('p-produced').textContent = data.job.produced_qty;
      document.getElementById('p-target').textContent = data.job.target_qty;
      
      const pct = Math.min(100, (data.job.produced_qty / data.job.target_qty) * 100);
      document.getElementById('p-progress-bar').style.width = pct + '%';
      document.getElementById('p-status').textContent = 'Active Production';
      document.querySelector('.portal-pulse').style.background = 'var(--ti-emerald)';
    } else {
      document.getElementById('p-part-no').textContent = 'No Active Job';
      document.getElementById('p-part-name').textContent = 'Machine is currently idle';
      document.getElementById('p-status').textContent = 'Idle';
      document.querySelector('.portal-pulse').style.background = '#6b7280';
      document.getElementById('p-progress-bar').style.width = '0%';
    }

    // 3. Tool Health Dial
    renderToolDial(data.tool);
  }

  function renderToolDial(tool) {
    if (!tool) {
      document.getElementById('dial-container').innerHTML = '<div style="padding-top:80px; text-align:center; color:rgba(255,255,255,0.2)">No Tool Data</div>';
      return;
    }

    document.getElementById('p-tool-no').textContent = tool.tool_no;
    document.getElementById('p-tool-rem').textContent = tool.remaining_strokes.toLocaleString();

    const pct = Math.max(0, Math.min(100, (tool.remaining_strokes / tool.total_life) * 100));
    
    // Color mapping: Emerald -> Amber -> Crimson
    const color = pct > 20 ? (pct > 50 ? '#10b981' : '#f59e0b') : '#ef4444';

    const dialData = [
      {
        type: "indicator",
        mode: "gauge+number",
        value: pct,
        number: { suffix: "%", font: { size: 24, color: "#fff" } },
        gauge: {
          axis: { range: [0, 100], tickwidth: 1, tickcolor: "rgba(255,255,255,0.1)" },
          bar: { color: color },
          bgcolor: "rgba(255,255,255,0.05)",
          borderwidth: 2,
          bordercolor: "rgba(255,255,255,0.1)",
          steps: [
            { range: [0, 20], color: "rgba(239, 68, 68, 0.1)" },
            { range: [20, 50], color: "rgba(245, 158, 11, 0.1)" }
          ],
        }
      }
    ];

    const layout = {
      width: 280,
      height: 220,
      margin: { t: 30, b: 0, l: 30, r: 30 },
      paper_bgcolor: "transparent",
      font: { color: "#fff", family: "Inter" }
    };

    Plotly.newPlot('dial-container', dialData, layout, { staticPlot: true });
  }

  // 4. Button Handlers
  document.getElementById('btn-dpr').addEventListener('click', () => {
    window.location.href = `/app?section=dpr&mid=${mid}`;
  });

  document.getElementById('btn-wh').addEventListener('click', () => {
    window.location.href = "/app";
  });

  // Init
  updatePortal();
  pollInterval = setInterval(updatePortal, 10000); // Sync every 10s

})();
