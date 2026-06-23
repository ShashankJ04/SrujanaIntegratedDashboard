-- Laser Welding v4: group modal-save lines via cd_line_id
-- Re-runnable: ignore duplicate-column / duplicate-index errors if already applied.
--
-- Backfill strategy (better than cd_line_id = line_id for every row):
--   1. Infer one session per modal save from shared operator, time_taken_minutes,
--      ot_flag, part/BOM, parent lot (for consume/rework), and created_at second.
--   2. Attach packing tray/carton material lines to the product packing session
--      saved in the same second with the same operator/time/OT.
--   3. Fallback: any remaining committed line becomes its own session (line_id).
--   4. Pending draft rows (source_lot_no = '__session__', qty 0) stay NULL.
--
-- Historical merges (same part+operator all day with different saves but identical
-- metadata) cannot be split perfectly; new saves use insert-only cd_line_id batches.

ALTER TABLE laser_welding_line
  ADD COLUMN cd_line_id INT NULL AFTER line_id;

ALTER TABLE laser_welding_line
  ADD INDEX idx_lwl_line_cd (cd_line_id);

DROP TEMPORARY TABLE IF EXISTS lw_cd_session_map;

CREATE TEMPORARY TABLE lw_cd_session_map (
  line_id    INT PRIMARY KEY,
  cd_line_id INT NOT NULL
);

-- Grid-modal sessions: inspection, cleaning, QA, packing (source lots only)
INSERT INTO lw_cd_session_map (line_id, cd_line_id)
SELECT
  ln.line_id,
  grp.cd_line_id
FROM laser_welding_line ln
INNER JOIN (
  SELECT
    MIN(line_id) AS cd_line_id,
    line_type,
    production_date,
    COALESCE(operator_id, -1) AS op_id,
    COALESCE(time_taken_minutes, -1) AS time_mins,
    ot_flag,
    TRIM(part_number) AS part_no,
    COALESCE(bom_id, '') AS bom_key,
    DATE_FORMAT(created_at, '%Y-%m-%d %H:%i:%s') AS created_sec
  FROM laser_welding_line
  WHERE cd_line_id IS NULL
    AND source_lot_no <> '__session__'
    AND (
      line_type IN ('Part_Inspection', 'Assembly_Inspection', 'QA_Disposition')
      OR (line_type = 'Packing' AND lot_id IS NOT NULL)
    )
  GROUP BY
    line_type,
    production_date,
    op_id,
    time_mins,
    ot_flag,
    part_no,
    bom_key,
    created_sec
) grp
  ON ln.line_type = grp.line_type
 AND ln.production_date = grp.production_date
 AND COALESCE(ln.operator_id, -1) = grp.op_id
 AND COALESCE(ln.time_taken_minutes, -1) = grp.time_mins
 AND ln.ot_flag = grp.ot_flag
 AND TRIM(ln.part_number) = grp.part_no
 AND COALESCE(ln.bom_id, '') = grp.bom_key
 AND DATE_FORMAT(ln.created_at, '%Y-%m-%d %H:%i:%s') = grp.created_sec
WHERE ln.cd_line_id IS NULL
  AND ln.source_lot_no <> '__session__'
  AND (
    ln.line_type IN ('Part_Inspection', 'Assembly_Inspection', 'QA_Disposition')
    OR (ln.line_type = 'Packing' AND ln.lot_id IS NOT NULL)
  );

-- Weld / sub-assembly consume & rework: one session per parent lot save
INSERT INTO lw_cd_session_map (line_id, cd_line_id)
SELECT
  ln.line_id,
  grp.cd_line_id
FROM laser_welding_line ln
INNER JOIN (
  SELECT
    MIN(line_id) AS cd_line_id,
    line_type,
    production_date,
    COALESCE(operator_id, -1) AS op_id,
    COALESCE(machine_id, -1) AS machine_key,
    COALESCE(time_taken_minutes, -1) AS time_mins,
    ot_flag,
    lot_id AS parent_lot_id,
    DATE_FORMAT(created_at, '%Y-%m-%d %H:%i:%s') AS created_sec
  FROM laser_welding_line
  WHERE cd_line_id IS NULL
    AND source_lot_no <> '__session__'
    AND lot_id IS NOT NULL
    AND line_type IN (
      'Welding_Consume',
      'Welding_Rework',
      'SubAssembly_Consume',
      'SubAssembly_Rework',
      'Assembly_Consume'
    )
  GROUP BY
    line_type,
    production_date,
    op_id,
    machine_key,
    time_mins,
    ot_flag,
    parent_lot_id,
    created_sec
) grp
  ON ln.line_type = grp.line_type
 AND ln.production_date = grp.production_date
 AND COALESCE(ln.operator_id, -1) = grp.op_id
 AND COALESCE(ln.machine_id, -1) = grp.machine_key
 AND COALESCE(ln.time_taken_minutes, -1) = grp.time_mins
 AND ln.ot_flag = grp.ot_flag
 AND ln.lot_id = grp.parent_lot_id
 AND DATE_FORMAT(ln.created_at, '%Y-%m-%d %H:%i:%s') = grp.created_sec
WHERE ln.cd_line_id IS NULL
  AND ln.source_lot_no <> '__session__'
  AND ln.lot_id IS NOT NULL
  AND ln.line_type IN (
    'Welding_Consume',
    'Welding_Rework',
    'SubAssembly_Consume',
    'SubAssembly_Rework',
    'Assembly_Consume'
  );

UPDATE laser_welding_line ln
INNER JOIN lw_cd_session_map m ON m.line_id = ln.line_id
SET ln.cd_line_id = m.cd_line_id;

-- Packing tray/carton lines → same cd_line_id as product lines from that save
UPDATE laser_welding_line mat
INNER JOIN (
  SELECT
    mat.line_id,
    MIN(prod.line_id) AS cd_line_id
  FROM laser_welding_line mat
  INNER JOIN laser_welding_line prod
    ON prod.line_type = 'Packing'
   AND prod.lot_id IS NOT NULL
   AND prod.production_date = mat.production_date
   AND COALESCE(prod.operator_id, -1) = COALESCE(mat.operator_id, -1)
   AND COALESCE(prod.time_taken_minutes, -1) = COALESCE(mat.time_taken_minutes, -1)
   AND prod.ot_flag = mat.ot_flag
   AND DATE_FORMAT(prod.created_at, '%Y-%m-%d %H:%i:%s')
       = DATE_FORMAT(mat.created_at, '%Y-%m-%d %H:%i:%s')
  WHERE mat.line_type = 'Packing'
    AND mat.lot_id IS NULL
    AND mat.source_lot_no = '__session__'
    AND mat.cd_line_id IS NULL
  GROUP BY mat.line_id
) sess ON sess.line_id = mat.line_id
SET mat.cd_line_id = sess.cd_line_id;

-- Singleton fallback for anything else committed (legacy / odd rows)
UPDATE laser_welding_line
SET cd_line_id = line_id
WHERE cd_line_id IS NULL;
DROP TEMPORARY TABLE IF EXISTS lw_cd_session_map;

-- ---------------------------------------------------------------------------
-- Re-infer sessions after the naive backfill (cd_line_id = line_id):
--   UPDATE laser_welding_line SET cd_line_id = NULL WHERE source_lot_no <> '__session__';
-- Then re-run from "DROP TEMPORARY TABLE IF EXISTS lw_cd_session_map" (before INSERTs) through here.
-- ---------------------------------------------------------------------------
