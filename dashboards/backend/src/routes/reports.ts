import { Hono } from "hono";
import ExcelJS from "exceljs";
import { createPool } from "mysql2/promise";
import { env } from "../env";
import { requireAccess, requirePlusAccess } from "../middleware";
import {
  compileReportQuery,
  createGroup,
  createReport,
  deleteGroup,
  deleteReport,
  getGroups,
  getReportById,
  getReports,
  updateReport,
} from "../db/reportsStore";

const reports = new Hono();

reports.use("*", requireAccess("reports"));

const reportQueryPool = createPool({
  host: env.DB_HOST,
  port: env.DB_PORT,
  user: env.DB_USER,
  password: env.DB_PASSWORD,
  database: env.DB_NAME,
  connectionLimit: 5,
});

function safeExcelFilename(name: string): string {
  const cleaned = name.replace(/[^a-zA-Z0-9-_ ]+/g, " ").trim().replace(/\s+/g, "_");
  return cleaned || "report";
}

async function runReportQuery(reportId: string, variables?: Record<string, string>) {
  const report = await getReportById(reportId);
  if (!report) {
    throw new Error("Report not found");
  }

  const compiled = compileReportQuery({
    queryTemplate: report.queryTemplate,
    providedVariables: variables,
  });

  const [rows, fields] = await reportQueryPool.execute<any[]>(compiled.sql, compiled.params);
  const columns = Array.isArray(fields) ? fields.map((f: any) => String(f.name)) : [];

  return {
    report,
    columns,
    rows,
  };
}

reports.get("/groups", async (c) => {
  const groups = await getGroups();
  return c.json(groups);
});

reports.post("/groups", requirePlusAccess("reports"), async (c) => {
  const body = await c.req.json<{ name?: string }>();

  if (!body.name) {
    return c.json({ message: "name is required" }, 400);
  }

  try {
    const group = await createGroup(body.name);
    return c.json(group, 201);
  } catch (err: any) {
    return c.json({ message: err.message }, 409);
  }
});

reports.delete("/groups/:groupId", requirePlusAccess("reports"), async (c) => {
  const groupId = c.req.param("groupId");

  try {
    await deleteGroup(groupId);
    return c.json({ message: "Group deleted" });
  } catch (err: any) {
    const msg = String(err?.message ?? "Failed to delete group");
    const status = msg.includes("not found") ? 404 : 409;
    return c.json({ message: msg }, status);
  }
});

reports.get("/reports", async (c) => {
  const groupId = c.req.query("groupId");
  const items = await getReports(groupId);
  return c.json(items);
});

reports.get("/reports/:reportId", async (c) => {
  const reportId = c.req.param("reportId");
  const report = await getReportById(reportId);

  if (!report) {
    return c.json({ message: "Report not found" }, 404);
  }

  return c.json(report);
});

reports.post("/reports", requirePlusAccess("reports"), async (c) => {
  const body = await c.req.json<{
    groupId?: string;
    name?: string;
    queryTemplate?: string;
  }>();

  if (!body.groupId || !body.name || !body.queryTemplate) {
    return c.json({ message: "groupId, name, and queryTemplate are required" }, 400);
  }

  try {
    const report = await createReport({
      groupId: body.groupId,
      name: body.name,
      queryTemplate: body.queryTemplate,
    });

    return c.json(report, 201);
  } catch (err: any) {
    const msg = String(err?.message ?? "");
    const status = msg.includes("not found") ? 404 : 409;
    return c.json({ message: msg || "Failed to create report" }, status);
  }
});

reports.patch("/reports/:reportId", requirePlusAccess("reports"), async (c) => {
  const reportId = c.req.param("reportId");
  const body = await c.req.json<{ name?: string; queryTemplate?: string }>();

  if (!body.name || !body.queryTemplate) {
    return c.json({ message: "name and queryTemplate are required" }, 400);
  }

  try {
    const updated = await updateReport(reportId, {
      name: body.name,
      queryTemplate: body.queryTemplate,
    });
    return c.json(updated);
  } catch (err: any) {
    const msg = String(err?.message ?? "Failed to update report");
    const status = msg.includes("not found") ? 404 : 409;
    return c.json({ message: msg }, status);
  }
});

reports.delete("/reports/:reportId", requirePlusAccess("reports"), async (c) => {
  const reportId = c.req.param("reportId");

  try {
    await deleteReport(reportId);
    return c.json({ message: "Report deleted" });
  } catch (err: any) {
    const msg = String(err?.message ?? "Failed to delete report");
    const status = msg.includes("not found") ? 404 : 409;
    return c.json({ message: msg }, status);
  }
});

reports.post("/reports/:reportId/run", async (c) => {
  const reportId = c.req.param("reportId");
  const body = (await c.req
    .json<{ variables?: Record<string, string> }>()
    .catch(() => ({ variables: {} as Record<string, string> }))) as {
    variables?: Record<string, string>;
  };

  try {
    const result = await runReportQuery(reportId, body.variables);
    return c.json({
      reportId,
      columns: result.columns,
      rows: result.rows,
      rowCount: Array.isArray(result.rows) ? result.rows.length : 0,
      executedAt: new Date().toISOString(),
    });
  } catch (err: any) {
    const msg = String(err?.message ?? "Failed to run report");
    const status = msg.includes("not found") ? 404 : 400;
    return c.json({ message: msg }, status);
  }
});

reports.post("/reports/:reportId/export", async (c) => {
  const reportId = c.req.param("reportId");
  const body = (await c.req
    .json<{ variables?: Record<string, string>; asOf?: string }>()
    .catch(() => ({ variables: {} as Record<string, string> }))) as {
    variables?: Record<string, string>;
    asOf?: string;
  };

  try {
    const result = await runReportQuery(reportId, body.variables);
    const workbook = new ExcelJS.Workbook();
    const worksheet = workbook.addWorksheet((result.report.name || "Report").slice(0, 31));

    const exportColumns = result.columns.length > 0 ? result.columns : ["Result"];

    worksheet.columns = exportColumns.map((col) => ({
      header: col,
      key: col,
      width: Math.min(Math.max(col.length + 4, 16), 48),
    }));

    for (const row of result.rows) {
      const rowObject = exportColumns.reduce<Record<string, unknown>>((acc, col) => {
        acc[col] = row?.[col] ?? null;
        return acc;
      }, {});
      worksheet.addRow(rowObject);
    }

    const asOfDate = body.asOf ? new Date(body.asOf) : new Date();
    const validAsOf = Number.isNaN(asOfDate.getTime()) ? new Date() : asOfDate;
    const headingText = `${result.report.name} as on ${validAsOf.toLocaleString("en-IN")}`;

    worksheet.insertRow(1, [headingText]);
    worksheet.insertRow(2, []);
    worksheet.mergeCells(1, 1, 1, Math.max(exportColumns.length, 1));

    const headingCell = worksheet.getCell(1, 1);
    headingCell.font = { bold: true, size: 13 };

    worksheet.getRow(3).font = { bold: true };

    const buffer = await workbook.xlsx.writeBuffer();
    const fileName = `${safeExcelFilename(result.report.name)}.xlsx`;

    return new Response(Buffer.from(buffer), {
      headers: {
        "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "Content-Disposition": `attachment; filename="${fileName}"`,
      },
    });
  } catch (err: any) {
    const msg = String(err?.message ?? "Failed to export report");
    const status = msg.includes("not found") ? 404 : 400;
    return c.json({ message: msg }, status);
  }
});

export default reports;
