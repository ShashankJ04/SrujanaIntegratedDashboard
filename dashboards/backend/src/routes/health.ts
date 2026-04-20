import { Hono } from "hono";
import { db } from "../db";
import { sql } from "kysely";

const health = new Hono();

health.get("/", async (c) => {
  try {
    // Verify DB connectivity
    await sql`SELECT 1`.execute(db);
    return c.json({
      status: "ok",
      timestamp: new Date().toISOString(),
      db: "connected",
    });
  } catch (error) {
    return c.json(
      {
        status: "error",
        timestamp: new Date().toISOString(),
        db: "disconnected",
      },
      503
    );
  }
});

export default health;
