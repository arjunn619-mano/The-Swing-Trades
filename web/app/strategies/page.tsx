import { Badge, Card, SectionHeading } from "@/components/ui";

export const revalidate = 3600;

const STRATEGIES = [
  {
    name: "Bottom Breakout",
    key: "bullish_vol_rsi_candle",
    idea: "An oversold stock waking up on heavy volume — a potential bottom reversal.",
    rules: [
      "Volume ≥ 1.5× the 14-day average volume",
      "Volume > 50,000 shares (liquidity floor)",
      "RSI(14) < 50 (still oversold / not yet strong)",
      "A bullish candle: Marubozu, Bullish Engulfing, Strong Green, Hammer, or Long Lower Wick",
    ],
  },
  {
    name: "Top Breakout",
    key: "top_breakout",
    idea: "Strength confirming on volume — a continuation setup rather than a reversal.",
    rules: [
      "Volume ≥ 1.5× the 14-day average volume",
      "Volume > 50,000 shares (liquidity floor)",
      "RSI(14) > 55 (already strong, momentum building)",
      "A bullish candle (same patterns as above)",
    ],
  },
  {
    name: "Supertrend Buy",
    key: "supertrend_buy",
    idea: "A fresh trend change — the trend filter flips from down to up today.",
    rules: [
      "Supertrend (ATR period 10, multiplier 3.0) flips from short → long today",
      "Volume confirmation: ≥ 1.5× the 14-day average and > 50,000 shares",
    ],
  },
];

export default function StrategiesPage() {
  return (
    <div className="space-y-6">
      <SectionHeading
        title="Strategies"
        subtitle="The exact rules each screen applies every evening. Parameters are fixed in advance (no tuning on the data) so the measured edge stays honest."
      />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {STRATEGIES.map((s) => (
          <Card key={s.key} className="space-y-3">
            <div>
              <div className="text-base font-semibold text-slate-100">{s.name}</div>
              <code className="text-xs text-slate-500">{s.key}</code>
            </div>
            <p className="text-sm text-slate-400">{s.idea}</p>
            <div>
              <div className="mb-1 text-xs uppercase tracking-wide text-slate-500">Qualifies when ALL hold</div>
              <ul className="space-y-1 text-sm text-slate-300">
                {s.rules.map((r, i) => (
                  <li key={i} className="flex gap-2">
                    <span className="text-emerald-400">✓</span>
                    <span>{r}</span>
                  </li>
                ))}
              </ul>
            </div>
          </Card>
        ))}
      </div>

      <Card className="space-y-2 bg-navy-900/40">
        <div className="text-sm font-medium text-slate-200">How a qualifying stock is measured</div>
        <p className="text-sm text-slate-400">
          When a stock qualifies, it becomes a tracker entry keyed on <span className="text-slate-300">(stock × strategy)</span>.
          Its entry price is locked to that day&apos;s close and never changes. Each evening for the next 100 trading days, the
          entry&apos;s return is recorded. A strategy&apos;s <span className="text-slate-300">hit rate</span> is then shown next to the
          market&apos;s <span className="text-slate-300">base rate</span> — its edge is the <em>excess</em> over the market, not the raw
          hit rate. Indicators (RSI-14, ATR-10, Supertrend, 14-day average volume) use Wilder&apos;s smoothing.
        </p>
        <div className="flex flex-wrap gap-1.5 pt-1">
          <Badge tone="blue">RSI(14)</Badge>
          <Badge tone="amber">14-day vol avg</Badge>
          <Badge tone="green">Bullish candles</Badge>
          <Badge tone="slate">Supertrend (10, 3.0)</Badge>
        </div>
      </Card>

      <p className="text-xs text-slate-600">
        These are common retail signals with marginal, regime-dependent edge at best. The point of this tool is to <em>measure</em>
        whether they actually work against the right benchmark — not to assume they do. Not investment advice.
      </p>
    </div>
  );
}
