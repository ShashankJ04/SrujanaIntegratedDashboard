-- Laser Welding v3 — remarks, rework qty, OT flag on line rows
-- Re-runnable: ignore duplicate-column errors if already applied.

ALTER TABLE laser_welding_line
  ADD COLUMN scrap_remark VARCHAR(255) NULL AFTER scrap_qty;

ALTER TABLE laser_welding_line
  ADD COLUMN rework_qty INT NOT NULL DEFAULT 0 AFTER scrap_remark;

ALTER TABLE laser_welding_line
  ADD COLUMN rework_remark VARCHAR(255) NULL AFTER rework_qty;

ALTER TABLE laser_welding_line
  ADD COLUMN ot_flag CHAR(1) NOT NULL DEFAULT 'N' AFTER time_taken_minutes;
