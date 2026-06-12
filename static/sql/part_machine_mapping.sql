CREATE TABLE IF NOT EXISTS part_machine_mapping (
  mapping_id                INT AUTO_INCREMENT PRIMARY KEY,
  part_no                   VARCHAR(100) NOT NULL,
  part_name                 VARCHAR(255) NOT NULL,
  component_id              INT NULL,
  primary_machine_name      VARCHAR(100) NOT NULL,
  primary_machine_id        INT UNSIGNED NULL,
  alternate_machines_summary VARCHAR(500) NULL,
  spm                       DECIMAL(10,2) NULL,
  cavity                    INT NOT NULL DEFAULT 0,
  is_supplier               TINYINT(1) NOT NULL DEFAULT 0,
  created_at                DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at                DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_part_primary (part_no, primary_machine_name),
  INDEX idx_pmm_part_no (part_no),
  INDEX idx_pmm_component (component_id),
  INDEX idx_pmm_primary_machine (primary_machine_id),
  INDEX idx_pmm_primary_name (primary_machine_name),
  INDEX idx_pmm_supplier (is_supplier)
);

CREATE TABLE IF NOT EXISTS part_machine_alternate (
  alt_id        INT AUTO_INCREMENT PRIMARY KEY,
  mapping_id    INT NOT NULL,
  machine_name  VARCHAR(100) NOT NULL,
  machine_id    INT UNSIGNED NULL,
  alt_rank      TINYINT UNSIGNED NOT NULL,
  UNIQUE KEY uq_mapping_rank (mapping_id, alt_rank),
  INDEX idx_pma_machine_name (machine_name),
  INDEX idx_pma_machine_id (machine_id),
  CONSTRAINT fk_pma_mapping
    FOREIGN KEY (mapping_id) REFERENCES part_machine_mapping(mapping_id) ON DELETE CASCADE
);

-- Migration (run once if upgrading from earlier schema):
-- ALTER TABLE part_machine_mapping DROP COLUMN parts_per_day;
