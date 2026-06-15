import { NextResponse } from "next/server";
import { sql } from "@/lib/db";

// Toggle a starred stock. POST { instrumentId, starred } — starred=true adds, false removes.
// The dashboard URL is public; this only ever inserts/deletes rows in the `starred` table.
export async function POST(req: Request) {
  if (!sql) return NextResponse.json({ ok: false, error: "no database" }, { status: 500 });

  let body: { instrumentId?: number; starred?: boolean };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "bad json" }, { status: 400 });
  }

  const id = Number(body.instrumentId);
  if (!Number.isFinite(id)) {
    return NextResponse.json({ ok: false, error: "instrumentId required" }, { status: 400 });
  }

  try {
    await sql`CREATE TABLE IF NOT EXISTS starred (
      instrument_id BIGINT PRIMARY KEY REFERENCES instruments(id) ON DELETE CASCADE,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )`;
    if (body.starred) {
      await sql`INSERT INTO starred (instrument_id) VALUES (${id}) ON CONFLICT (instrument_id) DO NOTHING`;
    } else {
      await sql`DELETE FROM starred WHERE instrument_id = ${id}`;
    }
    return NextResponse.json({ ok: true, instrumentId: id, starred: Boolean(body.starred) });
  } catch (e) {
    console.error("star route failed:", e);
    return NextResponse.json({ ok: false, error: "db error" }, { status: 500 });
  }
}
