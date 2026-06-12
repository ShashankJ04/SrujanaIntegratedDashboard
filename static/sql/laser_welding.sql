DROP TABLE IF EXISTS laser_welding_processing;

CREATE TABLE IF NOT EXISTS laser_welding_lot (
  lot_id              INT AUTO_INCREMENT PRIMARY KEY,
  part_number         VARCHAR(100) NOT NULL,
  bom_id              VARCHAR(36) NULL,
  product_name        VARCHAR(255) NULL,
  operator_id         INT NULL,
  new_lot_no          VARCHAR(50) NULL,
  work_date           DATE NOT NULL,
  total_inspected     INT NOT NULL DEFAULT 0,
  total_qa            INT NOT NULL DEFAULT 0,
  total_okayed        INT NOT NULL DEFAULT 0,
  scrap               INT NOT NULL DEFAULT 0,
  rework_pending      INT NOT NULL DEFAULT 0,
  rework_pool         INT NOT NULL DEFAULT 0,
  uncleaned_qty       INT NOT NULL DEFAULT 0,
  inspection_pending  INT NOT NULL DEFAULT 0,
  time_taken_minutes  INT NULL,
  processed_at        DATETIME NULL,
  processed_by        INT NULL,
  qa_approved_at      DATETIME NULL,
  qa_approved_by      INT NULL,
  created_by          INT NULL,
  created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at          DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_new_lot (new_lot_no),
  INDEX idx_lwl_date (work_date),
  INDEX idx_lwl_part (part_number),
  INDEX idx_lwl_bom (bom_id)
);

CREATE TABLE IF NOT EXISTS laser_welding_line (
  line_id           INT AUTO_INCREMENT PRIMARY KEY,
  part_number       VARCHAR(100) NOT NULL,
  lot_id            INT NULL,
  child_lot_id      INT NULL,
  line_type         ENUM('production','rework','assembly_consume') NOT NULL DEFAULT 'production',
  source_lot_no     VARCHAR(100) NOT NULL,
  production_date   DATE NULL,
  inspected_qty     INT NOT NULL DEFAULT 0,
  qa_qty            INT NOT NULL DEFAULT 0,
  created_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at        DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_lwl_line_draft (part_number, line_type, source_lot_no, production_date),
  INDEX idx_lwl_line_rework_day (lot_id, line_type, production_date),
  INDEX idx_lwl_line_lot (lot_id),
  CONSTRAINT fk_lwl_line_lot FOREIGN KEY (lot_id) REFERENCES laser_welding_lot(lot_id) ON DELETE CASCADE
);

Migration for existing DBs:
ALTER TABLE laser_welding_lot
  ADD COLUMN bom_id VARCHAR(36) NULL AFTER part_number,
  ADD COLUMN product_name VARCHAR(255) NULL AFTER bom_id,
  ADD COLUMN uncleaned_qty INT NOT NULL DEFAULT 0 AFTER rework_pool,
  ADD COLUMN inspection_pending INT NOT NULL DEFAULT 0 AFTER uncleaned_qty;
ALTER TABLE laser_welding_line
  ADD COLUMN child_lot_id INT NULL AFTER lot_id,
  MODIFY line_type ENUM('production','rework','assembly_consume') NOT NULL DEFAULT 'production';
-- 