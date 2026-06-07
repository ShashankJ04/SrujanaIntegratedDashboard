CREATE TABLE IF NOT EXISTS laser_welding_processing (
  lwp_id           INT AUTO_INCREMENT PRIMARY KEY,
  tab_type         VARCHAR(20) NOT NULL DEFAULT 'child_parts',
  part_number      VARCHAR(100) NOT NULL,
  stage_id         INT NOT NULL,
  source_lot_no    VARCHAR(100) NOT NULL,
  production_date  DATE NULL,
  no_of_comp       INT NOT NULL DEFAULT 0,
  qty_processed    INT NOT NULL DEFAULT 0,
  new_lot_no       VARCHAR(50) NULL,
  processed_at     DATETIME NULL,
  processed_by     INT NULL,
  created_by       INT NULL,
  created_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at       DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_lwp_tab_part (tab_type, part_number, stage_id),
  INDEX idx_lwp_new_lot (new_lot_no)
);
