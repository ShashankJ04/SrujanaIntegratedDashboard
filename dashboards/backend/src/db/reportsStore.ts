import { existsSync, mkdirSync, writeFileSync } from "fs";
import { dirname, join } from "path";

export interface ReportGroup {
  id: string;
  name: string;
  createdAt: string;
  updatedAt: string;
}

export interface ReportDefinition {
  id: string;
  groupId: string;
  name: string;
  queryTemplate: string;
  variables: string[];
  createdAt: string;
  updatedAt: string;
}

export interface CompileReportInput {
  queryTemplate: string;
  providedVariables?: Record<string, string | number | boolean | null | undefined>;
}

export interface CompiledReportQuery {
  sql: string;
  params: Array<string | number | boolean | null>;
}

interface ReportsStoreData {
  groups: ReportGroup[];
  reports: ReportDefinition[];
}

const STORE_PATH = join(process.cwd(), "data", "reports.json");

function getIsoNow(): string {
  return new Date().toISOString();
}

function ensureStoreFile(): void {
  const dir = dirname(STORE_PATH);
  if (!existsSync(dir)) {
    mkdirSync(dir, { recursive: true });
  }

  if (!existsSync(STORE_PATH)) {
    writeFileSync(STORE_PATH, JSON.stringify({ groups: [], reports: [] }, null, 2), "utf-8");
  }
}

async function readStore(): Promise<ReportsStoreData> {
  ensureStoreFile();
  const file = Bun.file(STORE_PATH);
  const content = await file.text();

  if (!content.trim()) {
    return { groups: [], reports: [] };
  }

  const parsed = JSON.parse(content) as Partial<ReportsStoreData>;
  return {
    groups: Array.isArray(parsed.groups) ? parsed.groups : [],
    reports: Array.isArray(parsed.reports) ? parsed.reports : [],
  };
}

async function writeStore(data: ReportsStoreData): Promise<void> {
  await Bun.write(STORE_PATH, JSON.stringify(data, null, 2));
}

function extractVariables(queryTemplate: string): string[] {
  const re = /\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}/g;
  const found = new Set<string>();
  let match: RegExpExecArray | null = null;

  while ((match = re.exec(queryTemplate)) !== null) {
    found.add(match[1]);
  }

  return Array.from(found);
}

export function assertReadOnlyQuery(queryTemplate: string): void {
  const cleaned = queryTemplate.trim().replace(/^\(+/, "").toLowerCase();
  if (!cleaned.startsWith("select")) {
    throw new Error("Only read-only SELECT queries are allowed");
  }
}

export function compileReportQuery(input: CompileReportInput): CompiledReportQuery {
  const queryTemplate = input.queryTemplate.trim();
  assertReadOnlyQuery(queryTemplate);

  const provided = input.providedVariables ?? {};
  const params: Array<string | number | boolean | null> = [];
  const variablePattern = /\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}/g;

  const sql = queryTemplate.replace(variablePattern, (_, variableName: string) => {
    if (!(variableName in provided)) {
      throw new Error(`Missing value for variable {${variableName}}`);
    }

    const rawValue = provided[variableName];
    if (rawValue === undefined) {
      throw new Error(`Missing value for variable {${variableName}}`);
    }

    params.push(rawValue);
    return "?";
  });

  return { sql, params };
}

export async function getGroups(): Promise<ReportGroup[]> {
  const store = await readStore();
  return store.groups.sort((a, b) => a.name.localeCompare(b.name));
}

export async function createGroup(name: string): Promise<ReportGroup> {
  const trimmed = name.trim();
  if (!trimmed) {
    throw new Error("Group name is required");
  }

  const store = await readStore();
  const dup = store.groups.find((g) => g.name.toLowerCase() === trimmed.toLowerCase());
  if (dup) {
    throw new Error("A group with this name already exists");
  }

  const now = getIsoNow();
  const group: ReportGroup = {
    id: crypto.randomUUID(),
    name: trimmed,
    createdAt: now,
    updatedAt: now,
  };

  store.groups.push(group);
  await writeStore(store);
  return group;
}

export async function getReports(groupId?: string): Promise<ReportDefinition[]> {
  const store = await readStore();
  const filtered = groupId
    ? store.reports.filter((r) => r.groupId === groupId)
    : store.reports;

  return filtered.sort((a, b) => a.name.localeCompare(b.name));
}

export async function getReportById(reportId: string): Promise<ReportDefinition | null> {
  const store = await readStore();
  return store.reports.find((r) => r.id === reportId) ?? null;
}

export async function createReport(input: {
  groupId: string;
  name: string;
  queryTemplate: string;
}): Promise<ReportDefinition> {
  const groupId = input.groupId.trim();
  const name = input.name.trim();
  const queryTemplate = input.queryTemplate.trim();

  if (!groupId) {
    throw new Error("groupId is required");
  }
  if (!name) {
    throw new Error("Report name is required");
  }
  if (!queryTemplate) {
    throw new Error("queryTemplate is required");
  }

  assertReadOnlyQuery(queryTemplate);

  const store = await readStore();
  const groupExists = store.groups.some((g) => g.id === groupId);
  if (!groupExists) {
    throw new Error("Group not found");
  }

  const dup = store.reports.find(
    (r) => r.groupId === groupId && r.name.toLowerCase() === name.toLowerCase(),
  );
  if (dup) {
    throw new Error("A report with this name already exists in this group");
  }

  const now = getIsoNow();
  const report: ReportDefinition = {
    id: crypto.randomUUID(),
    groupId,
    name,
    queryTemplate,
    variables: extractVariables(queryTemplate),
    createdAt: now,
    updatedAt: now,
  };

  store.reports.push(report);
  await writeStore(store);
  return report;
}

export async function updateReport(
  reportId: string,
  input: { name: string; queryTemplate: string },
): Promise<ReportDefinition> {
  const name = input.name.trim();
  const queryTemplate = input.queryTemplate.trim();

  if (!name) {
    throw new Error("Report name is required");
  }
  if (!queryTemplate) {
    throw new Error("queryTemplate is required");
  }

  assertReadOnlyQuery(queryTemplate);

  const store = await readStore();
  const index = store.reports.findIndex((r) => r.id === reportId);
  if (index < 0) {
    throw new Error("Report not found");
  }

  const current = store.reports[index];
  const dup = store.reports.find(
    (r) =>
      r.id !== reportId &&
      r.groupId === current.groupId &&
      r.name.toLowerCase() === name.toLowerCase(),
  );
  if (dup) {
    throw new Error("A report with this name already exists in this group");
  }

  const updated: ReportDefinition = {
    ...current,
    name,
    queryTemplate,
    variables: extractVariables(queryTemplate),
    updatedAt: getIsoNow(),
  };

  store.reports[index] = updated;
  await writeStore(store);
  return updated;
}

export async function deleteReport(reportId: string): Promise<void> {
  const store = await readStore();
  const initialLength = store.reports.length;
  store.reports = store.reports.filter((r) => r.id !== reportId);

  if (store.reports.length === initialLength) {
    throw new Error("Report not found");
  }

  await writeStore(store);
}

export async function deleteGroup(groupId: string): Promise<void> {
  const store = await readStore();
  const initialGroupsLength = store.groups.length;
  store.groups = store.groups.filter((g) => g.id !== groupId);

  if (store.groups.length === initialGroupsLength) {
    throw new Error("Group not found");
  }

  // Cascade delete reports in this group.
  store.reports = store.reports.filter((r) => r.groupId !== groupId);
  await writeStore(store);
}
