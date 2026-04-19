---
name: optimize-bharat-dashboard-performance
overview: Optimize the heavy vw_bharat_dashboard view by improving SQL, indexing, and adding an efficient data-access/caching layer so the dashboard stays fast even with near real-time data.
todos:
  - id: analyze-sql-and-indexes
    content: Review the view definition and existing indexes, and design concrete index and date-filter changes to make vw_bharat_dashboard sargable and efficient.
    status: pending
  - id: design-cache-layer
    content: Design a small dashboard cache abstraction (in-process initially, Redis-ready) and decide on TTL and maximum row safeguards.
    status: pending
  - id: refactor-get-rows-to-use-cache
    content: Refactor backend get_rows logic to fetch full view results on cache miss, then apply search, sort and pagination in Python using the cached dataset.
    status: pending
  - id: align-export-with-cache
    content: Update the export path to reuse the cached dataset where possible so heavy view execution is shared between UI and exports.
    status: pending
  - id: add-config-and-monitoring
    content: Add configuration for cache TTL and logging/metrics to monitor query times, cache hits, and export performance.
    status: pending
isProject: false
---

## Goal

Make the `vw_bharat_dashboard` dashboard fast and responsive even though the underlying SQL view is heavy, while keeping data **near real-time** for the current month.

We’ll combine **query-level optimization** with a **smarter app-side data-access pattern** so the view is computed as few times as possible, and all pagination/sorting/searching are done efficiently.

## Current situation

- The dashboard reads from a database view defined in `[static/sql/vw_bharat_dashboard.sql](static/sql/vw_bharat_dashboard.sql)`.
- The view:
  - Aggregates **sales demand** for the current month from `sales_order` and `bom_lin_item` (`subquery x`).
  - Computes **FG stock** for last month’s closing from `comp_stockhistory` and `comp_transaction` (`subquery y_fg`).
  - Computes **WIP stock** similarly for all stages other than 6 (`subquery y_wip`).
  - Aggregates **produced quantity** for the current month from `scheduled_production`, `production_details`, `schedule_master`, and `components` (`subquery z`).
  - Joins them on `PART_NO` and calculates buffer, total stock, and production pending.
- The backend (`[backend/models.py](backend/models.py)`) treats this view as the target table, doing:
  - `SELECT COUNT(*) FROM <view>` for pagination total.
  - `SELECT * FROM <view> ... LIMIT ... OFFSET ...` for each page.
  - This means the **entire view is evaluated twice per request**, which is expensive even though the result set is < 10k rows.
- The frontend only needs **current-month** data, with global search, sorting, and pagination.

Conceptually, the data flow today is:

```mermaid
flowchart LR
  browser[Browser] --> api[Flask API /rows]
  api --> dbView[vw_bharat_dashboard]
  dbView --> api
  api --> browser
```



## High-level strategy

1. **Optimize the SQL view and indexing** so a single execution of the view is as fast as reasonably possible.
2. **Change the backend data-access pattern** so the heavy view is evaluated **at most once per short interval**, and **never twice per request**.
3. For our scale (<10k rows per month), **cache the full current-month dataset** in the app (or Redis), and perform pagination, sorting, and global search **in Python**.

This keeps data near real-time (cache TTL can be 30–120 seconds) while dramatically reducing database load.

## Step 1: SQL and index improvements

- **Rewrite date filters to be index-friendly**:
  - Replace patterns like `EXTRACT(YEAR_MONTH FROM DLV_DATE) = EXTRACT(YEAR_MONTH FROM current_date)` with explicit range predicates, e.g. `DLV_DATE >= :startOfMonth AND DLV_DATE < :startOfNextMonth`.
  - Do the same for `PD_DATE`, and for previous-month logic in `comp_stockhistory`/`comp_transaction`.
- **Verify and add indexes on filter/join columns** (exact DDL will depend on existing indexes):
  - `sales_order`: composite index on `(DLV_DATE, CATEGORY_ID, SO_TYPE_ID, STATUS_ID)` plus an index including `bom_no` if used heavily.
  - `bom_lin_item`: index on `(bom_id, PART_NO)`.
  - `bom`: index on `(bom_no, is_latest_version, bom_id)`.
  - `comp_stockhistory`: composite index on `(CH_PlantId, CH_Year, CH_Month, CH_StageId, CH_CompId)`.
  - `comp_transaction`: composite index on `(CT_PlantId, CT_Date, CT_CompId, CT_Nextstage, CT_Opstage)`.
  - `scheduled_production` / `production_details` / `schedule_master` / `components`: indexes on join keys and `PD_DATE`, `SM_Status`, `PS_plantId`, `CO_Id`, `CO_PartNo`.
- **Check logical predicates for selectivity and correctness**:
  - In `y_wip`, confirm whether `(CT_Nextstage != 6 OR CT_Opstage != 6)` should actually be `AND` (current `OR` may include many rows unnecessarily).
- **Measure the impact** using EXPLAIN plans and actual timings for the rewritten query.

This step ensures that even when the view is evaluated (cache miss), it runs as quickly as practical.

## Step 2: Introduce a dashboard data cache

Given the view result is <10k rows and we need near real-time data, we can cache the **entire current-month dataset** in memory and reuse it across requests.

- **Design a cache key** like `"bharat_dashboard:<yearMonth>"`.
- Implement a small cache abstraction in Python (in a new module like `backend/dashboard_cache.py`) that supports:
  - `get_current_month()` → returns cached rows + timestamp if present.
  - `set_current_month(rows)` → stores rows and a `last_refreshed` timestamp.
  - Configurable **TTL** in seconds (e.g. 60–120s).
- Start with **in-process cache** (a module-level variable or `functools.lru_cache` wrapper) and optionally allow plugging in Redis later.
- Data shape stored in cache should be a list of dicts matching the columns of the view.

## Step 3: Change `get_rows` to use cached data and in-Python pagination

Instead of having `get_rows` in `[backend/models.py](backend/models.py)` hit the view directly for every page:

- **New flow**:
  1. On each `get_rows` call, compute the current `yearMonth` and ask the cache for data.
  2. On cache miss or TTL expiry:
    - Run a single `SELECT * FROM vw_bharat_dashboard` for the current month.
    - Store the full result set in cache.
  3. With the full dataset (list of dicts) in Python:
    - Apply **global search** (case-insensitive substring on text columns).
    - Apply **sorting** in memory based on `sort_by` / `sort_dir`.
    - Compute `totalCount` from the filtered list length.
    - Apply **pagination** by slicing the list for the requested `page` and `pageSize`.
  4. Return `rows`, `totalCount`, `page`, `pageSize` exactly as the frontend expects.
- This eliminates the `COUNT(*)` and `LIMIT/OFFSET` queries on the view and turns all per-request work into fast in-process operations.

Updated data flow with caching:

```mermaid
flowchart LR
  browser[Browser] --> api[Flask API /rows]
  api --> cache[DashboardCache]
  cache -->|hit| api
  cache -->|miss| dbView[vw_bharat_dashboard]
  dbView --> cache
  api --> browser
```



## Step 4: Keep exports efficient and consistent

- For the **export endpoint** (`/api/export`, implemented with `generate_excel_response` in `[backend/export.py](backend/export.py)`):
  - Reuse the same cache if the export filters (current-month, search, sort) match the cached dataset.
  - If an export is requested during cache TTL, export from the in-memory list instead of re-hitting the view.
  - If the cache is cold or TTL expired, allow the export path to repopulate the cache by running the view once.

This keeps exports fast and ensures the exported data matches what the user sees in the UI.

## Step 5: Configuration and safety knobs

- Add config entries in `[backend/config.py](backend/config.py)` for:
  - `DASHBOARD_CACHE_TTL_SECONDS` (e.g. 60–300 seconds).
  - `DASHBOARD_MAX_ROWS` guardrail (e.g. 50,000) to avoid caching unexpectedly huge datasets.
- Implement simple logging around cache refresh events and query durations to see how often the heavy query runs and validate performance gains.
- Optionally add an **admin-only endpoint** to explicitly clear/refresh the dashboard cache if operators need an immediate update after known large data changes.

## Step 6: Future enhancements (optional)

If performance is still not sufficient after the above:

- Move from in-process caching to **Redis** so multiple app instances share the same snapshot and you avoid recomputing the view per process.
- Consider a **materialized summary table** maintained by a scheduled job if the view itself becomes too slow even for periodic evaluation.
  - The app would then query the summary table directly instead of the view, but the API contract to the frontend can remain unchanged.
- Explore pushing some of the metrics computation into ETL or upstream systems if this dashboard becomes central to many tools.

This staged approach lets you start with minimal invasive changes (better SQL + caching around the existing view) and leaves room to evolve toward a more ETL-driven architecture if needed.