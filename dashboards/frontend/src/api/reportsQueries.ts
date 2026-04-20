import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, getAuthToken } from "./client";

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

export interface ReportRunResult {
  reportId: string;
  columns: string[];
  rows: Array<Record<string, unknown>>;
  rowCount: number;
  executedAt: string;
}

export function useReportGroups() {
  return useQuery({
    queryKey: ["report-groups"],
    queryFn: () => apiFetch<ReportGroup[]>("/api/reports/groups"),
  });
}

export function useReports(groupId: string | null) {
  return useQuery({
    queryKey: ["reports", groupId],
    queryFn: () => {
      const params = groupId ? `?groupId=${encodeURIComponent(groupId)}` : "";
      return apiFetch<ReportDefinition[]>(`/api/reports/reports${params}`);
    },
  });
}

export function useReportById(reportId: string | null) {
  return useQuery({
    queryKey: ["report", reportId],
    queryFn: () => apiFetch<ReportDefinition>(`/api/reports/reports/${reportId}`),
    enabled: !!reportId,
  });
}

export function useCreateGroup() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: (name: string) =>
      apiFetch<ReportGroup>("/api/reports/groups", {
        method: "POST",
        body: JSON.stringify({ name }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["report-groups"] });
    },
  });
}

export function useCreateReport() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: (payload: {
      groupId: string;
      name: string;
      queryTemplate: string;
    }) =>
      apiFetch<ReportDefinition>("/api/reports/reports", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    onSuccess: (_, vars) => {
      qc.invalidateQueries({ queryKey: ["reports", vars.groupId] });
    },
  });
}

export function useUpdateReport() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: (payload: {
      reportId: string;
      groupId: string;
      name: string;
      queryTemplate: string;
    }) =>
      apiFetch<ReportDefinition>(`/api/reports/reports/${payload.reportId}`, {
        method: "PATCH",
        body: JSON.stringify({
          name: payload.name,
          queryTemplate: payload.queryTemplate,
        }),
      }),
    onSuccess: (_, vars) => {
      qc.invalidateQueries({ queryKey: ["reports", vars.groupId] });
      qc.invalidateQueries({ queryKey: ["report", vars.reportId] });
    },
  });
}

export function useDeleteGroup() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: (groupId: string) =>
      apiFetch<{ message: string }>(`/api/reports/groups/${groupId}`, {
        method: "DELETE",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["report-groups"] });
      qc.invalidateQueries({ queryKey: ["reports"] });
    },
  });
}

export function useDeleteReport() {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: (payload: { reportId: string; groupId: string }) =>
      apiFetch<{ message: string }>(`/api/reports/reports/${payload.reportId}`, {
        method: "DELETE",
      }),
    onSuccess: (_, vars) => {
      qc.invalidateQueries({ queryKey: ["reports", vars.groupId] });
      qc.invalidateQueries({ queryKey: ["report", vars.reportId] });
    },
  });
}

export function useRunReport() {
  return useMutation({
    mutationFn: (payload: {
      reportId: string;
      variables?: Record<string, string>;
    }) =>
      apiFetch<ReportRunResult>(`/api/reports/reports/${payload.reportId}/run`, {
        method: "POST",
        body: JSON.stringify({ variables: payload.variables ?? {} }),
      }),
  });
}

export function useExportReport() {
  return useMutation({
    mutationFn: async (payload: {
      reportId: string;
      variables?: Record<string, string>;
      fileName?: string;
      asOf?: string;
    }) => {
      const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";
      const token = getAuthToken();
      const res = await fetch(`${API_BASE}/api/reports/reports/${payload.reportId}/export`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ variables: payload.variables ?? {}, asOf: payload.asOf }),
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
      anchor.download = payload.fileName ?? "report.xlsx";
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
      URL.revokeObjectURL(downloadUrl);
    },
  });
}
