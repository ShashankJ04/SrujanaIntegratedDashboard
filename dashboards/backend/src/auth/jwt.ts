import { SignJWT, jwtVerify } from "jose";
import { env } from "../env";

const JWT_SECRET = new TextEncoder().encode(env.JWT_SECRET);

export interface AuthTokenPayload {
  userId: number;
  login: string;
  isAdmin: boolean;
}

export async function signAuthToken(payload: AuthTokenPayload): Promise<string> {
  return new SignJWT({ login: payload.login, isAdmin: payload.isAdmin })
    .setProtectedHeader({ alg: "HS256" })
    .setSubject(String(payload.userId))
    .setIssuedAt()
    .setExpirationTime(`${env.JWT_TTL_MINUTES}m`)
    .sign(JWT_SECRET);
}

export async function verifyAuthToken(token: string): Promise<AuthTokenPayload> {
  const { payload } = await jwtVerify(token, JWT_SECRET);
  const userId = Number(payload.sub ?? 0);
  const login = String(payload.login ?? "");
  const isAdmin = Boolean(payload.isAdmin);

  if (!userId || !login) {
    throw new Error("Invalid token payload");
  }

  return { userId, login, isAdmin };
}
