import { NextRequest, NextResponse } from "next/server";

// Vercel Cron pings this once a day; it triggers the GitHub Actions "News Capture" workflow.
// Mirrors /api/cron/scan — the single reliable scheduler (GitHub's own cron is unreliable). The
// news capture runs EVERY day (companies file on weekends too); the EOD scan then prices + enrols
// whatever was captured. Scheduled 30 min before the scan so same-day filings enrol same-day.
export const dynamic = "force-dynamic";

const REPO = "arjunn619-mano/The-Swing-Trades";
const WORKFLOW = "capture_news.yml";

export async function GET(req: NextRequest) {
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
