import { Hono } from "hono";
import { sql } from "kysely";
import { db } from "../db";
import { requireAccess } from "../middleware";

const production = new Hono();

production.use("*", requireAccess("production"));

/**
 * GET /api/production/:ddmmyyyy
 *
 * Returns JSON with all production that occurred on the given date,
 * along with its corresponding production-schedule details.
 */
production.get("/:ddmmyyyy", async (c) => {
  const param = c.req.param("ddmmyyyy");

  // ── Validate input ──────────────────────────────────────────────
  if (!param || param.length !== 8 || !/^\d{8}$/.test(param)) {
    return c.json(
      { error: "Use format DDMMYYYY, e.g. /api/production/01032026" },
      400
    );
  }

  const day = parseInt(param.slice(0, 2), 10);
  const month = parseInt(param.slice(2, 4), 10);
  const year = parseInt(param.slice(4, 8), 10);

  if (month < 1 || month > 12) {
    return c.json({ error: "Month must be between 01 and 12" }, 400);
  }
  if (day < 1 || day > 31) {
    return c.json({ error: "Day must be between 01 and 31" }, 400);
  }

  const dateStr = `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;

  const parsed = new Date(dateStr);
  if (isNaN(parsed.getTime()) || parsed.getDate() !== day) {
    return c.json({ error: `Invalid date: ${dateStr}` }, 400);
  }

  // ── Query ───────────────────────────────────────────────────────
  const rows = await sql<{
    customer: string;
    partno: string;
    partname: string;
    raw_material: string | null;
    scheduled_date: string;
    scheduled_qty: number;
    prod_qty: number;
    qty_kg: number;
    setup_wastage: number | null;
    sf_rejection: number | null;
    net_qty: number;
    issued_qty: number;
    required_qty: number;
    fg_stock: number;
    wip_stock: number;
    total_stock: number;
  }>`
    SELECT
      cu.CU_Name                AS customer,
      co.CO_PARTNO              AS partno,
      co.CO_PARTNAME            AS partname,
      mm.MM_RawMtPartNo         AS raw_material,
      ps.PS_DATE                AS scheduled_date,
      ps.PS_QTY                 AS scheduled_qty,
      pd.PD_PRODQTY             AS prod_qty,
      pd.PD_QTYKG               AS qty_kg,
      pd.PD_SWQTY               AS setup_wastage,
      pd.PD_SFREJECT             AS sf_rejection,
      pd.PD_NETQTY               AS net_qty,
      ps.PS_QTYKG               AS issued_qty,
      pd.PD_QTYKG               AS required_qty,
      COALESCE(stk.fg_stock, 0)    AS fg_stock,
      COALESCE(stk.wip_stock, 0)   AS wip_stock,
      COALESCE(stk.total_stock, 0) AS total_stock
    FROM production_details pd
      JOIN scheduled_production ps ON pd.PD_PSID   = ps.PS_ID
      JOIN components_tool ct      ON pd.PD_TOOLID  = ct.CT_ID
      JOIN components co           ON ct.CT_COMPID  = co.CO_ID
      JOIN customer cu             ON co.CO_CUSTID  = cu.CU_Id
      LEFT JOIN materialmaster mm  ON pd.PD_RMID    = mm.MM_Id
      LEFT JOIN (
        SELECT
          CS_COMPID,
          SUM(CASE WHEN CS_STAGEID = 6 THEN CS_QTY ELSE 0 END) AS fg_stock,
          SUM(CASE WHEN CS_STAGEID != 6 THEN CS_QTY ELSE 0 END) AS wip_stock,
          SUM(CS_QTY) AS total_stock
        FROM comp_stock
        GROUP BY CS_COMPID
      ) stk ON stk.CS_COMPID = co.CO_ID
    WHERE DATE(pd.PD_DATE) = ${dateStr}
    ORDER BY cu.CU_Name, co.CO_PARTNO
  `.execute(db);

  // ── Build response ──────────────────────────────────────────────
  const entries = rows.rows.map((r) => ({
    customer: r.customer,
    partno: r.partno,
    partname: r.partname,
    rawMaterial: r.raw_material ?? "",
    scheduledDate: r.scheduled_date,
    scheduledQty: Number(r.scheduled_qty),
    prodQty: Number(r.prod_qty),
    qtyKg: Number(r.qty_kg),
    setupWastage: Number(r.setup_wastage ?? 0),
    sfRejection: Number(r.sf_rejection ?? 0),
    netQty: Number(r.net_qty),
    issuedQty: Number(r.issued_qty),
    requiredQty: Number(r.required_qty),
    variance: Number(r.prod_qty) - Number(r.scheduled_qty),
    fgStock: Number(r.fg_stock),
    wipStock: Number(r.wip_stock),
    totalStock: Number(r.total_stock),
  }));

  const totals = entries.reduce(
    (acc, e) => {
      acc.scheduledQty += e.scheduledQty;
      acc.prodQty += e.prodQty;
      acc.qtyKg += e.qtyKg;
      acc.setupWastage += e.setupWastage;
      acc.sfRejection += e.sfRejection;
      acc.netQty += e.netQty;
      acc.issuedQty += e.issuedQty;
      acc.requiredQty += e.requiredQty;
      acc.variance += e.variance;
      return acc;
    },
    {
      scheduledQty: 0,
      prodQty: 0,
      qtyKg: 0,
      setupWastage: 0,
      sfRejection: 0,
      netQty: 0,
      issuedQty: 0,
      requiredQty: 0,
      variance: 0,
    }
  );

  return c.json({
    date: dateStr,
    count: entries.length,
    totals,
    entries,
  });
});

export default production;
