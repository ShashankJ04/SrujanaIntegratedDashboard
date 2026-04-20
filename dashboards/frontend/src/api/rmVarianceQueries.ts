import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "./client";

// ── Types ──────────────────────────────────────────────────────────

export interface RMVarianceEntry {
  partno: string;
  rm: string;
  tool: string;
  custReqQty: number;
  schQty: number;
  schKg: number;
  prodQty: number;
  usedQty: number;
  theoKg: number;
  variance: number;  
  variancePer: number;
}

export interface RMVarianceTotals {
  custReqQty: number;
  schQty: number;
  schKg: number;
  prodQty: number;
  usedQty: number;
  theoKg: number;
  variance: number;
  variancePer: number;
}

export interface RMVarianceResponse {
  month: number;
  year: number;
  plantId: number;
  count: number;
  totals: RMVarianceTotals;
  entries: RMVarianceEntry[];
}

// ── Hook ───────────────────────────────────────────────────────────

/**
 * Fetch RM Variance data for a given month, year, and plant ID.
 */
export function useRMVariance(
  month: number | null,
  year: number | null,
  plantId: number | null
) {
  return useQuery({
    queryKey: ["rm-variance", month, year, plantId],
    queryFn: () =>
      apiFetch<RMVarianceResponse>(
        `/api/rm-variance/${month}/${year}/${plantId}`
      ),
    enabled: !!month && !!year && !!plantId,
  });
}
