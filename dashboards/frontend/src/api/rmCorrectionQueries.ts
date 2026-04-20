import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "./client";

export interface RMCorrectionEntry {
  rawMaterial: string;
  batch: string;
  rmGiven: number;
  totalInwarded: number;
  rmRemaining: number;
  scrap: number;
}

export interface RMCorrectionResponse {
  count: number;
  entries: RMCorrectionEntry[];
}

export interface RMCorrectionBatchDetailEntry {
  productionDate: string;
  partNo: string;
  lotNo: string;
  tool: string;
  calCompWt: number;
  noOfComp: number;
  sfRejNos: number;
  suWastageNos: number;
  scrapKg: number;
  partWtKg: number;
  theoRmKg: number;
}

export interface RMCorrectionBatchDetailResponse {
  count: number;
  entries: RMCorrectionBatchDetailEntry[];
}

export function useRMCorrectionEntries(startDate: string | null) {
  return useQuery({
    queryKey: ["rm-correction", startDate],
    queryFn: async () => {
      const startedAt = performance.now();
      const query = startDate ? `?startDate=${encodeURIComponent(startDate)}` : "";
      console.log(`[RM Correction][API] /api/rm-correction${query} request started`);
      const response = await apiFetch<RMCorrectionResponse>(`/api/rm-correction${query}`);
      const durationMs = performance.now() - startedAt;
      console.log(
        `[RM Correction][API] /api/rm-correction${query} completed in ${durationMs.toFixed(2)} ms (rows=${response.entries.length})`
      );
      return response;
    },
  });
}

export function useRMCorrectionBatchDetails(
  batch: string,
  enabled: boolean
) {
  return useQuery({
    queryKey: ["rm-correction-batch", batch],
    enabled: enabled && !!batch,
    queryFn: async () => {
      return apiFetch<RMCorrectionBatchDetailResponse>(`/api/rm-correction/batch/${encodeURIComponent(batch)}`);
    },
  });
}
