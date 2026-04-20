import { Hono } from "hono";
import { serveStatic } from "hono/bun";
import { corsMiddleware, logger, authMiddleware } from "./middleware";
import {
  healthRoutes,
  toolsRoutes,
  pmRoutes,
  scheduleRoutes,
  productionRoutes,
  rmVarianceRoutes,
  rmCorrectionRoutes,
  reportsRoutes,
  authRoutes,
  adminRoutes,
} from "./routes";
import { env } from "./env";
import { join } from "path";

const app = new Hono();

// Global middleware
app.use("*", corsMiddleware);
app.use("*", logger);
app.use("/api/*", authMiddleware);
app.use("/schedule*", authMiddleware);

// ================= API ROUTES =================
app.route("/api/health", healthRoutes);
app.route("/api/auth", authRoutes);
app.route("/api/admin", adminRoutes);
app.route("/api/tools", toolsRoutes);
app.route("/api/pm", pmRoutes);
app.route("/schedule", scheduleRoutes);
app.route("/api/production", productionRoutes);
app.route("/api/rm-variance", rmVarianceRoutes);
app.route("/api/rm-correction", rmCorrectionRoutes);
app.route("/api/reports", reportsRoutes);

// ================= FRONTEND STATIC =================

// Serve static assets (JS, CSS, images)
app.use(
  "/*",
  serveStatic({
    root: join(process.cwd(), "../frontend/dist"),
  })
);

// SPA fallback (important for React Router)
app.get("*", async (c, next) => {
  return serveStatic({
    path: "index.html",
    root: join(process.cwd(), "../frontend/dist"),
  })(c, next);
});

console.log(`🚀 Server starting on port ${env.PORT}`);

export default {
  port: env.PORT,
  fetch: app.fetch,
};