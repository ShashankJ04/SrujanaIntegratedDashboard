-- Tool breakdowns schema updates (run once against the application database).
-- Skip any line that errors with "Duplicate column name" if already applied.

ALTER TABLE tool_breakdowns
  ADD COLUMN tool_down VARCHAR(32) DEFAULT 'Breakdown' AFTER issue;

ALTER TABLE tool_breakdowns
  ADD COLUMN analysis TEXT NULL AFTER root_cause_at;

ALTER TABLE tool_breakdowns
  ADD COLUMN hours_spent DECIMAL(10, 2) NULL AFTER completed_by_name;

ALTER TABLE tool_breakdowns
  ADD COLUMN current_stroke INT NULL AFTER hours_spent;

ALTER TABLE tool_breakdowns
  ADD COLUMN next_stroke INT NULL AFTER current_stroke;
