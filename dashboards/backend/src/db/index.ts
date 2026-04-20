import { Kysely, MysqlDialect } from "kysely";
import { createPool } from "mysql2";
import { env } from "../env";
import type { Database } from "./types";

const dialect = new MysqlDialect({
  pool: createPool({
    host: env.DB_HOST,
    port: env.DB_PORT,
    user: env.DB_USER,
    password: env.DB_PASSWORD,
    database: env.DB_NAME,
    connectionLimit: 10,
  }),
});

export const db = new Kysely<Database>({
  dialect,
});
