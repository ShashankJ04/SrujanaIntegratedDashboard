/* Dashboards Utility Functions
   Port of frontend/src/utils/formatNumber.ts */

/**
 * Format a number with Indian numbering (e.g. 12,34,567).
 */
function formatIndianNumber(n) {
  if (n == null || isNaN(n)) return '0';
  n = Math.round(Number(n));
  const neg = n < 0;
  const abs = Math.abs(n);
  const s = String(abs);
  if (s.length <= 3) return (neg ? '-' : '') + s;
  const last3 = s.slice(-3);
  let rest = s.slice(0, -3);
  const parts = [];
  while (rest.length > 2) {
    parts.unshift(rest.slice(-2));
    rest = rest.slice(0, -2);
  }
  if (rest) parts.unshift(rest);
  return (neg ? '-' : '') + parts.join(',') + ',' + last3;
}

/**
 * Compact Indian format (e.g. 1.2L, 45K).
 */
function formatIndianCompact(n) {
  if (n == null || isNaN(n)) return '0';
  n = Number(n);
  const abs = Math.abs(n);
  const neg = n < 0 ? '-' : '';
  if (abs >= 1_00_00_000) return neg + (abs / 1_00_00_000).toFixed(1).replace(/\.0$/, '') + 'Cr';
  if (abs >= 1_00_000) return neg + (abs / 1_00_000).toFixed(1).replace(/\.0$/, '') + 'L';
  if (abs >= 1_000) return neg + (abs / 1_000).toFixed(1).replace(/\.0$/, '') + 'K';
  return neg + String(Math.round(abs));
}

/**
 * Show a snackbar toast message.
 */
function showSnackbar(message, duration = 4000) {
  let el = document.getElementById('dash-snackbar');
  if (!el) {
    el = document.createElement('div');
    el.id = 'dash-snackbar';
    el.className = 'dash-snackbar';
    document.body.appendChild(el);
  }
  el.textContent = message;
  el.classList.add('show');
  clearTimeout(el._timer);
  el._timer = setTimeout(() => el.classList.remove('show'), duration);
}

/**
 * Create a variance chip element.
 */
function createVarianceChip(value, options = {}) {
  const rounded = Math.round(value * 100) / 100;
  const el = document.createElement('span');
  el.className = 'dash-chip ';
  if (rounded === 0) {
    el.className += 'dash-chip-neutral';
    el.textContent = '0';
  } else if (rounded > 0) {
    el.className += options.invertColors ? 'dash-chip-danger' : 'dash-chip-success';
    el.textContent = (options.format ? Math.abs(rounded).toFixed(2) : formatIndianNumber(Math.abs(rounded)));
    el.innerHTML = '▲ ' + el.textContent;
  } else {
    el.className += options.invertColors ? 'dash-chip-success' : 'dash-chip-danger';
    el.textContent = (options.format ? Math.abs(rounded).toFixed(2) : formatIndianNumber(Math.abs(rounded)));
    el.innerHTML = '▼ ' + el.textContent;
  }
  return el;
}
