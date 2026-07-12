import { NextResponse } from "next/server";
import { revalidatePath } from "next/cache";

// Manual "refresh": bust the ISR cache for every route so the next render pulls the latest
// already-scanned data from Postgres instead of waiting out the revalidate window. The dashboard
// is read-only, so this is harmless to trigger — it only re-reads, never writes.
export const dynamic = "force-dynamic";

export async function POST() {
  revalidatePath("/", "layout");
  return NextResponse.json({ revalidated: true, at: Date.now() });
}
