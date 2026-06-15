# 04 — Dhan Integration

Everything the worker needs to talk to Dhan. All endpoints are `api.dhan.co` / `images.dhan.co` — official API + CDN, **not** behind NSE's Akamai bot-wall. Static-IP whitelisting is required **only for order placement** (which we never do), so GitHub Actions' rotating IPs are fine for data.

Use the official **`dhanhq` Python SDK** (`pip install dhanhq`). Do **not** depend on the course `Dhan_Tradehull_V2.py` wrapper — it's 1879 lines of Python-3.8 live-trading/order-placement code; useful only as a parsing reference.

## Authentication (TOTP, unattended)
- Tokens are **24 hours** (SEBI rule — no long-lived token exists).
- The worker generates its own token each run from stored secrets via the PIN + TOTP flow.

```
POST https://auth.dhan.co/app/generateAccessToken?dhanClientId=<ID>&pin=<PIN>&totp=<code>
→ { "accessToken": "<JWT>", "expiryTime": "<+24h>" }
```
SDK equivalent: `DhanLogin.generate_token(pin, totp)`. Compute `totp` with `pyotp.TOTP(secret).now()`.

**Secrets (GitHub Actions Secrets, private repo):** `DHAN_CLIENT_ID`, `DHAN_PIN`, `DHAN_TOTP_SECRET`. These generate a full-access token → treat as account-level credentials; never in code or committed to the repo.

## 1. Universe — instrument master CSV
One CDN download; no scraping.
```
https://images.dhan.co/api-data/api-scrip-master-detailed.csv
```
Columns used: `SECURITY_ID`, `ISIN`, `EXCH_ID` (NSE/BSE), `SEGMENT` (E = Equity), `SYMBOL_NAME`, `SERIES`, `ASM_GSM_FLAG`, `LOT_SIZE`.
- Filter to **active NSE + BSE equities** → the scan universe (~2,000 names).
- Resolve dual-listing by ISIN → keep NSE as canonical, store BSE scrip code for reference (Rule #4).
- Optionally exclude `ASM_GSM_FLAG = 'Y'` (surveillance) stocks.
- Refresh daily (cheap) so new listings/changes are picked up.

## 2. History backfill — Historical Data API
For indicators we need trailing daily candles. Backfill once (then append daily).
```
POST https://api.dhan.co/v2/charts/historical
{
  "securityId": "1333",
  "exchangeSegment": "NSE_EQ",   // or BSE_EQ
  "instrument": "EQUITY",
  "fromDate": "2024-06-01",
  "toDate": "2026-06-09"
}
→ parallel arrays: open[], high[], low[], close[], volume[], timestamp[]
```
- One call per security; daily candles back to inception (we only need ~200 trading days for the indicators).
- Limits are generous (daily allows 365 days/request; data-API rate limits are liberal). ~2,000 calls for a full backfill is a one-time, minutes-long job.
- Store into `price_history`.

## 3. Daily prices — Bulk Market Quote (the workhorse)
The efficient daily path. **`/marketfeed/quote` (full mode) returns volume** — confirmed from the docs.
```
POST https://api.dhan.co/v2/marketfeed/quote
Headers: access-token, client-id
Body (≤1000 instruments per call, grouped by segment):
{ "NSE_EQ": [11536, 1333, ...], "BSE_EQ": [500325, ...] }
→ per instrument: last_price, ohlc{open,high,low,close}, volume, average_price, ...
```
- **Up to 1000 instruments per request**, 1 request/second. The whole ~2,000-stock universe → **2–3 calls per night.**
- Returns OHLC **and volume** (strategies need volume).
- Note: `/marketfeed/ohlc` is prices-only (no volume) — do **not** use it for the scan; `/marketfeed/ltp` is last-price-only.

## Endpoint summary
| Need | Endpoint | Frequency | Notes |
|------|----------|-----------|-------|
| Token | `auth/generateAccessToken` | once per run | PIN + TOTP |
| Universe | `images.dhan.co/.../api-scrip-master-detailed.csv` | daily | CDN, no auth |
| History backfill | `/v2/charts/historical` | once (+ gap fills) | per security |
| Daily OHLCV | `/v2/marketfeed/quote` | daily | bulk, incl. volume |

## Exchange-segment enums
`NSE_EQ`, `BSE_EQ` (equity). Map each instrument's `EXCH_ID` + `SEGMENT` to the right enum when calling the APIs.

## Rate limits & etiquette
- Data APIs: liberal (multiple requests/sec; quote = 1 req/sec for the 1000-instrument bulk call; 100k requests/day).
- Build a small batched fetcher with retries + backoff (reuse v1's batching idea, but against Dhan not yfinance).
- Respect the 1 req/sec on bulk quote; the universe needs only 2–3 calls anyway.

## Open / to verify at build time
- **Corporate-action adjustment** (splits/bonuses): unconfirmed whether Dhan daily candles are adjusted. **Deferred** per decision. If raw, a large unexplained overnight gap on a tracked stock can distort a signal or a tracker entry — later mitigation: detect the gap and flag/skip, or apply a corporate-action adjustment from Dhan's/NSE's action list.
