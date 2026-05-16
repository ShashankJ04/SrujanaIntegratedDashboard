// Production Calendar baseline: reuse Dispatch Calendar behavior.
(function () {
  'use strict';

  function getDispatchPage() {
    return window.DispatchCalendarPage || null;
  }

  window.ProductionCalendarPage = {
    init() {
      const dc = getDispatchPage();
      if (!dc || typeof dc.init !== 'function') {
        console.warn('DispatchCalendarPage is not available yet.');
        return;
      }
      dc.init({
        endpoint: '/api/production-calendar',
        layoutKey: 'production_calendar_v2',
      });
    },
    refresh() {
      const dc = getDispatchPage();
      if (dc && typeof dc.refresh === 'function') {
        dc.refresh();
      }
    },
  };
})();
