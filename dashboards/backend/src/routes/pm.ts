import { Hono } from "hono";
import { sql } from "kysely";
import ExcelJS from "exceljs";
import { db } from "../db";
import { env } from "../env";
import { mkdirSync, existsSync } from "fs";
import { join, extname } from "path";
import { requireAnyAccess, requirePlusAccess } from "../middleware";
import {
  getEntries,
  addEntry,
  updateEntry,
  confirmMaintenance,
  deleteEntry,
  getStrokeInfo,
  getToolStrokes,
} from "../db/pmStore";

const pm = new Hono();

type PMExportMode = "all" | "safe" | "warning" | "critical";

function parsePMExportMode(value: string | undefined): PMExportMode {
  if (value === "safe" || value === "warning" || value === "critical") {
    return value;
  }
  return "all";
}

function matchPMThreshold(mode: PMExportMode, pmPercentage: number): boolean {
  if (mode === "critical") return pmPercentage >= 100;
  if (mode === "warning") return pmPercentage >= 80 && pmPercentage < 100;
  if (mode === "safe") return pmPercentage < 80;
  return true;
}

// GET / — list all PM entries (tool_life + maintenance history)
pm.get("/", requireAnyAccess(["preventive_maintenance", "life_report"]), async (c) => {
  const entries = await getEntries();
  return c.json(entries);
});

// GET /status — PM entries relative to their next PM stroke target
// ?threshold=N (default 80) — only return tools with pmPercentage >= N
pm.get("/status", requireAnyAccess(["preventive_maintenance", "life_report"]), async (c) => {
  const thresholdParam = c.req.query("threshold");
  const threshold = thresholdParam !== undefined ? Number(thresholdParam) : 80;

  // Single efficient query: join tool_life with latest PM entry + aggregated strokes
  const rows = await sql<{
    toolId: number;
    toolNo: string;
    toolLife: number;
    spm: number;
    pmStrokes: number;
    pmCurrentStroke: number;
    nextStroke: number;
    lastMaintenanceDate: string | null;
    totalLifetimeStrokes: number;
    maintenanceCount: number;
  }>`
    SELECT
      tl.TL_tool_id          AS toolId,
      tl.TL_tool_number      AS toolNo,
      tl.TL_life_span        AS toolLife,
      tl.TL_spm              AS spm,
      tl.TL_preventive_maintenance_strokes AS pmStrokes,
      COALESCE((
        SELECT MAX(comp.componentStrokes)
        FROM (
          SELECT
            ct.CT_COMPID,
            SUM(pd.PD_PRODQTY / GREATEST(COALESCE(ct.CT_NO_OF_CAVITY, 1), 1)) AS componentStrokes
          FROM production_details pd
          INNER JOIN components_tool ct ON ct.CT_ID = pd.PD_TOOLID
          WHERE ct.CT_TOOLNO = tl.TL_tool_number
            AND pd.PD_DATE <= pm.PM_date
          GROUP BY ct.CT_COMPID
        ) comp
      ), 0)                 AS pmCurrentStroke,
      pm.PM_next_stroke      AS nextStroke,
      pm.PM_date             AS lastMaintenanceDate,
      COALESCE(strokes.totalStrokes, 0) AS totalLifetimeStrokes,
      COALESCE(pm_count.cnt, 0)         AS maintenanceCount
    FROM tool_life tl
    INNER JOIN (
      SELECT pm1.*
      FROM preventive_maintenance pm1
      INNER JOIN (
        SELECT PM_tool_number, MAX(PM_id) AS maxId
        FROM preventive_maintenance
        GROUP BY PM_tool_number
      ) latest_pm ON latest_pm.PM_tool_number = pm1.PM_tool_number
        AND latest_pm.maxId = pm1.PM_id
    ) pm ON pm.PM_tool_number = tl.TL_tool_number
    LEFT JOIN (
      SELECT
        comp.toolNo,
        MAX(comp.componentStrokes) AS totalStrokes
      FROM (
        SELECT
          ct.CT_TOOLNO AS toolNo,
          ct.CT_COMPID,
          SUM(pd.PD_PRODQTY / GREATEST(COALESCE(ct.CT_NO_OF_CAVITY, 1), 1)) AS componentStrokes
        FROM production_details pd
        INNER JOIN components_tool ct ON ct.CT_ID = pd.PD_TOOLID
        GROUP BY ct.CT_TOOLNO, ct.CT_COMPID
      ) comp
      GROUP BY comp.toolNo
    ) strokes ON strokes.toolNo = tl.TL_tool_number
    LEFT JOIN (
      SELECT PM_tool_number, COUNT(*) AS cnt
      FROM preventive_maintenance
      GROUP BY PM_tool_number
    ) pm_count ON pm_count.PM_tool_number = tl.TL_tool_number
    WHERE tl.TL_tool_id = (
      SELECT tl2.TL_tool_id
      FROM tool_life tl2
      WHERE tl2.TL_tool_number = tl.TL_tool_number
      ORDER BY tl2.TL_created_at DESC, tl2.TL_tool_id DESC
      LIMIT 1
    )
      AND EXISTS (
        SELECT 1
        FROM components_tool ct_active
        WHERE ct_active.CT_TOOLNO = tl.TL_tool_number
          AND ct_active.CT_ACTIVEYN = 'Y'
      )
  `.execute(db);

  const results = [];

  for (const row of rows.rows) {
    const pmStrokes = Number(row.pmStrokes);
    const nextStroke = Number(row.nextStroke);
    const totalLifetimeStrokes = Number(row.totalLifetimeStrokes);
    const cycleStartStroke = nextStroke - pmStrokes;
    const completedInCurrentCycle = totalLifetimeStrokes - cycleStartStroke;
    const pmPercentage =
      pmStrokes > 0
        ? Math.max(0, Math.round((completedInCurrentCycle / pmStrokes) * 100))
        : 0;
    if (pmPercentage >= threshold) {
      results.push({
        toolId: Number(row.toolId),
        toolNo: row.toolNo,
        toolLife: Number(row.toolLife),
        spm: Number(row.spm),
        pmStrokes,
        pmCurrentStroke: cycleStartStroke,
        nextStroke,
        totalLifetimeStrokes,
        pmPercentage,
        lastMaintenanceDate: row.lastMaintenanceDate ?? null,
        maintenanceCount: Number(row.maintenanceCount),
      });
    }
  }

  return c.json(results);
});

// GET /export — export PM dashboard table to Excel
// query: mode=all|safe|warning|critical, search=text, asOf=ISO
pm.get("/export", requireAnyAccess(["preventive_maintenance", "life_report"]), async (c) => {
  const mode = parsePMExportMode(c.req.query("mode"));
  const search = (c.req.query("search") ?? "").trim().toLowerCase();
  const asOf = c.req.query("asOf");

  const allTools = await db
    .selectFrom("components_tool")
    .innerJoin("components as c", "c.CO_ID", "components_tool.CT_COMPID")
    .select([
      sql<number>`MIN(components_tool.CT_ID)`.as("id"),
      "components_tool.CT_TOOLNO as toolNo",
      sql<string>`GROUP_CONCAT(DISTINCT c.CO_PARTNO ORDER BY c.CO_PARTNO SEPARATOR ', ')`.as("partNo"),
    ])
    .where("components_tool.CT_ACTIVEYN", "=", "Y")
    .groupBy("components_tool.CT_TOOLNO")
    .orderBy("components_tool.CT_TOOLNO", "asc")
    .execute();

  const entries = await getEntries();
  const entryByToolNo = new Map(entries.map((entry) => [entry.toolNo, entry]));

  const statusRows = await sql<{
    toolNo: string;
    pmStrokes: number;
    pmCurrentStroke: number;
    nextStroke: number;
    totalLifetimeStrokes: number;
  }>`
    SELECT
      tl.TL_tool_number AS toolNo,
      tl.TL_preventive_maintenance_strokes AS pmStrokes,
      COALESCE((
        SELECT MAX(comp.componentStrokes)
        FROM (
          SELECT
            ct.CT_COMPID,
            SUM(pd.PD_PRODQTY / GREATEST(COALESCE(ct.CT_NO_OF_CAVITY, 1), 1)) AS componentStrokes
          FROM production_details pd
          INNER JOIN components_tool ct ON ct.CT_ID = pd.PD_TOOLID
          WHERE ct.CT_TOOLNO = tl.TL_tool_number
            AND pd.PD_DATE <= pm.PM_date
          GROUP BY ct.CT_COMPID
        ) comp
      ), 0) AS pmCurrentStroke,
      pm.PM_next_stroke AS nextStroke,
      COALESCE(strokes.totalStrokes, 0) AS totalLifetimeStrokes
    FROM tool_life tl
    INNER JOIN (
      SELECT pm1.*
      FROM preventive_maintenance pm1
      INNER JOIN (
        SELECT PM_tool_number, MAX(PM_id) AS maxId
        FROM preventive_maintenance
        GROUP BY PM_tool_number
      ) latest_pm ON latest_pm.PM_tool_number = pm1.PM_tool_number
        AND latest_pm.maxId = pm1.PM_id
    ) pm ON pm.PM_tool_number = tl.TL_tool_number
    LEFT JOIN (
      SELECT
        comp.toolNo,
        MAX(comp.componentStrokes) AS totalStrokes
      FROM (
        SELECT
          ct.CT_TOOLNO AS toolNo,
          ct.CT_COMPID,
          SUM(pd.PD_PRODQTY / GREATEST(COALESCE(ct.CT_NO_OF_CAVITY, 1), 1)) AS componentStrokes
        FROM production_details pd
        INNER JOIN components_tool ct ON ct.CT_ID = pd.PD_TOOLID
        GROUP BY ct.CT_TOOLNO, ct.CT_COMPID
      ) comp
      GROUP BY comp.toolNo
    ) strokes ON strokes.toolNo = tl.TL_tool_number
    WHERE tl.TL_tool_id = (
      SELECT tl2.TL_tool_id
      FROM tool_life tl2
      WHERE tl2.TL_tool_number = tl.TL_tool_number
      ORDER BY tl2.TL_created_at DESC, tl2.TL_tool_id DESC
      LIMIT 1
    )
      AND EXISTS (
        SELECT 1
        FROM components_tool ct_active
        WHERE ct_active.CT_TOOLNO = tl.TL_tool_number
          AND ct_active.CT_ACTIVEYN = 'Y'
      )
  `.execute(db);

  const statusByToolNo = new Map(
    statusRows.rows.map((row) => {
      const pmStrokes = Number(row.pmStrokes);
      const nextStroke = Number(row.nextStroke);
      const totalLifetimeStrokes = Number(row.totalLifetimeStrokes);
      const cycleStartStroke = nextStroke - pmStrokes;
      const completedInCurrentCycle = totalLifetimeStrokes - cycleStartStroke;
      const pmPercentage =
        pmStrokes > 0
          ? Math.max(0, Math.round((completedInCurrentCycle / pmStrokes) * 100))
          : 0;

      return [
        row.toolNo,
        {
          totalLifetimeStrokes,
          pmPercentage,
        },
      ] as const;
    })
  );

  const exportRows = allTools
    .map((tool, index) => {
      const entry = entryByToolNo.get(tool.toolNo);
      const status = statusByToolNo.get(tool.toolNo);
      const latestMaintenance =
        entry && entry.maintenanceHistory.length > 0
          ? entry.maintenanceHistory[entry.maintenanceHistory.length - 1]
          : null;

      const pmPercentage = status?.pmPercentage ?? 0;

      return {
        slNo: index + 1,
        toolNo: tool.toolNo,
        partNo: tool.partNo ?? "",
        toolLife: entry?.toolLife ?? null,
        spm: entry?.spm ?? null,
        pmStrokes: entry?.pmStrokes ?? null,
        productionDone: status?.totalLifetimeStrokes ?? (entry ? 0 : null),
        nextPmStroke: entry ? latestMaintenance?.nextStroke ?? "Not set" : null,
        lastMaintenance: entry
          ? latestMaintenance
            ? new Date(latestMaintenance.date).toLocaleDateString("en-IN", {
                day: "2-digit",
                month: "short",
                year: "numeric",
              })
            : "No maintenance"
          : null,
        pmCount: entry ? entry.maintenanceHistory.length : null,
        pmPercentage,
      };
    })
    .filter((row) => {
      if (!matchPMThreshold(mode, row.pmPercentage)) {
        return false;
      }
      if (!search) {
        return true;
      }
      return (
        row.toolNo.toLowerCase().includes(search) ||
        row.partNo.toLowerCase().includes(search)
      );
    });

  const workbook = new ExcelJS.Workbook();
  const worksheet = workbook.addWorksheet("Preventive Maintenance");

  worksheet.columns = [
    { header: "Sl No", key: "slNo", width: 8 },
    { header: "Tool No", key: "toolNo", width: 20 },
    { header: "Part No", key: "partNo", width: 20 },
    { header: "Tool Life", key: "toolLife", width: 14 },
    { header: "SPM", key: "spm", width: 10 },
    { header: "PM Strokes", key: "pmStrokes", width: 14 },
    { header: "Strokes Completed", key: "productionDone", width: 18 },
    { header: "Next PM Stroke", key: "nextPmStroke", width: 16 },
    { header: "Last Maintenance", key: "lastMaintenance", width: 18 },
    { header: "PM Count", key: "pmCount", width: 10 },
    { header: "PM %", key: "pmPercentage", width: 10 },
  ];

  for (const row of exportRows) {
    worksheet.addRow(row);
  }

  const asOfDate = asOf ? new Date(asOf) : new Date();
  const validAsOf = Number.isNaN(asOfDate.getTime()) ? new Date() : asOfDate;
  const headingText = `Preventive Maintenance as on ${validAsOf.toLocaleString("en-IN")}`;

  worksheet.insertRow(1, [headingText]);
  worksheet.insertRow(2, []);
  worksheet.mergeCells(1, 1, 1, 11);

  const headingCell = worksheet.getCell(1, 1);
  headingCell.font = { bold: true, size: 13 };

  worksheet.getRow(3).font = { bold: true };

  const buffer = await workbook.xlsx.writeBuffer();

  return new Response(Buffer.from(buffer), {
    headers: {
      "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      "Content-Disposition": "attachment; filename=\"preventive_maintenance.xlsx\"",
    },
  });
});

// GET /tool-strokes/:toolId — get total strokes for any tool (no tool_life entry required)
pm.get("/tool-strokes/:toolId", requireAnyAccess(["preventive_maintenance", "life_report"]), async (c) => {
  const toolId = Number(c.req.param("toolId"));
  const totalStrokes = await getToolStrokes(toolId);
  return c.json({ totalStrokes });
});

// POST / — add a new tool_life entry (optionally with initial PM record)
pm.post("/", requirePlusAccess("preventive_maintenance"), async (c) => {
  const body = await c.req.json<{
    toolId: number;
    toolNo: string;
    toolLife: number;
    spm: number;
    pmStrokes: number;
    nextStroke?: number;
  }>();

  if (!body.toolId || !body.toolNo || !body.toolLife || !body.pmStrokes) {
    return c.json({ message: "toolId, toolNo, toolLife, spm, and pmStrokes are required" }, 400);
  }

  try {
    const entry = await addEntry(body.toolId, body.toolNo, body.toolLife, body.spm ?? 0, body.pmStrokes, body.nextStroke);
    return c.json(entry, 201);
  } catch (err: any) {
    return c.json({ message: err.message }, 409);
  }
});

// PATCH /:toolId — update tool life, PM strokes, and/or SPM
pm.patch("/:toolId", requirePlusAccess("preventive_maintenance"), async (c) => {
  const toolId = Number(c.req.param("toolId"));
  const body = await c.req.json<{ toolLife?: number; pmStrokes?: number; spm?: number }>();

  if (body.toolLife === undefined && body.pmStrokes === undefined && body.spm === undefined) {
    return c.json({ message: "At least one of toolLife, pmStrokes, or spm is required" }, 400);
  }

  try {
    const entry = await updateEntry(toolId, body);
    return c.json(entry);
  } catch (err: any) {
    return c.json({ message: err.message }, 404);
  }
});

// GET /:toolId/stroke-info — get current stroke and suggested next PM stroke
pm.get("/:toolId/stroke-info", requireAnyAccess(["preventive_maintenance", "life_report"]), async (c) => {
  const toolId = Number(c.req.param("toolId"));
  try {
    const info = await getStrokeInfo(toolId);
    return c.json(info);
  } catch (err: any) {
    return c.json({ message: err.message }, 404);
  }
});

// POST /:toolId/confirm — confirm maintenance done (supports multipart file upload)
pm.post("/:toolId/confirm", requirePlusAccess("preventive_maintenance"), async (c) => {
  const toolId = Number(c.req.param("toolId"));
  const contentType = c.req.header("content-type") || "";

  let nextStroke: number | undefined;
  let attachmentFileName: string | null = null;

  if (contentType.includes("multipart/form-data")) {
    const formData = await c.req.formData();
    const nextStrokeVal = formData.get("nextStroke");
    nextStroke = nextStrokeVal ? Number(nextStrokeVal) : undefined;

    const file = formData.get("attachment") as File | null;
    if (file && file.size > 0) {
      // Ensure attachments directory exists
      const attachDir = env.PM_ATTACHMENTS_DIR;
      if (!existsSync(attachDir)) {
        mkdirSync(attachDir, { recursive: true });
      }

      // Look up tool number
      const entries = await getEntries();
      const toolEntry = entries.find((e) => e.toolId === toolId);
      const toolNumber = toolEntry?.toolNo ?? String(toolId);

      // Build filename: toolNumber_YYYY-MM-DD_HH-MM-SS + original extension
      const now = new Date();
      const dateStr = now.toISOString().slice(0, 19).replace("T", "_").replace(/:/g, "-"); // YYYY-MM-DD_HH-MM-SS
      const ext = extname(file.name) || "";
      attachmentFileName = `${toolNumber}_${dateStr}${ext}`;

      // Write file to disk
      const filePath = join(attachDir, attachmentFileName);
      const arrayBuffer = await file.arrayBuffer();
      await Bun.write(filePath, arrayBuffer);
    }
  } else {
    const body = await c.req.json<{ nextStroke: number }>();
    nextStroke = body.nextStroke;
  }

  if (nextStroke === undefined) {
    return c.json({ message: "nextStroke is required" }, 400);
  }

  try {
    const entry = await confirmMaintenance(toolId, nextStroke, attachmentFileName ?? undefined);
    return c.json(entry);
  } catch (err: any) {
    return c.json({ message: err.message }, 404);
  }
});

// DELETE /:toolId — remove a tool_life entry and its maintenance records
pm.delete("/:toolId", requirePlusAccess("preventive_maintenance"), async (c) => {
  const toolId = Number(c.req.param("toolId"));

  try {
    await deleteEntry(toolId);
    return c.json({ message: "Deleted" });
  } catch (err: any) {
    return c.json({ message: err.message }, 404);
  }
});

// GET /attachment/:filename — serve a saved PM attachment
pm.get("/attachment/:filename", requireAnyAccess(["preventive_maintenance", "life_report"]), async (c) => {
  const filename = c.req.param("filename");
  const filePath = join(env.PM_ATTACHMENTS_DIR, filename);

  if (!existsSync(filePath)) {
    return c.json({ message: "Attachment not found" }, 404);
  }

  const file = Bun.file(filePath);
  return new Response(file.stream(), {
    headers: {
      "Content-Type": file.type || "application/octet-stream",
      "Content-Disposition": `inline; filename="${filename}"`,
    },
  });
});

export default pm;
