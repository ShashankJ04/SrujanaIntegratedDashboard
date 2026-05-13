-- Supplier/component balance by stage → comp_stockhistory (plant fixed as 0).
-- Mirrors your pivot’s inner totals; one history row per component + stage.

INSERT INTO comp_stockhistory (
    CH_PLANTID,
    CH_MONTH,
    CH_YEAR,
    CH_COMPID,
    CH_STAGEID,
    CH_QTY,
    CH_WEEK,
    CH_LASTUPDATED
)
SELECT
    0 AS CH_PLANTID,
    MONTH(CURDATE()) AS CH_MONTH,
    YEAR(CURDATE()) AS CH_YEAR,
    t.cd_compid AS CH_COMPID,
    t.cd_opstage AS CH_STAGEID,
    t.compbalance AS CH_QTY,
    WEEK(CURDATE(), 3) AS CH_WEEK,
    NOW() AS CH_LASTUPDATED
FROM (
    SELECT
        cd_compid,
        cd_opstage,
        COALESCE(
            SUM(
                CASE
                    WHEN cm_movement = 'O' THEN cd_qty
                    WHEN cm_movement = 'I' THEN -cd_qty
                    ELSE 0
                END
            ),
            0
        ) - COALESCE(SUM(sd_qty), 0) AS compbalance
    FROM comp_inwardmaster
    INNER JOIN comp_inwarddetails ON cm_id = cd_cmid
    LEFT JOIN comp_opstages ON cd_opstage = os_id
    LEFT JOIN components ON CD_COMPID = co_id AND CO_ACTIVEYN = 'Y'
    LEFT JOIN comp_scrapdetails
        ON sd_source = 'S'
        AND sd_src = 3
        AND sd_refno = CD_CMID
        AND sd_compid = cd_compid
        AND SD_OPSTAGE = cd_opstage
    WHERE co_id IS NOT NULL
      AND CD_SOURCE = 'C'
    GROUP BY cd_compid, cd_opstage
) AS t
WHERE t.compbalance > 0
  AND t.cd_opstage IS NOT NULL;
