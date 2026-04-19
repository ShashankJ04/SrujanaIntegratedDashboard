/**
 * TiExcelDisplay — Shared spreadsheet-style table chrome for hub pages.
 *
 * Applies the same visual language as SuperGrid (`static/js/supergrid.js`):
 * `ti-excel-table`, optional `ti-excel-table--original` (blue header band).
 * DPR (`hub_dpr.html` + `dpr.js`) uses this plus column pin/resize wired in JS so
 * behavior matches the generic Excel-style grid.
 *
 * Usage:
 *   TiExcelDisplay.apply(document.querySelector('#my-table'), { variant: 'original' });
 *   TiExcelDisplay.applyHost(document.querySelector('#scroll-wrap'));
 */
window.TiExcelDisplay = (() => {
  /**
   * @param {HTMLTableElement | null} tableEl
   * @param {{ variant?: 'default' | 'original' }} [opts] original = dark blue header band (legacy dashboard look)
   */
  function apply(tableEl, opts = {}) {
    if (!tableEl) return;
    tableEl.classList.add("ti-excel-table");
    const v = opts.variant || "default";
    if (v === "original") tableEl.classList.add("ti-excel-table--original");
  }

  /** @param {HTMLElement | null} scrollEl */
  function applyHost(scrollEl) {
    if (!scrollEl) return;
    scrollEl.classList.add("ti-excel-host");
  }

  return { apply, applyHost };
})();
