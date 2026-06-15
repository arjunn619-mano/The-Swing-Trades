import { neon } from "@neondatabase/serverless";

// Reads use the POOLED Neon connection (set DATABASE_URL_POOLED in Vercel). Falls back to
// DATABASE_URL for local dev. If neither is set (e.g. CI build with no secrets), `sql` is null
// and queries return empty results so the app still renders.
const url = process.env.DATABASE_URL_POOLED || process.env.DATABASE_URL;

export const sql = url ? neon(url) : null;
export const hasDb = Boolean(url);
