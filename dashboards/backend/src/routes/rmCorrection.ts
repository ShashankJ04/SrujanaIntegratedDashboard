import { Hono } from "hono";
import { sql } from "kysely";
import { db } from "../db";

const rmCorrection = new Hono();

rmCorrection.get("/batch/:batch", async (c) => {
  const batch = (c.req.param("batch") ?? "").trim();

  if (!batch) {
    return c.json({ error: "Batch is required" }, 400);
  }

  try {
    const rows = await sql<{
      productionDate: string;
      partNo: string | null;
      lotNo: string | null;
      tool: string | null;
      calCompWt: number;
      noOfComp: number;
      sfRejNos: number;
      suWastageNos: number;
      scrapKg: number;
      partWtKg: number;
      theoRmKg: number;
    }>`
      SELECT
        DATE_FORMAT(pd_date, '%d-%m-%Y') AS productionDate,
        CO_PARTNO AS partNo,
        PD_LotNo AS lotNo,
        CT_TOOLNO AS tool,
        ROUND((COALESCE(CO_WEIGHT, 0) * COALESCE(pd_prodqty, 0)) / 1000, 4) AS calCompWt,
        pd_prodqty AS noOfComp,
        PD_SFREJECT AS sfRejNos,
        PD_SWQTY AS suWastageNos,
        PD_SCRAPQTY AS scrapKg,
        PD_QTYKG AS partWtKg,
        ROUND(pd_prodqty / NULLIF(conVal, 0), 4) AS theoRmKg
      FROM production_details
      LEFT JOIN materialmaster ON mm_id = pd_rmid
      LEFT JOIN components_tool ON ct_id = pd_toolid
      LEFT JOIN scheduled_production ON pd_psid = ps_id
      LEFT JOIN components ON PS_PARENTCOMPID = CO_ID
      LEFT JOIN (
        SELECT
          CT_ID AS ctid,
          ((1 / ((MT_Density * MM_Thickness) * MM_StripWidth)) * ((1000 * CT_NO_OF_CAVITY) / CT_Pitch)) AS conVal
        FROM components_tool
        INNER JOIN materialmaster ON CT_RMID = MM_Id
        INNER JOIN materialtypemaster ON MM_MTID = MT_Id
        WHERE CT_ActiveYN = 'Y' AND CT_PITCH > 0 AND CT_NO_OF_CAVITY > 0
      ) toolConv ON ctid = ct_id
      WHERE pd_batchno = ${batch}
      ORDER BY pd_date DESC
    `.execute(db);

    const entries = rows.rows.map((r) => ({
      productionDate: r.productionDate,
      partNo: r.partNo ?? "",
      lotNo: r.lotNo ?? "",
      tool: r.tool ?? "",
      calCompWt: Number(r.calCompWt),
      noOfComp: Number(r.noOfComp),
      sfRejNos: Number(r.sfRejNos),
      suWastageNos: Number(r.suWastageNos),
      scrapKg: Number(r.scrapKg),
      partWtKg: Number(r.partWtKg),
      theoRmKg: Number(r.theoRmKg),
    }));

    return c.json({ count: entries.length, entries });
  } catch (err: any) {
    console.error("RM Correction batch details query error:", err);
    return c.json(
      { error: "Database query failed", details: err?.message ?? String(err) },
      500
    );
  }
});

/**
 * GET /api/rm-correction
 *
 * Returns stock adjustment candidates with RM remaining and scrap.
 */
rmCorrection.get("/", async (c) => {
  const startDateParam = (c.req.query("startDate") ?? "").trim();
  const isValidStartDate = /^\d{4}-\d{2}-\d{2}$/.test(startDateParam);
  const startDate = isValidStartDate ? startDateParam : null;

  try {
    const rows = await sql<{
      "Raw Material": string | null;
      batch: string;
      "Total Inwarded": number;
      "RM Given": number;
      "RM Remaining": number;
      Scrap: number;
    }>`
      SELECT
        COALESCE(prodQ.MM_RawMtPartNo, '') AS \`Raw Material\`,
        prodRM.batch AS batch,
        ROUND(COALESCE(inwardTotals.totalInwarded, 0), 2) AS \`Total Inwarded\`,
        ROUND(COALESCE(prodRM.RMGiven, 0), 2) AS \`RM Given\`,
        ROUND(COALESCE((prodRM.RMGiven - prodQ.ThRMForProduction), 0), 2) AS \`RM Remaining\`,
        ROUND(COALESCE(prodQ.pdscrap, 0), 2) AS Scrap
      FROM (
        SELECT
          RD_BATCHNO AS batch,
          rd_rmid,
          ROUND(
            SUM(CASE WHEN ri_movement = 'O' THEN rd_qty ELSE 0 END) -
            SUM(CASE WHEN ri_movement = 'I' THEN rd_acceptedqty ELSE 0 END),
            2
          ) AS RMGiven
        FROM rm_inwarddetails
        JOIN rm_inwardmaster ON rd_riid = ri_id
        WHERE RI_MOVEMENTTYPE = 3
        GROUP BY RD_BATCHNO, rd_rmid
      ) prodRM
      JOIN (
        SELECT DISTINCT PD_BATCHNO AS batch
        FROM production_details
        WHERE PD_DATE >= COALESCE(${startDate}, DATE_SUB(CURDATE(), INTERVAL 10 DAY))
          AND PD_DATE <= CURDATE()
      ) recentBatches ON recentBatches.batch = prodRM.batch
      LEFT JOIN (
        SELECT
          RD_BATCHNO AS batch,
          rd_rmid,
          ROUND(SUM(CASE WHEN ri_movement = 'I' AND RI_MOVEMENTTYPE = 1 THEN rd_acceptedqty ELSE 0 END), 2) AS totalInwarded
        FROM rm_inwarddetails
        JOIN rm_inwardmaster ON rd_riid = ri_id
        GROUP BY RD_BATCHNO, rd_rmid
      ) inwardTotals ON inwardTotals.batch = prodRM.batch AND inwardTotals.rd_rmid = prodRM.rd_rmid
      LEFT JOIN (
        SELECT
          pd_batchno AS batch,
          MM_RawMtPartNo,
          mm_id,
          ROUND(SUM(PD_PRODQTY / conVal), 2) AS ThRMForProduction,
          SUM(PD_SCRAPQTY) AS pdscrap
        FROM production_details
        LEFT JOIN scheduled_production ON pd_psid = ps_id
        LEFT JOIN (
          SELECT
            CT_COMPID,
            mm_id,
            MM_RawMtPartNo,
            ((1 / ((MT_Density * MM_Thickness) * MM_StripWidth)) * ((1000 * CT_NO_OF_CAVITY) / CT_Pitch)) AS conVal
          FROM components_tool
          INNER JOIN materialmaster ON CT_RMID = MM_Id
          INNER JOIN materialtypemaster ON MM_MTID = MT_Id
          WHERE CT_ActiveYN = 'Y'
            AND CT_PPC = 'Y'
            AND CT_PITCH > 0
            AND CT_NO_OF_CAVITY > 0
        ) t ON CT_COMPID = PS_PARENTCOMPID
        GROUP BY pd_batchno, mm_id, MM_RawMtPartNo
      ) prodQ ON prodQ.batch = prodRM.batch AND prodQ.mm_id = prodRM.rd_rmid
      WHERE NOT (
        ROUND(COALESCE((prodRM.RMGiven - prodQ.ThRMForProduction), 0), 2) = 0
        AND ROUND(COALESCE(prodQ.pdscrap, 0), 2) = 0
      )
      ORDER BY \`Raw Material\`, batch
    `.execute(db);

    const entries = rows.rows.map((r) => ({
      rawMaterial: r["Raw Material"] ?? "",
      batch: r.batch,
      totalInwarded: Number(r["Total Inwarded"]),
      rmGiven: Number(r["RM Given"]),
      rmRemaining: Number(r["RM Remaining"]),
      scrap: Number(r.Scrap),
    }));

    return c.json({
      count: entries.length,
      entries,
    });
  } catch (err: any) {
    console.error("RM Correction query error:", err);
    return c.json(
      { error: "Database query failed", details: err?.message ?? String(err) },
      500
    );
  }
});

export default rmCorrection;
