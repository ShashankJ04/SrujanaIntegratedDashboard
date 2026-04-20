import type { MiddlewareHandler } from "hono";
import { verifyAuthToken } from "../auth/jwt";

const PUBLIC_PATHS = new Set(["/api/health", "/api/auth/login"]);

export type AuthContext = {
  userId: number;
  login: string;
  isAdmin: boolean;
};

export const authMiddleware: MiddlewareHandler = async (c, next) => {
  const path = c.req.path;
  if (c.req.method === "OPTIONS") {
    return next();
  }
  if (PUBLIC_PATHS.has(path)) {
    return next();
  }

  const authHeader = c.req.header("authorization") ?? "";
  const token = authHeader.startsWith("Bearer ") ? authHeader.slice(7) : null;

  if (!token) {
    return c.json({ message: "Missing Authorization token" }, 401);
  }

  try {
    const payload = await verifyAuthToken(token);
    c.set("auth", payload);
    return next();
  } catch (err) {
    return c.json({ message: "Invalid or expired token" }, 401);
  }
};

export function getAuth(c: { get: (key: string) => AuthContext | undefined }): AuthContext {
  const auth = c.get("auth");
  if (!auth) {
    throw new Error("Missing auth context");
  }
  return auth;
}
