import { Hono } from "hono";
import { sql } from "kysely";
import { db } from "../db";
import ExcelJS from "exceljs";
import { requireAccess } from "../middleware";

const schedule = new Hono();

schedule.use("*", requireAccess("production"));

/**
 * GET /api/schedule/export?month=1&year=2026
 *
 * Returns an Excel file with columns:
 *   customer | partno | 1 | 2 | 3 | ... | <last day of month>
 *
 * Each cell under a day column contains the sum(qty) from scheduled_customer
 * for that customer+partno on that day, or blank if nothing is scheduled.
 */
schedule.get("/:mmyyyy", async (c) => {
  const param = c.req.param("mmyyyy");

  if (!param || param.length !== 6 || !/^\d{6}$/.test(param)) {
    return c.json({ error: "Use format MMYYYY, e.g. /schedule/022026" }, 400);
  }

  const month = parseInt(param.slice(0, 2), 10);
  const year = parseInt(param.slice(2, 6), 10);

  if (month < 1 || month > 12) {
    return c.json({ error: "Month must be between 01 and 12" }, 400);
  }
  if (year < 2000 || year > 2100) {
    return c.json({ error: "Year must be between 2000 and 2100" }, 400);
  }

  // Number of days in the requested month
  const daysInMonth = new Date(year, month, 0).getDate();

  // Query: join schedule_master → schedule_details → scheduled_customer
  //        + components (for partno) + customer (for name)
  // Group by customer, partno, day-of-month and sum qty
  const rows = await sql<{
    customer: string;
    partno: string;
    day_num: number;
    total_qty: number;
  }>`
    SELECT
      cu.CU_Name      AS customer,
      c.CO_PARTNO     AS partno,
      DAY(sc.CS_DATE)  AS day_num,
      SUM(sc.CS_QTY)   AS total_qty
    FROM schedule_master sm
      JOIN schedule_details sd   ON sm.SM_ID   = sd.SC_SMID
      JOIN scheduled_customer sc ON sd.SC_ID   = sc.CS_SCID
      JOIN components c          ON sd.SC_COMPID = c.CO_ID
      JOIN customer cu           ON c.CO_CUSTID  = cu.CU_Id
    WHERE sm.SM_MONTH = ${month}
      AND sm.SM_YEAR  = ${year}
      AND sc.CS_SCHEDULESTATE IN (1, 2)
    GROUP BY cu.CU_Name, c.CO_PARTNO, DAY(sc.CS_DATE)
    ORDER BY cu.CU_Name, c.CO_PARTNO, DAY(sc.CS_DATE)
  `.execute(db);

  // ── Pivot into { "customer|partno" → { day → qty } } ──────────
  type RowKey = string;
  const pivot = new Map<
    RowKey,
    { customer: string; partno: string; days: Map<number, number> }
  >();

  for (const r of rows.rows) {
    const key: RowKey = `${r.customer}|${r.partno}`;
    if (!pivot.has(key)) {
      pivot.set(key, {
        customer: r.customer,
        partno: r.partno,
        days: new Map(),
      });
    }
    pivot.get(key)!.days.set(r.day_num, Number(r.total_qty));
  }

  // ── Build Excel workbook ───────────────────────────────────────
  const workbook = new ExcelJS.Workbook();
  const sheet = workbook.addWorksheet(
    `Customer Schedule ${String(month).padStart(2, "0")}-${year}`
  );

  // Month names for the title
  const monthNames = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
  ];

  // Title row – include current IST date-time
  const now = new Date(new Date().toLocaleString("en-US", { timeZone: "Asia/Kolkata" }));
  const dd = String(now.getDate()).padStart(2, "0");
  const mm = String(now.getMonth() + 1).padStart(2, "0");
  const yyyy = now.getFullYear();
  const hh = String(now.getHours()).padStart(2, "0");
  const min = String(now.getMinutes()).padStart(2, "0");
  const istStamp = `${dd}-${mm}-${yyyy} ${hh}:${min}`;
  const titleRow = sheet.addRow([`Customer Schedule for ${monthNames[month - 1]} ${year} as on ${istStamp}`]);
  titleRow.getCell(1).font = { bold: true, size: 14 };
  titleRow.getCell(1).alignment = { horizontal: "left", vertical: "middle" };
  sheet.mergeCells(1, 1, 1, daysInMonth + 3);

  // Pre-compute grand totals from pivot data
  const grandTotalByDay = new Array<number>(daysInMonth).fill(0);
  let grandTotal = 0;

  for (const entry of pivot.values()) {
    for (let d = 1; d <= daysInMonth; d++) {
      const qty = entry.days.get(d);
      if (qty !== undefined) {
        grandTotal += qty;
        grandTotalByDay[d - 1] += qty;
      }
    }
  }

  // Grand total row (above the header)
  const grandRow: (string | number | null)[] = ["", "Grand Total", grandTotal];
  for (let d = 0; d < daysInMonth; d++) {
    grandRow.push(grandTotalByDay[d] || null);
  }
  const grandTotalRow = sheet.addRow(grandRow);
  grandTotalRow.eachCell((cell) => {
    cell.font = { bold: true };
    cell.border = { bottom: { style: "thin" } };
  });

  // Header row
  const headerRow = ["Customer", "Part No", "Total"];
  for (let d = 1; d <= daysInMonth; d++) {
    headerRow.push(String(d));
  }
  const header = sheet.addRow(headerRow);

  // Style the header
  header.eachCell((cell) => {
    cell.font = { bold: true };
    cell.alignment = { horizontal: "center", vertical: "middle" };
    cell.fill = {
      type: "pattern",
      pattern: "solid",
      fgColor: { argb: "FFD9E1F2" },
    };
    cell.border = {
      bottom: { style: "thin" },
    };
  });

  // Set column widths
  sheet.getColumn(1).width = 30; // Customer
  sheet.getColumn(2).width = 20; // Part No
  sheet.getColumn(3).width = 10; // Total
  for (let d = 1; d <= daysInMonth; d++) {
    sheet.getColumn(d + 3).width = 8;
  }

  // Data rows
  for (const entry of pivot.values()) {
    let total = 0;
    const dayCells: (number | null)[] = [];
    for (let d = 1; d <= daysInMonth; d++) {
      const qty = entry.days.get(d);
      if (qty !== undefined) {
        dayCells.push(qty);
        total += qty;
      } else {
        dayCells.push(null);
      }
    }
    const row: (string | number | null)[] = [entry.customer, entry.partno, total, ...dayCells];
    sheet.addRow(row);
  }

  // ── Sheet 2: PartNo Schedule ────────────────────────────────────
  const partSheet = workbook.addWorksheet(
    `PartNo Schedule ${String(month).padStart(2, "0")}-${year}`
  );

  // Aggregate pivot data by partno (sum across customers)
  const partPivot = new Map<string, Map<number, number>>();
  for (const entry of pivot.values()) {
    if (!partPivot.has(entry.partno)) {
      partPivot.set(entry.partno, new Map());
    }
    const dayMap = partPivot.get(entry.partno)!;
    for (let d = 1; d <= daysInMonth; d++) {
      const qty = entry.days.get(d);
      if (qty !== undefined) {
        dayMap.set(d, (dayMap.get(d) ?? 0) + qty);
      }
    }
  }

  // Title row
  const partTitleRow = partSheet.addRow([
    `PartNo Schedule for ${monthNames[month - 1]} ${year} as on ${istStamp}`,
  ]);
  partTitleRow.getCell(1).font = { bold: true, size: 14 };
  partTitleRow.getCell(1).alignment = { horizontal: "left", vertical: "middle" };
  partSheet.mergeCells(1, 1, 1, daysInMonth + 2);

  // Grand total row for partno sheet
  const partGrandTotalByDay = new Array<number>(daysInMonth).fill(0);
  let partGrandTotal = 0;
  for (const dayMap of partPivot.values()) {
    for (let d = 1; d <= daysInMonth; d++) {
      const qty = dayMap.get(d);
      if (qty !== undefined) {
        partGrandTotal += qty;
        partGrandTotalByDay[d - 1] += qty;
      }
    }
  }

  const partGrandRow: (string | number | null)[] = ["Grand Total", partGrandTotal];
  for (let d = 0; d < daysInMonth; d++) {
    partGrandRow.push(partGrandTotalByDay[d] || null);
  }
  const partGrandTotalRow = partSheet.addRow(partGrandRow);
  partGrandTotalRow.eachCell((cell) => {
    cell.font = { bold: true };
    cell.border = { bottom: { style: "thin" } };
  });

  // Header row
  const partHeaderRow = ["Part No", "Total"];
  for (let d = 1; d <= daysInMonth; d++) {
    partHeaderRow.push(String(d));
  }
  const partHeader = partSheet.addRow(partHeaderRow);
  partHeader.eachCell((cell) => {
    cell.font = { bold: true };
    cell.alignment = { horizontal: "center", vertical: "middle" };
    cell.fill = {
      type: "pattern",
      pattern: "solid",
      fgColor: { argb: "FFD9E1F2" },
    };
    cell.border = { bottom: { style: "thin" } };
  });

  // Column widths
  partSheet.getColumn(1).width = 20; // Part No
  partSheet.getColumn(2).width = 10; // Total
  for (let d = 1; d <= daysInMonth; d++) {
    partSheet.getColumn(d + 2).width = 8;
  }

  // Data rows – one row per partno, sorted by partno
  const sortedPartNos = [...partPivot.entries()].sort((a, b) =>
    a[0].localeCompare(b[0])
  );
  for (const [partno, dayMap] of sortedPartNos) {
    let total = 0;
    const dayCells: (number | null)[] = [];
    for (let d = 1; d <= daysInMonth; d++) {
      const qty = dayMap.get(d);
      if (qty !== undefined) {
        dayCells.push(qty);
        total += qty;
      } else {
        dayCells.push(null);
      }
    }
    partSheet.addRow([partno, total, ...dayCells]);
  }

  // ── Write to buffer & respond ──────────────────────────────────
  const buffer = await workbook.xlsx.writeBuffer();

  const filename = `schedule_${year}_${String(month).padStart(2, "0")}.xlsx`;

  return new Response(buffer as ArrayBuffer, {
    status: 200,
    headers: {
      "Content-Type":
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      "Content-Disposition": `attachment; filename="${filename}"`,
    },
  });
});

export default schedule;
