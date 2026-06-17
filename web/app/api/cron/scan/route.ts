import { NextRequest, NextResponse } from "next/server";

// Vercel Cron pings this once a day; it triggers the GitHub Actions "EOD Scan" workflow.
// This is the SINGLE scheduler for the scan (GitHub's own cron is unreliable and is disabled).
export const dynamic = "force-dynamic";

const REPO = "arjunn619-mano/The-Swing-Trades";
const WORKFLOW = "scan.yml";

export async function GET(req: NextRequest) {
  // Vercel sends `Authorization: Bearer <CRON_SECRET>` on cron invocations when CRON_SECRET is set.
  const secret = process.env.CRON_SECRET;
  if (secret && req.headers.get("authorization") !== `Bearer ${secret}`) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const token = process.env.GH_DISPATCH_TOKEN;
  if (!token) {
    return NextResponse.json({ error: "GH_DISPATCH_TOKEN not set" }, { status: 500 });
  }

  const resp = await fetch(
    `https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ ref: "main" }),
    },
  );

  const ok = resp.status === 204; // GitHub returns 204 No Content on a successful dispatch
  const detail = ok ? "" : (await resp.text()).slice(0, 300);
  return NextResponse.json({ triggered: ok, githubStatus: resp.status, detail }, { status: ok ? 200 : 502 });
}
