import { db } from "./index";
import { sql } from "kysely";
import type { ToolLifeTable, PreventiveMaintenanceTable } from "./types";

// ── Public-facing shapes (kept compatible with frontend) ───────────

export interface MaintenanceRecord {
  id: number;
  date: string;
  currentStroke: number;
  nextStroke: number;
  attachment: string | null;
}

export interface PMEntry {
  toolId: number;
  toolNo: string;
  toolLife: number;
  spm: number;
  pmStrokes: number;
  maintenanceHistory: MaintenanceRecord[];
  createdAt: string;
}

// ── Helpers ────────────────────────────────────────────────────────

function formatDate(d: string | Date): string {
  const date = typeof d === "string" ? new Date(d) : d;
  return date.toISOString();
}

async function resolveToolNumber(toolId: number): Promise<string | null> {
  const fromToolLife = await db
    .selectFrom("tool_life")
    .select("TL_tool_number as toolNo")
    .where("TL_tool_id", "=", toolId)
    .executeTakeFirst();

  if (fromToolLife?.toolNo) {
    return fromToolLife.toolNo;
  }

  const fromToolMaster = await db
    .selectFrom("components_tool")
    .select("CT_TOOLNO as toolNo")
    .where("CT_ID", "=", toolId)
    .executeTakeFirst();

  return fromToolMaster?.toolNo ?? null;
}

async function getToolStrokesByToolNo(toolNo: string): Promise<number> {
  const result = await sql<{ totalQty: number }>`
    SELECT COALESCE(MAX(comp.componentStrokes), 0) AS totalQty
    FROM (
      SELECT
        ct.CT_COMPID,
        SUM(pd.PD_PRODQTY / GREATEST(COALESCE(ct.CT_NO_OF_CAVITY, 1), 1)) AS componentStrokes
      FROM production_details pd
      INNER JOIN components_tool ct ON ct.CT_ID = pd.PD_TOOLID
      WHERE ct.CT_TOOLNO = ${toolNo}
      GROUP BY ct.CT_COMPID
    ) comp
  `.execute(db);

  return Number(result.rows[0]?.totalQty ?? 0);
}

// ── Public API ─────────────────────────────────────────────────────

/** Get all tool_life rows with their maintenance history attached. */
export async function getEntries(): Promise<PMEntry[]> {
  const tools = await db
    .selectFrom("tool_life")
    .selectAll()
    .execute();

  const pmRows = await db
    .selectFrom("preventive_maintenance")
    .selectAll()
    .orderBy("PM_id", "asc")
    .execute();

  const historyByToolId = new Map<number, MaintenanceRecord[]>();
  for (const pm of pmRows) {
    const list = historyByToolId.get(pm.PM_tool_id) ?? [];
    list.push({
      id: pm.PM_id,
      date: formatDate(pm.PM_date),
      currentStroke: Number(pm.PM_current_stroke),
      nextStroke: Number(pm.PM_next_stroke),
      attachment: pm.PM_maintenance_attachment,
    });
    historyByToolId.set(pm.PM_tool_id, list);
  }

  return tools.map((t) => {
    const history = historyByToolId.get(t.TL_tool_id) ?? [];

    return {
      toolId: t.TL_tool_id,
      toolNo: t.TL_tool_number,
      toolLife: Number(t.TL_life_span),
      spm: t.TL_spm,
      pmStrokes: Number(t.TL_preventive_maintenance_strokes),
      maintenanceHistory: history,
      createdAt: formatDate(t.TL_created_at),
    };
  });
}

/** Add a new tool_life row. Optionally creates an initial preventive_maintenance record. Throws on duplicate toolId. */
export async function addEntry(
  toolId: number,
  toolNo: string,
  toolLife: number,
  spm: number,
  pmStrokes: number,
  nextStroke?: number
): Promise<PMEntry> {
  // Check for existing row (PK will also enforce this but gives a nicer message)
  const existing = await db
    .selectFrom("tool_life")
    .select("TL_tool_number")
    .where("TL_tool_number", "=", toolNo)
    .executeTakeFirst();

  if (existing) {
    throw new Error(`Tool ${toolNo} (ID: ${toolId}) is already added`);
  }

  await db
    .insertInto("tool_life")
    .values({
      TL_tool_id: toolId,
      TL_tool_number: toolNo,
      TL_life_span: toolLife,
      TL_spm: spm,
      TL_preventive_maintenance_strokes: pmStrokes,
    })
    .execute();

  // If nextStroke is provided, create an initial preventive_maintenance record
  if (nextStroke !== undefined) {
    const currentStroke = await getToolStrokes(toolId);
    await db
      .insertInto("preventive_maintenance")
      .values({
        PM_tool_id: toolId,
        PM_tool_number: toolNo,
        PM_date: new Date().toISOString().slice(0, 19).replace("T", " "),
        PM_current_stroke: currentStroke,
        PM_next_stroke: nextStroke,
        PM_maintenance_attachment: null,
      })
      .execute();
  }

  const entries = await getEntries();
  return entries.find((e) => e.toolId === toolId)!;
}

/** Update tool_life fields for a given toolId. */
export async function updateEntry(
  toolId: number,
  updates: { toolLife?: number; pmStrokes?: number; spm?: number }
): Promise<PMEntry> {
  const row = await db
    .selectFrom("tool_life")
    .selectAll()
    .where("TL_tool_id", "=", toolId)
    .executeTakeFirst();

  if (!row) {
    throw new Error(`Tool ID ${toolId} not found`);
  }

  const setValues: Record<string, unknown> = {};
  if (updates.toolLife !== undefined) setValues.TL_life_span = updates.toolLife;
  if (updates.pmStrokes !== undefined) setValues.TL_preventive_maintenance_strokes = updates.pmStrokes;
  if (updates.spm !== undefined) setValues.TL_spm = updates.spm;

  if (Object.keys(setValues).length > 0) {
    await db
      .updateTable("tool_life")
      .set(setValues)
      .where("TL_tool_id", "=", toolId)
      .execute();
  }

  // Fetch updated record with history
  const entries = await getEntries();
  const entry = entries.find((e) => e.toolId === toolId);
  return entry!;
}

/** Get total strokes for any tool from production_details (does NOT require tool_life entry). */
export async function getToolStrokes(toolId: number): Promise<number> {
  const toolNo = await resolveToolNumber(toolId);
  if (!toolNo) {
    return 0;
  }

  return getToolStrokesByToolNo(toolNo);
}

/** Get current total strokes and suggested next PM stroke for a given toolId. */
export async function getStrokeInfo(
  toolId: number
): Promise<{ currentStroke: number; suggestedNextStroke: number }> {
  const row = await db
    .selectFrom("tool_life")
    .selectAll()
    .where("TL_tool_id", "=", toolId)
    .executeTakeFirst();

  if (!row) {
    throw new Error(`Tool ID ${toolId} not found`);
  }

  const currentStroke = await getToolStrokes(toolId);
  const suggestedNextStroke = currentStroke + Number(row.TL_preventive_maintenance_strokes);

  return { currentStroke, suggestedNextStroke };
}

/** Record a maintenance event for a given toolId. Computes current stroke from production_details. */
export async function confirmMaintenance(
  toolId: number,
  nextStroke: number,
  attachment?: string
): Promise<PMEntry> {
  const row = await db
    .selectFrom("tool_life")
    .selectAll()
    .where("TL_tool_id", "=", toolId)
    .executeTakeFirst();

  if (!row) {
    throw new Error(`Tool ID ${toolId} not found`);
  }

  // Compute current total strokes from production_details
  const currentStroke = await getToolStrokes(toolId);

  await db
    .insertInto("preventive_maintenance")
    .values({
      PM_tool_id: toolId,
      PM_tool_number: row.TL_tool_number,
      PM_date: new Date().toISOString().slice(0, 19).replace("T", " "),
      PM_current_stroke: currentStroke,
      PM_next_stroke: nextStroke,
      PM_maintenance_attachment: attachment ?? null,
    })
    .execute();

  const entries = await getEntries();
  return entries.find((e) => e.toolId === toolId)!;
}

/** Delete a tool_life row (and cascade will handle PM rows via RESTRICT — must delete PM rows first). */
export async function deleteEntry(toolId: number): Promise<void> {
  const row = await db
    .selectFrom("tool_life")
    .select("TL_tool_id")
    .where("TL_tool_id", "=", toolId)
    .executeTakeFirst();

  if (!row) {
    throw new Error(`Tool ID ${toolId} not found`);
  }

  // Delete related preventive_maintenance rows first (FK is RESTRICT)
  await db
    .deleteFrom("preventive_maintenance")
    .where("PM_tool_id", "=", toolId)
    .execute();

  await db
    .deleteFrom("tool_life")
    .where("TL_tool_id", "=", toolId)
    .execute();
}
