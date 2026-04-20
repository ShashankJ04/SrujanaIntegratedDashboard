import { z } from "zod";
import { config } from "dotenv";

// Ensure local .env values override inherited shell variables.
config({ override: true });

const envSchema = z.object({
  DB_HOST: z.string().default("localhost"),
  DB_PORT: z.coerce.number().default(3306),
  DB_USER: z.string().default("root"),
  DB_PASSWORD: z.string().default("root"),
  DB_NAME: z.string().default("erp"),
  PORT: z.coerce.number().default(3001),
  PM_ATTACHMENTS_DIR: z.string().default("../pm-attachments"),
  JWT_SECRET: z.string().default("change-me"),
  JWT_TTL_MINUTES: z.coerce.number().default(720),
});

export const env = envSchema.parse(process.env);
