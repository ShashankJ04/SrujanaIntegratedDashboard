/* ═══════════════════════════════════════════════════════════════════════════
   HUB.JS — Central Operations Hub
   Unified API client, SPA router, sidebar, search, utilities
   ═══════════════════════════════════════════════════════════════════════════ */

const Hub = (() => {
  // ── State ──────────────────────────────────────────────────────────────
  let currentSection = 'overview';
  let sidebarCollapsed = localStorage.getItem('hub_sidebar') === 'collapsed';
  let currentTheme = localStorage.getItem('hub_theme') || 'light';

  // ── API Client ─────────────────────────────────────────────────────────
  const api = {
    async fetch(path, options = {}) {
      const res = await fetch(path, {
        headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
        credentials: 'same-origin',
        ...options,
      });
      if (res.status === 401) {
        window.location.href = '/login';
        throw new Error('Session expired');
      }
      if (res.status === 403) {
        let msg = 'Access denied';
        try {
          const j = await res.json();
          msg = j.message || j.error || msg;
        } catch { /* ignore */ }
        throw new Error(msg);
      }
      if (!res.ok) {
        let msg;
        try {
          const j = await res.json();
          msg = j.message || j.error;
        } catch { msg = res.statusText; }
        throw new Error(msg || `Error ${res.status}`);
      }
      const ct = res.headers.get('content-type') || '';
      return ct.includes('json') ? res.json() : res;
    },
    get(path)         { return this.fetch(path); },
    post(path, body)  { return this.fetch(path, { method: 'POST', body: JSON.stringify(body) }); },
    patch(path, body) { return this.fetch(path, { method: 'PATCH', body: JSON.stringify(body) }); },
    put(path, body)   { return this.fetch(path, { method: 'PUT', body: JSON.stringify(body) }); },
    del(path)         { return this.fetch(path, { method: 'DELETE' }); },
    async postForm(path, formData) {
      const res = await fetch(path, { method: 'POST', credentials: 'same-origin', body: formData });
      if (res.status === 401) { window.location.href = '/login'; throw new Error('Session expired'); }
      if (!res.ok) { let m; try { m = (await res.json()).message; } catch { m = res.statusText; } throw new Error(m || `Error ${res.status}`); }
      return res.json();
    },
    async download(path, body, fileName) {
      const res = await fetch(path, {
        method: body ? 'POST' : 'GET',
        headers: body ? { 'Content-Type': 'application/json' } : {},
        credentials: 'same-origin',
        body: body ? JSON.stringify(body) : undefined,
      });
      if (res.status === 401) {
        window.location.href = '/login';
        throw new Error('Session expired');
      }
      if (res.status === 403) {
        let msg = 'Access denied';
        try {
          const j = await res.json();
          msg = j.message || j.error || msg;
        } catch { /* ignore */ }
        throw new Error(msg);
      }
      if (!res.ok) throw new Error(`Download error: ${res.status}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = fileName || 'download.xlsx';
      document.body.appendChild(a); a.click();
      setTimeout(() => { document.body.removeChild(a); URL.revokeObjectURL(url); }, 100);
    },
    // Legacy ApiClient compatibility
    buildQuery(params) {
      const sp = new URLSearchParams();
      Object.entries(params).forEach(([k, v]) => { if (v != null && v !== '') sp.set(k, String(v)); });
      return sp.toString();
    },
    buildExportUrl(params) { return `/api/export?${this.buildQuery(params)}`; },
    getColumns()          { return this.get('/api/columns'); },
    getRows(params)       { return this.get(`/api/rows?${this.buildQuery(params)}`); },
    getDashboardRows(p)   { return this.get(`/api/dashboard-rows?${this.buildQuery(p)}`); },
    refreshDashboard()    { return this.post('/api/dashboard-refresh'); },
    updateBufferConfig(pn, q) { return this.put(`/api/buffer-config/${encodeURIComponent(pn)}`, { buffer_qty: q }); },
    getReportSummary()    { return this.get('/api/reports/summary'); },
    getProductionVsReq(l) { return this.get(`/api/reports/production-vs-requirement?limit=${l || 15}`); },
    getCompletionBuckets(){ return this.get('/api/reports/completion-buckets'); },
    getTopShortfalls(l)   { return this.get(`/api/reports/top-shortfalls?limit=${l || 20}`); },
    getPendingTreemap(l)  { return this.get(`/api/reports/pending-treemap?limit=${l || 40}`); },
    getRmChartData(l)     { return this.get(`/api/dashboard/rm-charts?limit=${l || 20}`); },
  };

  // ── Utilities ──────────────────────────────────────────────────────────
  const utils = {
    formatIndian(n) {
      if (n == null || isNaN(n)) return '0';
      n = Math.round(Number(n));
      const neg = n < 0; const abs = Math.abs(n); const s = String(abs);
      if (s.length <= 3) return (neg ? '-' : '') + s;
      const last3 = s.slice(-3); let rest = s.slice(0, -3);
      const parts = [];
      while (rest.length > 2) { parts.unshift(rest.slice(-2)); rest = rest.slice(0, -2); }
      if (rest) parts.unshift(rest);
      return (neg ? '-' : '') + parts.join(',') + ',' + last3;
    },
    formatCompact(n) {
      if (n == null || isNaN(n)) return '0';
      n = Number(n); const abs = Math.abs(n); const neg = n < 0 ? '-' : '';
      if (abs >= 1_00_00_000) return neg + (abs / 1_00_00_000).toFixed(1).replace(/\.0$/, '') + 'Cr';
      if (abs >= 1_00_000)    return neg + (abs / 1_00_000).toFixed(1).replace(/\.0$/, '') + 'L';
      if (abs >= 1_000)       return neg + (abs / 1_000).toFixed(1).replace(/\.0$/, '') + 'K';
      return neg + String(Math.round(abs));
    },
    snackbar(msg, dur = 4000) {
      let el = document.getElementById('ti-snackbar');
      if (!el) { el = document.createElement('div'); el.id = 'ti-snackbar'; el.className = 'ti-snackbar'; document.body.appendChild(el); }
      el.textContent = msg; el.classList.add('show');
      clearTimeout(el._t); el._t = setTimeout(() => el.classList.remove('show'), dur);
    },
    varianceChip(val, opts = {}) {
      const r = Math.round(val * 100) / 100;
      const el = document.createElement('span');
      el.className = 'ti-chip ';
      if (r === 0) { el.className += 'ti-chip-neutral'; el.textContent = '0'; }
      else if (r > 0) {
        el.className += opts.invert ? 'ti-chip-danger' : 'ti-chip-success';
        el.innerHTML = '▲ ' + (opts.fmt ? Math.abs(r).toFixed(2) : this.formatIndian(Math.abs(r)));
      } else {
        el.className += opts.invert ? 'ti-chip-success' : 'ti-chip-danger';
        el.innerHTML = '▼ ' + (opts.fmt ? Math.abs(r).toFixed(2) : this.formatIndian(Math.abs(r)));
      }
      return el;
    },
    $(sel) { return document.querySelector(sel); },
    $$(sel) { return document.querySelectorAll(sel); },
  };

  // ── SPA Router ─────────────────────────────────────────────────────
  /** Hub RM Variance section — off while under development; set true to restore nav + deep links */
  const RM_VARIANCE_HUB_ENABLED = false;

  const SECTIONS = {
    overview:    { title: 'Overview',        icon: '📊' },
    production:  { title: 'Production',      icon: '🏭' },
    inventory:   { title: 'Inventory',       icon: '📦' },
    maintenance: { title: 'Maintenance',     icon: '🔧' },
    'rm-variance':{ title: 'RM Variance',    icon: '📈' },
    'rm-correction':{ title: 'RM Correction', icon: '✏️' },
    dpr:         { title: 'Daily Production Review',             icon: '📝' },
    'dispatch-calendar': { title: 'Dispatch Calendar', icon: '📅' },
    'production-calendar': { title: 'Production Calendar', icon: '🏗️' },
    executive:   { title: 'Executive View',  icon: '🎯' },
    reports:     { title: 'Reports',         icon: '📋' },
    'reports-manage': { title: 'Report management', icon: '🗂️' },
    admin:       { title: 'Administration',  icon: '⚙️' },
  };
  const _accessRaw = (window.CURRENT_PERMISSIONS && window.CURRENT_PERMISSIONS.access) || [];
  const ACCESS = new Set(_accessRaw);
  /* Legacy RBAC stored "reports" — server maps to rept; mirror here if cookie/session still has old shape */
  if (ACCESS.has('reports')) ACCESS.add('rept');
  const PLUS_ACCESS = new Set((window.CURRENT_PERMISSIONS && window.CURRENT_PERMISSIONS.plusAccess) || []);

  function canAccessSection(section) {
    if (section === 'overview') return true;
    if (section === 'admin') return Number(window.CURRENT_USER?.userId || 0) === 43;
    if (section === 'production') return ACCESS.has('production');
    if (section === 'dpr') return ACCESS.has('rept');
    if (section === 'dispatch-calendar') return ACCESS.has('rept');
    if (section === 'production-calendar') return ACCESS.has('rept');
    if (section === 'inventory') return ACCESS.has('rept');
    if (section === 'rm-variance') return RM_VARIANCE_HUB_ENABLED && ACCESS.has('rm_variance');
    if (section === 'rm-correction') return ACCESS.has('rm_correction') || ACCESS.has('rm_variance');
    if (section === 'executive') return ACCESS.has('executive');
    if (section === 'reports') return ACCESS.has('rept');
    if (section === 'reports-manage') return PLUS_ACCESS.has('rept_plus');
    if (section === 'maintenance') {
      return ACCESS.has('tools') || ACCESS.has('preventive_maintenance') || ACCESS.has('life_report');
    }
    return true;
  }

  function getDefaultSection() {
    const order = ['overview', 'production', 'maintenance', 'executive', 'reports', 'admin'];
    return order.find(canAccessSection) || 'overview';
  }

  function applyNavVisibility() {
    utils.$$('.ti-nav-link[data-section]').forEach(link => {
      const section = link.dataset.section;
      const navItem = link.closest('.ti-nav-item');
      if (!section || !navItem) return;
      const allowed = canAccessSection(section);
      navItem.style.display = allowed ? '' : 'none';
      link.setAttribute('aria-hidden', allowed ? 'false' : 'true');
      if (!allowed) link.classList.remove('active');
    });
  }

  function getReportIdFromLocation() {
    return new URLSearchParams(window.location.search).get('report');
  }

  function highlightReportInTree(reportId) {
    document.querySelectorAll('.ti-nav-report').forEach((el) => {
      el.classList.toggle('ti-nav-report--active', Boolean(reportId && el.dataset.reportId === String(reportId)));
    });
  }

  function expandReportGroupForReportId(reportId) {
    if (reportId == null || reportId === '') return;
    const rid = String(reportId);
    document.querySelectorAll('.ti-nav-report').forEach(el => {
      if (el.dataset.reportId !== rid) return;
      const ul = el.closest('.ti-nav-tree-reports');
      if (!ul) return;
      ul.hidden = false;
      const head = ul.previousElementSibling;
      if (head && head.classList.contains('ti-nav-tree-group-head')) {
        head.setAttribute('aria-expanded', 'true');
        const chev = head.querySelector('.ti-nav-tree-group-chev');
        if (chev) chev.textContent = '▾';
      }
    });
  }

  let reportsFlyoutHideTimer = null;

  function hideReportsFlyoutImmediate() {
    clearTimeout(reportsFlyoutHideTimer);
    reportsFlyoutHideTimer = null;
    const flyout = document.getElementById('ti-reports-flyout');
    if (!flyout) return;
    flyout.classList.remove('is-visible');
    flyout.hidden = true;
    flyout.setAttribute('aria-hidden', 'true');
  }

  function positionReportsFlyout() {
    const wrap = document.getElementById('ti-nav-reports-wrap');
    const flyout = document.getElementById('ti-reports-flyout');
    if (!wrap || !flyout) return;
    const r = wrap.getBoundingClientRect();
    const gap = 6;
    flyout.style.top = `${Math.max(8, r.top)}px`;
    flyout.style.left = `${r.right + gap}px`;
    requestAnimationFrame(() => {
      const fr = flyout.getBoundingClientRect();
      const vw = window.innerWidth;
      const vh = window.innerHeight;
      let left = parseFloat(flyout.style.left) || 0;
      let top = parseFloat(flyout.style.top) || 0;
      if (fr.right > vw - 8) {
        left = Math.max(8, r.left - fr.width - gap);
        flyout.style.left = `${left}px`;
      }
      if (fr.bottom > vh - 8) {
        top = Math.max(8, vh - fr.height - 8);
        flyout.style.top = `${top}px`;
      }
    });
  }

  function showReportsFlyout() {
    const sidebar = utils.$('.ti-sidebar');
    const flyout = document.getElementById('ti-reports-flyout');
    if (!sidebar || !flyout) return;
    if (!sidebar.classList.contains('collapsed')) return;
    if (window.innerWidth <= 768) return;
    clearTimeout(reportsFlyoutHideTimer);
    reportsFlyoutHideTimer = null;
    positionReportsFlyout();
    flyout.hidden = false;
    flyout.setAttribute('aria-hidden', 'false');
    flyout.classList.add('is-visible');
  }

  function scheduleHideReportsFlyout() {
    clearTimeout(reportsFlyoutHideTimer);
    reportsFlyoutHideTimer = setTimeout(() => hideReportsFlyoutImmediate(), 180);
  }

  function initReportsFlyoutHover() {
    const wrap = document.getElementById('ti-nav-reports-wrap');
    const flyout = document.getElementById('ti-reports-flyout');
    if (!wrap || !flyout) return;

    wrap.addEventListener('mouseenter', () => {
      if (utils.$('.ti-sidebar')?.classList.contains('collapsed')) showReportsFlyout();
    });
    wrap.addEventListener('mouseleave', scheduleHideReportsFlyout);
    flyout.addEventListener('mouseenter', () => {
      clearTimeout(reportsFlyoutHideTimer);
    });
    flyout.addEventListener('mouseleave', scheduleHideReportsFlyout);

    const reposition = () => {
      if (flyout.classList.contains('is-visible')) positionReportsFlyout();
    };
    window.addEventListener('scroll', reposition, true);
    window.addEventListener('resize', reposition);
  }

  function buildReportGroupElement(g, reports) {
    const groupLi = document.createElement('li');
    groupLi.className = 'ti-nav-tree-group';

    const head = document.createElement('button');
    head.type = 'button';
    head.className = 'ti-nav-tree-group-head';
    head.setAttribute('aria-expanded', 'false');
    const chev = document.createElement('span');
    chev.className = 'ti-nav-tree-group-chev';
    chev.setAttribute('aria-hidden', 'true');
    chev.textContent = '▸';
    const title = document.createElement('span');
    title.className = 'ti-nav-tree-group-title';
    title.textContent = g.name;
    const countEl = document.createElement('span');
    countEl.className = 'ti-nav-tree-group-count';
    countEl.textContent = String(reports.length);
    head.appendChild(chev);
    head.appendChild(title);
    head.appendChild(countEl);

    const ul = document.createElement('ul');
    ul.className = 'ti-nav-tree-reports';
    ul.hidden = true;

    head.addEventListener('click', () => {
      const open = ul.hidden;
      ul.hidden = !open;
      head.setAttribute('aria-expanded', open ? 'true' : 'false');
      chev.textContent = open ? '▾' : '▸';
    });

    reports.forEach(r => {
      const rli = document.createElement('li');
      rli.className = 'ti-nav-report';
      rli.dataset.reportId = r.id;
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'ti-nav-report-btn';
      btn.textContent = r.name;
      btn.title = r.name;
      btn.addEventListener('click', e => {
        e.preventDefault();
        hideReportsFlyoutImmediate();
        navigate('reports', { reportId: r.id });
      });
      rli.appendChild(btn);
      ul.appendChild(rli);
    });

    groupLi.appendChild(head);
    groupLi.appendChild(ul);
    return groupLi;
  }

  function expandReportsNav(open) {
    const tree = document.getElementById('ti-nav-reports-tree');
    const chev = document.getElementById('ti-nav-reports-chevron');
    if (!tree) return;
    tree.hidden = !open;
    if (chev) {
      chev.setAttribute('aria-expanded', open ? 'true' : 'false');
      chev.textContent = open ? '▾' : '▸';
    }
  }

  function updateNavActive(section) {
    utils.$$('.ti-nav-link[data-section]').forEach(link => {
      link.classList.toggle('active', link.dataset.section === section);
    });
    if (section !== 'reports') {
      highlightReportInTree(null);
    }
  }

  async function loadReportsSidebarTree() {
    const tree = document.getElementById('ti-nav-reports-tree');
    const flyoutInner = document.getElementById('ti-reports-flyout-inner');
    if (!tree && !flyoutInner) return;
    try {
      const groups = await api.get('/api/reports/groups');
      const bundles = [];
      for (const g of groups) {
        const reports = await api.get(`/api/reports/reports?groupId=${encodeURIComponent(g.id)}&pinnedOnly=1`);
        if (reports.length) bundles.push({ g, reports });
      }
      const fill = (container) => {
        if (!container) return;
        container.innerHTML = '';
        for (const { g, reports } of bundles) {
          container.appendChild(buildReportGroupElement(g, reports));
        }
      };
      fill(tree);
      fill(flyoutInner);
      const rid = getReportIdFromLocation();
      highlightReportInTree(rid);
      expandReportGroupForReportId(rid);
      updateNavActive(currentSection);
      if (typeof window.__hubReportsRefreshPicker === 'function') window.__hubReportsRefreshPicker();
    } catch (err) {
      console.error('Reports nav tree:', err);
    }
  }

  function setSectionTitle(text) {
    const t = String(text || '');
    utils.$$('.ti-section-title').forEach((el) => { el.textContent = t; });
  }

  async function navigate(section, opts = {}) {
    if (!SECTIONS[section]) section = 'overview';
    if (!canAccessSection(section)) section = getDefaultSection();
    if (section !== 'dpr') document.body.classList.remove('dpr-fullscreen-mode');
    const skipHistory = opts.skipHistory === true;

    let reportId = null;
    if (section === 'reports') {
      if ('reportId' in opts) {
        reportId = opts.reportId == null || opts.reportId === '' ? null : String(opts.reportId);
      } else {
        const r = getReportIdFromLocation();
        reportId = r ? String(r) : null;
      }
    }

    const contentEl = utils.$('#hub-content');
    const fastReports =
      currentSection === 'reports' &&
      section === 'reports' &&
      contentEl?.querySelector('#section-reports') &&
      'reportId' in opts &&
      !opts.forceReload;

    if (fastReports) {
      currentSection = section;
      if (!skipHistory) {
        let url = '/app?section=reports';
        if (reportId) url += '&report=' + encodeURIComponent(reportId);
        history.pushState({ section: 'reports', reportId: reportId || undefined }, '', url);
      }
      if (window.__hubReportsOpenReport) {
        await window.__hubReportsOpenReport(reportId || null);
      }
      updateNavActive(section);
      highlightReportInTree(reportId);
      expandReportGroupForReportId(reportId);
      expandReportsNav(true);
      setSectionTitle(SECTIONS[section].title);
      if (window.innerWidth <= 768) closeMobileSidebar();
      return;
    }

    currentSection = section;

    if (!skipHistory) {
      let url = section === 'overview' ? '/app' : `/app?section=${encodeURIComponent(section)}`;
      if (section === 'reports' && reportId) {
        url += '&report=' + encodeURIComponent(reportId);
      }
      if (section === 'inventory' && opts.rowFilter) {
        url += '&rowFilter=' + encodeURIComponent(opts.rowFilter);
      }
      const st = { section, reportId: section === 'reports' ? (reportId || undefined) : undefined, rowFilter: section === 'inventory' ? (opts.rowFilter || undefined) : undefined };
      const cur = window.location.pathname + window.location.search;
      if (cur === url) {
        history.replaceState(st, '', url);
      } else {
        history.pushState(st, '', url);
      }
    }

    updateNavActive(section);
    setSectionTitle(SECTIONS[section].title);

    if (section === 'reports') expandReportsNav(true);

    const content = utils.$('#hub-content');
    if (!content) return;
    content.innerHTML = '<div class="ti-loading"><div class="ti-spinner"></div></div>';

    try {
      const res = await fetch(`/app/section/${section}`, { credentials: 'same-origin' });
      if (res.status === 401) { window.location.href = '/login'; return; }
      if (!res.ok) throw new Error(`Failed to load section: ${res.status}`);
      const html = await res.text();
      content.innerHTML = html;
      content.classList.remove('ti-section-enter');
      void content.offsetWidth; // reflow
      content.classList.add('ti-section-enter');

      content.querySelectorAll('script').forEach(oldScript => {
        const newScript = document.createElement('script');
        if (oldScript.src) { newScript.src = oldScript.src; }
        else { newScript.textContent = oldScript.textContent; }
        oldScript.replaceWith(newScript);
      });

      if (section === 'dispatch-calendar' && typeof window.DispatchCalendarPage?.init === 'function') {
        window.DispatchCalendarPage.init();
      }

      if (section === 'production-calendar' && typeof window.ProductionCalendarPage?.init === 'function') {
        window.ProductionCalendarPage.init();
      }

      if (section === 'reports') {
        const rid = getReportIdFromLocation();
        highlightReportInTree(rid);
        expandReportGroupForReportId(rid);
      }
    } catch (err) {
      console.error(err);
      content.innerHTML = `<div class="ti-empty"><div class="ti-empty-icon">⚠️</div><div class="ti-empty-text">Failed to load ${SECTIONS[section]?.title || section}</div></div>`;
    }

    if (window.innerWidth <= 768) closeMobileSidebar();
  }

  // ── Sidebar ────────────────────────────────────────────────────────
  function toggleSidebar() {
    const sidebar = utils.$('.ti-sidebar');
    if (!sidebar) return;
    sidebarCollapsed = !sidebarCollapsed;
    sidebar.classList.toggle('collapsed', sidebarCollapsed);
    localStorage.setItem('hub_sidebar', sidebarCollapsed ? 'collapsed' : 'expanded');
    if (!sidebarCollapsed) hideReportsFlyoutImmediate();
  }

  function closeMobileSidebar() {
    const sb = utils.$('.ti-sidebar');
    if (sb) {
      sb.classList.remove('mobile-open');
      if (window.innerWidth > 768 && localStorage.getItem('hub_sidebar') === 'collapsed') {
        sb.classList.add('collapsed');
      }
    }
    utils.$('.ti-mobile-overlay')?.classList.remove('open');
  }

  function openMobileSidebar() {
    const sb = utils.$('.ti-sidebar');
    if (sb) {
      sb.classList.add('mobile-open');
      sb.classList.remove('collapsed');
    }
    utils.$('.ti-mobile-overlay')?.classList.add('open');
  }

  // ── System Pulse (LED + Ticker) ──────────────────────────────────
  async function updatePulse() {
    // 1. Update Status Indicator (LED)
    const bar = utils.$('.ti-pulse-bar');
    if (bar) {
      try {
        const pmData = await api.get('/api/pm/status?threshold=80&mode=above');
        if (Array.isArray(pmData)) {
          const critical = pmData.filter(d => d.pmPercentage >= 100).length;
          const warning = pmData.filter(d => d.pmPercentage >= 80 && d.pmPercentage < 100).length;
          if (critical > 0) bar.className = 'ti-pulse-bar critical';
          else if (warning > 0) bar.className = 'ti-pulse-bar warning';
          else bar.className = 'ti-pulse-bar';
        }
      } catch (err) { /* silent */ }
    }

    // 2. Update Pulse Ticker (Text) — ERP production + DPR snapshot (see /api/hub/pulse)
    const tickerA = document.getElementById('pulse-ticker-a');
    const tickerB = document.getElementById('pulse-ticker-b');
    const tickerTrack = document.getElementById('pulse-ticker-track');
    if (tickerA && tickerB && tickerTrack) {
      let line = '';
      try {
        const data = await api.get('/api/hub/pulse');
        if (Array.isArray(data) && data.length > 0) {
          line = data.map(d => `• ${d.text}`).join('   |   ');
        } else {
          line =
            '• No recent ticker items — production/DPR data will appear here as activity is logged.';
        }
      } catch (err) {
        line = '• Pulse feed unavailable — check connection and try refreshing.';
      }
      tickerA.textContent = line;
      tickerB.textContent = line;
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          const half = tickerTrack.scrollWidth / 2;
          if (!half || !Number.isFinite(half)) return;
          const pxPerSec = 42;
          const sec = Math.max(18, Math.min(140, half / pxPerSec));
          tickerTrack.style.setProperty('--ti-pulse-dur', `${sec}s`);
          tickerTrack.classList.remove('ti-pulse-ticker-track--run');
          void tickerTrack.offsetWidth;
          tickerTrack.classList.add('ti-pulse-ticker-track--run');
        });
      });
    }
  }

  // ── Command Palette (Ctrl+K) ──────────────────────────────────────
  function initCmdPal() {
    document.addEventListener('keydown', e => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        toggleCmdPal();
      }
      if (e.key === 'Escape') closeCmdPal();
    });

    const overlay = utils.$('.ti-cmdpal-overlay');
    if (overlay) overlay.addEventListener('click', e => { if (e.target === overlay) closeCmdPal(); });

    const input = utils.$('.ti-cmdpal-input');
    if (input) input.addEventListener('input', () => filterCmdPal(input.value));
  }

  function toggleCmdPal() {
    const overlay = utils.$('.ti-cmdpal-overlay');
    if (!overlay) return;
    const isOpen = overlay.classList.contains('open');
    if (isOpen) { closeCmdPal(); } else { openCmdPal(); }
  }

  function openCmdPal() {
    const overlay = utils.$('.ti-cmdpal-overlay');
    if (!overlay) return;
    overlay.classList.add('open');
    const input = utils.$('.ti-cmdpal-input');
    if (input) { input.value = ''; input.focus(); }
    renderCmdPalItems('');
  }

  function closeCmdPal() {
    utils.$('.ti-cmdpal-overlay')?.classList.remove('open');
  }


  function renderCmdPalItems(query) {
    const container = utils.$('.ti-cmdpal-results');
    if (!container) return;

    const items = Object.entries(SECTIONS)
      .filter(([key]) => canAccessSection(key))
      .map(([key, info]) => ({
      key, label: info.title, icon: info.icon, type: 'section'
      }));

    const q = query.toLowerCase();
    const filtered = q ? items.filter(i => i.label.toLowerCase().includes(q)) : items;

    container.innerHTML = filtered.map(i => `
      <div class="ti-cmdpal-item" data-action="section" data-key="${i.key}">
        <span class="ti-cmdpal-item-icon">${i.icon}</span>
        <span class="ti-cmdpal-item-label">${i.label}</span>
        <span class="ti-cmdpal-item-hint">Navigate</span>
      </div>
    `).join('') || '<div class="ti-placeholder">No results</div>';

    container.querySelectorAll('.ti-cmdpal-item').forEach(el => {
      el.addEventListener('click', () => {
        navigate(el.dataset.key);
        closeCmdPal();
      });
    });
  }

  async function filterCmdPal(query) { 
    if (query.length < 1) {
      renderCmdPalItems(query);
      return;
    }
    
    // Global search fetch
    const container = utils.$('.ti-cmdpal-results');
    if (!container) return;
    
    try {
      const results = await api.get(`/api/search/global?q=${encodeURIComponent(query)}`);
      if (results.length === 0) {
        container.innerHTML = '<div class="ti-placeholder">No global results found</div>';
        return;
      }
      
      const iconByType = {
        Part: '🏭',
        Tag: '📦',
        Order: '🧾',
        Report: '📋',
        'DPR Machine': '🛠️',
        'DPR Part': '📝',
      };

      container.innerHTML = results.map(i => `
        <div class="ti-cmdpal-item" data-type="${i.type}" data-link="${i.link}">
          <span class="ti-cmdpal-item-icon">${iconByType[i.type] || '⚙️'}</span>
          <span class="ti-cmdpal-item-label">${i.label}</span>
          <span class="ti-cmdpal-item-hint">${i.type}</span>
        </div>
      `).join('');

      container.querySelectorAll('.ti-cmdpal-item').forEach(el => {
        el.addEventListener('click', () => {
          if (el.dataset.link.startsWith('/app')) {
            const url = new URL(el.dataset.link, window.location.origin);
            const section = url.searchParams.get('section') || 'overview';
            const reportId = url.searchParams.get('report');
            if (section === 'reports' && reportId) {
              navigate('reports', { reportId, forceReload: true });
            } else {
              const rowFilter = url.searchParams.get('rowFilter');
              navigate(section, { rowFilter: rowFilter || undefined });
            }
          } else {
            window.location.href = el.dataset.link;
          }
          closeCmdPal();
        });
      });
    } catch (err) {
      console.error('Global search failed:', err);
    }
  }

  // ── Init ────────────────────────────────────────────────────────────
  function init() {
    // Sidebar collapse state
    const sidebar = utils.$('.ti-sidebar');
    if (sidebar && sidebarCollapsed) sidebar.classList.add('collapsed');

    applyNavVisibility();

    // Nav click handlers
    utils.$$('.ti-nav-link[data-section]').forEach(link => {
      link.addEventListener('click', e => {
        e.preventDefault();
        navigate(link.dataset.section);
      });
    });

    const chev = document.getElementById('ti-nav-reports-chevron');
    const tree = document.getElementById('ti-nav-reports-tree');
    if (chev && tree) {
      chev.addEventListener('click', e => {
        e.preventDefault();
        e.stopPropagation();
        expandReportsNav(tree.hidden);
      });
    }
    initReportsFlyoutHover();
    loadReportsSidebarTree();

    // Collapse button
    utils.$('.ti-collapse-btn')?.addEventListener('click', toggleSidebar);

    // Mobile toggle
    utils.$('.ti-sidebar-mobile-toggle')?.addEventListener('click', openMobileSidebar);
    utils.$('.ti-mobile-overlay')?.addEventListener('click', closeMobileSidebar);

    // Search trigger
    utils.$('.ti-search-trigger')?.addEventListener('click', openCmdPal);

    // Command palette
    initCmdPal();

    window.addEventListener('popstate', () => {
      const params = new URLSearchParams(window.location.search);
      const rowFilter = params.get('rowFilter');
      navigate(getInitialSection(), { skipHistory: true, rowFilter: rowFilter || undefined });
    });

    // Initial section
    const initParams = new URLSearchParams(window.location.search);
    const initRowFilter = initParams.get('rowFilter');
    const section = getInitialSection();
    navigate(section, { rowFilter: initRowFilter || undefined });

    // Pulse bar update
    updatePulse();
    setInterval(updatePulse, 60000); // every 60s

    // Theme toggle
    initTheme();
  }

  function initTheme() {
    applyTheme(currentTheme);
    const btn = utils.$('#theme-toggle');
    if (btn) btn.addEventListener('click', () => {
      currentTheme = currentTheme === 'dark' ? 'light' : 'dark';
      localStorage.setItem('hub_theme', currentTheme);
      applyTheme(currentTheme);
    });
  }

  function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    const btn = utils.$('#theme-toggle');
    if (btn) btn.textContent = theme === 'dark' ? '\u2600\uFE0F' : '\uD83C\uDF19';
    // Re-render any visible Plotly charts with the new text color
    if (typeof HubCharts !== 'undefined' && HubCharts.recolor) HubCharts.recolor(theme);
  }

  function getInitialSection() {
    const params = new URLSearchParams(window.location.search);
    const requested = params.get('section') || 'overview';
    return canAccessSection(requested) ? requested : getDefaultSection();
  }

  // ── Public API ─────────────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', init);

  return {
    api,
    utils,
    navigate,
    updatePulse,
    SECTIONS,
    getTheme: () => currentTheme,
    refreshReportsNav: loadReportsSidebarTree,
  };
})();

window.Hub = Hub;
window.HubRefreshReportsNav = Hub.refreshReportsNav;

// ── Legacy Compatibility Layer ─────────────────────────────────────────
// These globals ensure existing table.js, pagination.js, etc. work unchanged
const ApiClient = Hub.api;
const apiFetch  = (p, o) => Hub.api.fetch(p, o);
const apiPost   = (p, b) => Hub.api.post(p, b);
const apiPatch  = (p, b) => Hub.api.patch(p, b);
const apiPut    = (p, b) => Hub.api.put(p, b);
const apiDelete = (p) => Hub.api.del(p);
const apiPostForm = (p, f) => Hub.api.postForm(p, f);
const apiDownload = (p, b, f) => Hub.api.download(p, b, f);
const apiDownloadGet = (p, f) => Hub.api.download(p, null, f);
const formatIndianNumber = Hub.utils.formatIndian;
const formatIndianCompact = Hub.utils.formatCompact;
const showSnackbar = Hub.utils.snackbar;
const createVarianceChip = (v, o) => Hub.utils.varianceChip(v, { invert: o?.invertColors, fmt: o?.format });
