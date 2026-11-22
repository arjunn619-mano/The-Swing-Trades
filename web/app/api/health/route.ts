import { NextResponse } from "next/server";
import { getHealth } from "@/lib/health";

// Read-only JSON of the latest judged health (no secrets: states, numbers, plain-word texts). The NIFTY firm's VM
// reads it about once an hour for its Outside limits register, so a Swing Trades problem shows there too.
export const revalidate = 600;

export async function GET() {
  const h = await getHealth();
  return NextResponse.json({
    ok: h.ok,
    log_started: h.logStarted,
    state: h.state,
    judged_at: h.judgedAt,
    judged_by: h.judgedBy,
    items: h.items.map(({ key, name, used, limit, unit, pct, forecast, forecast_pct, state, text }) => ({
      key, name, used, limit, unit, pct, forecast, forecast_pct, state, text,
    })),
  });
}
