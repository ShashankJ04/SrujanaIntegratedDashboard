import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "./client";

interface HealthResponse {
  status: string;
  timestamp: string;
  db: string;
}

export function useHealthCheck() {
  return useQuery({
    queryKey: ["health"],
    queryFn: () => apiFetch<HealthResponse>("/api/health"),
    refetchInterval: 30_000,
  });
}
