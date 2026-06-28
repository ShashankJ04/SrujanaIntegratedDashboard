-- DPR — operator per production line (press / MCM_Type=1 machines)
-- Re-runnable: ignore duplicate-column errors if already applied.

ALTER TABLE dpr_daily_review
  ADD COLUMN op_id INT NULL AFTER machine_id;
