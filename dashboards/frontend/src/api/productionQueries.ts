import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "./client";

// ── Types ──────────────────────────────────────────────────────────

export interface ProductionEntry {
  customer: string;
  partno: string;
  partname: string;
  rawMaterial: string;
  scheduledDate: string;
  scheduledQty: number;
  prodQty: number;
  qtyKg: number;
  setupWastage: number;
  sfRejection: number;
  netQty: number;
  issuedQty: number;
  requiredQty: number;
  variance: number;
  fgStock: number;
  wipStock: number;
  totalStock: number;
}

export interface ProductionTotals {
  scheduledQty: number;
  prodQty: number;
  qtyKg: number;
  setupWastage: number;
  sfRejection: number;
  netQty: number;
  issuedQty: number;
  requiredQty: number;
  variance: number;
}

export interface ProductionResponse {
  date: string;
  count: number;
  totals: ProductionTotals;
  entries: ProductionEntry[];
}

// ── Hook ───────────────────────────────────────────────────────────

/**
 * Fetch production data for a given date.
 * @param ddmmyyyy - date in DDMMYYYY format, e.g. "01032026"
 */
export function useProductionByDate(ddmmyyyy: string | null) {
  return useQuery({
    queryKey: ["production", ddmmyyyy],
    queryFn: () =>
      apiFetch<ProductionResponse>(`/api/production/${ddmmyyyy}`),
    enabled: !!ddmmyyyy && ddmmyyyy.length === 8,
  });
}
