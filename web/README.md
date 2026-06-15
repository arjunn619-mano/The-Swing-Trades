# web/ — The Swing Trades dashboard

Next.js (App Router) + Tailwind + shadcn/ui. Deployed on Vercel (set Vercel's **Root Directory** to `web/`). Read-only over Neon via the **pooled** connection, served through ISR caching so visitors hit the CDN, not the DB. Mobile-first; installable as a PWA.

**Built in Phase 5** (after the worker writes real data). See `../Planning Pack/06_BUILD_PHASES.md`.
