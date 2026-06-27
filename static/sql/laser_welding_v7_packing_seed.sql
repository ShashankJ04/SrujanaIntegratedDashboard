-- =============================================================================
-- Laser Welding v7: seed packing trays/cartons from Packing Naming Excel
-- =============================================================================
-- Source workbook: Packing Naming (1).xlsx
--   Sheet "Packing Trays" (row 5+) + "Carton Box" (row 4+)
-- Prereq: laser_welding_v5_packing_materials.sql, v6_packing_bom_map.sql
--
-- Inserts (idempotent): ITEM_MASTER, lw_packing_tray, lw_packing_carton,
-- lw_packing_part_map
--
-- Part mappings resolve co_id from components, else bom_id from bom,
-- scoped by customer name. Rows with no matching part are skipped.
--
--   mysql -u USER -p DBNAME -e "source static/sql/laser_welding_v7_packing_seed.sql"
-- =============================================================================

-- ---------------------------------------------------------------------------
-- ITEM_MASTER — trays (27)
-- ---------------------------------------------------------------------------
INSERT INTO ITEM_MASTER (ITEM_MASTER_ID, ITEM_CODE, ITEM_NAME, CUST_ID, CATEGORY_CODE, REVISION, UOM, LAST_UPDATED_DATE)
SELECT UUID(), 'SE-1-2P-14C-1', 'Tray', NULL, 'BO', '1', 'NOS', CURDATE()
WHERE NOT EXISTS (SELECT 1 FROM ITEM_MASTER WHERE TRIM(ITEM_CODE) = 'SE-1-2P-14C-1');
INSERT INTO ITEM_MASTER (ITEM_MASTER_ID, ITEM_CODE, ITEM_NAME, CUST_ID, CATEGORY_CODE, REVISION, UOM, LAST_UPDATED_DATE)
SELECT UUID(), 'SE-1-2P-15C-1', 'Tray', NULL, 'BO', '1', 'NOS', CURDATE()
WHERE NOT EXISTS (SELECT 1 FROM ITEM_MASTER WHERE TRIM(ITEM_CODE) = 'SE-1-2P-15C-1');
INSERT INTO ITEM_MASTER (ITEM_MASTER_ID, ITEM_CODE, ITEM_NAME, CUST_ID, CATEGORY_CODE, REVISION, UOM, LAST_UPDATED_DATE)
SELECT UUID(), 'SE-1-2P-6C-1', 'Tray', NULL, 'BO', '1', 'NOS', CURDATE()
WHERE NOT EXISTS (SELECT 1 FROM ITEM_MASTER WHERE TRIM(ITEM_CODE) = 'SE-1-2P-6C-1');
INSERT INTO ITEM_MASTER (ITEM_MASTER_ID, ITEM_CODE, ITEM_NAME, CUST_ID, CATEGORY_CODE, REVISION, UOM, LAST_UPDATED_DATE)
SELECT UUID(), 'SE-1-2P-6C-2', 'Tray', NULL, 'BO', '1', 'NOS', CURDATE()
WHERE NOT EXISTS (SELECT 1 FROM ITEM_MASTER WHERE TRIM(ITEM_CODE) = 'SE-1-2P-6C-2');
INSERT INTO ITEM_MASTER (ITEM_MASTER_ID, ITEM_CODE, ITEM_NAME, CUST_ID, CATEGORY_CODE, REVISION, UOM, LAST_UPDATED_DATE)
SELECT UUID(), 'SE-1-4P-4C-1', 'Tray', NULL, 'BO', '1', 'NOS', CURDATE()
WHERE NOT EXISTS (SELECT 1 FROM ITEM_MASTER WHERE TRIM(ITEM_CODE) = 'SE-1-4P-4C-1');
INSERT INTO ITEM_MASTER (ITEM_MASTER_ID, ITEM_CODE, ITEM_NAME, CUST_ID, CATEGORY_CODE, REVISION, UOM, LAST_UPDATED_DATE)
SELECT UUID(), 'SE-1-S-121C-1', 'Tray', NULL, 'BO', '1', 'NOS', CURDATE()
WHERE NOT EXISTS (SELECT 1 FROM ITEM_MASTER WHERE TRIM(ITEM_CODE) = 'SE-1-S-121C-1');
INSERT INTO ITEM_MASTER (ITEM_MASTER_ID, ITEM_CODE, ITEM_NAME, CUST_ID, CATEGORY_CODE, REVISION, UOM, LAST_UPDATED_DATE)
SELECT UUID(), 'SE-1-S-12C-1', 'Tray', NULL, 'BO', '1', 'NOS', CURDATE()
WHERE NOT EXISTS (SELECT 1 FROM ITEM_MASTER WHERE TRIM(ITEM_CODE) = 'SE-1-S-12C-1');
INSERT INTO ITEM_MASTER (ITEM_MASTER_ID, ITEM_CODE, ITEM_NAME, CUST_ID, CATEGORY_CODE, REVISION, UOM, LAST_UPDATED_DATE)
SELECT UUID(), 'SE-1-S-14C-1', 'Tray', NULL, 'BO', '1', 'NOS', CURDATE()
WHERE NOT EXISTS (SELECT 1 FROM ITEM_MASTER WHERE TRIM(ITEM_CODE) = 'SE-1-S-14C-1');
INSERT INTO ITEM_MASTER (ITEM_MASTER_ID, ITEM_CODE, ITEM_NAME, CUST_ID, CATEGORY_CODE, REVISION, UOM, LAST_UPDATED_DATE)
SELECT UUID(), 'SE-1-S-14C-2', 'Tray', NULL, 'BO', '1', 'NOS', CURDATE()
WHERE NOT EXISTS (SELECT 1 FROM ITEM_MASTER WHERE TRIM(ITEM_CODE) = 'SE-1-S-14C-2');
INSERT INTO ITEM_MASTER (ITEM_MASTER_ID, ITEM_CODE, ITEM_NAME, CUST_ID, CATEGORY_CODE, REVISION, UOM, LAST_UPDATED_DATE)
SELECT UUID(), 'SE-1-S-14C-3', 'Tray', NULL, 'BO', '1', 'NOS', CURDATE()
WHERE NOT EXISTS (SELECT 1 FROM ITEM_MASTER WHERE TRIM(ITEM_CODE) = 'SE-1-S-14C-3');
INSERT INTO ITEM_MASTER (ITEM_MASTER_ID, ITEM_CODE, ITEM_NAME, CUST_ID, CATEGORY_CODE, REVISION, UOM, LAST_UPDATED_DATE)
SELECT UUID(), 'SE-1-S-15C-1', 'Tray', NULL, 'BO', '1', 'NOS', CURDATE()
WHERE NOT EXISTS (SELECT 1 FROM ITEM_MASTER WHERE TRIM(ITEM_CODE) = 'SE-1-S-15C-1');
INSERT INTO ITEM_MASTER (ITEM_MASTER_ID, ITEM_CODE, ITEM_NAME, CUST_ID, CATEGORY_CODE, REVISION, UOM, LAST_UPDATED_DATE)
SELECT UUID(), 'SE-1-S-16C-1', 'Tray', NULL, 'BO', '1', 'NOS', CURDATE()
WHERE NOT EXISTS (SELECT 1 FROM ITEM_MASTER WHERE TRIM(ITEM_CODE) = 'SE-1-S-16C-1');
INSERT INTO ITEM_MASTER (ITEM_MASTER_ID, ITEM_CODE, ITEM_NAME, CUST_ID, CATEGORY_CODE, REVISION, UOM, LAST_UPDATED_DATE)
SELECT UUID(), 'SE-1-S-18C-1', 'Tray', NULL, 'BO', '1', 'NOS', CURDATE()
WHERE NOT EXISTS (SELECT 1 FROM ITEM_MASTER WHERE TRIM(ITEM_CODE) = 'SE-1-S-18C-1');
INSERT INTO ITEM_MASTER (ITEM_MASTER_ID, ITEM_CODE, ITEM_NAME, CUST_ID, CATEGORY_CODE, REVISION, UOM, LAST_UPDATED_DATE)
SELECT UUID(), 'SE-1-S-20C-1', 'Tray', NULL, 'BO', '1', 'NOS', CURDATE()
WHERE NOT EXISTS (SELECT 1 FROM ITEM_MASTER WHERE TRIM(ITEM_CODE) = 'SE-1-S-20C-1');
INSERT INTO ITEM_MASTER (ITEM_MASTER_ID, ITEM_CODE, ITEM_NAME, CUST_ID, CATEGORY_CODE, REVISION, UOM, LAST_UPDATED_DATE)
SELECT UUID(), 'SE-1-S-24C-1', 'Tray', NULL, 'BO', '1', 'NOS', CURDATE()
WHERE NOT EXISTS (SELECT 1 FROM ITEM_MASTER WHERE TRIM(ITEM_CODE) = 'SE-1-S-24C-1');
INSERT INTO ITEM_MASTER (ITEM_MASTER_ID, ITEM_CODE, ITEM_NAME, CUST_ID, CATEGORY_CODE, REVISION, UOM, LAST_UPDATED_DATE)
SELECT UUID(), 'SE-1-S-25C-1', 'Tray', NULL, 'BO', '1', 'NOS', CURDATE()
WHERE NOT EXISTS (SELECT 1 FROM ITEM_MASTER WHERE TRIM(ITEM_CODE) = 'SE-1-S-25C-1');
INSERT INTO ITEM_MASTER (ITEM_MASTER_ID, ITEM_CODE, ITEM_NAME, CUST_ID, CATEGORY_CODE, REVISION, UOM, LAST_UPDATED_DATE)
SELECT UUID(), 'SE-1-S-28C-1', 'Tray', NULL, 'BO', '1', 'NOS', CURDATE()
WHERE NOT EXISTS (SELECT 1 FROM ITEM_MASTER WHERE TRIM(ITEM_CODE) = 'SE-1-S-28C-1');
INSERT INTO ITEM_MASTER (ITEM_MASTER_ID, ITEM_CODE, ITEM_NAME, CUST_ID, CATEGORY_CODE, REVISION, UOM, LAST_UPDATED_DATE)
SELECT UUID(), 'SE-1-S-28C-2', 'Tray', NULL, 'BO', '1', 'NOS', CURDATE()
WHERE NOT EXISTS (SELECT 1 FROM ITEM_MASTER WHERE TRIM(ITEM_CODE) = 'SE-1-S-28C-2');
INSERT INTO ITEM_MASTER (ITEM_MASTER_ID, ITEM_CODE, ITEM_NAME, CUST_ID, CATEGORY_CODE, REVISION, UOM, LAST_UPDATED_DATE)
SELECT UUID(), 'SE-1-S-6C-1', 'Tray', NULL, 'BO', '1', 'NOS', CURDATE()
WHERE NOT EXISTS (SELECT 1 FROM ITEM_MASTER WHERE TRIM(ITEM_CODE) = 'SE-1-S-6C-1');
INSERT INTO ITEM_MASTER (ITEM_MASTER_ID, ITEM_CODE, ITEM_NAME, CUST_ID, CATEGORY_CODE, REVISION, UOM, LAST_UPDATED_DATE)
SELECT UUID(), 'SE-1-S-6C-2', 'Tray', NULL, 'BO', '1', 'NOS', CURDATE()
WHERE NOT EXISTS (SELECT 1 FROM ITEM_MASTER WHERE TRIM(ITEM_CODE) = 'SE-1-S-6C-2');
INSERT INTO ITEM_MASTER (ITEM_MASTER_ID, ITEM_CODE, ITEM_NAME, CUST_ID, CATEGORY_CODE, REVISION, UOM, LAST_UPDATED_DATE)
SELECT UUID(), 'SE-1-S-7C-1', 'Tray', NULL, 'BO', '1', 'NOS', CURDATE()
WHERE NOT EXISTS (SELECT 1 FROM ITEM_MASTER WHERE TRIM(ITEM_CODE) = 'SE-1-S-7C-1');
INSERT INTO ITEM_MASTER (ITEM_MASTER_ID, ITEM_CODE, ITEM_NAME, CUST_ID, CATEGORY_CODE, REVISION, UOM, LAST_UPDATED_DATE)
SELECT UUID(), 'SE-1-S-7C-2', 'Tray', NULL, 'BO', '1', 'NOS', CURDATE()
WHERE NOT EXISTS (SELECT 1 FROM ITEM_MASTER WHERE TRIM(ITEM_CODE) = 'SE-1-S-7C-2');
INSERT INTO ITEM_MASTER (ITEM_MASTER_ID, ITEM_CODE, ITEM_NAME, CUST_ID, CATEGORY_CODE, REVISION, UOM, LAST_UPDATED_DATE)
SELECT UUID(), 'SE-1-S-7C-3', 'Tray', NULL, 'BO', '1', 'NOS', CURDATE()
WHERE NOT EXISTS (SELECT 1 FROM ITEM_MASTER WHERE TRIM(ITEM_CODE) = 'SE-1-S-7C-3');
INSERT INTO ITEM_MASTER (ITEM_MASTER_ID, ITEM_CODE, ITEM_NAME, CUST_ID, CATEGORY_CODE, REVISION, UOM, LAST_UPDATED_DATE)
SELECT UUID(), 'SE-1-S-8C-1', 'Tray', NULL, 'BO', '1', 'NOS', CURDATE()
WHERE NOT EXISTS (SELECT 1 FROM ITEM_MASTER WHERE TRIM(ITEM_CODE) = 'SE-1-S-8C-1');
INSERT INTO ITEM_MASTER (ITEM_MASTER_ID, ITEM_CODE, ITEM_NAME, CUST_ID, CATEGORY_CODE, REVISION, UOM, LAST_UPDATED_DATE)
SELECT UUID(), 'SE-2-S-130C-1', 'Tray', NULL, 'BO', '1', 'NOS', CURDATE()
WHERE NOT EXISTS (SELECT 1 FROM ITEM_MASTER WHERE TRIM(ITEM_CODE) = 'SE-2-S-130C-1');
INSERT INTO ITEM_MASTER (ITEM_MASTER_ID, ITEM_CODE, ITEM_NAME, CUST_ID, CATEGORY_CODE, REVISION, UOM, LAST_UPDATED_DATE)
SELECT UUID(), 'SE-2-S-88C-1', 'Tray', NULL, 'BO', '1', 'NOS', CURDATE()
WHERE NOT EXISTS (SELECT 1 FROM ITEM_MASTER WHERE TRIM(ITEM_CODE) = 'SE-2-S-88C-1');
INSERT INTO ITEM_MASTER (ITEM_MASTER_ID, ITEM_CODE, ITEM_NAME, CUST_ID, CATEGORY_CODE, REVISION, UOM, LAST_UPDATED_DATE)
SELECT UUID(), 'SE-2-S-88C-2', 'Tray', NULL, 'BO', '1', 'NOS', CURDATE()
WHERE NOT EXISTS (SELECT 1 FROM ITEM_MASTER WHERE TRIM(ITEM_CODE) = 'SE-2-S-88C-2');

-- ---------------------------------------------------------------------------
-- ITEM_MASTER — cartons/bins (11)
-- ---------------------------------------------------------------------------
INSERT INTO ITEM_MASTER (ITEM_MASTER_ID, ITEM_CODE, ITEM_NAME, CUST_ID, CATEGORY_CODE, REVISION, UOM, LAST_UPDATED_DATE)
SELECT UUID(), 'SE-B-600400125-1', 'Carton', NULL, 'BO', '1', 'NOS', CURDATE()
WHERE NOT EXISTS (SELECT 1 FROM ITEM_MASTER WHERE TRIM(ITEM_CODE) = 'SE-B-600400125-1');
INSERT INTO ITEM_MASTER (ITEM_MASTER_ID, ITEM_CODE, ITEM_NAME, CUST_ID, CATEGORY_CODE, REVISION, UOM, LAST_UPDATED_DATE)
SELECT UUID(), 'SE-B-600400125-2', 'Carton', NULL, 'BO', '1', 'NOS', CURDATE()
WHERE NOT EXISTS (SELECT 1 FROM ITEM_MASTER WHERE TRIM(ITEM_CODE) = 'SE-B-600400125-2');
INSERT INTO ITEM_MASTER (ITEM_MASTER_ID, ITEM_CODE, ITEM_NAME, CUST_ID, CATEGORY_CODE, REVISION, UOM, LAST_UPDATED_DATE)
SELECT UUID(), 'SE-C-330280500', 'Carton', NULL, 'BO', '1', 'NOS', CURDATE()
WHERE NOT EXISTS (SELECT 1 FROM ITEM_MASTER WHERE TRIM(ITEM_CODE) = 'SE-C-330280500');
INSERT INTO ITEM_MASTER (ITEM_MASTER_ID, ITEM_CODE, ITEM_NAME, CUST_ID, CATEGORY_CODE, REVISION, UOM, LAST_UPDATED_DATE)
SELECT UUID(), 'SE-C-345220360', 'Carton', NULL, 'BO', '1', 'NOS', CURDATE()
WHERE NOT EXISTS (SELECT 1 FROM ITEM_MASTER WHERE TRIM(ITEM_CODE) = 'SE-C-345220360');
INSERT INTO ITEM_MASTER (ITEM_MASTER_ID, ITEM_CODE, ITEM_NAME, CUST_ID, CATEGORY_CODE, REVISION, UOM, LAST_UPDATED_DATE)
SELECT UUID(), 'SE-C-355300200', 'Carton', NULL, 'BO', '1', 'NOS', CURDATE()
WHERE NOT EXISTS (SELECT 1 FROM ITEM_MASTER WHERE TRIM(ITEM_CODE) = 'SE-C-355300200');
INSERT INTO ITEM_MASTER (ITEM_MASTER_ID, ITEM_CODE, ITEM_NAME, CUST_ID, CATEGORY_CODE, REVISION, UOM, LAST_UPDATED_DATE)
SELECT UUID(), 'SE-C-380220360', 'Carton', NULL, 'BO', '1', 'NOS', CURDATE()
WHERE NOT EXISTS (SELECT 1 FROM ITEM_MASTER WHERE TRIM(ITEM_CODE) = 'SE-C-380220360');
INSERT INTO ITEM_MASTER (ITEM_MASTER_ID, ITEM_CODE, ITEM_NAME, CUST_ID, CATEGORY_CODE, REVISION, UOM, LAST_UPDATED_DATE)
SELECT UUID(), 'SE-C-380280185', 'Carton', NULL, 'BO', '1', 'NOS', CURDATE()
WHERE NOT EXISTS (SELECT 1 FROM ITEM_MASTER WHERE TRIM(ITEM_CODE) = 'SE-C-380280185');
INSERT INTO ITEM_MASTER (ITEM_MASTER_ID, ITEM_CODE, ITEM_NAME, CUST_ID, CATEGORY_CODE, REVISION, UOM, LAST_UPDATED_DATE)
SELECT UUID(), 'SE-C-415240360', 'Carton', NULL, 'BO', '1', 'NOS', CURDATE()
WHERE NOT EXISTS (SELECT 1 FROM ITEM_MASTER WHERE TRIM(ITEM_CODE) = 'SE-C-415240360');
INSERT INTO ITEM_MASTER (ITEM_MASTER_ID, ITEM_CODE, ITEM_NAME, CUST_ID, CATEGORY_CODE, REVISION, UOM, LAST_UPDATED_DATE)
SELECT UUID(), 'SE-C-450235185', 'Carton', NULL, 'BO', '1', 'NOS', CURDATE()
WHERE NOT EXISTS (SELECT 1 FROM ITEM_MASTER WHERE TRIM(ITEM_CODE) = 'SE-C-450235185');
INSERT INTO ITEM_MASTER (ITEM_MASTER_ID, ITEM_CODE, ITEM_NAME, CUST_ID, CATEGORY_CODE, REVISION, UOM, LAST_UPDATED_DATE)
SELECT UUID(), 'SE-C-430315075', 'Carton', NULL, 'BO', '1', 'NOS', CURDATE()
WHERE NOT EXISTS (SELECT 1 FROM ITEM_MASTER WHERE TRIM(ITEM_CODE) = 'SE-C-430315075');
INSERT INTO ITEM_MASTER (ITEM_MASTER_ID, ITEM_CODE, ITEM_NAME, CUST_ID, CATEGORY_CODE, REVISION, UOM, LAST_UPDATED_DATE)
SELECT UUID(), 'SE-C-470310185', 'Carton', NULL, 'BO', '1', 'NOS', CURDATE()
WHERE NOT EXISTS (SELECT 1 FROM ITEM_MASTER WHERE TRIM(ITEM_CODE) = 'SE-C-470310185');

-- ---------------------------------------------------------------------------
-- lw_packing_tray (27)
-- ---------------------------------------------------------------------------
INSERT INTO lw_packing_tray (tray_item_code, material, type, cavity, cust_id)
SELECT 'SE-1-2P-14C-1', 1, '2P', 14, NULL
WHERE NOT EXISTS (SELECT 1 FROM lw_packing_tray WHERE tray_item_code = 'SE-1-2P-14C-1');
INSERT INTO lw_packing_tray (tray_item_code, material, type, cavity, cust_id)
SELECT 'SE-1-2P-15C-1', 1, '2P', 15, NULL
WHERE NOT EXISTS (SELECT 1 FROM lw_packing_tray WHERE tray_item_code = 'SE-1-2P-15C-1');
INSERT INTO lw_packing_tray (tray_item_code, material, type, cavity, cust_id)
SELECT 'SE-1-2P-6C-1', 1, '2P', 6, NULL
WHERE NOT EXISTS (SELECT 1 FROM lw_packing_tray WHERE tray_item_code = 'SE-1-2P-6C-1');
INSERT INTO lw_packing_tray (tray_item_code, material, type, cavity, cust_id)
SELECT 'SE-1-2P-6C-2', 1, '2P', 6, NULL
WHERE NOT EXISTS (SELECT 1 FROM lw_packing_tray WHERE tray_item_code = 'SE-1-2P-6C-2');
INSERT INTO lw_packing_tray (tray_item_code, material, type, cavity, cust_id)
SELECT 'SE-1-4P-4C-1', 1, '4P', 4, NULL
WHERE NOT EXISTS (SELECT 1 FROM lw_packing_tray WHERE tray_item_code = 'SE-1-4P-4C-1');
INSERT INTO lw_packing_tray (tray_item_code, material, type, cavity, cust_id)
SELECT 'SE-1-S-121C-1', 1, 'S', 121, NULL
WHERE NOT EXISTS (SELECT 1 FROM lw_packing_tray WHERE tray_item_code = 'SE-1-S-121C-1');
INSERT INTO lw_packing_tray (tray_item_code, material, type, cavity, cust_id)
SELECT 'SE-1-S-12C-1', 1, 'S', 12, NULL
WHERE NOT EXISTS (SELECT 1 FROM lw_packing_tray WHERE tray_item_code = 'SE-1-S-12C-1');
INSERT INTO lw_packing_tray (tray_item_code, material, type, cavity, cust_id)
SELECT 'SE-1-S-14C-1', 1, 'S', 14, NULL
WHERE NOT EXISTS (SELECT 1 FROM lw_packing_tray WHERE tray_item_code = 'SE-1-S-14C-1');
INSERT INTO lw_packing_tray (tray_item_code, material, type, cavity, cust_id)
SELECT 'SE-1-S-14C-2', 1, 'S', 14, NULL
WHERE NOT EXISTS (SELECT 1 FROM lw_packing_tray WHERE tray_item_code = 'SE-1-S-14C-2');
INSERT INTO lw_packing_tray (tray_item_code, material, type, cavity, cust_id)
SELECT 'SE-1-S-14C-3', 1, 'S', 14, NULL
WHERE NOT EXISTS (SELECT 1 FROM lw_packing_tray WHERE tray_item_code = 'SE-1-S-14C-3');
INSERT INTO lw_packing_tray (tray_item_code, material, type, cavity, cust_id)
SELECT 'SE-1-S-15C-1', 1, 'S', 15, NULL
WHERE NOT EXISTS (SELECT 1 FROM lw_packing_tray WHERE tray_item_code = 'SE-1-S-15C-1');
INSERT INTO lw_packing_tray (tray_item_code, material, type, cavity, cust_id)
SELECT 'SE-1-S-16C-1', 1, 'S', 16, NULL
WHERE NOT EXISTS (SELECT 1 FROM lw_packing_tray WHERE tray_item_code = 'SE-1-S-16C-1');
INSERT INTO lw_packing_tray (tray_item_code, material, type, cavity, cust_id)
SELECT 'SE-1-S-18C-1', 1, 'S', 18, NULL
WHERE NOT EXISTS (SELECT 1 FROM lw_packing_tray WHERE tray_item_code = 'SE-1-S-18C-1');
INSERT INTO lw_packing_tray (tray_item_code, material, type, cavity, cust_id)
SELECT 'SE-1-S-20C-1', 1, 'S', 20, NULL
WHERE NOT EXISTS (SELECT 1 FROM lw_packing_tray WHERE tray_item_code = 'SE-1-S-20C-1');
INSERT INTO lw_packing_tray (tray_item_code, material, type, cavity, cust_id)
SELECT 'SE-1-S-24C-1', 1, 'S', 24, NULL
WHERE NOT EXISTS (SELECT 1 FROM lw_packing_tray WHERE tray_item_code = 'SE-1-S-24C-1');
INSERT INTO lw_packing_tray (tray_item_code, material, type, cavity, cust_id)
SELECT 'SE-1-S-25C-1', 1, 'S', 25, NULL
WHERE NOT EXISTS (SELECT 1 FROM lw_packing_tray WHERE tray_item_code = 'SE-1-S-25C-1');
INSERT INTO lw_packing_tray (tray_item_code, material, type, cavity, cust_id)
SELECT 'SE-1-S-28C-1', 1, 'S', 28, NULL
WHERE NOT EXISTS (SELECT 1 FROM lw_packing_tray WHERE tray_item_code = 'SE-1-S-28C-1');
INSERT INTO lw_packing_tray (tray_item_code, material, type, cavity, cust_id)
SELECT 'SE-1-S-28C-2', 1, 'S', 28, NULL
WHERE NOT EXISTS (SELECT 1 FROM lw_packing_tray WHERE tray_item_code = 'SE-1-S-28C-2');
INSERT INTO lw_packing_tray (tray_item_code, material, type, cavity, cust_id)
SELECT 'SE-1-S-6C-1', 1, 'S', 6, NULL
WHERE NOT EXISTS (SELECT 1 FROM lw_packing_tray WHERE tray_item_code = 'SE-1-S-6C-1');
INSERT INTO lw_packing_tray (tray_item_code, material, type, cavity, cust_id)
SELECT 'SE-1-S-6C-2', 1, 'S', 6, NULL
WHERE NOT EXISTS (SELECT 1 FROM lw_packing_tray WHERE tray_item_code = 'SE-1-S-6C-2');
INSERT INTO lw_packing_tray (tray_item_code, material, type, cavity, cust_id)
SELECT 'SE-1-S-7C-1', 1, 'S', 7, NULL
WHERE NOT EXISTS (SELECT 1 FROM lw_packing_tray WHERE tray_item_code = 'SE-1-S-7C-1');
INSERT INTO lw_packing_tray (tray_item_code, material, type, cavity, cust_id)
SELECT 'SE-1-S-7C-2', 1, 'S', 7, NULL
WHERE NOT EXISTS (SELECT 1 FROM lw_packing_tray WHERE tray_item_code = 'SE-1-S-7C-2');
INSERT INTO lw_packing_tray (tray_item_code, material, type, cavity, cust_id)
SELECT 'SE-1-S-7C-3', 1, 'S', 7, NULL
WHERE NOT EXISTS (SELECT 1 FROM lw_packing_tray WHERE tray_item_code = 'SE-1-S-7C-3');
INSERT INTO lw_packing_tray (tray_item_code, material, type, cavity, cust_id)
SELECT 'SE-1-S-8C-1', 1, 'S', 8, NULL
WHERE NOT EXISTS (SELECT 1 FROM lw_packing_tray WHERE tray_item_code = 'SE-1-S-8C-1');
INSERT INTO lw_packing_tray (tray_item_code, material, type, cavity, cust_id)
SELECT 'SE-2-S-130C-1', 2, 'S', 130, NULL
WHERE NOT EXISTS (SELECT 1 FROM lw_packing_tray WHERE tray_item_code = 'SE-2-S-130C-1');
INSERT INTO lw_packing_tray (tray_item_code, material, type, cavity, cust_id)
SELECT 'SE-2-S-88C-1', 2, 'S', 88, NULL
WHERE NOT EXISTS (SELECT 1 FROM lw_packing_tray WHERE tray_item_code = 'SE-2-S-88C-1');
INSERT INTO lw_packing_tray (tray_item_code, material, type, cavity, cust_id)
SELECT 'SE-2-S-88C-2', 2, 'S', 88, NULL
WHERE NOT EXISTS (SELECT 1 FROM lw_packing_tray WHERE tray_item_code = 'SE-2-S-88C-2');

-- ---------------------------------------------------------------------------
-- lw_packing_carton (11)
-- ---------------------------------------------------------------------------
INSERT INTO lw_packing_carton (carton_item_code, length_mm, width_mm, height_mm)
SELECT 'SE-B-600400125-1', 600, 400, 125
WHERE NOT EXISTS (SELECT 1 FROM lw_packing_carton WHERE carton_item_code = 'SE-B-600400125-1');
INSERT INTO lw_packing_carton (carton_item_code, length_mm, width_mm, height_mm)
SELECT 'SE-B-600400125-2', 600, 400, 125
WHERE NOT EXISTS (SELECT 1 FROM lw_packing_carton WHERE carton_item_code = 'SE-B-600400125-2');
INSERT INTO lw_packing_carton (carton_item_code, length_mm, width_mm, height_mm)
SELECT 'SE-C-330280500', 330, 280, 500
WHERE NOT EXISTS (SELECT 1 FROM lw_packing_carton WHERE carton_item_code = 'SE-C-330280500');
INSERT INTO lw_packing_carton (carton_item_code, length_mm, width_mm, height_mm)
SELECT 'SE-C-345220360', 345, 220, 360
WHERE NOT EXISTS (SELECT 1 FROM lw_packing_carton WHERE carton_item_code = 'SE-C-345220360');
INSERT INTO lw_packing_carton (carton_item_code, length_mm, width_mm, height_mm)
SELECT 'SE-C-355300200', 355, 300, 200
WHERE NOT EXISTS (SELECT 1 FROM lw_packing_carton WHERE carton_item_code = 'SE-C-355300200');
INSERT INTO lw_packing_carton (carton_item_code, length_mm, width_mm, height_mm)
SELECT 'SE-C-380220360', 380, 220, 360
WHERE NOT EXISTS (SELECT 1 FROM lw_packing_carton WHERE carton_item_code = 'SE-C-380220360');
INSERT INTO lw_packing_carton (carton_item_code, length_mm, width_mm, height_mm)
SELECT 'SE-C-380280185', 380, 280, 185
WHERE NOT EXISTS (SELECT 1 FROM lw_packing_carton WHERE carton_item_code = 'SE-C-380280185');
INSERT INTO lw_packing_carton (carton_item_code, length_mm, width_mm, height_mm)
SELECT 'SE-C-415240360', 415, 240, 360
WHERE NOT EXISTS (SELECT 1 FROM lw_packing_carton WHERE carton_item_code = 'SE-C-415240360');
INSERT INTO lw_packing_carton (carton_item_code, length_mm, width_mm, height_mm)
SELECT 'SE-C-450235185', 450, 235, 185
WHERE NOT EXISTS (SELECT 1 FROM lw_packing_carton WHERE carton_item_code = 'SE-C-450235185');
INSERT INTO lw_packing_carton (carton_item_code, length_mm, width_mm, height_mm)
SELECT 'SE-C-430315075', 430, 315, 75
WHERE NOT EXISTS (SELECT 1 FROM lw_packing_carton WHERE carton_item_code = 'SE-C-430315075');
INSERT INTO lw_packing_carton (carton_item_code, length_mm, width_mm, height_mm)
SELECT 'SE-C-470310185', 470, 310, 185
WHERE NOT EXISTS (SELECT 1 FROM lw_packing_carton WHERE carton_item_code = 'SE-C-470310185');

-- ---------------------------------------------------------------------------
-- lw_packing_part_map (37 parts with trays)
-- Skipped: RIVER/R107017351 (carton-only, no tray — SE-C-430315075 seeded above)
-- ---------------------------------------------------------------------------
-- ATHER / BY00000480_PILOT
INSERT INTO lw_packing_part_map (co_id, bom_id, cust_id, tray_item_code, carton_item_code, tray_capacity, carton_capacity)
SELECT src.co_id, src.bom_id, src.cust_id, 'SE-1-S-28C-1', 'SE-B-600400125-2', 16, 448
FROM (
    SELECT
        (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'BY00000480_PILOT'
          AND TRIM(cu.CU_Name) LIKE '%ATHER%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) AS co_id,
        CASE WHEN (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'BY00000480_PILOT'
          AND TRIM(cu.CU_Name) LIKE '%ATHER%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) IS NULL THEN (
        SELECT b.bom_id
        FROM bom b
        INNER JOIN customer cu ON cu.CU_Id = b.cust_id
        WHERE TRIM(b.bom_no) = 'BY00000480_PILOT'
          AND b.is_latest_version = 'Y'
          AND TRIM(cu.CU_Name) LIKE '%ATHER%'
        ORDER BY b.cust_id
        LIMIT 1
    ) ELSE NULL END AS bom_id,
        COALESCE(
        (SELECT c.CO_CUSTID FROM components c
         INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
         WHERE TRIM(c.CO_PARTNO) = 'BY00000480_PILOT' AND TRIM(cu.CU_Name) LIKE '%ATHER%' AND c.CO_ACTIVEYN = 'Y'
         ORDER BY c.CO_ID DESC LIMIT 1),
        (SELECT b.cust_id FROM bom b
         INNER JOIN customer cu ON cu.CU_Id = b.cust_id
         WHERE TRIM(b.bom_no) = 'BY00000480_PILOT' AND b.is_latest_version = 'Y' AND TRIM(cu.CU_Name) LIKE '%ATHER%'
         LIMIT 1),
        (SELECT cu.CU_Id FROM customer cu WHERE TRIM(cu.CU_Name) LIKE '%ATHER%' LIMIT 1)
    ) AS cust_id
) src
WHERE (src.co_id IS NOT NULL OR src.bom_id IS NOT NULL)
  AND NOT EXISTS (
    SELECT 1 FROM lw_packing_part_map m
    WHERE (
        (src.co_id IS NOT NULL AND m.co_id = src.co_id AND (m.cust_id = src.cust_id OR (m.cust_id IS NULL AND src.cust_id IS NULL)))
        OR (src.bom_id IS NOT NULL AND m.bom_id = src.bom_id AND m.cust_id = src.cust_id)
    )
  );


-- ATHER / BY00000481
INSERT INTO lw_packing_part_map (co_id, bom_id, cust_id, tray_item_code, carton_item_code, tray_capacity, carton_capacity)
SELECT src.co_id, src.bom_id, src.cust_id, 'SE-1-S-14C-1', 'SE-B-600400125-1', 8, 112
FROM (
    SELECT
        (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'BY00000481'
          AND TRIM(cu.CU_Name) LIKE '%ATHER%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) AS co_id,
        CASE WHEN (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'BY00000481'
          AND TRIM(cu.CU_Name) LIKE '%ATHER%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) IS NULL THEN (
        SELECT b.bom_id
        FROM bom b
        INNER JOIN customer cu ON cu.CU_Id = b.cust_id
        WHERE TRIM(b.bom_no) = 'BY00000481'
          AND b.is_latest_version = 'Y'
          AND TRIM(cu.CU_Name) LIKE '%ATHER%'
        ORDER BY b.cust_id
        LIMIT 1
    ) ELSE NULL END AS bom_id,
        COALESCE(
        (SELECT c.CO_CUSTID FROM components c
         INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
         WHERE TRIM(c.CO_PARTNO) = 'BY00000481' AND TRIM(cu.CU_Name) LIKE '%ATHER%' AND c.CO_ACTIVEYN = 'Y'
         ORDER BY c.CO_ID DESC LIMIT 1),
        (SELECT b.cust_id FROM bom b
         INNER JOIN customer cu ON cu.CU_Id = b.cust_id
         WHERE TRIM(b.bom_no) = 'BY00000481' AND b.is_latest_version = 'Y' AND TRIM(cu.CU_Name) LIKE '%ATHER%'
         LIMIT 1),
        (SELECT cu.CU_Id FROM customer cu WHERE TRIM(cu.CU_Name) LIKE '%ATHER%' LIMIT 1)
    ) AS cust_id
) src
WHERE (src.co_id IS NOT NULL OR src.bom_id IS NOT NULL)
  AND NOT EXISTS (
    SELECT 1 FROM lw_packing_part_map m
    WHERE (
        (src.co_id IS NOT NULL AND m.co_id = src.co_id AND (m.cust_id = src.cust_id OR (m.cust_id IS NULL AND src.cust_id IS NULL)))
        OR (src.bom_id IS NOT NULL AND m.bom_id = src.bom_id AND m.cust_id = src.cust_id)
    )
  );


-- ATHER / BY00000484
INSERT INTO lw_packing_part_map (co_id, bom_id, cust_id, tray_item_code, carton_item_code, tray_capacity, carton_capacity)
SELECT src.co_id, src.bom_id, src.cust_id, 'SE-1-S-14C-2', 'SE-B-600400125-1', 8, 112
FROM (
    SELECT
        (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'BY00000484'
          AND TRIM(cu.CU_Name) LIKE '%ATHER%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) AS co_id,
        CASE WHEN (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'BY00000484'
          AND TRIM(cu.CU_Name) LIKE '%ATHER%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) IS NULL THEN (
        SELECT b.bom_id
        FROM bom b
        INNER JOIN customer cu ON cu.CU_Id = b.cust_id
        WHERE TRIM(b.bom_no) = 'BY00000484'
          AND b.is_latest_version = 'Y'
          AND TRIM(cu.CU_Name) LIKE '%ATHER%'
        ORDER BY b.cust_id
        LIMIT 1
    ) ELSE NULL END AS bom_id,
        COALESCE(
        (SELECT c.CO_CUSTID FROM components c
         INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
         WHERE TRIM(c.CO_PARTNO) = 'BY00000484' AND TRIM(cu.CU_Name) LIKE '%ATHER%' AND c.CO_ACTIVEYN = 'Y'
         ORDER BY c.CO_ID DESC LIMIT 1),
        (SELECT b.cust_id FROM bom b
         INNER JOIN customer cu ON cu.CU_Id = b.cust_id
         WHERE TRIM(b.bom_no) = 'BY00000484' AND b.is_latest_version = 'Y' AND TRIM(cu.CU_Name) LIKE '%ATHER%'
         LIMIT 1),
        (SELECT cu.CU_Id FROM customer cu WHERE TRIM(cu.CU_Name) LIKE '%ATHER%' LIMIT 1)
    ) AS cust_id
) src
WHERE (src.co_id IS NOT NULL OR src.bom_id IS NOT NULL)
  AND NOT EXISTS (
    SELECT 1 FROM lw_packing_part_map m
    WHERE (
        (src.co_id IS NOT NULL AND m.co_id = src.co_id AND (m.cust_id = src.cust_id OR (m.cust_id IS NULL AND src.cust_id IS NULL)))
        OR (src.bom_id IS NOT NULL AND m.bom_id = src.bom_id AND m.cust_id = src.cust_id)
    )
  );


-- ATHER / BY00000560
INSERT INTO lw_packing_part_map (co_id, bom_id, cust_id, tray_item_code, carton_item_code, tray_capacity, carton_capacity)
SELECT src.co_id, src.bom_id, src.cust_id, 'SE-1-S-28C-2', 'SE-B-600400125-2', 16, 448
FROM (
    SELECT
        (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'BY00000560'
          AND TRIM(cu.CU_Name) LIKE '%ATHER%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) AS co_id,
        CASE WHEN (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'BY00000560'
          AND TRIM(cu.CU_Name) LIKE '%ATHER%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) IS NULL THEN (
        SELECT b.bom_id
        FROM bom b
        INNER JOIN customer cu ON cu.CU_Id = b.cust_id
        WHERE TRIM(b.bom_no) = 'BY00000560'
          AND b.is_latest_version = 'Y'
          AND TRIM(cu.CU_Name) LIKE '%ATHER%'
        ORDER BY b.cust_id
        LIMIT 1
    ) ELSE NULL END AS bom_id,
        COALESCE(
        (SELECT c.CO_CUSTID FROM components c
         INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
         WHERE TRIM(c.CO_PARTNO) = 'BY00000560' AND TRIM(cu.CU_Name) LIKE '%ATHER%' AND c.CO_ACTIVEYN = 'Y'
         ORDER BY c.CO_ID DESC LIMIT 1),
        (SELECT b.cust_id FROM bom b
         INNER JOIN customer cu ON cu.CU_Id = b.cust_id
         WHERE TRIM(b.bom_no) = 'BY00000560' AND b.is_latest_version = 'Y' AND TRIM(cu.CU_Name) LIKE '%ATHER%'
         LIMIT 1),
        (SELECT cu.CU_Id FROM customer cu WHERE TRIM(cu.CU_Name) LIKE '%ATHER%' LIMIT 1)
    ) AS cust_id
) src
WHERE (src.co_id IS NOT NULL OR src.bom_id IS NOT NULL)
  AND NOT EXISTS (
    SELECT 1 FROM lw_packing_part_map m
    WHERE (
        (src.co_id IS NOT NULL AND m.co_id = src.co_id AND (m.cust_id = src.cust_id OR (m.cust_id IS NULL AND src.cust_id IS NULL)))
        OR (src.bom_id IS NOT NULL AND m.bom_id = src.bom_id AND m.cust_id = src.cust_id)
    )
  );


-- ATHER / BY00002338_PILOT
INSERT INTO lw_packing_part_map (co_id, bom_id, cust_id, tray_item_code, carton_item_code, tray_capacity, carton_capacity)
SELECT src.co_id, src.bom_id, src.cust_id, 'SE-1-S-121C-1', 'SE-B-600400125-2', 4, 484
FROM (
    SELECT
        (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'BY00002338_PILOT'
          AND TRIM(cu.CU_Name) LIKE '%ATHER%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) AS co_id,
        CASE WHEN (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'BY00002338_PILOT'
          AND TRIM(cu.CU_Name) LIKE '%ATHER%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) IS NULL THEN (
        SELECT b.bom_id
        FROM bom b
        INNER JOIN customer cu ON cu.CU_Id = b.cust_id
        WHERE TRIM(b.bom_no) = 'BY00002338_PILOT'
          AND b.is_latest_version = 'Y'
          AND TRIM(cu.CU_Name) LIKE '%ATHER%'
        ORDER BY b.cust_id
        LIMIT 1
    ) ELSE NULL END AS bom_id,
        COALESCE(
        (SELECT c.CO_CUSTID FROM components c
         INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
         WHERE TRIM(c.CO_PARTNO) = 'BY00002338_PILOT' AND TRIM(cu.CU_Name) LIKE '%ATHER%' AND c.CO_ACTIVEYN = 'Y'
         ORDER BY c.CO_ID DESC LIMIT 1),
        (SELECT b.cust_id FROM bom b
         INNER JOIN customer cu ON cu.CU_Id = b.cust_id
         WHERE TRIM(b.bom_no) = 'BY00002338_PILOT' AND b.is_latest_version = 'Y' AND TRIM(cu.CU_Name) LIKE '%ATHER%'
         LIMIT 1),
        (SELECT cu.CU_Id FROM customer cu WHERE TRIM(cu.CU_Name) LIKE '%ATHER%' LIMIT 1)
    ) AS cust_id
) src
WHERE (src.co_id IS NOT NULL OR src.bom_id IS NOT NULL)
  AND NOT EXISTS (
    SELECT 1 FROM lw_packing_part_map m
    WHERE (
        (src.co_id IS NOT NULL AND m.co_id = src.co_id AND (m.cust_id = src.cust_id OR (m.cust_id IS NULL AND src.cust_id IS NULL)))
        OR (src.bom_id IS NOT NULL AND m.bom_id = src.bom_id AND m.cust_id = src.cust_id)
    )
  );


-- REML / RBB00007
INSERT INTO lw_packing_part_map (co_id, bom_id, cust_id, tray_item_code, carton_item_code, tray_capacity, carton_capacity)
SELECT src.co_id, src.bom_id, src.cust_id, 'SE-1-2P-15C-1', 'SE-B-600400125-2', 4, 4
FROM (
    SELECT
        (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'RBB00007'
          AND TRIM(cu.CU_Name) LIKE '%REML%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) AS co_id,
        CASE WHEN (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'RBB00007'
          AND TRIM(cu.CU_Name) LIKE '%REML%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) IS NULL THEN (
        SELECT b.bom_id
        FROM bom b
        INNER JOIN customer cu ON cu.CU_Id = b.cust_id
        WHERE TRIM(b.bom_no) = 'RBB00007'
          AND b.is_latest_version = 'Y'
          AND TRIM(cu.CU_Name) LIKE '%REML%'
        ORDER BY b.cust_id
        LIMIT 1
    ) ELSE NULL END AS bom_id,
        COALESCE(
        (SELECT c.CO_CUSTID FROM components c
         INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
         WHERE TRIM(c.CO_PARTNO) = 'RBB00007' AND TRIM(cu.CU_Name) LIKE '%REML%' AND c.CO_ACTIVEYN = 'Y'
         ORDER BY c.CO_ID DESC LIMIT 1),
        (SELECT b.cust_id FROM bom b
         INNER JOIN customer cu ON cu.CU_Id = b.cust_id
         WHERE TRIM(b.bom_no) = 'RBB00007' AND b.is_latest_version = 'Y' AND TRIM(cu.CU_Name) LIKE '%REML%'
         LIMIT 1),
        (SELECT cu.CU_Id FROM customer cu WHERE TRIM(cu.CU_Name) LIKE '%REML%' LIMIT 1)
    ) AS cust_id
) src
WHERE (src.co_id IS NOT NULL OR src.bom_id IS NOT NULL)
  AND NOT EXISTS (
    SELECT 1 FROM lw_packing_part_map m
    WHERE (
        (src.co_id IS NOT NULL AND m.co_id = src.co_id AND (m.cust_id = src.cust_id OR (m.cust_id IS NULL AND src.cust_id IS NULL)))
        OR (src.bom_id IS NOT NULL AND m.bom_id = src.bom_id AND m.cust_id = src.cust_id)
    )
  );


-- REML / RBB00008
INSERT INTO lw_packing_part_map (co_id, bom_id, cust_id, tray_item_code, carton_item_code, tray_capacity, carton_capacity)
SELECT src.co_id, src.bom_id, src.cust_id, 'SE-1-2P-15C-1', 'SE-B-600400125-2', 4, 4
FROM (
    SELECT
        (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'RBB00008'
          AND TRIM(cu.CU_Name) LIKE '%REML%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) AS co_id,
        CASE WHEN (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'RBB00008'
          AND TRIM(cu.CU_Name) LIKE '%REML%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) IS NULL THEN (
        SELECT b.bom_id
        FROM bom b
        INNER JOIN customer cu ON cu.CU_Id = b.cust_id
        WHERE TRIM(b.bom_no) = 'RBB00008'
          AND b.is_latest_version = 'Y'
          AND TRIM(cu.CU_Name) LIKE '%REML%'
        ORDER BY b.cust_id
        LIMIT 1
    ) ELSE NULL END AS bom_id,
        COALESCE(
        (SELECT c.CO_CUSTID FROM components c
         INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
         WHERE TRIM(c.CO_PARTNO) = 'RBB00008' AND TRIM(cu.CU_Name) LIKE '%REML%' AND c.CO_ACTIVEYN = 'Y'
         ORDER BY c.CO_ID DESC LIMIT 1),
        (SELECT b.cust_id FROM bom b
         INNER JOIN customer cu ON cu.CU_Id = b.cust_id
         WHERE TRIM(b.bom_no) = 'RBB00008' AND b.is_latest_version = 'Y' AND TRIM(cu.CU_Name) LIKE '%REML%'
         LIMIT 1),
        (SELECT cu.CU_Id FROM customer cu WHERE TRIM(cu.CU_Name) LIKE '%REML%' LIMIT 1)
    ) AS cust_id
) src
WHERE (src.co_id IS NOT NULL OR src.bom_id IS NOT NULL)
  AND NOT EXISTS (
    SELECT 1 FROM lw_packing_part_map m
    WHERE (
        (src.co_id IS NOT NULL AND m.co_id = src.co_id AND (m.cust_id = src.cust_id OR (m.cust_id IS NULL AND src.cust_id IS NULL)))
        OR (src.bom_id IS NOT NULL AND m.bom_id = src.bom_id AND m.cust_id = src.cust_id)
    )
  );


-- REML / RBB00009
INSERT INTO lw_packing_part_map (co_id, bom_id, cust_id, tray_item_code, carton_item_code, tray_capacity, carton_capacity)
SELECT src.co_id, src.bom_id, src.cust_id, 'SE-1-2P-15C-1', 'SE-B-600400125-2', 4, 8
FROM (
    SELECT
        (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'RBB00009'
          AND TRIM(cu.CU_Name) LIKE '%REML%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) AS co_id,
        CASE WHEN (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'RBB00009'
          AND TRIM(cu.CU_Name) LIKE '%REML%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) IS NULL THEN (
        SELECT b.bom_id
        FROM bom b
        INNER JOIN customer cu ON cu.CU_Id = b.cust_id
        WHERE TRIM(b.bom_no) = 'RBB00009'
          AND b.is_latest_version = 'Y'
          AND TRIM(cu.CU_Name) LIKE '%REML%'
        ORDER BY b.cust_id
        LIMIT 1
    ) ELSE NULL END AS bom_id,
        COALESCE(
        (SELECT c.CO_CUSTID FROM components c
         INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
         WHERE TRIM(c.CO_PARTNO) = 'RBB00009' AND TRIM(cu.CU_Name) LIKE '%REML%' AND c.CO_ACTIVEYN = 'Y'
         ORDER BY c.CO_ID DESC LIMIT 1),
        (SELECT b.cust_id FROM bom b
         INNER JOIN customer cu ON cu.CU_Id = b.cust_id
         WHERE TRIM(b.bom_no) = 'RBB00009' AND b.is_latest_version = 'Y' AND TRIM(cu.CU_Name) LIKE '%REML%'
         LIMIT 1),
        (SELECT cu.CU_Id FROM customer cu WHERE TRIM(cu.CU_Name) LIKE '%REML%' LIMIT 1)
    ) AS cust_id
) src
WHERE (src.co_id IS NOT NULL OR src.bom_id IS NOT NULL)
  AND NOT EXISTS (
    SELECT 1 FROM lw_packing_part_map m
    WHERE (
        (src.co_id IS NOT NULL AND m.co_id = src.co_id AND (m.cust_id = src.cust_id OR (m.cust_id IS NULL AND src.cust_id IS NULL)))
        OR (src.bom_id IS NOT NULL AND m.bom_id = src.bom_id AND m.cust_id = src.cust_id)
    )
  );


-- REML / RBB00010
INSERT INTO lw_packing_part_map (co_id, bom_id, cust_id, tray_item_code, carton_item_code, tray_capacity, carton_capacity)
SELECT src.co_id, src.bom_id, src.cust_id, 'SE-1-2P-15C-1', 'SE-B-600400125-2', 4, 44
FROM (
    SELECT
        (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'RBB00010'
          AND TRIM(cu.CU_Name) LIKE '%REML%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) AS co_id,
        CASE WHEN (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'RBB00010'
          AND TRIM(cu.CU_Name) LIKE '%REML%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) IS NULL THEN (
        SELECT b.bom_id
        FROM bom b
        INNER JOIN customer cu ON cu.CU_Id = b.cust_id
        WHERE TRIM(b.bom_no) = 'RBB00010'
          AND b.is_latest_version = 'Y'
          AND TRIM(cu.CU_Name) LIKE '%REML%'
        ORDER BY b.cust_id
        LIMIT 1
    ) ELSE NULL END AS bom_id,
        COALESCE(
        (SELECT c.CO_CUSTID FROM components c
         INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
         WHERE TRIM(c.CO_PARTNO) = 'RBB00010' AND TRIM(cu.CU_Name) LIKE '%REML%' AND c.CO_ACTIVEYN = 'Y'
         ORDER BY c.CO_ID DESC LIMIT 1),
        (SELECT b.cust_id FROM bom b
         INNER JOIN customer cu ON cu.CU_Id = b.cust_id
         WHERE TRIM(b.bom_no) = 'RBB00010' AND b.is_latest_version = 'Y' AND TRIM(cu.CU_Name) LIKE '%REML%'
         LIMIT 1),
        (SELECT cu.CU_Id FROM customer cu WHERE TRIM(cu.CU_Name) LIKE '%REML%' LIMIT 1)
    ) AS cust_id
) src
WHERE (src.co_id IS NOT NULL OR src.bom_id IS NOT NULL)
  AND NOT EXISTS (
    SELECT 1 FROM lw_packing_part_map m
    WHERE (
        (src.co_id IS NOT NULL AND m.co_id = src.co_id AND (m.cust_id = src.cust_id OR (m.cust_id IS NULL AND src.cust_id IS NULL)))
        OR (src.bom_id IS NOT NULL AND m.bom_id = src.bom_id AND m.cust_id = src.cust_id)
    )
  );


-- REML / RBB00011
INSERT INTO lw_packing_part_map (co_id, bom_id, cust_id, tray_item_code, carton_item_code, tray_capacity, carton_capacity)
SELECT src.co_id, src.bom_id, src.cust_id, 'SE-1-2P-14C-1', 'SE-B-600400125-2', 4, 32
FROM (
    SELECT
        (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'RBB00011'
          AND TRIM(cu.CU_Name) LIKE '%REML%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) AS co_id,
        CASE WHEN (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'RBB00011'
          AND TRIM(cu.CU_Name) LIKE '%REML%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) IS NULL THEN (
        SELECT b.bom_id
        FROM bom b
        INNER JOIN customer cu ON cu.CU_Id = b.cust_id
        WHERE TRIM(b.bom_no) = 'RBB00011'
          AND b.is_latest_version = 'Y'
          AND TRIM(cu.CU_Name) LIKE '%REML%'
        ORDER BY b.cust_id
        LIMIT 1
    ) ELSE NULL END AS bom_id,
        COALESCE(
        (SELECT c.CO_CUSTID FROM components c
         INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
         WHERE TRIM(c.CO_PARTNO) = 'RBB00011' AND TRIM(cu.CU_Name) LIKE '%REML%' AND c.CO_ACTIVEYN = 'Y'
         ORDER BY c.CO_ID DESC LIMIT 1),
        (SELECT b.cust_id FROM bom b
         INNER JOIN customer cu ON cu.CU_Id = b.cust_id
         WHERE TRIM(b.bom_no) = 'RBB00011' AND b.is_latest_version = 'Y' AND TRIM(cu.CU_Name) LIKE '%REML%'
         LIMIT 1),
        (SELECT cu.CU_Id FROM customer cu WHERE TRIM(cu.CU_Name) LIKE '%REML%' LIMIT 1)
    ) AS cust_id
) src
WHERE (src.co_id IS NOT NULL OR src.bom_id IS NOT NULL)
  AND NOT EXISTS (
    SELECT 1 FROM lw_packing_part_map m
    WHERE (
        (src.co_id IS NOT NULL AND m.co_id = src.co_id AND (m.cust_id = src.cust_id OR (m.cust_id IS NULL AND src.cust_id IS NULL)))
        OR (src.bom_id IS NOT NULL AND m.bom_id = src.bom_id AND m.cust_id = src.cust_id)
    )
  );


-- REML / RBB00012
INSERT INTO lw_packing_part_map (co_id, bom_id, cust_id, tray_item_code, carton_item_code, tray_capacity, carton_capacity)
SELECT src.co_id, src.bom_id, src.cust_id, 'SE-1-2P-14C-1', 'SE-B-600400125-2', 4, 24
FROM (
    SELECT
        (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'RBB00012'
          AND TRIM(cu.CU_Name) LIKE '%REML%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) AS co_id,
        CASE WHEN (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'RBB00012'
          AND TRIM(cu.CU_Name) LIKE '%REML%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) IS NULL THEN (
        SELECT b.bom_id
        FROM bom b
        INNER JOIN customer cu ON cu.CU_Id = b.cust_id
        WHERE TRIM(b.bom_no) = 'RBB00012'
          AND b.is_latest_version = 'Y'
          AND TRIM(cu.CU_Name) LIKE '%REML%'
        ORDER BY b.cust_id
        LIMIT 1
    ) ELSE NULL END AS bom_id,
        COALESCE(
        (SELECT c.CO_CUSTID FROM components c
         INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
         WHERE TRIM(c.CO_PARTNO) = 'RBB00012' AND TRIM(cu.CU_Name) LIKE '%REML%' AND c.CO_ACTIVEYN = 'Y'
         ORDER BY c.CO_ID DESC LIMIT 1),
        (SELECT b.cust_id FROM bom b
         INNER JOIN customer cu ON cu.CU_Id = b.cust_id
         WHERE TRIM(b.bom_no) = 'RBB00012' AND b.is_latest_version = 'Y' AND TRIM(cu.CU_Name) LIKE '%REML%'
         LIMIT 1),
        (SELECT cu.CU_Id FROM customer cu WHERE TRIM(cu.CU_Name) LIKE '%REML%' LIMIT 1)
    ) AS cust_id
) src
WHERE (src.co_id IS NOT NULL OR src.bom_id IS NOT NULL)
  AND NOT EXISTS (
    SELECT 1 FROM lw_packing_part_map m
    WHERE (
        (src.co_id IS NOT NULL AND m.co_id = src.co_id AND (m.cust_id = src.cust_id OR (m.cust_id IS NULL AND src.cust_id IS NULL)))
        OR (src.bom_id IS NOT NULL AND m.bom_id = src.bom_id AND m.cust_id = src.cust_id)
    )
  );


-- RIVER / R107020697
INSERT INTO lw_packing_part_map (co_id, bom_id, cust_id, tray_item_code, carton_item_code, tray_capacity, carton_capacity)
SELECT src.co_id, src.bom_id, src.cust_id, 'SE-1-4P-4C-1', 'SE-C-380280185', 12, 48
FROM (
    SELECT
        (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'R107020697'
          AND TRIM(cu.CU_Name) LIKE '%RIVER%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) AS co_id,
        CASE WHEN (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'R107020697'
          AND TRIM(cu.CU_Name) LIKE '%RIVER%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) IS NULL THEN (
        SELECT b.bom_id
        FROM bom b
        INNER JOIN customer cu ON cu.CU_Id = b.cust_id
        WHERE TRIM(b.bom_no) = 'R107020697'
          AND b.is_latest_version = 'Y'
          AND TRIM(cu.CU_Name) LIKE '%RIVER%'
        ORDER BY b.cust_id
        LIMIT 1
    ) ELSE NULL END AS bom_id,
        COALESCE(
        (SELECT c.CO_CUSTID FROM components c
         INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
         WHERE TRIM(c.CO_PARTNO) = 'R107020697' AND TRIM(cu.CU_Name) LIKE '%RIVER%' AND c.CO_ACTIVEYN = 'Y'
         ORDER BY c.CO_ID DESC LIMIT 1),
        (SELECT b.cust_id FROM bom b
         INNER JOIN customer cu ON cu.CU_Id = b.cust_id
         WHERE TRIM(b.bom_no) = 'R107020697' AND b.is_latest_version = 'Y' AND TRIM(cu.CU_Name) LIKE '%RIVER%'
         LIMIT 1),
        (SELECT cu.CU_Id FROM customer cu WHERE TRIM(cu.CU_Name) LIKE '%RIVER%' LIMIT 1)
    ) AS cust_id
) src
WHERE (src.co_id IS NOT NULL OR src.bom_id IS NOT NULL)
  AND NOT EXISTS (
    SELECT 1 FROM lw_packing_part_map m
    WHERE (
        (src.co_id IS NOT NULL AND m.co_id = src.co_id AND (m.cust_id = src.cust_id OR (m.cust_id IS NULL AND src.cust_id IS NULL)))
        OR (src.bom_id IS NOT NULL AND m.bom_id = src.bom_id AND m.cust_id = src.cust_id)
    )
  );


-- RIVER / R107020698
INSERT INTO lw_packing_part_map (co_id, bom_id, cust_id, tray_item_code, carton_item_code, tray_capacity, carton_capacity)
SELECT src.co_id, src.bom_id, src.cust_id, 'SE-1-4P-4C-1', 'SE-C-380280185', 12, 48
FROM (
    SELECT
        (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'R107020698'
          AND TRIM(cu.CU_Name) LIKE '%RIVER%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) AS co_id,
        CASE WHEN (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'R107020698'
          AND TRIM(cu.CU_Name) LIKE '%RIVER%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) IS NULL THEN (
        SELECT b.bom_id
        FROM bom b
        INNER JOIN customer cu ON cu.CU_Id = b.cust_id
        WHERE TRIM(b.bom_no) = 'R107020698'
          AND b.is_latest_version = 'Y'
          AND TRIM(cu.CU_Name) LIKE '%RIVER%'
        ORDER BY b.cust_id
        LIMIT 1
    ) ELSE NULL END AS bom_id,
        COALESCE(
        (SELECT c.CO_CUSTID FROM components c
         INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
         WHERE TRIM(c.CO_PARTNO) = 'R107020698' AND TRIM(cu.CU_Name) LIKE '%RIVER%' AND c.CO_ACTIVEYN = 'Y'
         ORDER BY c.CO_ID DESC LIMIT 1),
        (SELECT b.cust_id FROM bom b
         INNER JOIN customer cu ON cu.CU_Id = b.cust_id
         WHERE TRIM(b.bom_no) = 'R107020698' AND b.is_latest_version = 'Y' AND TRIM(cu.CU_Name) LIKE '%RIVER%'
         LIMIT 1),
        (SELECT cu.CU_Id FROM customer cu WHERE TRIM(cu.CU_Name) LIKE '%RIVER%' LIMIT 1)
    ) AS cust_id
) src
WHERE (src.co_id IS NOT NULL OR src.bom_id IS NOT NULL)
  AND NOT EXISTS (
    SELECT 1 FROM lw_packing_part_map m
    WHERE (
        (src.co_id IS NOT NULL AND m.co_id = src.co_id AND (m.cust_id = src.cust_id OR (m.cust_id IS NULL AND src.cust_id IS NULL)))
        OR (src.bom_id IS NOT NULL AND m.bom_id = src.bom_id AND m.cust_id = src.cust_id)
    )
  );


-- RIVER / R107020699
INSERT INTO lw_packing_part_map (co_id, bom_id, cust_id, tray_item_code, carton_item_code, tray_capacity, carton_capacity)
SELECT src.co_id, src.bom_id, src.cust_id, 'SE-1-S-8C-1', 'SE-C-380280185', 7, 56
FROM (
    SELECT
        (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'R107020699'
          AND TRIM(cu.CU_Name) LIKE '%RIVER%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) AS co_id,
        CASE WHEN (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'R107020699'
          AND TRIM(cu.CU_Name) LIKE '%RIVER%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) IS NULL THEN (
        SELECT b.bom_id
        FROM bom b
        INNER JOIN customer cu ON cu.CU_Id = b.cust_id
        WHERE TRIM(b.bom_no) = 'R107020699'
          AND b.is_latest_version = 'Y'
          AND TRIM(cu.CU_Name) LIKE '%RIVER%'
        ORDER BY b.cust_id
        LIMIT 1
    ) ELSE NULL END AS bom_id,
        COALESCE(
        (SELECT c.CO_CUSTID FROM components c
         INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
         WHERE TRIM(c.CO_PARTNO) = 'R107020699' AND TRIM(cu.CU_Name) LIKE '%RIVER%' AND c.CO_ACTIVEYN = 'Y'
         ORDER BY c.CO_ID DESC LIMIT 1),
        (SELECT b.cust_id FROM bom b
         INNER JOIN customer cu ON cu.CU_Id = b.cust_id
         WHERE TRIM(b.bom_no) = 'R107020699' AND b.is_latest_version = 'Y' AND TRIM(cu.CU_Name) LIKE '%RIVER%'
         LIMIT 1),
        (SELECT cu.CU_Id FROM customer cu WHERE TRIM(cu.CU_Name) LIKE '%RIVER%' LIMIT 1)
    ) AS cust_id
) src
WHERE (src.co_id IS NOT NULL OR src.bom_id IS NOT NULL)
  AND NOT EXISTS (
    SELECT 1 FROM lw_packing_part_map m
    WHERE (
        (src.co_id IS NOT NULL AND m.co_id = src.co_id AND (m.cust_id = src.cust_id OR (m.cust_id IS NULL AND src.cust_id IS NULL)))
        OR (src.bom_id IS NOT NULL AND m.bom_id = src.bom_id AND m.cust_id = src.cust_id)
    )
  );


-- RIVER / R107020700
INSERT INTO lw_packing_part_map (co_id, bom_id, cust_id, tray_item_code, carton_item_code, tray_capacity, carton_capacity)
SELECT src.co_id, src.bom_id, src.cust_id, 'SE-1-4P-4C-1', 'SE-C-380280185', 12, 48
FROM (
    SELECT
        (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'R107020700'
          AND TRIM(cu.CU_Name) LIKE '%RIVER%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) AS co_id,
        CASE WHEN (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'R107020700'
          AND TRIM(cu.CU_Name) LIKE '%RIVER%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) IS NULL THEN (
        SELECT b.bom_id
        FROM bom b
        INNER JOIN customer cu ON cu.CU_Id = b.cust_id
        WHERE TRIM(b.bom_no) = 'R107020700'
          AND b.is_latest_version = 'Y'
          AND TRIM(cu.CU_Name) LIKE '%RIVER%'
        ORDER BY b.cust_id
        LIMIT 1
    ) ELSE NULL END AS bom_id,
        COALESCE(
        (SELECT c.CO_CUSTID FROM components c
         INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
         WHERE TRIM(c.CO_PARTNO) = 'R107020700' AND TRIM(cu.CU_Name) LIKE '%RIVER%' AND c.CO_ACTIVEYN = 'Y'
         ORDER BY c.CO_ID DESC LIMIT 1),
        (SELECT b.cust_id FROM bom b
         INNER JOIN customer cu ON cu.CU_Id = b.cust_id
         WHERE TRIM(b.bom_no) = 'R107020700' AND b.is_latest_version = 'Y' AND TRIM(cu.CU_Name) LIKE '%RIVER%'
         LIMIT 1),
        (SELECT cu.CU_Id FROM customer cu WHERE TRIM(cu.CU_Name) LIKE '%RIVER%' LIMIT 1)
    ) AS cust_id
) src
WHERE (src.co_id IS NOT NULL OR src.bom_id IS NOT NULL)
  AND NOT EXISTS (
    SELECT 1 FROM lw_packing_part_map m
    WHERE (
        (src.co_id IS NOT NULL AND m.co_id = src.co_id AND (m.cust_id = src.cust_id OR (m.cust_id IS NULL AND src.cust_id IS NULL)))
        OR (src.bom_id IS NOT NULL AND m.bom_id = src.bom_id AND m.cust_id = src.cust_id)
    )
  );


-- RIVER / R107020701
INSERT INTO lw_packing_part_map (co_id, bom_id, cust_id, tray_item_code, carton_item_code, tray_capacity, carton_capacity)
SELECT src.co_id, src.bom_id, src.cust_id, 'SE-1-2P-6C-1', 'SE-C-470310185', 12, 72
FROM (
    SELECT
        (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'R107020701'
          AND TRIM(cu.CU_Name) LIKE '%RIVER%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) AS co_id,
        CASE WHEN (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'R107020701'
          AND TRIM(cu.CU_Name) LIKE '%RIVER%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) IS NULL THEN (
        SELECT b.bom_id
        FROM bom b
        INNER JOIN customer cu ON cu.CU_Id = b.cust_id
        WHERE TRIM(b.bom_no) = 'R107020701'
          AND b.is_latest_version = 'Y'
          AND TRIM(cu.CU_Name) LIKE '%RIVER%'
        ORDER BY b.cust_id
        LIMIT 1
    ) ELSE NULL END AS bom_id,
        COALESCE(
        (SELECT c.CO_CUSTID FROM components c
         INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
         WHERE TRIM(c.CO_PARTNO) = 'R107020701' AND TRIM(cu.CU_Name) LIKE '%RIVER%' AND c.CO_ACTIVEYN = 'Y'
         ORDER BY c.CO_ID DESC LIMIT 1),
        (SELECT b.cust_id FROM bom b
         INNER JOIN customer cu ON cu.CU_Id = b.cust_id
         WHERE TRIM(b.bom_no) = 'R107020701' AND b.is_latest_version = 'Y' AND TRIM(cu.CU_Name) LIKE '%RIVER%'
         LIMIT 1),
        (SELECT cu.CU_Id FROM customer cu WHERE TRIM(cu.CU_Name) LIKE '%RIVER%' LIMIT 1)
    ) AS cust_id
) src
WHERE (src.co_id IS NOT NULL OR src.bom_id IS NOT NULL)
  AND NOT EXISTS (
    SELECT 1 FROM lw_packing_part_map m
    WHERE (
        (src.co_id IS NOT NULL AND m.co_id = src.co_id AND (m.cust_id = src.cust_id OR (m.cust_id IS NULL AND src.cust_id IS NULL)))
        OR (src.bom_id IS NOT NULL AND m.bom_id = src.bom_id AND m.cust_id = src.cust_id)
    )
  );


-- RIVER / R107020702
INSERT INTO lw_packing_part_map (co_id, bom_id, cust_id, tray_item_code, carton_item_code, tray_capacity, carton_capacity)
SELECT src.co_id, src.bom_id, src.cust_id, 'SE-1-2P-6C-1', 'SE-C-470310185', 12, 72
FROM (
    SELECT
        (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'R107020702'
          AND TRIM(cu.CU_Name) LIKE '%RIVER%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) AS co_id,
        CASE WHEN (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'R107020702'
          AND TRIM(cu.CU_Name) LIKE '%RIVER%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) IS NULL THEN (
        SELECT b.bom_id
        FROM bom b
        INNER JOIN customer cu ON cu.CU_Id = b.cust_id
        WHERE TRIM(b.bom_no) = 'R107020702'
          AND b.is_latest_version = 'Y'
          AND TRIM(cu.CU_Name) LIKE '%RIVER%'
        ORDER BY b.cust_id
        LIMIT 1
    ) ELSE NULL END AS bom_id,
        COALESCE(
        (SELECT c.CO_CUSTID FROM components c
         INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
         WHERE TRIM(c.CO_PARTNO) = 'R107020702' AND TRIM(cu.CU_Name) LIKE '%RIVER%' AND c.CO_ACTIVEYN = 'Y'
         ORDER BY c.CO_ID DESC LIMIT 1),
        (SELECT b.cust_id FROM bom b
         INNER JOIN customer cu ON cu.CU_Id = b.cust_id
         WHERE TRIM(b.bom_no) = 'R107020702' AND b.is_latest_version = 'Y' AND TRIM(cu.CU_Name) LIKE '%RIVER%'
         LIMIT 1),
        (SELECT cu.CU_Id FROM customer cu WHERE TRIM(cu.CU_Name) LIKE '%RIVER%' LIMIT 1)
    ) AS cust_id
) src
WHERE (src.co_id IS NOT NULL OR src.bom_id IS NOT NULL)
  AND NOT EXISTS (
    SELECT 1 FROM lw_packing_part_map m
    WHERE (
        (src.co_id IS NOT NULL AND m.co_id = src.co_id AND (m.cust_id = src.cust_id OR (m.cust_id IS NULL AND src.cust_id IS NULL)))
        OR (src.bom_id IS NOT NULL AND m.bom_id = src.bom_id AND m.cust_id = src.cust_id)
    )
  );


-- RIVER / R107020707
INSERT INTO lw_packing_part_map (co_id, bom_id, cust_id, tray_item_code, carton_item_code, tray_capacity, carton_capacity)
SELECT src.co_id, src.bom_id, src.cust_id, 'SE-1-4P-4C-1', 'SE-C-380280185', 12, 48
FROM (
    SELECT
        (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'R107020707'
          AND TRIM(cu.CU_Name) LIKE '%RIVER%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) AS co_id,
        CASE WHEN (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'R107020707'
          AND TRIM(cu.CU_Name) LIKE '%RIVER%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) IS NULL THEN (
        SELECT b.bom_id
        FROM bom b
        INNER JOIN customer cu ON cu.CU_Id = b.cust_id
        WHERE TRIM(b.bom_no) = 'R107020707'
          AND b.is_latest_version = 'Y'
          AND TRIM(cu.CU_Name) LIKE '%RIVER%'
        ORDER BY b.cust_id
        LIMIT 1
    ) ELSE NULL END AS bom_id,
        COALESCE(
        (SELECT c.CO_CUSTID FROM components c
         INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
         WHERE TRIM(c.CO_PARTNO) = 'R107020707' AND TRIM(cu.CU_Name) LIKE '%RIVER%' AND c.CO_ACTIVEYN = 'Y'
         ORDER BY c.CO_ID DESC LIMIT 1),
        (SELECT b.cust_id FROM bom b
         INNER JOIN customer cu ON cu.CU_Id = b.cust_id
         WHERE TRIM(b.bom_no) = 'R107020707' AND b.is_latest_version = 'Y' AND TRIM(cu.CU_Name) LIKE '%RIVER%'
         LIMIT 1),
        (SELECT cu.CU_Id FROM customer cu WHERE TRIM(cu.CU_Name) LIKE '%RIVER%' LIMIT 1)
    ) AS cust_id
) src
WHERE (src.co_id IS NOT NULL OR src.bom_id IS NOT NULL)
  AND NOT EXISTS (
    SELECT 1 FROM lw_packing_part_map m
    WHERE (
        (src.co_id IS NOT NULL AND m.co_id = src.co_id AND (m.cust_id = src.cust_id OR (m.cust_id IS NULL AND src.cust_id IS NULL)))
        OR (src.bom_id IS NOT NULL AND m.bom_id = src.bom_id AND m.cust_id = src.cust_id)
    )
  );


-- RIVER / R107027666
INSERT INTO lw_packing_part_map (co_id, bom_id, cust_id, tray_item_code, carton_item_code, tray_capacity, carton_capacity)
SELECT src.co_id, src.bom_id, src.cust_id, 'SE-1-S-6C-1', 'SE-C-450235185', 10, 60
FROM (
    SELECT
        (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'R107027666'
          AND TRIM(cu.CU_Name) LIKE '%RIVER%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) AS co_id,
        CASE WHEN (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'R107027666'
          AND TRIM(cu.CU_Name) LIKE '%RIVER%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) IS NULL THEN (
        SELECT b.bom_id
        FROM bom b
        INNER JOIN customer cu ON cu.CU_Id = b.cust_id
        WHERE TRIM(b.bom_no) = 'R107027666'
          AND b.is_latest_version = 'Y'
          AND TRIM(cu.CU_Name) LIKE '%RIVER%'
        ORDER BY b.cust_id
        LIMIT 1
    ) ELSE NULL END AS bom_id,
        COALESCE(
        (SELECT c.CO_CUSTID FROM components c
         INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
         WHERE TRIM(c.CO_PARTNO) = 'R107027666' AND TRIM(cu.CU_Name) LIKE '%RIVER%' AND c.CO_ACTIVEYN = 'Y'
         ORDER BY c.CO_ID DESC LIMIT 1),
        (SELECT b.cust_id FROM bom b
         INNER JOIN customer cu ON cu.CU_Id = b.cust_id
         WHERE TRIM(b.bom_no) = 'R107027666' AND b.is_latest_version = 'Y' AND TRIM(cu.CU_Name) LIKE '%RIVER%'
         LIMIT 1),
        (SELECT cu.CU_Id FROM customer cu WHERE TRIM(cu.CU_Name) LIKE '%RIVER%' LIMIT 1)
    ) AS cust_id
) src
WHERE (src.co_id IS NOT NULL OR src.bom_id IS NOT NULL)
  AND NOT EXISTS (
    SELECT 1 FROM lw_packing_part_map m
    WHERE (
        (src.co_id IS NOT NULL AND m.co_id = src.co_id AND (m.cust_id = src.cust_id OR (m.cust_id IS NULL AND src.cust_id IS NULL)))
        OR (src.bom_id IS NOT NULL AND m.bom_id = src.bom_id AND m.cust_id = src.cust_id)
    )
  );


-- RIVER / R107027670
INSERT INTO lw_packing_part_map (co_id, bom_id, cust_id, tray_item_code, carton_item_code, tray_capacity, carton_capacity)
SELECT src.co_id, src.bom_id, src.cust_id, 'SE-1-S-6C-2', 'SE-C-450235185', 10, 60
FROM (
    SELECT
        (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'R107027670'
          AND TRIM(cu.CU_Name) LIKE '%RIVER%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) AS co_id,
        CASE WHEN (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'R107027670'
          AND TRIM(cu.CU_Name) LIKE '%RIVER%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) IS NULL THEN (
        SELECT b.bom_id
        FROM bom b
        INNER JOIN customer cu ON cu.CU_Id = b.cust_id
        WHERE TRIM(b.bom_no) = 'R107027670'
          AND b.is_latest_version = 'Y'
          AND TRIM(cu.CU_Name) LIKE '%RIVER%'
        ORDER BY b.cust_id
        LIMIT 1
    ) ELSE NULL END AS bom_id,
        COALESCE(
        (SELECT c.CO_CUSTID FROM components c
         INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
         WHERE TRIM(c.CO_PARTNO) = 'R107027670' AND TRIM(cu.CU_Name) LIKE '%RIVER%' AND c.CO_ACTIVEYN = 'Y'
         ORDER BY c.CO_ID DESC LIMIT 1),
        (SELECT b.cust_id FROM bom b
         INNER JOIN customer cu ON cu.CU_Id = b.cust_id
         WHERE TRIM(b.bom_no) = 'R107027670' AND b.is_latest_version = 'Y' AND TRIM(cu.CU_Name) LIKE '%RIVER%'
         LIMIT 1),
        (SELECT cu.CU_Id FROM customer cu WHERE TRIM(cu.CU_Name) LIKE '%RIVER%' LIMIT 1)
    ) AS cust_id
) src
WHERE (src.co_id IS NOT NULL OR src.bom_id IS NOT NULL)
  AND NOT EXISTS (
    SELECT 1 FROM lw_packing_part_map m
    WHERE (
        (src.co_id IS NOT NULL AND m.co_id = src.co_id AND (m.cust_id = src.cust_id OR (m.cust_id IS NULL AND src.cust_id IS NULL)))
        OR (src.bom_id IS NOT NULL AND m.bom_id = src.bom_id AND m.cust_id = src.cust_id)
    )
  );


-- RIVER / R107027677
INSERT INTO lw_packing_part_map (co_id, bom_id, cust_id, tray_item_code, carton_item_code, tray_capacity, carton_capacity)
SELECT src.co_id, src.bom_id, src.cust_id, 'SE-1-2P-6C-2', 'SE-C-450235185', 15, 540
FROM (
    SELECT
        (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'R107027677'
          AND TRIM(cu.CU_Name) LIKE '%RIVER%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) AS co_id,
        CASE WHEN (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'R107027677'
          AND TRIM(cu.CU_Name) LIKE '%RIVER%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) IS NULL THEN (
        SELECT b.bom_id
        FROM bom b
        INNER JOIN customer cu ON cu.CU_Id = b.cust_id
        WHERE TRIM(b.bom_no) = 'R107027677'
          AND b.is_latest_version = 'Y'
          AND TRIM(cu.CU_Name) LIKE '%RIVER%'
        ORDER BY b.cust_id
        LIMIT 1
    ) ELSE NULL END AS bom_id,
        COALESCE(
        (SELECT c.CO_CUSTID FROM components c
         INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
         WHERE TRIM(c.CO_PARTNO) = 'R107027677' AND TRIM(cu.CU_Name) LIKE '%RIVER%' AND c.CO_ACTIVEYN = 'Y'
         ORDER BY c.CO_ID DESC LIMIT 1),
        (SELECT b.cust_id FROM bom b
         INNER JOIN customer cu ON cu.CU_Id = b.cust_id
         WHERE TRIM(b.bom_no) = 'R107027677' AND b.is_latest_version = 'Y' AND TRIM(cu.CU_Name) LIKE '%RIVER%'
         LIMIT 1),
        (SELECT cu.CU_Id FROM customer cu WHERE TRIM(cu.CU_Name) LIKE '%RIVER%' LIMIT 1)
    ) AS cust_id
) src
WHERE (src.co_id IS NOT NULL OR src.bom_id IS NOT NULL)
  AND NOT EXISTS (
    SELECT 1 FROM lw_packing_part_map m
    WHERE (
        (src.co_id IS NOT NULL AND m.co_id = src.co_id AND (m.cust_id = src.cust_id OR (m.cust_id IS NULL AND src.cust_id IS NULL)))
        OR (src.bom_id IS NOT NULL AND m.bom_id = src.bom_id AND m.cust_id = src.cust_id)
    )
  );


-- RIVER / R107027678
INSERT INTO lw_packing_part_map (co_id, bom_id, cust_id, tray_item_code, carton_item_code, tray_capacity, carton_capacity)
SELECT src.co_id, src.bom_id, src.cust_id, 'SE-1-2P-6C-2', 'SE-C-450235185', 15, 630
FROM (
    SELECT
        (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'R107027678'
          AND TRIM(cu.CU_Name) LIKE '%RIVER%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) AS co_id,
        CASE WHEN (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'R107027678'
          AND TRIM(cu.CU_Name) LIKE '%RIVER%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) IS NULL THEN (
        SELECT b.bom_id
        FROM bom b
        INNER JOIN customer cu ON cu.CU_Id = b.cust_id
        WHERE TRIM(b.bom_no) = 'R107027678'
          AND b.is_latest_version = 'Y'
          AND TRIM(cu.CU_Name) LIKE '%RIVER%'
        ORDER BY b.cust_id
        LIMIT 1
    ) ELSE NULL END AS bom_id,
        COALESCE(
        (SELECT c.CO_CUSTID FROM components c
         INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
         WHERE TRIM(c.CO_PARTNO) = 'R107027678' AND TRIM(cu.CU_Name) LIKE '%RIVER%' AND c.CO_ACTIVEYN = 'Y'
         ORDER BY c.CO_ID DESC LIMIT 1),
        (SELECT b.cust_id FROM bom b
         INNER JOIN customer cu ON cu.CU_Id = b.cust_id
         WHERE TRIM(b.bom_no) = 'R107027678' AND b.is_latest_version = 'Y' AND TRIM(cu.CU_Name) LIKE '%RIVER%'
         LIMIT 1),
        (SELECT cu.CU_Id FROM customer cu WHERE TRIM(cu.CU_Name) LIKE '%RIVER%' LIMIT 1)
    ) AS cust_id
) src
WHERE (src.co_id IS NOT NULL OR src.bom_id IS NOT NULL)
  AND NOT EXISTS (
    SELECT 1 FROM lw_packing_part_map m
    WHERE (
        (src.co_id IS NOT NULL AND m.co_id = src.co_id AND (m.cust_id = src.cust_id OR (m.cust_id IS NULL AND src.cust_id IS NULL)))
        OR (src.bom_id IS NOT NULL AND m.bom_id = src.bom_id AND m.cust_id = src.cust_id)
    )
  );


-- TVS / HE240740
INSERT INTO lw_packing_part_map (co_id, bom_id, cust_id, tray_item_code, carton_item_code, tray_capacity, carton_capacity)
SELECT src.co_id, src.bom_id, src.cust_id, 'SE-1-S-18C-1', NULL, NULL, NULL
FROM (
    SELECT
        (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'HE240740'
          AND TRIM(cu.CU_Name) LIKE '%TVS%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) AS co_id,
        CASE WHEN (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'HE240740'
          AND TRIM(cu.CU_Name) LIKE '%TVS%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) IS NULL THEN (
        SELECT b.bom_id
        FROM bom b
        INNER JOIN customer cu ON cu.CU_Id = b.cust_id
        WHERE TRIM(b.bom_no) = 'HE240740'
          AND b.is_latest_version = 'Y'
          AND TRIM(cu.CU_Name) LIKE '%TVS%'
        ORDER BY b.cust_id
        LIMIT 1
    ) ELSE NULL END AS bom_id,
        COALESCE(
        (SELECT c.CO_CUSTID FROM components c
         INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
         WHERE TRIM(c.CO_PARTNO) = 'HE240740' AND TRIM(cu.CU_Name) LIKE '%TVS%' AND c.CO_ACTIVEYN = 'Y'
         ORDER BY c.CO_ID DESC LIMIT 1),
        (SELECT b.cust_id FROM bom b
         INNER JOIN customer cu ON cu.CU_Id = b.cust_id
         WHERE TRIM(b.bom_no) = 'HE240740' AND b.is_latest_version = 'Y' AND TRIM(cu.CU_Name) LIKE '%TVS%'
         LIMIT 1),
        (SELECT cu.CU_Id FROM customer cu WHERE TRIM(cu.CU_Name) LIKE '%TVS%' LIMIT 1)
    ) AS cust_id
) src
WHERE (src.co_id IS NOT NULL OR src.bom_id IS NOT NULL)
  AND NOT EXISTS (
    SELECT 1 FROM lw_packing_part_map m
    WHERE (
        (src.co_id IS NOT NULL AND m.co_id = src.co_id AND (m.cust_id = src.cust_id OR (m.cust_id IS NULL AND src.cust_id IS NULL)))
        OR (src.bom_id IS NOT NULL AND m.bom_id = src.bom_id AND m.cust_id = src.cust_id)
    )
  );


-- TVS / HE240760
INSERT INTO lw_packing_part_map (co_id, bom_id, cust_id, tray_item_code, carton_item_code, tray_capacity, carton_capacity)
SELECT src.co_id, src.bom_id, src.cust_id, 'SE-1-S-15C-1', NULL, NULL, NULL
FROM (
    SELECT
        (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'HE240760'
          AND TRIM(cu.CU_Name) LIKE '%TVS%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) AS co_id,
        CASE WHEN (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'HE240760'
          AND TRIM(cu.CU_Name) LIKE '%TVS%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) IS NULL THEN (
        SELECT b.bom_id
        FROM bom b
        INNER JOIN customer cu ON cu.CU_Id = b.cust_id
        WHERE TRIM(b.bom_no) = 'HE240760'
          AND b.is_latest_version = 'Y'
          AND TRIM(cu.CU_Name) LIKE '%TVS%'
        ORDER BY b.cust_id
        LIMIT 1
    ) ELSE NULL END AS bom_id,
        COALESCE(
        (SELECT c.CO_CUSTID FROM components c
         INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
         WHERE TRIM(c.CO_PARTNO) = 'HE240760' AND TRIM(cu.CU_Name) LIKE '%TVS%' AND c.CO_ACTIVEYN = 'Y'
         ORDER BY c.CO_ID DESC LIMIT 1),
        (SELECT b.cust_id FROM bom b
         INNER JOIN customer cu ON cu.CU_Id = b.cust_id
         WHERE TRIM(b.bom_no) = 'HE240760' AND b.is_latest_version = 'Y' AND TRIM(cu.CU_Name) LIKE '%TVS%'
         LIMIT 1),
        (SELECT cu.CU_Id FROM customer cu WHERE TRIM(cu.CU_Name) LIKE '%TVS%' LIMIT 1)
    ) AS cust_id
) src
WHERE (src.co_id IS NOT NULL OR src.bom_id IS NOT NULL)
  AND NOT EXISTS (
    SELECT 1 FROM lw_packing_part_map m
    WHERE (
        (src.co_id IS NOT NULL AND m.co_id = src.co_id AND (m.cust_id = src.cust_id OR (m.cust_id IS NULL AND src.cust_id IS NULL)))
        OR (src.bom_id IS NOT NULL AND m.bom_id = src.bom_id AND m.cust_id = src.cust_id)
    )
  );


-- TVS / HE240770
INSERT INTO lw_packing_part_map (co_id, bom_id, cust_id, tray_item_code, carton_item_code, tray_capacity, carton_capacity)
SELECT src.co_id, src.bom_id, src.cust_id, 'SE-1-S-12C-1', NULL, NULL, NULL
FROM (
    SELECT
        (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'HE240770'
          AND TRIM(cu.CU_Name) LIKE '%TVS%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) AS co_id,
        CASE WHEN (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'HE240770'
          AND TRIM(cu.CU_Name) LIKE '%TVS%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) IS NULL THEN (
        SELECT b.bom_id
        FROM bom b
        INNER JOIN customer cu ON cu.CU_Id = b.cust_id
        WHERE TRIM(b.bom_no) = 'HE240770'
          AND b.is_latest_version = 'Y'
          AND TRIM(cu.CU_Name) LIKE '%TVS%'
        ORDER BY b.cust_id
        LIMIT 1
    ) ELSE NULL END AS bom_id,
        COALESCE(
        (SELECT c.CO_CUSTID FROM components c
         INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
         WHERE TRIM(c.CO_PARTNO) = 'HE240770' AND TRIM(cu.CU_Name) LIKE '%TVS%' AND c.CO_ACTIVEYN = 'Y'
         ORDER BY c.CO_ID DESC LIMIT 1),
        (SELECT b.cust_id FROM bom b
         INNER JOIN customer cu ON cu.CU_Id = b.cust_id
         WHERE TRIM(b.bom_no) = 'HE240770' AND b.is_latest_version = 'Y' AND TRIM(cu.CU_Name) LIKE '%TVS%'
         LIMIT 1),
        (SELECT cu.CU_Id FROM customer cu WHERE TRIM(cu.CU_Name) LIKE '%TVS%' LIMIT 1)
    ) AS cust_id
) src
WHERE (src.co_id IS NOT NULL OR src.bom_id IS NOT NULL)
  AND NOT EXISTS (
    SELECT 1 FROM lw_packing_part_map m
    WHERE (
        (src.co_id IS NOT NULL AND m.co_id = src.co_id AND (m.cust_id = src.cust_id OR (m.cust_id IS NULL AND src.cust_id IS NULL)))
        OR (src.bom_id IS NOT NULL AND m.bom_id = src.bom_id AND m.cust_id = src.cust_id)
    )
  );


-- TVS / HE240780
INSERT INTO lw_packing_part_map (co_id, bom_id, cust_id, tray_item_code, carton_item_code, tray_capacity, carton_capacity)
SELECT src.co_id, src.bom_id, src.cust_id, 'SE-1-S-14C-3', NULL, NULL, NULL
FROM (
    SELECT
        (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'HE240780'
          AND TRIM(cu.CU_Name) LIKE '%TVS%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) AS co_id,
        CASE WHEN (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'HE240780'
          AND TRIM(cu.CU_Name) LIKE '%TVS%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) IS NULL THEN (
        SELECT b.bom_id
        FROM bom b
        INNER JOIN customer cu ON cu.CU_Id = b.cust_id
        WHERE TRIM(b.bom_no) = 'HE240780'
          AND b.is_latest_version = 'Y'
          AND TRIM(cu.CU_Name) LIKE '%TVS%'
        ORDER BY b.cust_id
        LIMIT 1
    ) ELSE NULL END AS bom_id,
        COALESCE(
        (SELECT c.CO_CUSTID FROM components c
         INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
         WHERE TRIM(c.CO_PARTNO) = 'HE240780' AND TRIM(cu.CU_Name) LIKE '%TVS%' AND c.CO_ACTIVEYN = 'Y'
         ORDER BY c.CO_ID DESC LIMIT 1),
        (SELECT b.cust_id FROM bom b
         INNER JOIN customer cu ON cu.CU_Id = b.cust_id
         WHERE TRIM(b.bom_no) = 'HE240780' AND b.is_latest_version = 'Y' AND TRIM(cu.CU_Name) LIKE '%TVS%'
         LIMIT 1),
        (SELECT cu.CU_Id FROM customer cu WHERE TRIM(cu.CU_Name) LIKE '%TVS%' LIMIT 1)
    ) AS cust_id
) src
WHERE (src.co_id IS NOT NULL OR src.bom_id IS NOT NULL)
  AND NOT EXISTS (
    SELECT 1 FROM lw_packing_part_map m
    WHERE (
        (src.co_id IS NOT NULL AND m.co_id = src.co_id AND (m.cust_id = src.cust_id OR (m.cust_id IS NULL AND src.cust_id IS NULL)))
        OR (src.bom_id IS NOT NULL AND m.bom_id = src.bom_id AND m.cust_id = src.cust_id)
    )
  );


-- TVS / HE240790
INSERT INTO lw_packing_part_map (co_id, bom_id, cust_id, tray_item_code, carton_item_code, tray_capacity, carton_capacity)
SELECT src.co_id, src.bom_id, src.cust_id, 'SE-1-S-24C-1', NULL, NULL, NULL
FROM (
    SELECT
        (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'HE240790'
          AND TRIM(cu.CU_Name) LIKE '%TVS%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) AS co_id,
        CASE WHEN (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'HE240790'
          AND TRIM(cu.CU_Name) LIKE '%TVS%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) IS NULL THEN (
        SELECT b.bom_id
        FROM bom b
        INNER JOIN customer cu ON cu.CU_Id = b.cust_id
        WHERE TRIM(b.bom_no) = 'HE240790'
          AND b.is_latest_version = 'Y'
          AND TRIM(cu.CU_Name) LIKE '%TVS%'
        ORDER BY b.cust_id
        LIMIT 1
    ) ELSE NULL END AS bom_id,
        COALESCE(
        (SELECT c.CO_CUSTID FROM components c
         INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
         WHERE TRIM(c.CO_PARTNO) = 'HE240790' AND TRIM(cu.CU_Name) LIKE '%TVS%' AND c.CO_ACTIVEYN = 'Y'
         ORDER BY c.CO_ID DESC LIMIT 1),
        (SELECT b.cust_id FROM bom b
         INNER JOIN customer cu ON cu.CU_Id = b.cust_id
         WHERE TRIM(b.bom_no) = 'HE240790' AND b.is_latest_version = 'Y' AND TRIM(cu.CU_Name) LIKE '%TVS%'
         LIMIT 1),
        (SELECT cu.CU_Id FROM customer cu WHERE TRIM(cu.CU_Name) LIKE '%TVS%' LIMIT 1)
    ) AS cust_id
) src
WHERE (src.co_id IS NOT NULL OR src.bom_id IS NOT NULL)
  AND NOT EXISTS (
    SELECT 1 FROM lw_packing_part_map m
    WHERE (
        (src.co_id IS NOT NULL AND m.co_id = src.co_id AND (m.cust_id = src.cust_id OR (m.cust_id IS NULL AND src.cust_id IS NULL)))
        OR (src.bom_id IS NOT NULL AND m.bom_id = src.bom_id AND m.cust_id = src.cust_id)
    )
  );


-- TVS / HE240800
INSERT INTO lw_packing_part_map (co_id, bom_id, cust_id, tray_item_code, carton_item_code, tray_capacity, carton_capacity)
SELECT src.co_id, src.bom_id, src.cust_id, 'SE-1-S-20C-1', NULL, NULL, NULL
FROM (
    SELECT
        (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'HE240800'
          AND TRIM(cu.CU_Name) LIKE '%TVS%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) AS co_id,
        CASE WHEN (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'HE240800'
          AND TRIM(cu.CU_Name) LIKE '%TVS%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) IS NULL THEN (
        SELECT b.bom_id
        FROM bom b
        INNER JOIN customer cu ON cu.CU_Id = b.cust_id
        WHERE TRIM(b.bom_no) = 'HE240800'
          AND b.is_latest_version = 'Y'
          AND TRIM(cu.CU_Name) LIKE '%TVS%'
        ORDER BY b.cust_id
        LIMIT 1
    ) ELSE NULL END AS bom_id,
        COALESCE(
        (SELECT c.CO_CUSTID FROM components c
         INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
         WHERE TRIM(c.CO_PARTNO) = 'HE240800' AND TRIM(cu.CU_Name) LIKE '%TVS%' AND c.CO_ACTIVEYN = 'Y'
         ORDER BY c.CO_ID DESC LIMIT 1),
        (SELECT b.cust_id FROM bom b
         INNER JOIN customer cu ON cu.CU_Id = b.cust_id
         WHERE TRIM(b.bom_no) = 'HE240800' AND b.is_latest_version = 'Y' AND TRIM(cu.CU_Name) LIKE '%TVS%'
         LIMIT 1),
        (SELECT cu.CU_Id FROM customer cu WHERE TRIM(cu.CU_Name) LIKE '%TVS%' LIMIT 1)
    ) AS cust_id
) src
WHERE (src.co_id IS NOT NULL OR src.bom_id IS NOT NULL)
  AND NOT EXISTS (
    SELECT 1 FROM lw_packing_part_map m
    WHERE (
        (src.co_id IS NOT NULL AND m.co_id = src.co_id AND (m.cust_id = src.cust_id OR (m.cust_id IS NULL AND src.cust_id IS NULL)))
        OR (src.bom_id IS NOT NULL AND m.bom_id = src.bom_id AND m.cust_id = src.cust_id)
    )
  );


-- TVS / HE240960
INSERT INTO lw_packing_part_map (co_id, bom_id, cust_id, tray_item_code, carton_item_code, tray_capacity, carton_capacity)
SELECT src.co_id, src.bom_id, src.cust_id, 'SE-1-S-16C-1', NULL, NULL, NULL
FROM (
    SELECT
        (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'HE240960'
          AND TRIM(cu.CU_Name) LIKE '%TVS%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) AS co_id,
        CASE WHEN (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'HE240960'
          AND TRIM(cu.CU_Name) LIKE '%TVS%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) IS NULL THEN (
        SELECT b.bom_id
        FROM bom b
        INNER JOIN customer cu ON cu.CU_Id = b.cust_id
        WHERE TRIM(b.bom_no) = 'HE240960'
          AND b.is_latest_version = 'Y'
          AND TRIM(cu.CU_Name) LIKE '%TVS%'
        ORDER BY b.cust_id
        LIMIT 1
    ) ELSE NULL END AS bom_id,
        COALESCE(
        (SELECT c.CO_CUSTID FROM components c
         INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
         WHERE TRIM(c.CO_PARTNO) = 'HE240960' AND TRIM(cu.CU_Name) LIKE '%TVS%' AND c.CO_ACTIVEYN = 'Y'
         ORDER BY c.CO_ID DESC LIMIT 1),
        (SELECT b.cust_id FROM bom b
         INNER JOIN customer cu ON cu.CU_Id = b.cust_id
         WHERE TRIM(b.bom_no) = 'HE240960' AND b.is_latest_version = 'Y' AND TRIM(cu.CU_Name) LIKE '%TVS%'
         LIMIT 1),
        (SELECT cu.CU_Id FROM customer cu WHERE TRIM(cu.CU_Name) LIKE '%TVS%' LIMIT 1)
    ) AS cust_id
) src
WHERE (src.co_id IS NOT NULL OR src.bom_id IS NOT NULL)
  AND NOT EXISTS (
    SELECT 1 FROM lw_packing_part_map m
    WHERE (
        (src.co_id IS NOT NULL AND m.co_id = src.co_id AND (m.cust_id = src.cust_id OR (m.cust_id IS NULL AND src.cust_id IS NULL)))
        OR (src.bom_id IS NOT NULL AND m.bom_id = src.bom_id AND m.cust_id = src.cust_id)
    )
  );


-- TVS / HE240970
INSERT INTO lw_packing_part_map (co_id, bom_id, cust_id, tray_item_code, carton_item_code, tray_capacity, carton_capacity)
SELECT src.co_id, src.bom_id, src.cust_id, 'SE-1-S-25C-1', NULL, NULL, NULL
FROM (
    SELECT
        (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'HE240970'
          AND TRIM(cu.CU_Name) LIKE '%TVS%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) AS co_id,
        CASE WHEN (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'HE240970'
          AND TRIM(cu.CU_Name) LIKE '%TVS%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) IS NULL THEN (
        SELECT b.bom_id
        FROM bom b
        INNER JOIN customer cu ON cu.CU_Id = b.cust_id
        WHERE TRIM(b.bom_no) = 'HE240970'
          AND b.is_latest_version = 'Y'
          AND TRIM(cu.CU_Name) LIKE '%TVS%'
        ORDER BY b.cust_id
        LIMIT 1
    ) ELSE NULL END AS bom_id,
        COALESCE(
        (SELECT c.CO_CUSTID FROM components c
         INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
         WHERE TRIM(c.CO_PARTNO) = 'HE240970' AND TRIM(cu.CU_Name) LIKE '%TVS%' AND c.CO_ACTIVEYN = 'Y'
         ORDER BY c.CO_ID DESC LIMIT 1),
        (SELECT b.cust_id FROM bom b
         INNER JOIN customer cu ON cu.CU_Id = b.cust_id
         WHERE TRIM(b.bom_no) = 'HE240970' AND b.is_latest_version = 'Y' AND TRIM(cu.CU_Name) LIKE '%TVS%'
         LIMIT 1),
        (SELECT cu.CU_Id FROM customer cu WHERE TRIM(cu.CU_Name) LIKE '%TVS%' LIMIT 1)
    ) AS cust_id
) src
WHERE (src.co_id IS NOT NULL OR src.bom_id IS NOT NULL)
  AND NOT EXISTS (
    SELECT 1 FROM lw_packing_part_map m
    WHERE (
        (src.co_id IS NOT NULL AND m.co_id = src.co_id AND (m.cust_id = src.cust_id OR (m.cust_id IS NULL AND src.cust_id IS NULL)))
        OR (src.bom_id IS NOT NULL AND m.bom_id = src.bom_id AND m.cust_id = src.cust_id)
    )
  );


-- TVS / KE241000
INSERT INTO lw_packing_part_map (co_id, bom_id, cust_id, tray_item_code, carton_item_code, tray_capacity, carton_capacity)
SELECT src.co_id, src.bom_id, src.cust_id, 'SE-1-S-6C-1', 'SE-C-330280500', 30, 180
FROM (
    SELECT
        (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'KE241000'
          AND TRIM(cu.CU_Name) LIKE '%TVS%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) AS co_id,
        CASE WHEN (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'KE241000'
          AND TRIM(cu.CU_Name) LIKE '%TVS%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) IS NULL THEN (
        SELECT b.bom_id
        FROM bom b
        INNER JOIN customer cu ON cu.CU_Id = b.cust_id
        WHERE TRIM(b.bom_no) = 'KE241000'
          AND b.is_latest_version = 'Y'
          AND TRIM(cu.CU_Name) LIKE '%TVS%'
        ORDER BY b.cust_id
        LIMIT 1
    ) ELSE NULL END AS bom_id,
        COALESCE(
        (SELECT c.CO_CUSTID FROM components c
         INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
         WHERE TRIM(c.CO_PARTNO) = 'KE241000' AND TRIM(cu.CU_Name) LIKE '%TVS%' AND c.CO_ACTIVEYN = 'Y'
         ORDER BY c.CO_ID DESC LIMIT 1),
        (SELECT b.cust_id FROM bom b
         INNER JOIN customer cu ON cu.CU_Id = b.cust_id
         WHERE TRIM(b.bom_no) = 'KE241000' AND b.is_latest_version = 'Y' AND TRIM(cu.CU_Name) LIKE '%TVS%'
         LIMIT 1),
        (SELECT cu.CU_Id FROM customer cu WHERE TRIM(cu.CU_Name) LIKE '%TVS%' LIMIT 1)
    ) AS cust_id
) src
WHERE (src.co_id IS NOT NULL OR src.bom_id IS NOT NULL)
  AND NOT EXISTS (
    SELECT 1 FROM lw_packing_part_map m
    WHERE (
        (src.co_id IS NOT NULL AND m.co_id = src.co_id AND (m.cust_id = src.cust_id OR (m.cust_id IS NULL AND src.cust_id IS NULL)))
        OR (src.bom_id IS NOT NULL AND m.bom_id = src.bom_id AND m.cust_id = src.cust_id)
    )
  );


-- TVS / KE242860
INSERT INTO lw_packing_part_map (co_id, bom_id, cust_id, tray_item_code, carton_item_code, tray_capacity, carton_capacity)
SELECT src.co_id, src.bom_id, src.cust_id, 'SE-1-S-7C-3', 'SE-C-380220360', 30, 210
FROM (
    SELECT
        (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'KE242860'
          AND TRIM(cu.CU_Name) LIKE '%TVS%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) AS co_id,
        CASE WHEN (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'KE242860'
          AND TRIM(cu.CU_Name) LIKE '%TVS%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) IS NULL THEN (
        SELECT b.bom_id
        FROM bom b
        INNER JOIN customer cu ON cu.CU_Id = b.cust_id
        WHERE TRIM(b.bom_no) = 'KE242860'
          AND b.is_latest_version = 'Y'
          AND TRIM(cu.CU_Name) LIKE '%TVS%'
        ORDER BY b.cust_id
        LIMIT 1
    ) ELSE NULL END AS bom_id,
        COALESCE(
        (SELECT c.CO_CUSTID FROM components c
         INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
         WHERE TRIM(c.CO_PARTNO) = 'KE242860' AND TRIM(cu.CU_Name) LIKE '%TVS%' AND c.CO_ACTIVEYN = 'Y'
         ORDER BY c.CO_ID DESC LIMIT 1),
        (SELECT b.cust_id FROM bom b
         INNER JOIN customer cu ON cu.CU_Id = b.cust_id
         WHERE TRIM(b.bom_no) = 'KE242860' AND b.is_latest_version = 'Y' AND TRIM(cu.CU_Name) LIKE '%TVS%'
         LIMIT 1),
        (SELECT cu.CU_Id FROM customer cu WHERE TRIM(cu.CU_Name) LIKE '%TVS%' LIMIT 1)
    ) AS cust_id
) src
WHERE (src.co_id IS NOT NULL OR src.bom_id IS NOT NULL)
  AND NOT EXISTS (
    SELECT 1 FROM lw_packing_part_map m
    WHERE (
        (src.co_id IS NOT NULL AND m.co_id = src.co_id AND (m.cust_id = src.cust_id OR (m.cust_id IS NULL AND src.cust_id IS NULL)))
        OR (src.bom_id IS NOT NULL AND m.bom_id = src.bom_id AND m.cust_id = src.cust_id)
    )
  );


-- TVS / KE242880
INSERT INTO lw_packing_part_map (co_id, bom_id, cust_id, tray_item_code, carton_item_code, tray_capacity, carton_capacity)
SELECT src.co_id, src.bom_id, src.cust_id, 'SE-1-S-7C-1', 'SE-C-345220360', 10, 70
FROM (
    SELECT
        (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'KE242880'
          AND TRIM(cu.CU_Name) LIKE '%TVS%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) AS co_id,
        CASE WHEN (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'KE242880'
          AND TRIM(cu.CU_Name) LIKE '%TVS%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) IS NULL THEN (
        SELECT b.bom_id
        FROM bom b
        INNER JOIN customer cu ON cu.CU_Id = b.cust_id
        WHERE TRIM(b.bom_no) = 'KE242880'
          AND b.is_latest_version = 'Y'
          AND TRIM(cu.CU_Name) LIKE '%TVS%'
        ORDER BY b.cust_id
        LIMIT 1
    ) ELSE NULL END AS bom_id,
        COALESCE(
        (SELECT c.CO_CUSTID FROM components c
         INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
         WHERE TRIM(c.CO_PARTNO) = 'KE242880' AND TRIM(cu.CU_Name) LIKE '%TVS%' AND c.CO_ACTIVEYN = 'Y'
         ORDER BY c.CO_ID DESC LIMIT 1),
        (SELECT b.cust_id FROM bom b
         INNER JOIN customer cu ON cu.CU_Id = b.cust_id
         WHERE TRIM(b.bom_no) = 'KE242880' AND b.is_latest_version = 'Y' AND TRIM(cu.CU_Name) LIKE '%TVS%'
         LIMIT 1),
        (SELECT cu.CU_Id FROM customer cu WHERE TRIM(cu.CU_Name) LIKE '%TVS%' LIMIT 1)
    ) AS cust_id
) src
WHERE (src.co_id IS NOT NULL OR src.bom_id IS NOT NULL)
  AND NOT EXISTS (
    SELECT 1 FROM lw_packing_part_map m
    WHERE (
        (src.co_id IS NOT NULL AND m.co_id = src.co_id AND (m.cust_id = src.cust_id OR (m.cust_id IS NULL AND src.cust_id IS NULL)))
        OR (src.bom_id IS NOT NULL AND m.bom_id = src.bom_id AND m.cust_id = src.cust_id)
    )
  );


-- TVS / KE242900
INSERT INTO lw_packing_part_map (co_id, bom_id, cust_id, tray_item_code, carton_item_code, tray_capacity, carton_capacity)
SELECT src.co_id, src.bom_id, src.cust_id, 'SE-1-S-7C-2', 'SE-C-415240360', 10, 70
FROM (
    SELECT
        (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'KE242900'
          AND TRIM(cu.CU_Name) LIKE '%TVS%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) AS co_id,
        CASE WHEN (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = 'KE242900'
          AND TRIM(cu.CU_Name) LIKE '%TVS%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) IS NULL THEN (
        SELECT b.bom_id
        FROM bom b
        INNER JOIN customer cu ON cu.CU_Id = b.cust_id
        WHERE TRIM(b.bom_no) = 'KE242900'
          AND b.is_latest_version = 'Y'
          AND TRIM(cu.CU_Name) LIKE '%TVS%'
        ORDER BY b.cust_id
        LIMIT 1
    ) ELSE NULL END AS bom_id,
        COALESCE(
        (SELECT c.CO_CUSTID FROM components c
         INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
         WHERE TRIM(c.CO_PARTNO) = 'KE242900' AND TRIM(cu.CU_Name) LIKE '%TVS%' AND c.CO_ACTIVEYN = 'Y'
         ORDER BY c.CO_ID DESC LIMIT 1),
        (SELECT b.cust_id FROM bom b
         INNER JOIN customer cu ON cu.CU_Id = b.cust_id
         WHERE TRIM(b.bom_no) = 'KE242900' AND b.is_latest_version = 'Y' AND TRIM(cu.CU_Name) LIKE '%TVS%'
         LIMIT 1),
        (SELECT cu.CU_Id FROM customer cu WHERE TRIM(cu.CU_Name) LIKE '%TVS%' LIMIT 1)
    ) AS cust_id
) src
WHERE (src.co_id IS NOT NULL OR src.bom_id IS NOT NULL)
  AND NOT EXISTS (
    SELECT 1 FROM lw_packing_part_map m
    WHERE (
        (src.co_id IS NOT NULL AND m.co_id = src.co_id AND (m.cust_id = src.cust_id OR (m.cust_id IS NULL AND src.cust_id IS NULL)))
        OR (src.bom_id IS NOT NULL AND m.bom_id = src.bom_id AND m.cust_id = src.cust_id)
    )
  );


-- YAZAKI / 7117-6243-02
INSERT INTO lw_packing_part_map (co_id, bom_id, cust_id, tray_item_code, carton_item_code, tray_capacity, carton_capacity)
SELECT src.co_id, src.bom_id, src.cust_id, 'SE-2-S-88C-1', 'SE-C-355300200', 25, 2200
FROM (
    SELECT
        (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = '7117-6243-02'
          AND TRIM(cu.CU_Name) LIKE '%YAZAKI%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) AS co_id,
        CASE WHEN (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = '7117-6243-02'
          AND TRIM(cu.CU_Name) LIKE '%YAZAKI%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) IS NULL THEN (
        SELECT b.bom_id
        FROM bom b
        INNER JOIN customer cu ON cu.CU_Id = b.cust_id
        WHERE TRIM(b.bom_no) = '7117-6243-02'
          AND b.is_latest_version = 'Y'
          AND TRIM(cu.CU_Name) LIKE '%YAZAKI%'
        ORDER BY b.cust_id
        LIMIT 1
    ) ELSE NULL END AS bom_id,
        COALESCE(
        (SELECT c.CO_CUSTID FROM components c
         INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
         WHERE TRIM(c.CO_PARTNO) = '7117-6243-02' AND TRIM(cu.CU_Name) LIKE '%YAZAKI%' AND c.CO_ACTIVEYN = 'Y'
         ORDER BY c.CO_ID DESC LIMIT 1),
        (SELECT b.cust_id FROM bom b
         INNER JOIN customer cu ON cu.CU_Id = b.cust_id
         WHERE TRIM(b.bom_no) = '7117-6243-02' AND b.is_latest_version = 'Y' AND TRIM(cu.CU_Name) LIKE '%YAZAKI%'
         LIMIT 1),
        (SELECT cu.CU_Id FROM customer cu WHERE TRIM(cu.CU_Name) LIKE '%YAZAKI%' LIMIT 1)
    ) AS cust_id
) src
WHERE (src.co_id IS NOT NULL OR src.bom_id IS NOT NULL)
  AND NOT EXISTS (
    SELECT 1 FROM lw_packing_part_map m
    WHERE (
        (src.co_id IS NOT NULL AND m.co_id = src.co_id AND (m.cust_id = src.cust_id OR (m.cust_id IS NULL AND src.cust_id IS NULL)))
        OR (src.bom_id IS NOT NULL AND m.bom_id = src.bom_id AND m.cust_id = src.cust_id)
    )
  );


-- YAZAKI / 7117-6244-02
INSERT INTO lw_packing_part_map (co_id, bom_id, cust_id, tray_item_code, carton_item_code, tray_capacity, carton_capacity)
SELECT src.co_id, src.bom_id, src.cust_id, 'SE-2-S-88C-2', 'SE-C-355300200', 25, 2200
FROM (
    SELECT
        (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = '7117-6244-02'
          AND TRIM(cu.CU_Name) LIKE '%YAZAKI%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) AS co_id,
        CASE WHEN (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = '7117-6244-02'
          AND TRIM(cu.CU_Name) LIKE '%YAZAKI%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) IS NULL THEN (
        SELECT b.bom_id
        FROM bom b
        INNER JOIN customer cu ON cu.CU_Id = b.cust_id
        WHERE TRIM(b.bom_no) = '7117-6244-02'
          AND b.is_latest_version = 'Y'
          AND TRIM(cu.CU_Name) LIKE '%YAZAKI%'
        ORDER BY b.cust_id
        LIMIT 1
    ) ELSE NULL END AS bom_id,
        COALESCE(
        (SELECT c.CO_CUSTID FROM components c
         INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
         WHERE TRIM(c.CO_PARTNO) = '7117-6244-02' AND TRIM(cu.CU_Name) LIKE '%YAZAKI%' AND c.CO_ACTIVEYN = 'Y'
         ORDER BY c.CO_ID DESC LIMIT 1),
        (SELECT b.cust_id FROM bom b
         INNER JOIN customer cu ON cu.CU_Id = b.cust_id
         WHERE TRIM(b.bom_no) = '7117-6244-02' AND b.is_latest_version = 'Y' AND TRIM(cu.CU_Name) LIKE '%YAZAKI%'
         LIMIT 1),
        (SELECT cu.CU_Id FROM customer cu WHERE TRIM(cu.CU_Name) LIKE '%YAZAKI%' LIMIT 1)
    ) AS cust_id
) src
WHERE (src.co_id IS NOT NULL OR src.bom_id IS NOT NULL)
  AND NOT EXISTS (
    SELECT 1 FROM lw_packing_part_map m
    WHERE (
        (src.co_id IS NOT NULL AND m.co_id = src.co_id AND (m.cust_id = src.cust_id OR (m.cust_id IS NULL AND src.cust_id IS NULL)))
        OR (src.bom_id IS NOT NULL AND m.bom_id = src.bom_id AND m.cust_id = src.cust_id)
    )
  );


-- YAZAKI / 7117-6245-02
INSERT INTO lw_packing_part_map (co_id, bom_id, cust_id, tray_item_code, carton_item_code, tray_capacity, carton_capacity)
SELECT src.co_id, src.bom_id, src.cust_id, 'SE-2-S-130C-1', 'SE-C-355300200', 20, 2600
FROM (
    SELECT
        (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = '7117-6245-02'
          AND TRIM(cu.CU_Name) LIKE '%YAZAKI%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) AS co_id,
        CASE WHEN (
        SELECT c.CO_ID
        FROM components c
        INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
        WHERE TRIM(c.CO_PARTNO) = '7117-6245-02'
          AND TRIM(cu.CU_Name) LIKE '%YAZAKI%'
          AND c.CO_ACTIVEYN = 'Y'
        ORDER BY c.CO_ID DESC
        LIMIT 1
    ) IS NULL THEN (
        SELECT b.bom_id
        FROM bom b
        INNER JOIN customer cu ON cu.CU_Id = b.cust_id
        WHERE TRIM(b.bom_no) = '7117-6245-02'
          AND b.is_latest_version = 'Y'
          AND TRIM(cu.CU_Name) LIKE '%YAZAKI%'
        ORDER BY b.cust_id
        LIMIT 1
    ) ELSE NULL END AS bom_id,
        COALESCE(
        (SELECT c.CO_CUSTID FROM components c
         INNER JOIN customer cu ON cu.CU_Id = c.CO_CUSTID
         WHERE TRIM(c.CO_PARTNO) = '7117-6245-02' AND TRIM(cu.CU_Name) LIKE '%YAZAKI%' AND c.CO_ACTIVEYN = 'Y'
         ORDER BY c.CO_ID DESC LIMIT 1),
        (SELECT b.cust_id FROM bom b
         INNER JOIN customer cu ON cu.CU_Id = b.cust_id
         WHERE TRIM(b.bom_no) = '7117-6245-02' AND b.is_latest_version = 'Y' AND TRIM(cu.CU_Name) LIKE '%YAZAKI%'
         LIMIT 1),
        (SELECT cu.CU_Id FROM customer cu WHERE TRIM(cu.CU_Name) LIKE '%YAZAKI%' LIMIT 1)
    ) AS cust_id
) src
WHERE (src.co_id IS NOT NULL OR src.bom_id IS NOT NULL)
  AND NOT EXISTS (
    SELECT 1 FROM lw_packing_part_map m
    WHERE (
        (src.co_id IS NOT NULL AND m.co_id = src.co_id AND (m.cust_id = src.cust_id OR (m.cust_id IS NULL AND src.cust_id IS NULL)))
        OR (src.bom_id IS NOT NULL AND m.bom_id = src.bom_id AND m.cust_id = src.cust_id)
    )
  );


