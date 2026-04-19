const Pagination = (() => {
  let els = {
    first: null,
    prev: null,
    next: null,
    last: null,
    pageInput: null,
    totalLabel: null,
  };

  function init({
    firstId,
    prevId,
    nextId,
    lastId,
    pageInputId,
    totalLabelId,
  }) {
    els.first = document.getElementById(firstId);
    els.prev = document.getElementById(prevId);
    els.next = document.getElementById(nextId);
    els.last = document.getElementById(lastId);
    els.pageInput = document.getElementById(pageInputId);
    els.totalLabel = document.getElementById(totalLabelId);

    wireEvents();
  }

  function wireEvents() {
    els.first.addEventListener("click", () => goToPage(1));
    els.prev.addEventListener("click", () => {
      const state = DataTable.getState();
      goToPage(Math.max(1, state.page - 1));
    });
    els.next.addEventListener("click", () => {
      const state = DataTable.getState();
      goToPage(Math.min(state.totalPages, state.page + 1));
    });
    els.last.addEventListener("click", () => {
      const state = DataTable.getState();
      goToPage(state.totalPages);
    });

    els.pageInput.addEventListener("change", () => {
      const val = parseInt(els.pageInput.value, 10);
      if (Number.isNaN(val) || val < 1) {
        const state = DataTable.getState();
        els.pageInput.value = String(state.page);
        return;
      }
      goToPage(val);
    });
  }

  function goToPage(page) {
    const state = DataTable.getState();
    const target = Math.max(1, Math.min(page, state.totalPages || 1));
    if (target === state.page) return;
    DataTable.setExternalState({ page: target });
    if (typeof window.DashboardController?.reload === "function") {
      window.DashboardController.reload();
    }
  }

  function applyPaginationMeta({ page, pageSize, totalCount }) {
    const totalPages = totalCount ? Math.ceil(totalCount / pageSize) : 1;
    DataTable.setExternalState({ page, pageSize, totalCount, totalPages });

    if (els.pageInput) {
      els.pageInput.value = String(page);
      els.pageInput.min = "1";
      els.pageInput.max = String(totalPages);
    }
    if (els.totalLabel) {
      els.totalLabel.textContent = `/ ${totalPages}`;
    }
    if (els.first && els.prev) {
      const disablePrev = page <= 1;
      els.first.disabled = disablePrev;
      els.prev.disabled = disablePrev;
    }
    if (els.next && els.last) {
      const disableNext = page >= totalPages;
      els.next.disabled = disableNext;
      els.last.disabled = disableNext;
    }

    DataTable.updateSummary();
  }

  return {
    init,
    applyPaginationMeta,
  };
})();

