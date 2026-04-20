import { cors } from "hono/cors";
import type { MiddlewareHandler } from "hono";

/**
 * CORS middleware configured for the frontend dev server.
 */
export const corsMiddleware: MiddlewareHandler = cors({
  origin: ["http://localhost:5173"],
  allowMethods: ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
  allowHeaders: ["Content-Type", "Authorization"],
  maxAge: 86400,
});
