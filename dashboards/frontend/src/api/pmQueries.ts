import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiFetch, getAuthToken } from "./client";

// ── Types ──────────────────────────────────────────────────────────

export interface ToolSearchResult {
  id: number;
  toolNo: string;
}

export interface AllToolsResult {
  id: number;
  toolNo: string;
  partNo: string;
}

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

// ── Queries ────────────────────────────────────────────────────────

export function useToolSearch(query: string) {
  return useQuery({
    queryKey: ["tools", "search", query],
    queryFn: () =>
      apiFetch<ToolSearchResult[]>(
        `/api/tools/search?q=${encodeURIComponent(query)}`
      ),
    enabled: query.length >= 1,
  });
}

export function useAllTools() {
  return useQuery({
    queryKey: ["tools", "all"],
    queryFn: () => apiFetch<AllToolsResult[]>("/api/tools/all"),
  });
}

export function usePMEntries() {
  return useQuery({
    queryKey: ["pm-entries"],
    queryFn: () => apiFetch<PMEntry[]>("/api/pm"),
  });
}

// ── Mutations ──────────────────────────────────────────────────────

export function useToolStrokes(toolId: number | null) {
  return useQuery({
    queryKey: ["tool-strokes", toolId],
    queryFn: () =>
      apiFetch<{ totalStrokes: number }>(`/api/pm/tool-strokes/${toolId}`),
    enabled: toolId !== null,
  });
}

export function useAddPMEntry() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: {
      toolId: number;
      toolNo: string;
      toolLife: number;
      spm: number;
      pmStrokes: number;
      nextStroke: number;
    }) =>
      apiFetch<PMEntry>("/api/pm", {
        method: "POST",
        body: JSON.stringify(data),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["pm-entries"] });
      qc.invalidateQueries({ queryKey: ["pm-status"] });
      qc.invalidateQueries({ queryKey: ["pm-status-all"] });
    },
  });
}

export function useUpdatePMEntry() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { toolId: number; toolLife?: number; pmStrokes?: number; spm?: number }) =>
      apiFetch<PMEntry>(`/api/pm/${data.toolId}`, {
        method: "PATCH",
        body: JSON.stringify({
          ...(data.toolLife !== undefined && { toolLife: data.toolLife }),
          ...(data.pmStrokes !== undefined && { pmStrokes: data.pmStrokes }),
          ...(data.spm !== undefined && { spm: data.spm }),
        }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["pm-entries"] });
      qc.invalidateQueries({ queryKey: ["pm-status"] });
      qc.invalidateQueries({ queryKey: ["pm-status-all"] });
    },
  });
}

export interface StrokeInfo {
  currentStroke: number;
  suggestedNextStroke: number;
}

export interface ToolStrokesResult {
  totalStrokes: number;
}

export function useStrokeInfo(toolId: number | null) {
  return useQuery({
    queryKey: ["stroke-info", toolId],
    queryFn: () => apiFetch<StrokeInfo>(`/api/pm/${toolId}/stroke-info`),
    enabled: toolId !== null,
  });
}

export function useConfirmMaintenance() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (data: {
      toolId: number;
      nextStroke: number;
      attachmentFile?: File;
    }) => {
      const formData = new FormData();
      formData.append("nextStroke", String(data.nextStroke));
      if (data.attachmentFile) {
        formData.append("attachment", data.attachmentFile);
      }

      const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";
      const token = getAuthToken();
      const res = await fetch(
        `${API_BASE}/api/pm/${data.toolId}/confirm`,
        {
          method: "POST",
          headers: token ? { Authorization: `Bearer ${token}` } : undefined,
          body: formData,
        }
      );

      if (res.status === 401 || res.status === 403) {
        if (typeof window !== "undefined") {
          window.dispatchEvent(new CustomEvent("auth:logout"));
        }
      }

      if (!res.ok) {
        const error = await res.json().catch(() => ({ message: res.statusText }));
        throw new Error(error.message || `API error: ${res.status}`);
      }

      return res.json() as Promise<PMEntry>;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["pm-entries"] });
      qc.invalidateQueries({ queryKey: ["pm-status"] });
      qc.invalidateQueries({ queryKey: ["pm-status-all"] });
    },
  });
}

export function useDeletePMEntry() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (toolId: number) =>
      apiFetch<{ message: string }>(`/api/pm/${toolId}`, {
        method: "DELETE",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["pm-entries"] });
      qc.invalidateQueries({ queryKey: ["pm-status"] });
      qc.invalidateQueries({ queryKey: ["pm-status-all"] });
    },
  });
}

// ── PM Status (tools reaching ≥80% threshold) ─────────────────────

export interface PMStatusEntry {
  toolId: number;
  toolNo: string;
  toolLife: number;
  spm: number;
  pmStrokes: number;
  pmCurrentStroke: number;
  nextStroke: number;
  totalLifetimeStrokes: number;
  pmPercentage: number;
  lastMaintenanceDate: string | null;
  maintenanceCount: number;
}

export function usePMStatus() {
  return useQuery({
    queryKey: ["pm-status"],
    queryFn: () => apiFetch<PMStatusEntry[]>("/api/pm/status"),
    refetchInterval: 60_000, // refresh every minute
  });
}

/** Fetch all PM entries with pmPercentage >= 50% (for stat cards) */
export function usePMStatusAll() {
  return useQuery({
    queryKey: ["pm-status-all"],
    queryFn: () => apiFetch<PMStatusEntry[]>("/api/pm/status?threshold=0"),
    refetchInterval: 60_000,
  });
}

export function useExportPM() {
  return useMutation({
    mutationFn: async (payload: {
      mode: "all" | "safe" | "warning" | "critical";
      search?: string;
      asOf?: string;
      fileName?: string;
    }) => {
      const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";
      const token = getAuthToken();
      const params = new URLSearchParams();
      params.set("mode", payload.mode);
      if (payload.search) params.set("search", payload.search);
      if (payload.asOf) params.set("asOf", payload.asOf);

      const res = await fetch(`${API_BASE}/api/pm/export?${params.toString()}`, {
        method: "GET",
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      });

      if (res.status === 401 || res.status === 403) {
        if (typeof window !== "undefined") {
          window.dispatchEvent(new CustomEvent("auth:logout"));
        }
      }

      if (!res.ok) {
        const error = await res.json().catch(() => ({ message: res.statusText }));
        throw new Error(error.message || `API error: ${res.status}`);
      }

      const blob = await res.blob();
      const downloadUrl = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = downloadUrl;
      anchor.download = payload.fileName ?? "preventive_maintenance.xlsx";
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
      URL.revokeObjectURL(downloadUrl);
    },
  });
}
