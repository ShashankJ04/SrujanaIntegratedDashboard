CREATE TABLE IF NOT EXISTS buffer_stock_config (
    part_no VARCHAR(100) NOT NULL PRIMARY KEY,
    buffer_qty DECIMAL(18,4) NOT NULL DEFAULT 0,
    updated_by VARCHAR(100) NULL,
    updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- Migration from buffer_pct to buffer_qty (run once):
-- ALTER TABLE buffer_stock_config ADD COLUMN buffer_qty DECIMAL(18,4) NOT NULL DEFAULT 0 AFTER part_no;
-- UPDATE buffer_stock_config SET buffer_qty = 0;
-- ALTER TABLE buffer_stock_config DROP COLUMN buffer_pct;

