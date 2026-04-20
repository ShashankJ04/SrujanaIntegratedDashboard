import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "./client";

// ── Response Types ─────────────────────────────────────────────────

export interface ToolMachine {
  machineId: number;
  machineName: string;
  machineCapacity: string;
  machineMake: string;
  scheduledQty: number;
  scheduledStrokes: number;
}

export interface ToolWithMachines {
  toolId: number;
  toolNo: string;
  drawingNo: string;
  partNo: string;
  partName: string;
  cavity: number;
  machineCount: number;
  totalScheduledQty: number;
  totalScheduledStrokes: number;
  machines: ToolMachine[];
}

export interface ToolsByDayResponse {
  date: string | null;
  count: number;
  tools: ToolWithMachines[];
}

export interface ToolsCountResponse {
  total: number;
}

// ── Hooks ──────────────────────────────────────────────────────────

export function useToolsCount() {
  return useQuery({
    queryKey: ["tools", "count"],
    queryFn: () => apiFetch<ToolsCountResponse>("/api/tools/count"),
  });
}

function withDateQuery(path: string, date?: string) {
  if (!date) return path;
  const params = new URLSearchParams({ date });
  return `${path}?${params.toString()}`;
}

export function useToolsToday(date?: string) {
  return useQuery({
    queryKey: ["tools", "today", date],
    queryFn: () =>
      apiFetch<ToolsByDayResponse>(withDateQuery("/api/tools/today", date)),
  });
}

export function useToolsTomorrow(date?: string) {
  return useQuery({
    queryKey: ["tools", "tomorrow", date],
    queryFn: () =>
      apiFetch<ToolsByDayResponse>(
        withDateQuery("/api/tools/tomorrow", date)
      ),
  });
}

export function useToolsForDate(date: string) {
  return useQuery({
    queryKey: ["tools", "date", date],
    queryFn: () =>
      apiFetch<ToolsByDayResponse>(
        withDateQuery("/api/tools/today", date)
      ),
    enabled: !!date,
  });
}
