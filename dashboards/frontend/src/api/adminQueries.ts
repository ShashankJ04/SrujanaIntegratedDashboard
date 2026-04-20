import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./client";
import type { DashboardKey } from "../auth/permissions";

export interface AdminUser {
  id: number;
  login: string;
  firstName: string;
  lastName: string;
}

export interface UserPermissions {
  userId: number;
  login?: string;
  access: DashboardKey[];
  plusAccess: DashboardKey[];
  updatedAt: string;
}

export interface RbacStoreResponse {
  dashboards: DashboardKey[];
  users: UserPermissions[];
}

export function useAdminUsers() {
  return useQuery({
    queryKey: ["admin-users"],
    queryFn: () => apiFetch<AdminUser[]>("/api/admin/users"),
  });
}

export function useRbacStore() {
  return useQuery({
    queryKey: ["admin-rbac"],
    queryFn: () => apiFetch<RbacStoreResponse>("/api/admin/rbac"),
  });
}

export function useUpdateUserPermissions() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: {
      userId: number;
      login?: string;
      access: DashboardKey[];
      plusAccess: DashboardKey[];
    }) =>
      apiFetch<UserPermissions>(`/api/admin/rbac/${payload.userId}`, {
        method: "PUT",
        body: JSON.stringify({
          login: payload.login,
          access: payload.access,
          plusAccess: payload.plusAccess,
        }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-rbac"] });
    },
  });
}
