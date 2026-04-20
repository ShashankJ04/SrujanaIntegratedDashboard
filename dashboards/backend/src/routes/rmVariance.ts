import { Hono } from "hono";
import { sql } from "kysely";
import { db } from "../db";
import { requireAccess } from "../middleware";

const rmVariance = new Hono();

rmVariance.use("*", requireAccess("rm_variance"));

/**
 * GET /api/rm-variance/:month/:year/:plantId
 *
 * Returns RM variance report for a given month, year, and plant.
 */
rmVariance.get("/:month/:year/:plantId", async (c) => {
  const monthStr = c.req.param("month");
  const yearStr = c.req.param("year");
  const plantIdStr = c.req.param("plantId");

  const month = parseInt(monthStr, 10);
  const year = parseInt(yearStr, 10);
  const plantId = parseInt(plantIdStr, 10);

  if (isNaN(month) || month < 1 || month > 12) {
    return c.json({ error: "Month must be between 1 and 12" }, 400);
  }
  if (isNaN(year) || year < 2000 || year > 2100) {
    return c.json({ error: "Year must be between 2000 and 2100" }, 400);
  }
  if (isNaN(plantId) || plantId <= 0) {
    return c.json({ error: "Invalid plant ID" }, 400);
  }

  // ── Query ───────────────────────────────────────────────────────
  try {
  const rows = await sql<{
    partno: string;
    RM: string;
    tool: string;
    custReqQty: number;
    schQty: number;
    schKg: number;
    prodQty: number;
    usedQty: number;
    theoKg: number;
  }>`
    SELECT
      co.CO_PARTNO AS partno,
      mm.MM_RawMtPartNo AS RM,
      ct.CT_TOOLNO AS tool,
      COALESCE(cust.custReqQty, 0) AS custReqQty,
      SUM(sp.PS_QTY) AS schQty,
      SUM(sp.PS_QTYKG) AS schKg,
      COALESCE(prd.prodQty, 0) AS prodQty,
      COALESCE(u.usedQty, 0) AS usedQty,
      COALESCE(prd.prodQty, 0) / cV.conVal AS theoKg
    FROM schedule_master sm
    JOIN schedule_details sd ON sd.SC_SMID = sm.SM_ID
    JOIN components co ON sd.SC_COMPID = co.CO_ID
    JOIN scheduled_production sp
      ON sp.PS_SMID = sm.SM_ID
      AND sp.PS_PARENTCOMPID = co.CO_ID
    JOIN components_tool ct ON sp.PS_TOOLID = ct.CT_ID
    JOIN materialmaster mm ON ct.CT_RMID = mm.MM_ID AND ct.CT_COMPID = co.CO_ID
    LEFT JOIN (
      SELECT CS_SCID, CS_PLANTID, SUM(CS_QTY) AS custReqQty
      FROM scheduled_customer
      GROUP BY CS_SCID, CS_PLANTID
    ) cust ON cust.CS_SCID = sd.SC_ID AND cust.CS_PLANTID = sp.PS_PLANTID
    LEFT JOIN (
      SELECT sp2.PS_PARENTCOMPID, sp2.PS_SMID, sp2.PS_PLANTID,
        SUM(pd.pd_prodqty) AS prodQty
      FROM production_details pd
      JOIN scheduled_production sp2 ON pd.PD_PSID = sp2.PS_ID
      GROUP BY sp2.PS_PARENTCOMPID, sp2.PS_SMID, sp2.PS_PLANTID
    ) prd ON prd.PS_PARENTCOMPID = co.CO_ID
      AND prd.PS_SMID = sm.SM_ID
      AND prd.PS_PLANTID = sp.PS_PLANTID
    LEFT JOIN (
      SELECT rd.rd_rmid, rd.rd_compid, rd.rd_smid, ri.RI_ISSUEPLANT,
        SUM(CASE WHEN ri.RI_MOVEMENT = 'O' THEN rd.RD_ACCEPTEDQTY ELSE 0 END) -
        SUM(CASE WHEN ri.RI_MOVEMENT = 'I' THEN rd.RD_ACCEPTEDQTY ELSE 0 END) AS usedQty
      FROM rm_inwarddetails rd
      JOIN rm_inwardmaster ri ON ri.RI_ID = rd.RD_RIID
      WHERE ri.RI_MOVEMENTTYPE = 3
      GROUP BY rd.rd_rmid, rd.rd_compid, rd.rd_smid, ri.RI_ISSUEPLANT
    ) u ON u.rd_rmid = ct.CT_RMID
      AND u.rd_compid = co.CO_ID
      AND u.rd_smid = sm.SM_ID
      AND u.RI_ISSUEPLANT = sp.PS_PLANTID
    JOIN (
      SELECT CT_COMPID, CT_ID AS ctid,
        ((1 / ((MT_Density * MM_Thickness) * MM_StripWidth)) * ((1000 * CT_NO_OF_CAVITY) / CT_Pitch)) AS conVal
      FROM components_tool
      INNER JOIN materialmaster ON CT_RMID = MM_Id
      INNER JOIN materialtypemaster ON MM_MTID = MT_Id
      WHERE CT_ActiveYN = 'Y' AND CT_PPC = 'Y' AND CT_PITCH > 0 AND CT_NO_OF_CAVITY > 0
    ) cV ON cV.CT_COMPID = co.CO_ID AND ct.CT_ID = cV.ctid
    WHERE sm.SM_YEAR = ${year}
      AND sm.SM_MONTH = ${month}
      AND sp.PS_PLANTID = ${plantId}
    GROUP BY co.CO_PARTNO, mm.MM_RawMtPartNo, ct.CT_TOOLNO,
      cust.custReqQty, prd.prodQty, u.usedQty, cV.conVal
    ORDER BY co.CO_PARTNO, mm.MM_RawMtPartNo, ct.CT_TOOLNO
  `.execute(db);

  // ── Build response ──────────────────────────────────────────────
  const entries = rows.rows.map((r) => ({
    partno: r.partno,
    rm: r.RM,
    tool: r.tool,
    custReqQty: Number(r.custReqQty),
    schQty: Number(r.schQty),
    schKg: Number(r.schKg),
    prodQty: Number(r.prodQty),
    usedQty: Number(r.usedQty),
    theoKg: Number(r.theoKg),
    variance: Number(r.usedQty) - Number(r.theoKg),
    variancePer: Number(r.theoKg) !== 0
      ? (Number(r.usedQty) / Number(r.theoKg)) * 100 - 100
      : 0,
  }));

  const totals = entries.reduce(
    (acc, e) => {
      acc.custReqQty += e.custReqQty;
      acc.schQty += e.schQty;
      acc.schKg += e.schKg;
      acc.prodQty += e.prodQty;
      acc.usedQty += e.usedQty;
      acc.theoKg += e.theoKg;
      acc.variance += e.variance;
      return acc;
    },
    {
      custReqQty: 0,
      schQty: 0,
      schKg: 0,
      prodQty: 0,
      usedQty: 0,
      theoKg: 0,
      variance: 0,
      variancePer: 0,
    }
  );

  return c.json({
    month,
    year,
    plantId,
    count: entries.length,
    totals,
    entries,
  });

  } catch (err: any) {
    console.error("RM Variance query error:", err);
    return c.json(
      { error: "Database query failed", details: err?.message ?? String(err) },
      500
    );
  }
});

export default rmVariance;
