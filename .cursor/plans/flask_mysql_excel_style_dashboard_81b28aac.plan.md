---
name: flask_mysql_excel_style_dashboard
overview: Implement a modern, fast Excel-like dashboard UI in vanilla JS backed by a Flask API over MySQL, supporting dynamic columns, search/filter/sort, pagination, and Excel export.
todos:
  - id: backend-setup
    content: Set up Flask app, configuration loading, and MySQL connection utilities.
    status: completed
  - id: api-endpoints
    content: Implement /api/columns, /api/rows, /api/export, and / routes in Flask.
    status: completed
  - id: excel-export
    content: Implement Excel export for the full filtered dataset using a library like pandas or openpyxl.
    status: completed
  - id: frontend-shell
    content: Create index.html with layout regions and load static JS/CSS assets.
    status: completed
  - id: frontend-table-logic
    content: Implement vanilla JS table rendering with dynamic columns, sorting, filtering, search, and column resizing.
    status: completed
  - id: frontend-pagination-controls
    content: Implement pagination bar and page-size selector that call the backend with appropriate query parameters.
    status: completed
  - id: ui-polish
    content: Apply modern light-theme styling, animations, sticky headers, and responsive layout.
    status: completed
isProject: false
---

## High-level architecture

- **Frontend**: Vanilla JS single-page dashboard with a responsive, light, clean, modern design. HTML served by Flask, static assets under `static/`.
- **Backend**: Flask app exposing JSON APIs for table metadata, paginated row data, and Excel export. Uses a MySQL client/ORM for data access.
- **Database**: Single primary MySQL table (configurable) that the dashboard reads from; schema may change over time, so column metadata is discovered dynamically at runtime.

## Project structure

- **Root**
  - `requirements.txt` — Flask, MySQL driver (e.g. `mysqlclient` or `pymysql`), and Excel export helpers (e.g. `openpyxl` or `pandas`, `xlsxwriter`).
  - `config_example.py` — Example configuration (DB connection URL, target table name, page size defaults).
- **Backend (Flask)**
  - `[backend/app.py](backend/app.py)` — Flask application factory, route registration, error handling, config loading.
  - `[backend/db.py](backend/db.py)` — MySQL connection utilities and helpers to introspect table schema and execute parameterized queries.
  - `[backend/models.py](backend/models.py)` — Abstractions for a generic "table" model (e.g. functions like `get_table_columns`, `get_rows`, `count_rows`).
  - `[backend/api.py](backend/api.py)` — Blueprint defining JSON endpoints for metadata, data, and export.
  - `[backend/export.py](backend/export.py)` — Logic to generate an Excel file for the full table (respecting filters if requested) and stream it as a download.
- **Frontend**
  - `[templates/index.html](templates/index.html)` — HTML shell for the dashboard, includes layout regions (header, controls, table container, pagination bar, footer).
  - `[static/css/styles.css](static/css/styles.css)` — Modern light theme, responsive layout, table styling, hover states, resizable columns, transitions.
  - `[static/js/api.js](static/js/api.js)` — Wrapper for calling backend APIs (metadata, data, export) with query parameters.
  - `[static/js/table.js](static/js/table.js)` — Core grid logic: rendering dynamic columns/rows, handling sorting, filtering, search, column resizing.
  - `[static/js/pagination.js](static/js/pagination.js)` — Pagination controls, page size selector, page navigation.
  - `[static/js/main.js](static/js/main.js)` — Initializes the dashboard, wires UI controls to table and API.

## Backend design

- **Configuration**
  - **DB settings**: Use environment variables or a config file (`DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`).
  - **Target table**: Configurable table name (e.g. `TARGET_TABLE_NAME`) so the same code can work with different datasets.
  - **Pagination defaults**: Configurable default page size and max page size (e.g. default 25, max 200) to balance flexibility and performance.
- **Database layer (`db.py`)**
  - **Connection helper**: Create a pooled connection (using `mysqlclient` or `pymysql` with connection parameters) and a context manager for queries.
  - **Safe query building**: Only allow filtering/sorting on known column names retrieved from metadata; use parameter binding for values to avoid SQL injection.
- **Metadata and data access (`models.py`)**
  - `**get_table_columns()**`
    - Query MySQL `INFORMATION_SCHEMA.COLUMNS` (or `DESCRIBE table`) to get ordered column list and data types.
    - Normalize into a frontend-friendly format: `{ name, label, dataType, isNumeric, isSortable }`.
  - `**get_rows(params)**`
    - Inputs: `page`, `pageSize`, `globalSearch`, `filters` (per-column), `sortBy`, `sortDir`.
    - Build `SELECT ... FROM table` with:
      - `WHERE` clauses for global search (e.g. `LIKE` over a subset of text columns) and column filters (exact or `LIKE`, depending on type).
      - `ORDER BY` restricted to sortable columns and validated sort direction.
      - `LIMIT` and `OFFSET` derived from `page` and `pageSize`.
  - `**count_rows(params)**`
    - Compute total row count using the same `WHERE` conditions to keep pagination accurate.
- **API routes (`api.py`)**
  - `**GET /api/columns**`
    - Returns metadata from `get_table_columns()`.
  - `**GET /api/rows**`
    - Query parameters: `page`, `pageSize`, `search`, `sortBy`, `sortDir`, and serialized column filters.
    - Returns `{ rows, totalCount, page, pageSize }`.
  - `**GET /api/export**`
    - Accepts same filter/search/sort query parameters.
    - Streams an Excel (XLSX) file containing **all matching rows** (ignoring pagination) for the table.
  - `**GET /**`
    - Renders `index.html` with minimal server-side data (e.g. page title, maybe default page size list).
- **Excel export (`export.py`)**
  - Use `pandas` or direct `openpyxl` to create an in-memory workbook from query results.
  - Apply basic styling: header row bold, auto column width (approximate), freeze header row.
  - Return with `Content-Disposition: attachment; filename="table_export.xlsx"`.

## Frontend design and UX

- **Overall layout (`index.html` + `styles.css`)**
  - **Top bar**: App title, brief description, and global search input.
  - **Control panel**: Row count selector (e.g. 25/50/100/200), export button, maybe a compact summary (`Showing X–Y of Z`).
  - **Table container**: A scrollable, responsive container that holds the Excel-like grid.
  - **Pagination bar**: Previous/Next buttons, current page display, first/last page jumps, quick page input or limited page numbers.
  - **Visual style**: Light, clean, high-contrast with subtle shadows, smooth hover states, and focus rings for accessibility.
- **Dynamic table rendering (`table.js`)**
  - On load, fetch `/api/columns` to discover columns.
  - Build table header (`<thead>`) dynamically:
    - Column title with sort toggles (click to cycle through asc/desc/none).
    - Optional filter input under each header for column-wise filtering.
    - Resizable columns: draggable handle on right edge updates a CSS variable or inline width.
  - Build `tbody` rows from `/api/rows` data.
  - Handle a "loading" state and empty-state messaging.
- **Search, filtering, and sorting interactions**
  - **Global search**: Debounced text input in the top bar; on change, reset to page 1 and request new data.
  - **Column filter row**: Text inputs (or type-aware controls where feasible) under each header; changes trigger debounced reload.
  - **Sorting**: Clicking on a header toggles sort direction; an arrow icon indicates current sort. Only one primary sort key at first (multi-sort can be optional later).
- **Pagination and page size (`pagination.js`)**
  - Maintain `currentPage`, `pageSize`, `totalCount` in JS state.
  - Disable Previous at first page and Next at last page.
  - Row-per-page dropdown updates `pageSize`, resets page to 1, and refetches rows.
  - Display `Showing X–Y of Z` using metadata from the server response.
- **Export action (`main.js`)**
  - Export button builds a URL to `/api/export` with current search/filter/sort parameters and navigates to it (or sets `window.location` / creates a hidden link) to trigger download.

## Performance and robustness

- **Server-side pagination and filtering**
  - Because you expect up to ~50k rows, use server-side pagination and filtering to keep memory and bandwidth usage low.
  - Limit page sizes to a safe maximum and validate all incoming parameters.
- **Indexing**
  - Recommend (in docs) adding appropriate indexes on frequently filtered/sorted columns to keep queries fast.
- **Caching**
  - Cache column metadata (`get_table_columns()`) at the app level so schema introspection isn’t repeated for every request.
- **Error handling**
  - Unified error responses for API endpoints (e.g. JSON with `error` field), and friendly UI messages when backend errors occur.

## Modern UI polish

- **Styling details (`styles.css`)**
  - Use CSS Grid/Flexbox for layout.
  - Add subtle transitions on hover/focus for buttons and table rows.
  - Sticky header row so column titles remain visible while scrolling.
  - Alternating row backgrounds, highlight on hover, and clear focus indicators.
- **Responsive design**
  - Ensure table container behaves well on smaller screens: horizontal scroll with header staying sticky; controls wrap neatly.
  - Controls (search, filters, pagination) adjust to narrow widths (e.g. collapsing labels, stacking vertically).

## Testing and validation

- **Manual testing scenarios**
  - Load with table having many columns (to verify dynamic rendering and horizontal scroll behavior).
  - Change table schema (add a column) and confirm UI reflects the new column without code changes.
  - Exercise global search, multi-column filters, sorting, and pagination together.
  - Export with and without filters to ensure the Excel file matches the displayed dataset.

## Implementation todos

- **backend-setup**: Set up Flask app, configuration, and MySQL connection utilities.
- **api-endpoints**: Implement `/api/columns`, `/api/rows`, `/api/export`, and `/` routes.
- **excel-export**: Implement efficient Excel export of full filtered dataset.
- **frontend-shell**: Create `index.html` layout with header, controls, table container, and pagination regions.
- **frontend-table-logic**: Implement JS to fetch metadata/data and render dynamic, resizable, sortable, filterable table.
- **frontend-pagination-controls**: Implement pagination and page-size controls wired to server-side queries.
- **ui-polish**: Apply modern light-theme styling and responsive behavior.

