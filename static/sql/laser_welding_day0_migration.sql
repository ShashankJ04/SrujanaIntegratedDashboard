-- =============================================================================
-- Laser Welding — Day0 opening-balance migration
-- =============================================================================
-- Run after laser_welding.sql (empty tables).
-- Re-runnable: deletes seeded lot numbers first (lines cascade).
--
--   mysql -u ... -p erp < static/sql/laser_welding.sql
--   mysql -u ... -p erp < static/sql/laser_welding_day0_migration.sql
--
-- Child lots (LN/26-27/*): part-inspection stock, bom_id NULL
-- Assembly lots (LW/26-27/*): bom_id resolved from latest BOM by bom_no
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Re-run guard — drop only the Day0 seed lot numbers (cascades to lines)
-- ---------------------------------------------------------------------------
DELETE FROM laser_welding_lot
WHERE new_lot_no IN (
    'LN/26-27/1991', 'LN/26-27/1992', 'LN/26-27/1993',
    'LW/26-27/1', 'LW/26-27/2', 'LW/26-27/3', 'LW/26-27/4', 'LW/26-27/5',
    'LW/26-27/6', 'LW/26-27/7', 'LW/26-27/8', 'LW/26-27/9',
    'LW/26-27/10', 'LW/26-27/11'
);

-- ---------------------------------------------------------------------------
-- Child part inspection lots (consumable in Laser Welding weld modal)
-- ---------------------------------------------------------------------------
INSERT INTO laser_welding_lot (
    part_number, bom_id, product_name, new_lot_no, work_date,
    total_inwarded, total_qa, total_okayed, scrap,
    rework_pending, rework_pool, inspection_pending,
    processed_at, qa_approved_at
)
SELECT
    resolved.part_number,
    NULL,
    NULL,
    resolved.new_lot_no,
    '2026-06-15',
    resolved.total_okayed,
    0,
    resolved.total_okayed,
    0,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM (
    SELECT 'LN/26-27/1991' AS new_lot_no, 'RBB00013' AS part_number, 97 AS total_okayed
    UNION ALL
    SELECT
        'LN/26-27/1992',
        COALESCE(
            (SELECT TRIM(c.CO_PARTNO)
             FROM components c
             WHERE c.CO_ACTIVEYN = 'Y'
               AND TRIM(c.CO_PARTNAME) LIKE '%Pos Rivit%'
             ORDER BY c.CO_ID
             LIMIT 1),
            (SELECT TRIM(bl.PART_NO)
             FROM bom_lin_item bl
             INNER JOIN bom b ON b.bom_id = bl.bom_id AND b.is_latest_version = 'Y'
             WHERE TRIM(bl.PART_NAME) LIKE '%Ather Pos Rivit%'
             ORDER BY bl.bom_id, bl.PART_NO
             LIMIT 1)
        ),
        142
    UNION ALL
    SELECT
        'LN/26-27/1993',
        COALESCE(
            (SELECT TRIM(c.CO_PARTNO)
             FROM components c
             WHERE c.CO_ACTIVEYN = 'Y'
               AND TRIM(c.CO_PARTNAME) LIKE '%Neg Rivit%'
             ORDER BY c.CO_ID
             LIMIT 1),
            (SELECT TRIM(bl.PART_NO)
             FROM bom_lin_item bl
             INNER JOIN bom b ON b.bom_id = bl.bom_id AND b.is_latest_version = 'Y'
             WHERE TRIM(bl.PART_NAME) LIKE '%Ather Neg Rivit%'
             ORDER BY bl.bom_id, bl.PART_NO
             LIMIT 1)
        ),
        1119
) AS resolved
WHERE resolved.part_number IS NOT NULL
  AND TRIM(resolved.part_number) != '';

-- ---------------------------------------------------------------------------
-- Final assembly lots (Laser Welding output / Cleaning)
-- part_number must equal bom.bom_no; inspection_pending = uncleaned weld qty
-- ---------------------------------------------------------------------------
INSERT INTO laser_welding_lot (
    part_number, bom_id, product_name, new_lot_no, work_date,
    total_inwarded, total_qa, total_okayed, scrap,
    rework_pending, rework_pool, inspection_pending,
    processed_at
)
SELECT
    TRIM(b.bom_no),
    b.bom_id,
    COALESCE(b.product_name, seed.product_name),
    seed.new_lot_no,
    '2026-06-15',
    seed.total_okayed,
    0,
    seed.total_okayed,
    0,
    0,
    0,
    seed.inspection_pending,
    NOW()
FROM (
    SELECT 'LW/26-27/1'  AS new_lot_no, 'KE242900'   AS bom_no, 'Connector Single Row Assy -LH'           AS product_name, 700  AS inspection_pending, 0    AS total_okayed
    UNION ALL SELECT 'LW/26-27/2',  'BY00000481', 'SC Negative Terminal Busbar Assy',         167,  672
    UNION ALL SELECT 'LW/26-27/3',  'BY00000484', 'SC Positive Terminal Busbar Assy',         434,  42
    UNION ALL SELECT 'LW/26-27/4',  'RBB00007',   'Busbar Assy Main Neg',                     0,    460
    UNION ALL SELECT 'LW/26-27/5',  'RBB00008',   'Busbar Assy Main Pos',                     0,    816
    UNION ALL SELECT 'LW/26-27/6',  'RBB00009',   'Busbar Assy I 21700, C6',                  0,    630
    UNION ALL SELECT 'LW/26-27/7',  'RBB00010',   'Busbar Assy H 21700,C6',                   1744, 4790
    UNION ALL SELECT 'LW/26-27/8',  'RBB00011',   'Busbar Ass, I2, 21700, C6',                449,  2748
    UNION ALL SELECT 'LW/26-27/9',  'RBB00012',   'Busbar Assy, H2, 21700',                   2332, 2816
    UNION ALL SELECT 'LW/26-27/10', 'R107027670', 'Positive Busbar Assy Battery Gen4',        995,  144
    UNION ALL SELECT 'LW/26-27/11', 'R107027666', 'Negative Busbar Assy Battery Gen4',          152,  102
) AS seed
INNER JOIN bom b
    ON TRIM(b.bom_no) = TRIM(seed.bom_no)
   AND b.is_latest_version = 'Y';

-- ---------------------------------------------------------------------------
-- Optional audit lines (Part_Inspection for child lots)
-- ---------------------------------------------------------------------------
INSERT INTO laser_welding_line (
    part_number, lot_id, line_type, source_lot_no, production_date,
    inspected_qty, qa_qty, scrap_qty, time_taken_minutes
)
SELECT
    l.part_number,
    l.lot_id,
    'Part_Inspection',
    l.new_lot_no,
    '2026-06-15',
    l.total_okayed,
    0,
    0,
    0
FROM laser_welding_lot l
WHERE l.bom_id IS NULL
  AND l.new_lot_no IN ('LN/26-27/1991', 'LN/26-27/1992', 'LN/26-27/1993');

-- ---------------------------------------------------------------------------
-- Verification (should return expected row counts)
-- ---------------------------------------------------------------------------
SELECT 'child_lots' AS section, COUNT(*) AS row_count
FROM laser_welding_lot
WHERE bom_id IS NULL
  AND new_lot_no LIKE 'LN/26-27/%'
UNION ALL
SELECT 'assembly_lots', COUNT(*)
FROM laser_welding_lot
WHERE bom_id IS NOT NULL
  AND new_lot_no LIKE 'LW/26-27/%'
UNION ALL
SELECT 'part_inspection_lines', COUNT(*)
FROM laser_welding_line
WHERE line_type = 'Part_Inspection'
  AND source_lot_no LIKE 'LN/26-27/%';
