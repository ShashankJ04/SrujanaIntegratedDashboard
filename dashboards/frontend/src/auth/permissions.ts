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

export interface Permissions {
  access: DashboardKey[];
  plusAccess: DashboardKey[];
}

export function hasAccess(permissions: Permissions | null, key: DashboardKey): boolean {
  return permissions?.access?.includes(key) ?? false;
}

export function hasPlusAccess(permissions: Permissions | null, key: DashboardKey): boolean {
  return permissions?.plusAccess?.includes(key) ?? false;
}
