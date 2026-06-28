const ApiClient = (() => {
  const BASE = "/api";

  function buildQuery(params) {
    const searchParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value === undefined || value === null || value === "") return;
      searchParams.set(key, String(value));
    });
    return searchParams.toString();
  }

  async function handleResponse(res) {
    if (res.status === 401) {
      const next = encodeURIComponent(
        `${window.location.pathname}${window.location.search}`,
      );
      window.location.href = `/login?next=${next}`;
      throw new Error("Session expired");
    }
    if (!res.ok) {
      let msg = `Request failed: ${res.status}`;
      try {
        const errBody = await res.json();
        if (errBody && errBody.error) msg = String(errBody.error);
      } catch (_) {
        /* ignore */
      }
      throw new Error(msg);
    }
    return res.json();
  }

  async function getDashboardRows(params) {
    const qs = buildQuery(params);
    const res = await fetch(`${BASE}/dashboard-rows?${qs}`);
    return handleResponse(res);
  }

  async function refreshDashboard() {
    const res = await fetch(`${BASE}/dashboard-refresh`, { method: "POST" });
    return handleResponse(res);
  }

  async function updateBufferConfig(partNo, bufferQty) {
    const res = await fetch(
      `${BASE}/buffer-config/${encodeURIComponent(partNo)}`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ buffer_qty: bufferQty }),
      },
    );
    return handleResponse(res);
  }

  function buildExportUrl(params) {
    const qs = buildQuery(params);
    return `${BASE}/export?${qs}`;
  }

  async function getReportSummary() {
    const res = await fetch(`${BASE}/reports/summary`);
    return handleResponse(res);
  }

  async function getProductionVsRequirement(limit = 15) {
    const qs = buildQuery({ limit });
    const res = await fetch(`${BASE}/reports/production-vs-requirement?${qs}`);
    return handleResponse(res);
  }

  async function getCompletionBuckets() {
    const res = await fetch(`${BASE}/reports/completion-buckets`);
    return handleResponse(res);
  }

  async function getTopShortfalls(limit = 20) {
    const qs = buildQuery({ limit });
    const res = await fetch(`${BASE}/reports/top-shortfalls?${qs}`);
    return handleResponse(res);
  }

  async function getPendingTreemap(limit = 40) {
    const qs = buildQuery({ limit });
    const res = await fetch(`${BASE}/reports/pending-treemap?${qs}`);
    return handleResponse(res);
  }

  async function getRmChartData(limit = 20) {
    const qs = buildQuery({ limit });
    const res = await fetch(`${BASE}/dashboard/rm-charts?${qs}`);
    return handleResponse(res);
  }

  async function getDprVersion(date) {
    const qs = buildQuery({ date });
    const res = await fetch(`${BASE}/dpr/version?${qs}`);
    return handleResponse(res);
  }

  async function getMachineDprToday(token, date) {
    const qs = buildQuery(date ? { date } : {});
    const suffix = qs ? `?${qs}` : "";
    const res = await fetch(`${BASE}/dpr/machine/${encodeURIComponent(token)}/today${suffix}`);
    return handleResponse(res);
  }

  async function putMachineProduced(token, payload) {
    const res = await fetch(`${BASE}/dpr/machine/${encodeURIComponent(token)}/produced`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return handleResponse(res);
  }

  return {
    getDashboardRows,
    updateBufferConfig,
    refreshDashboard,
    buildExportUrl,
    getReportSummary,
    getProductionVsRequirement,
    getCompletionBuckets,
    getTopShortfalls,
    getPendingTreemap,
    getRmChartData,
    getDprVersion,
    getMachineDprToday,
    putMachineProduced,
  };
})();
