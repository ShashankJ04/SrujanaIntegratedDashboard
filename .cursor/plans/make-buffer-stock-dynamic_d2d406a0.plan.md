---
name: make-buffer-stock-dynamic
overview: Make the Buffer Stock column dynamic based on a per-part percentage configured via the UI, persisted to the database, and applied efficiently without overloading the existing heavy view.
todos:
  - id: design-db-table
    content: Read the view query and check if it is possible to optimize the working. Instead of running the view break down the query and make it less heavy to optimize the working.
    status: completed
  - id: todo-1772924572920-drkfhybhr
    content: Design and document schema for buffer_stock_config (per-part buffer percentage).
    status: pending
  - id: update-models
    content: Update backend get_rows logic to join or enrich view data with buffer configuration and compute effective buffer stock.
    status: completed
  - id: buffer-config-api
    content: Add API endpoints to read/update per-part buffer percentage without hitting the heavy view.
    status: completed
  - id: frontend-display
    content: Update frontend table rendering to use dynamic buffer stock and show the current percentage per part.
    status: completed
  - id: frontend-edit-ui
    content: Add simple per-row UI to edit buffer percentage and wire it to the new API.Read the view query and check if it is possible to optimize the working. Instead of running the view break down the query and make it less heavy to optimize the working.
    status: completed
isProject: false
---

## Goal

Implement a **dynamic Buffer Stock** mechanism where:

- Users can set a **buffer percentage per part** from the UI at runtime.
- The value defaults to **0%** when not configured.
- The existing heavy view `vw_bharat_dashboard` is not further burdened; instead, we adjust or enrich the data in the app/backend layer.

## High-level approach

- Introduce a small **configuration table** for per-part buffer percentages.
- Expose a **lightweight API** to read/update these percentages.
- Adjust the backend’s row-loading logic (after the view) to compute the effective Buffer Stock using the configured percentage.
- Update the frontend table to:
  - Display the **computed Buffer Stock** column.
  - Optionally allow editing the percentage for a row via a small inline control or modal.

## Backend plan

- **1. Add buffer config table (DB)**
  - Create table (e.g. `buffer_stock_config`):
    - `part_no` (PK, matches `PART_NO` from the view)
    - `buffer_pct` (DECIMAL, percentage value; 0–100)
    - `updated_at` (timestamp, optional)
  - Seed nothing; default behavior is handled by **COALESCE to 0** when there is no row.
  - Keep `vw_bharat_dashboard` as-is for now (still contains its own `Buffer Stock` based on 30%) to avoid destabilizing core reporting logic.
- **2. Extend models to join config for reads**
  - In `[backend/models.py](backend/models.py)`, after loading rows from `vw_bharat_dashboard`, compute a **derived buffer stock**:
    - Fetch the per-part percentage via a single query that joins `buffer_stock_config` on `PART NUMBER` (or `PART_NO` depending on how the view is exposed).
    - Calculate: `effective_buffer = ROUND(FEB * (buffer_pct / 100))`.
    - If there is no config row, treat `buffer_pct = 0` so `effective_buffer = 0`.
  - Attach both `buffer_pct` and `effective_buffer` as extra fields in the returned row dict so the frontend can display them.
- **3. Add API endpoints for config**
  - In `[backend/api.py](backend/api.py)` create endpoints under `/api/buffer-config`:
    - `GET /api/buffer-config?partNo=...` -> current percentage (or 0).
    - `PUT /api/buffer-config` -> upsert `{ partNo, bufferPct }`.
  - Use simple validation (0–100, numeric) and return updated value.
  - Ensure these calls are **fast and independent** of the heavy view.

## Frontend plan

- **4. Surface dynamic buffer in table**
  - Decide representation in the table:
    - Keep the existing `Buffer Stock` column but replace its value with the **derived buffer** from the backend, or
    - Add a new column like `Dynamic Buffer` and optionally keep the original for comparison.
  - Update data-mapping code in `[static/js/table.js](static/js/table.js)` (or where rows are post-processed) so it uses the new `buffer_pct` and `effective_buffer` fields when rendering.
- **5. Add per-row UI to edit buffer percentage**
  - Add a **small control** in each row, for example:
    - A pencil icon or button in a new `Buffer %` column, which opens a tiny inline editor or modal.
  - When the user changes the value:
    - Call `PUT /api/buffer-config` with `partNo` and `bufferPct`.
    - On success, trigger `DashboardController.reload()` to fetch rows with the new computed buffers.
  - Display the current percentage in the row (e.g. `30%`) so users see what is applied.
- **6. Optional: global default control**
  - In the header or controls bar, add an optional **global buffer %** setting that:
    - Is stored in another config table/column (e.g. `buffer_stock_default`), or
    - Is kept purely in UI state for quick experimentation.
  - When per-part percentage is missing, use the global default instead of 0.

## Performance and safety

- Avoid changing the heavy view’s internals initially; instead, do a **left join from the view’s results to the small config table** in a separate query or via a simple join in `get_rows`.
- Ensure all new queries are indexed on `part_no` so lookups are O(1) per row.
- Keep all new logic behind the existing `/api/rows` path so the frontend continues to work, but with enriched, dynamic Buffer Stock values.

## Deliverables

- New DB table creation SQL for per-part buffer stock configuration.
- Updated backend models and API endpoints exposing dynamic buffer configuration.
- Updated frontend table rendering and controls to show the dynamic Buffer Stock and allow editing the percentage per part.
- Brief documentation comment or README note describing how buffer percentages are applied and how defaults work (0% or optional global default).

