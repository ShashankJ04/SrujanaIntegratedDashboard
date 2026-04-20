import { Hono } from "hono";
import { db } from "../db";
import { requireAdmin } from "../middleware";
import { DASHBOARD_KEYS, listUserPermissions, setUserPermissions } from "../rbac/store";

const admin = new Hono();

admin.use("*", requireAdmin);

admin.get("/users", async (c) => {
  const users = await db
    .selectFrom("users")
    .select([
      "US_ID as id",
      "US_Login as login",
      "US_FirstName as firstName",
      "US_LastName as lastName",
      "US_CurrentYn as currentYn",
    ])
    .where("US_CurrentYn", "=", "Y")
    .orderBy("US_Login", "asc")
    .execute();

  return c.json(
    users.map((u) => ({
      id: Number(u.id),
      login: u.login,
      firstName: u.firstName ?? "",
      lastName: u.lastName ?? "",
    }))
  );
});

admin.get("/rbac", async (c) => {
  const users = await listUserPermissions();
  return c.json({ dashboards: DASHBOARD_KEYS, users });
});

admin.put("/rbac/:userId", async (c) => {
  const userId = Number(c.req.param("userId"));
  if (!userId) {
    return c.json({ message: "Invalid userId" }, 400);
  }

  const body = await c.req.json<{
    login?: string;
    access?: string[];
    plusAccess?: string[];
  }>();

  const access = Array.isArray(body.access) ? body.access : [];
  const plusAccess = Array.isArray(body.plusAccess) ? body.plusAccess : [];

  const updated = await setUserPermissions({
    userId,
    login: body.login,
    access,
    plusAccess,
  });

  return c.json(updated);
});

export default admin;
