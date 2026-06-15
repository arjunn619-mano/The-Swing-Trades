# The Swing Trades: Critical Architecture Analysis (Historical)

Based on the `Decision_Draft.md`, I have critically evaluated the proposed architecture, performed market research, and identified potential pitfalls along with better tools available in the current market. 

---

## 1. The "Data Fetching" Blocker (The Biggest Risk)

**The Current Plan:** GitHub Actions (cron) running a Python script to download the NSE/BSE Bhavcopy.
**The Critical Issue:** NSE uses **Akamai API Protector**, which aggressively blocks datacenter IPs (like those used by GitHub Actions, AWS, Vercel, and GCP). If you try to fetch the Bhavcopy directly from a GitHub runner, you will almost certainly get a `403 Forbidden` or `Access Denied` error.

### Better Alternatives & Market Tools
Instead of brittle scraping or relying on `yfinance` (which is highly prone to rate-limiting for bulk downloads from a single IP), consider these better ways:

1.  **Upstox API (Highly Recommended):** 
    *   **Why it's better:** Upstox offers its API **completely free** for historical and EOD data. It is an official broker API, meaning it provides clean, adjusted data (handling splits/bonuses automatically) and is NOT blocked by Akamai. You just need an active (free) Upstox account to generate an API key.
    *   **How to use:** Your GitHub Action can authenticate with the Upstox API and fetch the daily candles for your universe without scraping HTML/ZIP files.
2.  **Community NPM/Python Packages:**
    *   Packages like `nse-bse-api` (NPM) or `nsepython` are decent fallbacks, but remember they are wrappers around the same web requests and can still suffer from IP bans if run from GitHub Actions.
3.  **Alternative Execution Environments:**
    *   If you *must* scrape the Bhavcopy, GitHub Actions might not work. You would need a cheap VPS with a residential IP proxy, or a local cron job on a Raspberry Pi / PC (which defeats the "cloud-only" goal). 

> [!IMPORTANT]
> **Recommendation:** Pivot from scraping the NSE Bhavcopy to using a free official broker API like **Upstox API** or **Dhan API** for EOD data. This eliminates the Akamai IP block risk entirely and gives you cleaner data.

---

## 2. The Data Store (Database)

**The Current Plan:** Neon Postgres (Serverless Postgres).
**The Critical Issue:** Neon is excellent, but for a personal tracker that updates *once a day*, you will face "cold start" latency. Neon scales to zero to save costs, meaning the first recruiter who clicks your portfolio link will wait 3-5 seconds while the database wakes up.

### Better Alternatives & Market Tools
1.  **Turso (libSQL / SQLite at the Edge):**
    *   **Why it's better:** Turso is a serverless database based on SQLite. It is specifically designed to have zero-latency cold starts. It pairs perfectly with Next.js and Vercel. Their free tier is incredibly generous (9 GB storage, 1 billion reads). For a tool that just reads a small list of stocks daily, Turso will feel *instantly* fast compared to Neon.
2.  **Supabase:**
    *   If you stick with Postgres, Supabase is often preferred over Neon for solo developers because it comes with built-in APIs (PostgREST). You wouldn't even need to write backend API routes in Next.js; your UI can fetch directly from Supabase securely.
3.  **Static JSON on GitHub (The ultra-lean option):**
    *   You mentioned this in the draft as a fallback. Given the data only updates once at 7:30 PM IST, writing the scan results to a JSON file and committing it back to the repo via GitHub Actions is 100% free, has ZERO cold starts, and loads instantly on Vercel (via CDN). For a personal portfolio piece, this is incredibly robust.

> [!TIP]
> **Recommendation:** If you want a database to show off backend skills, switch to **Turso (SQLite)** for instant Vercel loads. If you prioritize reliability and zero-cost maintenance, the **Static JSON commit** method is completely bulletproof.

---

## 3. The Compute / Scheduler

**The Current Plan:** GitHub Actions Cron (~14:00 UTC).
**The Critical Issue:** GitHub Actions cron schedules are notorious for being delayed. A job scheduled for 14:00 UTC might not run until 14:45 UTC depending on global load. 

### Better Alternatives & Market Tools
1.  **Vercel Cron Jobs:** Vercel allows you to trigger serverless functions via cron. If you move your Python worker logic to a Vercel Serverless Function (using Python or rewriting to TypeScript), Vercel Cron is much more precise. (However, Vercel Hobby tier restricts function execution time to 10 seconds, which is too short for a heavy scan).
2.  **Modal.com:**
    *   Modal is a specialized serverless platform for Python. It allows you to run heavy data-crunching scripts (like pandas calculations for RSI/ATR) on a schedule. It gives you $30/month in free credits (way more than enough for a daily EOD scan).

> [!NOTE]
> **Recommendation:** Stick with **GitHub Actions**, but trigger it manually via a webhook or accept that the run time will be variable (e.g., somewhere between 7:30 PM and 8:15 PM IST). 

---

## 4. Frontend & Architecture

**The Current Plan:** Next.js on Vercel. Responsive from Day 1.
**Analysis:** This is **LOCKED IN and PERFECT**. Next.js App Router, combined with Tailwind CSS (for easy responsive mobile-first design) and shadcn/ui components (for great looking data tables) is the industry standard. This will look highly professional to recruiters.

---

## Summary of the "Critical Lens" Verdict

Your 3-job split architecture is fundamentally sound. The main flaws lie in the **data acquisition method** and the **database cold-starts**.

**Proposed Optimized Stack for v2:**
1.  **UI:** Next.js on Vercel (Unchanged).
2.  **Data Source:** **Upstox Free API** instead of scraping Bhavcopy (Fixes the Akamai blocker).
3.  **Data Store:** **Turso** instead of Neon (Fixes the cold-start loading delay).
4.  **Worker:** GitHub Actions (Unchanged, but now immune to IP blocks because it's hitting an official broker API, not the NSE website).
