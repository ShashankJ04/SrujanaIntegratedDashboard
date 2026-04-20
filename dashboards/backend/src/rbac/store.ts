import { existsSync, mkdirSync, writeFileSync } from "fs";
import { dirname, join } from "path";

export type DashboardKey =
  | "tools"
  | "preventive_maintenance"
  | "life_report"
  | "production"
  | "rm_variance"
  | "reports";

export const DASHBOARD_KEYS: DashboardKey[] = [
  "tools",
  "preventive_maintenance",
  "life_report",
  "production",
  "rm_variance",
  "reports",
];

export interface UserPermissions {
  userId: number;
  login?: string;
  access: DashboardKey[];
  plusAccess: DashboardKey[];
  updatedAt: string;
}

interface RbacStoreData {
  users: UserPermissions[];
  updatedAt: string;
}

const STORE_PATH = join(process.cwd(), "data", "rbac.json");

function getIsoNow(): string {
  return new Date().toISOString();
}

function ensureStoreFile(): void {
  const dir = dirname(STORE_PATH);
  if (!existsSync(dir)) {
    mkdirSync(dir, { recursive: true });
  }

  if (!existsSync(STORE_PATH)) {
    writeFileSync(STORE_PATH, JSON.stringify({ users: [], updatedAt: getIsoNow() }, null, 2), "utf-8");
  }
}

async function readStore(): Promise<RbacStoreData> {
  ensureStoreFile();
  const file = Bun.file(STORE_PATH);
  const content = await file.text();

  if (!content.trim()) {
    return { users: [], updatedAt: getIsoNow() };
  }

  const parsed = JSON.parse(content) as Partial<RbacStoreData>;
  return {
    users: Array.isArray(parsed.users) ? parsed.users : [],
    updatedAt: parsed.updatedAt ?? getIsoNow(),
  };
}

async function writeStore(data: RbacStoreData): Promise<void> {
  await Bun.write(STORE_PATH, JSON.stringify(data, null, 2));
}

function normalizeKeys(keys: string[]): DashboardKey[] {
  const allowed = new Set(DASHBOARD_KEYS);
  const unique = new Set<DashboardKey>();
  for (const key of keys) {
    if (allowed.has(key as DashboardKey)) {
      unique.add(key as DashboardKey);
    }
  }
  return Array.from(unique);
}

export async function listUserPermissions(): Promise<UserPermissions[]> {
  const store = await readStore();
  return store.users;
}

export async function getUserPermissions(userId: number): Promise<UserPermissions | null> {
  const store = await readStore();
  return store.users.find((u) => u.userId === userId) ?? null;
}

export async function setUserPermissions(input: {
  userId: number;
  login?: string;
  access: string[];
  plusAccess: string[];
}): Promise<UserPermissions> {
  const store = await readStore();
  const access = normalizeKeys(input.access);
  const plusAccess = normalizeKeys(input.plusAccess).filter((key) => access.includes(key));
  const now = getIsoNow();

  const existingIndex = store.users.findIndex((u) => u.userId === input.userId);
  const nextEntry: UserPermissions = {
    userId: input.userId,
    login: input.login,
    access,
    plusAccess,
    updatedAt: now,
  };

  if (existingIndex >= 0) {
    store.users[existingIndex] = { ...store.users[existingIndex], ...nextEntry };
  } else {
    store.users.push(nextEntry);
  }

  store.updatedAt = now;
  await writeStore(store);
  return nextEntry;
}

export async function getEffectivePermissions(input: {
  userId: number;
  login: string;
  isAdmin: boolean;
}): Promise<{ access: DashboardKey[]; plusAccess: DashboardKey[] }> {
  const access = [...DASHBOARD_KEYS];

  if (input.isAdmin) {
    return {
      access,
      plusAccess: ["preventive_maintenance", "reports"],
    };
  }

  const stored = await getUserPermissions(input.userId);
  if (!stored) {
    return { access, plusAccess: [] };
  }

  const plusAccess = normalizeKeys(stored.plusAccess).filter((key) => access.includes(key));
  return { access, plusAccess };
}
