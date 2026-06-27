-- Laser Welding v6: BOM-only tray/carton mappings (when no ERP component exists)

ALTER TABLE lw_packing_part_map
  MODIFY co_id INT NULL,
  ADD COLUMN bom_id VARCHAR(36) NULL AFTER co_id;

ALTER TABLE lw_packing_part_map
  DROP INDEX uq_lw_pack_map_co;

CREATE UNIQUE INDEX uq_lw_pack_map_cust_co ON lw_packing_part_map (cust_id, co_id);
CREATE UNIQUE INDEX uq_lw_pack_map_cust_bom ON lw_packing_part_map (cust_id, bom_id);
