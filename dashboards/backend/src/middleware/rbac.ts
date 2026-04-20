import type { MiddlewareHandler } from "hono";
import { getAuth } from "./auth";
import { getEffectivePermissions, type DashboardKey } from "../rbac/store";

export function requireAccess(dashboard: DashboardKey): MiddlewareHandler {
  return async (c, next) => {
    const auth = getAuth(c);
    const permissions = await getEffectivePermissions({
      userId: auth.userId,
      login: auth.login,
      isAdmin: auth.isAdmin,
    });

    if (!permissions.access.includes(dashboard)) {
      return c.json({ message: "Forbidden" }, 403);
    }

    return next();
  };
}

export function requireAnyAccess(dashboards: DashboardKey[]): MiddlewareHandler {
  return async (c, next) => {
    const auth = getAuth(c);
    const permissions = await getEffectivePermissions({
      userId: auth.userId,
      login: auth.login,
      isAdmin: auth.isAdmin,
    });

    const allowed = dashboards.some((key) => permissions.access.includes(key));
    if (!allowed) {
      return c.json({ message: "Forbidden" }, 403);
    }

    return next();
  };
}

export function requirePlusAccess(dashboard: DashboardKey): MiddlewareHandler {
  return async (c, next) => {
    const auth = getAuth(c);
    const permissions = await getEffectivePermissions({
      userId: auth.userId,
      login: auth.login,
      isAdmin: auth.isAdmin,
    });

    if (!permissions.plusAccess.includes(dashboard)) {
      return c.json({ message: "Forbidden" }, 403);
    }

    return next();
  };
}

export const requireAdmin: MiddlewareHandler = async (c, next) => {
  const auth = getAuth(c);
  if (!auth.isAdmin) {
    return c.json({ message: "Forbidden" }, 403);
  }
  return next();
};
