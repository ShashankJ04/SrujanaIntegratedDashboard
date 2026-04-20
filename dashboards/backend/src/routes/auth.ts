import { Hono } from "hono";
import { db } from "../db";
import { decryptPassword, encryptPassword } from "../auth/password";
import { signAuthToken } from "../auth/jwt";
import { getEffectivePermissions } from "../rbac/store";
import { getAuth } from "../middleware/auth";

const auth = new Hono();

function isAdminUserId(userId: number): boolean {
  return userId === 43;
}

auth.post("/login", async (c) => {
  const body = await c.req.json<{ login?: string; password?: string }>().catch(() => ({}));
  const login = (body.login ?? "").trim();
  const password = body.password ?? "";

  if (!login || !password) {
    return c.json({ message: "login and password are required" }, 400);
  }

  const user = await db
    .selectFrom("users")
    .select([
      "US_ID as id",
      "US_Login as login",
      "US_Pwd as password",
      "US_FirstName as firstName",
      "US_LastName as lastName",
      "US_CurrentYN as currentYn",
    ])
    .where("US_Login", "=", login)
    .executeTakeFirst();

  if (!user || String(user.currentYn ?? "").toUpperCase() !== "Y") {
    return c.json({ message: "Invalid login or password" }, 401);
  }

  const storedPassword = user.password ?? "";
  let matches = false;

  try {
    const decrypted = decryptPassword(storedPassword);
    matches = decrypted === password;
  } catch (err) {
    matches = false;
  }

  if (!matches) {
    try {
      const encrypted = encryptPassword(password);
      matches = encrypted === storedPassword;
    } catch (err) {
      matches = false;
    }
  }

  if (!matches) {
    return c.json({ message: "Invalid login or password" }, 401);
  }

  const isAdmin = isAdminUserId(Number(user.id));
  const token = await signAuthToken({
    userId: Number(user.id),
    login: user.login,
    isAdmin,
  });

  const permissions = await getEffectivePermissions({
    userId: Number(user.id),
    login: user.login,
    isAdmin,
  });

  return c.json({
    token,
    user: {
      id: Number(user.id),
      login: user.login,
      firstName: user.firstName ?? "",
      lastName: user.lastName ?? "",
      isAdmin,
    },
    permissions,
  });
});

auth.get("/me", async (c) => {
  const authCtx = getAuth(c);

  const user = await db
    .selectFrom("users")
    .select([
      "US_ID as id",
      "US_Login as login",
      "US_FirstName as firstName",
      "US_LastName as lastName",
      "US_CurrentYN as currentYn",
    ])
    .where("US_ID", "=", authCtx.userId)
    .executeTakeFirst();

  if (!user || String(user.currentYn ?? "").toUpperCase() !== "Y") {
    return c.json({ message: "User not found" }, 404);
  }

  const permissions = await getEffectivePermissions({
    userId: Number(user.id),
    login: authCtx.login,
    isAdmin: authCtx.isAdmin,
  });

  return c.json({
    user: {
      id: Number(user.id),
      login: user.login,
      firstName: user.firstName ?? "",
      lastName: user.lastName ?? "",
      isAdmin: authCtx.isAdmin,
    },
    permissions,
  });
});

export default auth;
