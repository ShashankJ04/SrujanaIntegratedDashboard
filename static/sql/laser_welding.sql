DROP TABLE IF EXISTS laser_welding_processing;

CREATE TABLE IF NOT EXISTS laser_welding_lot (
  lot_id              INT AUTO_INCREMENT PRIMARY KEY,
  part_number         VARCHAR(100) NOT NULL,
  bom_id              VARCHAR(36) NULL,
  product_name        VARCHAR(255) NULL,
  new_lot_no          VARCHAR(50) NULL,
  work_date           DATE NOT NULL,
  total_inwarded      INT NOT NULL DEFAULT 0,
  total_qa            INT NOT NULL DEFAULT 0,
  total_okayed        INT NOT NULL DEFAULT 0,
  scrap               INT NOT NULL DEFAULT 0,
  rework_pending      INT NOT NULL DEFAULT 0,
  rework_pool         INT NOT NULL DEFAULT 0,
  inspection_pending  INT NOT NULL DEFAULT 0,
  cleaning_pending    INT NOT NULL DEFAULT 0,
  plant_id            INT NULL,
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
  line_id             INT AUTO_INCREMENT PRIMARY KEY,
  cd_line_id          INT NULL,
  part_number         VARCHAR(100) NOT NULL,
  lot_id              INT NULL,
  child_lot_id        INT NULL,
  bom_id              VARCHAR(36) NULL,
  line_type           ENUM('Part_Inspection','Assembly_Inspection','Assembly_Cleaning','Welding_Consume','Welding_Rework','SubAssembly_Consume','SubAssembly_Rework','QA_Disposition','Packing') NOT NULL DEFAULT 'Part_Inspection',
  source_lot_no       VARCHAR(100) NOT NULL DEFAULT '',
  production_date     DATE NULL,
  inspected_qty       INT NOT NULL DEFAULT 0,
  qa_qty              INT NOT NULL DEFAULT 0,
  scrap_qty           INT NOT NULL DEFAULT 0,
  scrap_remark        VARCHAR(255) NULL,
  qa_remark           VARCHAR(255) NULL,
  rework_qty          INT NOT NULL DEFAULT 0,
  rework_remark       VARCHAR(255) NULL,
  operator_ids        VARCHAR(500) NOT NULL DEFAULT '',
  machine_id          INT NULL,
  time_taken_minutes  INT NULL,
  ot_flag             CHAR(1) NOT NULL DEFAULT 'N',
  created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at          DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_lwl_line_draft (part_number, line_type, source_lot_no, production_date),
  INDEX idx_lwl_line_cd (cd_line_id),
  INDEX idx_lwl_line_rework_day (lot_id, line_type, production_date),
  INDEX idx_lwl_line_lot (lot_id),
  CONSTRAINT fk_lwl_line_lot FOREIGN KEY (lot_id) REFERENCES laser_welding_lot(lot_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS lw_re_work_scrap (
  scrap_log_id      INT AUTO_INCREMENT PRIMARY KEY,
  part_number       VARCHAR(100) NOT NULL,
  lot_id            INT NOT NULL,
  scrap_qty         INT NOT NULL,
  line_id           INT NOT NULL,
  created_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_lw_rws_lot (lot_id),
  INDEX idx_lw_rws_line (line_id),
  INDEX idx_lw_rws_part (part_number)
);

-- ALTER TABLE laser_welding_line
--   MODIFY line_type ENUM('Part_Inspection','Assembly_Inspection','Welding_Consume','Welding_Rework','SubAssembly_Consume','SubAssembly_Rework','QA_Disposition','Packing') NOT NULL DEFAULT 'Part_Inspection';
-- ALTER TABLE laser_welding_line ADD COLUMN machine_id INT NULL AFTER operator_id;
-- ALTER TABLE laser_welding_line ADD COLUMN operator_ids VARCHAR(500) NULL AFTER operator_id;
-- Migration: replace operator_id with operator_ids
-- UPDATE laser_welding_line SET operator_ids = CAST(operator_id AS CHAR) WHERE (operator_ids IS NULL OR operator_ids = '') AND operator_id IS NOT NULL;
-- ALTER TABLE laser_welding_line DROP COLUMN operator_id;
-- ALTER TABLE laser_welding_line MODIFY operator_ids VARCHAR(500) NOT NULL DEFAULT '';
-- ALTER TABLE laser_welding_line ADD COLUMN qa_remark VARCHAR(255) NULL AFTER scrap_remark;
-- ALTER TABLE laser_welding_lot ADD COLUMN plant_id INT NULL AFTER inspection_pending;
-- ALTER TABLE laser_welding_lot ADD COLUMN cleaning_pending INT NOT NULL DEFAULT 0 AFTER inspection_pending;
-- ALTER TABLE laser_welding_line MODIFY line_type ENUM(
--   'Part_Inspection','Assembly_Inspection','Assembly_Cleaning',
--   'Welding_Consume','Welding_Rework','SubAssembly_Consume',
--   'SubAssembly_Rework','QA_Disposition','Packing') NOT NULL DEFAULT 'Part_Inspection';
-- FG backfill after adding cleaning_pending:
-- UPDATE laser_welding_lot l INNER JOIN bom b ON b.bom_id = l.bom_id
-- SET cleaning_pending = l.inspection_pending,
--   inspection_pending = GREATEST(0, l.total_inwarded - COALESCE((
--     SELECT SUM(ln.inspected_qty) FROM laser_welding_line ln
--     WHERE ln.lot_id = l.lot_id AND ln.line_type = 'Assembly_Inspection'), 0))
-- WHERE TRIM(l.part_number) = TRIM(b.bom_no) AND l.new_lot_no IS NOT NULL AND l.new_lot_no NOT LIKE 'PCK/%';

