-- Laser Welding v5: tray/carton catalog (split tables)

CREATE TABLE IF NOT EXISTS lw_packing_tray (
  tray_item_code  VARCHAR(100) NOT NULL PRIMARY KEY,
  material        TINYINT NULL,
  type            VARCHAR(10) NULL,
  cavity          INT NULL,
  cust_id         INT NULL,
  created_by      INT NULL,
  created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_lw_pack_tray_cust (cust_id),
  INDEX idx_lw_pack_tray_attrs (type, cavity, cust_id)
);

CREATE TABLE IF NOT EXISTS lw_packing_carton (
  carton_item_code VARCHAR(100) NOT NULL PRIMARY KEY,
  length_mm        INT NULL,
  width_mm         INT NULL,
  height_mm        INT NULL,
  created_by       INT NULL,
  created_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_lw_pack_carton_dims (length_mm, width_mm, height_mm)
);

CREATE TABLE IF NOT EXISTS lw_packing_part_map (
  map_id            INT AUTO_INCREMENT PRIMARY KEY,
  co_id             INT NOT NULL,
  cust_id           INT NULL,
  tray_item_code    VARCHAR(100) NULL,
  carton_item_code  VARCHAR(100) NULL,
  tray_capacity     INT NULL,
  carton_capacity   INT NULL,
  is_active         TINYINT(1) NOT NULL DEFAULT 1,
  created_by        INT NULL,
  created_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at        DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_lw_pack_map_co (co_id),
  INDEX idx_lw_pack_map_tray (tray_item_code),
  INDEX idx_lw_pack_map_carton (carton_item_code)
);
