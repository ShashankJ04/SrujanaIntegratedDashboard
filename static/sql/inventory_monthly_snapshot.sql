-- Inventory report — frozen end-of-month snapshots (captured automatically at 23:59 on last day).

CREATE TABLE IF NOT EXISTS inventory_monthly_snapshots (
    snapshot_year INT NOT NULL,
    snapshot_month INT NOT NULL,
    captured_at DATETIME NOT NULL,
    row_count INT NOT NULL DEFAULT 0,
    PRIMARY KEY (snapshot_year, snapshot_month)
);

CREATE TABLE IF NOT EXISTS inventory_monthly_snapshot_rows (
    snapshot_year INT NOT NULL,
    snapshot_month INT NOT NULL,
    part_no VARCHAR(128) NOT NULL,
    row_json JSON NOT NULL,
    PRIMARY KEY (snapshot_year, snapshot_month, part_no),
    INDEX idx_inv_snap_period (snapshot_year, snapshot_month)
);
