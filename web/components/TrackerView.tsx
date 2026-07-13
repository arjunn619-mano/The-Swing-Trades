"use client";

import { useMemo, useState } from "react";
import { StarButton } from "@/components/StarButton";
import { ChartLink } from "@/components/ui";
import { dateStr, money, pct } from "@/lib/format";
import type { TrackerRow } from "@/lib/queries";

type SortKey = "symbol" | "firstSeenDate" | "entryClose" | "currentClose" | "dayN" | "latestReturn" | "maxReturn" | "appearanceCount";
type SortDir = "asc" | "desc";
type Sort = { key: SortKey; dir: SortDir };
type ReturnFilter = "all" | "positive" | "negative";

const COLUMNS: { key: SortKey | "star" | "name" | "strategy" | "chart"; label: string; align?: "right"; sortable?: boolean }[] = [
  { key: "star", label: "" },
  { key: "symbol", label: "Symbol", sortable: true },
  { key: "name", label: "Name" },
  { key: "strategy", label: "Strategy" },
  { key: "firstSeenDate", label: "First seen", sortable: true },
  { key: "entryClose", label: "Entry close", align: "right", sortable: true },
  { key: "currentClose", label: "Current close", align: "right", sortable: true },
  { key: "dayN", label: "Day", align: "right", sortable: true },
  { key: "latestReturn", label: "Return", align: "right", sortable: true },
  { key: "maxReturn", label: "Max return", align: "right", sortable: true },
  { key: "appearanceCount", label: "Appears", align: "right", sortable: true },
  { key: "chart", label: "Chart", align: "right" },
];

const SORT_OPTIONS = COLUMNS.filter((c) => c.sortable).map((c) => ({ key: c.key as SortKey, label: c.label }));
const labelOf = (k: SortKey) => SORT_OPTIONS.find((o) => o.key === k)?.label ?? k;

// Numeric columns that get a min/max range filter in the left panel.
// `pct` fields are stored as fractions (0.05 = 5%) but typed/compared in percent.
const RANGE_FIELDS: { key: string; label: string; get: (r: TrackerRow) => number | null; pct?: boolean }[] = [
  { key: "entryClose", label: "Entry close (₹)", get: (r) => r.entryClose },
  { key: "currentClose", label: "Current close (₹)", get: (r) => r.currentClose },
  { key: "dayN", label: "Day (0–100)", get: (r) => r.dayN },
  { key: "latestReturn", label: "Return (%)", get: (r) => r.latestReturn, pct: true },
  { key: "maxReturn", label: "Max return (%)", get: (r) => r.maxReturn, pct: true },
  { key: "appearanceCount", label: "Appears", get: (r) => r.appearanceCount },
];

// first_seen_date may arrive as a string ("2026-06-22") or a Date (driver-dependent);
// normalise to a local YYYY-MM-DD so the date-range filter compares correctly either way.
function isoDate(x: unknown): string {
  if (!x) return "";
  if (x instanceof Date) {
    const y = x.getFullYear();
    const m = String(x.getMonth() + 1).padStart(2, "0");
    const d = String(x.getDate()).padStart(2, "0");
    return `${y}-${m}-${d}`;
  }
  return String(x).slice(0, 10);
}

function value(r: TrackerRow, key: SortKey): number | string {
  switch (key) {
    case "symbol":
      return r.symbol ?? "";
    case "firstSeenDate":
      return r.firstSeenDate ?? "";
    case "entryClose":
      return r.entryClose ?? -Infinity;
    case "currentClose":
      return r.currentClose ?? -Infinity;
    case "dayN":
      return r.dayN ?? -Infinity;
    case "latestReturn":
      return r.latestReturn ?? -Infinity;
    case "maxReturn":
      return r.maxReturn ?? -Infinity;
    case "appearanceCount":
      return r.appearanceCount ?? -Infinity;
    default:
      return "";
  }
}

function ReturnCell({ value: v }: { value: number | null }) {
  if (v === null || Number.isNaN(v)) return <span className="text-slate-500">—</span>;
  const tone = v > 0 ? "bg-emerald-500/15 text-emerald-300" : v < 0 ? "bg-rose-500/15 text-rose-300" : "bg-slate-700/40 text-slate-300";
  return <span className={`rounded-md px-1.5 py-0.5 text-xs font-medium ${tone}`}>{v > 0 ? "+" : ""}{pct(v)}</span>;
}

// Day N of the 100-trading-day window as a scannable bar: slate while running,
// amber in the final stretch, sky once the window is complete.
function DayProgress({ dayN }: { dayN: number | null }) {
  if (dayN === null) return <span className="text-slate-500">—</span>;
  const n = Math.max(0, dayN);
  const frac = Math.min(1, n / 100);
  const done = n >= 100;
  const nearEnd = n >= 85 && !done;
  const bar = done ? "bg-sky-400" : nearEnd ? "bg-amber-400" : "bg-slate-500";
  const text = done ? "text-sky-300" : nearEnd ? "text-amber-300" : "text-slate-400";
  return (
    <span className="inline-flex items-center gap-2" title={`Trading day ${n} of 100`}>
      <span className="h-1.5 w-14 overflow-hidden rounded-full bg-navy-700">
        <span className={`block h-full rounded-full ${bar}`} style={{ width: `${frac * 100}%` }} />
      </span>
      <span className={`tabular-nums text-xs ${text}`}>{n}/100</span>
    </span>
  );
}

export function TrackerView({ rows, starredIds }: { rows: TrackerRow[]; starredIds: number[] }) {
  const [strategy, setStrategy] = useState<string>("all");
  const [returnFilter, setReturnFilter] = useState<ReturnFilter>("all");
  const [pullbackOnly, setPullbackOnly] = useState<boolean>(false);
  const [query, setQuery] = useState<string>("");
  const [sorts, setSorts] = useState<Sort[]>([]);
  const [ranges, setRanges] = useState<Record<string, { min: string; max: string }>>({});
  const [dateFrom, setDateFrom] = useState<string>("");
  const [dateTo, setDateTo] = useState<string>("");
  const [showFilters, setShowFilters] = useState<boolean>(false);

  const starred = useMemo(() => new Set(starredIds), [starredIds]);

  // Per-strategy count + how many are currently positive (drives the sidebar %).
  const strategyStats = useMemo(() => {
    const m = new Map<string, { count: number; pos: number }>();
    for (const r of rows) {
      const s = m.get(r.strategy) ?? { count: 0, pos: 0 };
      s.count += 1;
      if ((r.latestReturn ?? 0) > 0) s.pos += 1;
      m.set(r.strategy, s);
    }
    return m;
  }, [rows]);
  const strategies = useMemo(() => Array.from(strategyStats.keys()).sort(), [strategyStats]);
  const overallPos = useMemo(() => rows.filter((r) => (r.latestReturn ?? 0) > 0).length, [rows]);

  // Actual data min/max per numeric column — shown as placeholder hints in the filters.
  const bounds = useMemo(() => {
    const b: Record<string, { min: number; max: number }> = {};
    for (const f of RANGE_FIELDS) {
      let mn = Infinity;
      let mx = -Infinity;
      for (const r of rows) {
        const raw = f.get(r);
        if (raw === null || Number.isNaN(raw)) continue;
        const x = f.pct ? raw * 100 : raw;
        if (x < mn) mn = x;
        if (x > mx) mx = x;
      }
      b[f.key] = { min: mn === Infinity ? 0 : mn, max: mx === -Infinity ? 0 : mx };
    }
    return b;
  }, [rows]);

  const strategyFiltered = useMemo(
    () => (strategy === "all" ? rows : rows.filter((r) => r.strategy === strategy)),
    [rows, strategy]
  );

  const positives = strategyFiltered.filter((r) => (r.latestReturn ?? 0) > 0).length;
  const positivePct = strategyFiltered.length ? positives / strategyFiltered.length : 0;

  const filtered = useMemo(() => {
    let out = strategyFiltered;
    if (returnFilter === "positive") out = out.filter((r) => (r.latestReturn ?? 0) > 0);
    else if (returnFilter === "negative") out = out.filter((r) => (r.latestReturn ?? 0) < 0);
    // Pullback STACKS on top of the direction filter: currently below its own peak — gave some back.
    if (pullbackOnly) out = out.filter((r) => r.maxReturn !== null && r.latestReturn !== null && r.maxReturn > r.latestReturn);

    const q = query.trim().toLowerCase();
    if (q) out = out.filter((r) => (r.symbol ?? "").toLowerCase().includes(q) || (r.name ?? "").toLowerCase().includes(q));

    // Per-column numeric range filters.
    for (const f of RANGE_FIELDS) {
      const rg = ranges[f.key];
      if (!rg) continue;
      const min = rg.min === "" ? null : Number(rg.min);
      const max = rg.max === "" ? null : Number(rg.max);
      if (min === null && max === null) continue;
      out = out.filter((r) => {
        const raw = f.get(r);
        if (raw === null || Number.isNaN(raw)) return false;
        const v = f.pct ? raw * 100 : raw;
        if (min !== null && v < min) return false;
        if (max !== null && v > max) return false;
        return true;
      });
    }

    // First-seen date range (ISO YYYY-MM-DD compares lexicographically).
    if (dateFrom || dateTo) {
      out = out.filter((r) => {
        const d = isoDate(r.firstSeenDate);
        if (!d) return false;
        if (dateFrom && d < dateFrom) return false;
        if (dateTo && d > dateTo) return false;
        return true;
      });
    }

    // Multi-column sort: walk the stack in click-order; first non-tie wins.
    const arr = [...out];
    if (sorts.length) {
      arr.sort((a, b) => {
        for (const s of sorts) {
          const va = value(a, s.key);
          const vb = value(b, s.key);
          const c = typeof va === "string" && typeof vb === "string" ? va.localeCompare(vb) : (va as number) - (vb as number);
          if (c !== 0) return s.dir === "asc" ? c : -c;
        }
        return 0;
      });
    }
    return arr;
  }, [strategyFiltered, returnFilter, pullbackOnly, query, ranges, dateFrom, dateTo, sorts]);

  // Click a column: add as next sort level (desc) → flip to asc → remove.
  function cycleSort(key: SortKey) {
    setSorts((prev) => {
      const i = prev.findIndex((s) => s.key === key);
      if (i === -1) return [...prev, { key, dir: "desc" }];
      if (prev[i].dir === "desc") {
        const next = [...prev];
        next[i] = { key, dir: "asc" };
        return next;
      }
      return prev.filter((s) => s.key !== key);
    });
  }

  function setRange(key: string, side: "min" | "max", val: string) {
    setRanges((prev) => ({
      ...prev,
      [key]: { min: side === "min" ? val : prev[key]?.min ?? "", max: side === "max" ? val : prev[key]?.max ?? "" },
    }));
  }
  function clearFilters() {
    setRanges({});
    setDateFrom("");
    setDateTo("");
  }

  const activeFilterCount =
    RANGE_FIELDS.filter((f) => ranges[f.key] && (ranges[f.key].min !== "" || ranges[f.key].max !== "")).length +
    (dateFrom || dateTo ? 1 : 0);

  if (rows.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-navy-700/60 bg-navy-900/40 p-4 text-center text-sm text-slate-400">
        No tracked stocks yet. Entries appear after the first scan finds qualifying stocks.
      </div>
    );
  }

  const sidebarItems = [
    { key: "all", label: "All strategies", count: rows.length, posPct: rows.length ? Math.round((overallPos / rows.length) * 100) : null },
    ...strategies.map((s) => {
      const st = strategyStats.get(s) ?? { count: 0, pos: 0 };
      return { key: s, label: s, count: st.count, posPct: st.count ? Math.round((st.pos / st.count) * 100) : null };
    }),
  ];
  const returnTabs: { key: ReturnFilter; label: string }[] = [
    { key: "all", label: "All" },
    { key: "positive", label: "Positive" },
    { key: "negative", label: "Negative" },
  ];

  const inputCls =
    "w-full min-w-0 rounded-md border border-navy-700/60 bg-navy-900 px-2 py-1 text-xs text-slate-200 placeholder:text-slate-600 focus:border-navy-600 focus:outline-none";

  return (
    <div className="flex flex-col gap-4 lg:flex-row">
      {/* Strategy filter + range filters — horizontal on mobile, sidebar on desktop */}
      <aside className="lg:w-60 lg:shrink-0">
        <div className="mb-2 hidden text-xs uppercase tracking-wide text-slate-400 lg:block">Strategy</div>
        <div className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1 lg:mx-0 lg:flex-col lg:gap-1 lg:overflow-visible lg:px-0 lg:pb-0 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
          {sidebarItems.map((item) => {
            const active = strategy === item.key;
            return (
              <button
                key={item.key}
                onClick={() => setStrategy(item.key)}
                className={`flex shrink-0 items-center gap-2 whitespace-nowrap rounded-md px-3 py-2 text-left text-sm transition-colors lg:w-full lg:justify-between lg:shrink ${
                  active ? "bg-navy-700 text-white" : "bg-navy-900/60 text-slate-300 hover:bg-navy-800 lg:bg-transparent"
                }`}
              >
                <span className="truncate">{item.label}</span>
                <span className="flex shrink-0 items-center gap-1.5">
                  {item.posPct !== null ? (
                    <span className={`text-xs ${active ? "text-emerald-200" : "text-emerald-400/70"}`} title="% of entries currently positive">
                      {item.posPct}%
                    </span>
                  ) : null}
                  <span className={`text-xs ${active ? "text-slate-300" : "text-slate-500"}`}>{item.count}</span>
                </span>
              </button>
            );
          })}
        </div>

        {/* Range filters */}
        <div className="mt-4">
          <button
            onClick={() => setShowFilters((v) => !v)}
            className="flex w-full items-center justify-between text-xs font-medium uppercase tracking-wide text-slate-400 hover:text-slate-200"
          >
            <span>Filters{activeFilterCount ? <span className="ml-1 text-sky-300">· {activeFilterCount}</span> : null}</span>
            <span className="text-slate-500">{showFilters ? "▲" : "▼"}</span>
          </button>
          {showFilters ? (
            <div className="mt-2 space-y-3">
              {RANGE_FIELDS.map((f) => (
                <div key={f.key}>
                  <div className="text-xs text-slate-400">{f.label}</div>
                  <div className="mt-1 flex items-center gap-1">
                    <input
                      type="number"
                      inputMode="decimal"
                      value={ranges[f.key]?.min ?? ""}
                      onChange={(e) => setRange(f.key, "min", e.target.value)}
                      placeholder={`${Math.floor(bounds[f.key].min)}`}
                      aria-label={`${f.label} minimum`}
                      className={inputCls}
                    />
                    <span className="text-slate-600">–</span>
                    <input
                      type="number"
                      inputMode="decimal"
                      value={ranges[f.key]?.max ?? ""}
                      onChange={(e) => setRange(f.key, "max", e.target.value)}
                      placeholder={`${Math.ceil(bounds[f.key].max)}`}
                      aria-label={`${f.label} maximum`}
                      className={inputCls}
                    />
                  </div>
                </div>
              ))}
              <div>
                <div className="text-xs text-slate-400">First seen</div>
                <div className="mt-1 flex items-center gap-1">
                  <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} aria-label="First seen from" className={inputCls} />
                  <span className="text-slate-600">–</span>
                  <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} aria-label="First seen to" className={inputCls} />
                </div>
              </div>
              {activeFilterCount > 0 ? (
                <button onClick={clearFilters} className="text-xs text-sky-400 hover:text-sky-300">
                  Clear filters
                </button>
              ) : null}
            </div>
          ) : null}
        </div>
      </aside>

      <div className="min-w-0 flex-1 space-y-3">
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search symbol or name…"
          aria-label="Search symbol or name"
          className="w-full rounded-md border border-navy-700/60 bg-navy-900 px-3 py-1.5 text-sm text-slate-200 placeholder:text-slate-500 focus:border-navy-600 focus:outline-none sm:max-w-xs"
        />
        {/* Controls */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="text-slate-400">
              {filtered.length.toLocaleString("en-IN")} of {strategyFiltered.length.toLocaleString("en-IN")}
            </span>
            <span className="rounded-md bg-navy-800 px-2 py-1 text-xs text-slate-300">
              <span className="font-semibold text-emerald-300">{(positivePct * 100).toFixed(1)}%</span> positive
            </span>
            {sorts.length > 0 ? (
              <button
                onClick={() => setSorts([])}
                className="rounded-md border border-navy-700/60 bg-navy-900 px-2 py-1 text-xs text-slate-300 hover:text-white"
              >
                Clear sort{sorts.length > 1 ? ` (${sorts.length})` : ""}
              </button>
            ) : null}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {/* Mobile multi-sort: active levels as chips (tap to cycle/remove) + add */}
            <div className="flex flex-wrap items-center gap-1 md:hidden">
              {sorts.map((s, i) => (
                <button
                  key={s.key}
                  onClick={() => cycleSort(s.key)}
                  className="inline-flex items-center gap-1 rounded-md border border-navy-700/60 bg-navy-800 px-2 py-1 text-xs text-slate-200"
                  title="Tap to flip direction, again to remove"
                >
                  <span className="text-slate-500">{i + 1}</span>
                  {labelOf(s.key)} {s.dir === "asc" ? "▲" : "▼"}
                </button>
              ))}
              <select
                value=""
                onChange={(e) => {
                  if (e.target.value) cycleSort(e.target.value as SortKey);
                }}
                className="rounded-md border border-navy-700/60 bg-navy-900 px-2 py-1 text-xs text-slate-300"
                aria-label="Add sort column"
              >
                <option value="">+ Sort…</option>
                {SORT_OPTIONS.filter((o) => !sorts.some((s) => s.key === o.key)).map((o) => (
                  <option key={o.key} value={o.key}>
                    {o.label}
                  </option>
                ))}
              </select>
            </div>
            {/* Return filter */}
            <div className="flex gap-0.5 rounded-lg border border-navy-700/60 bg-navy-900/60 p-0.5">
              {returnTabs.map((t) => (
                <button
                  key={t.key}
                  onClick={() => setReturnFilter(t.key)}
                  className={`rounded-md px-2.5 py-1 text-sm transition-colors ${
                    returnFilter === t.key ? "bg-navy-700 text-white" : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>
            {/* Pullback toggle — stacks on top of the direction filter (combine + sort within) */}
            <button
              onClick={() => setPullbackOnly((v) => !v)}
              title="Show only stocks currently below their own peak (max return > current return)"
              className={`rounded-md border px-2.5 py-1 text-sm transition-colors ${
                pullbackOnly
                  ? "border-sky-500/50 bg-sky-500/15 text-sky-300"
                  : "border-navy-700/60 bg-navy-900/60 text-slate-400 hover:text-slate-200"
              }`}
            >
              ↓ Pullback
            </button>
          </div>
        </div>

        {/* Desktop table */}
        <div className="hidden overflow-x-auto rounded-xl border border-navy-700/60 bg-navy-900/40 md:block">
          <table className="w-full min-w-[1000px] text-sm">
            <thead>
              <tr className="bg-navy-900/70 text-left text-xs uppercase tracking-wide text-slate-400">
                {COLUMNS.map((c) => {
                  const sortIndex = c.sortable ? sorts.findIndex((s) => s.key === c.key) : -1;
                  const sort = sortIndex >= 0 ? sorts[sortIndex] : null;
                  return (
                    <th
                      key={c.key}
                      onClick={c.sortable ? () => cycleSort(c.key as SortKey) : undefined}
                      title={c.sortable ? "Click to sort (click more columns to add tie-breakers)" : undefined}
                      className={`whitespace-nowrap px-3 py-2 font-medium ${c.align === "right" ? "text-right" : ""} ${
                        c.sortable ? "cursor-pointer select-none hover:text-slate-200" : ""
                      }`}
                    >
                      <span className={`inline-flex items-center gap-1 ${c.align === "right" ? "flex-row-reverse" : ""}`}>
                        {c.label}
                        {sort ? (
                          <span className="inline-flex items-center gap-0.5 text-sky-300">
                            {sorts.length > 1 ? <span className="text-[10px] font-semibold">{sortIndex + 1}</span> : null}
                            <span>{sort.dir === "asc" ? "▲" : "▼"}</span>
                          </span>
                        ) : null}
                      </span>
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {filtered.map((r, i) => (
                <tr key={i} className="border-t border-navy-700/40 hover:bg-navy-800/40">
                  <td className="px-3 py-2"><StarButton instrumentId={r.instrumentId} initialStarred={starred.has(r.instrumentId)} /></td>
                  <td className="whitespace-nowrap px-3 py-2 font-semibold text-slate-100">{r.symbol}</td>
                  <td className="whitespace-nowrap px-3 py-2 text-slate-400">{r.name}</td>
                  <td className="whitespace-nowrap px-3 py-2 text-slate-300">{r.strategy}</td>
                  <td className="whitespace-nowrap px-3 py-2 text-slate-300">{dateStr(r.firstSeenDate)}</td>
                  <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums text-slate-200">{money(r.entryClose)}</td>
                  <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums text-slate-200">{money(r.currentClose)}</td>
                  <td className="whitespace-nowrap px-3 py-2 text-right"><DayProgress dayN={r.dayN} /></td>
                  <td className="whitespace-nowrap px-3 py-2 text-right"><ReturnCell value={r.latestReturn} /></td>
                  <td className="whitespace-nowrap px-3 py-2 text-right"><ReturnCell value={r.maxReturn} /></td>
                  <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums text-slate-300">{r.appearanceCount}×</td>
                  <td className="whitespace-nowrap px-3 py-2 text-right"><ChartLink exchange={r.exchange} ticker={r.symbol} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Mobile cards */}
        <div className="space-y-2 md:hidden">
          {filtered.map((r, i) => (
            <div key={i} className="rounded-lg border border-navy-700/60 bg-navy-900/40 p-3">
              <div className="flex items-center justify-between gap-2">
                <div className="flex min-w-0 items-center gap-2">
                  <StarButton instrumentId={r.instrumentId} initialStarred={starred.has(r.instrumentId)} />
                  <span className="truncate font-semibold text-slate-100">{r.symbol}</span>
                  <ChartLink exchange={r.exchange} ticker={r.symbol} />
                </div>
                <ReturnCell value={r.latestReturn} />
              </div>
              <div className="mt-1 truncate text-xs text-slate-500">{r.name}</div>
              <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
                <span className="text-slate-500">Strategy <span className="text-slate-300">{r.strategy}</span></span>
                <span className="text-slate-500">First seen <span className="text-slate-300">{dateStr(r.firstSeenDate)}</span></span>
                <span className="text-slate-500">Entry <span className="text-slate-300">{money(r.entryClose)}</span></span>
                <span className="text-slate-500">Now <span className="text-slate-300">{money(r.currentClose)}</span></span>
                <span className="inline-flex items-center gap-1 text-slate-500">Day <DayProgress dayN={r.dayN} /></span>
                <span className="inline-flex items-center gap-1 text-slate-500">Max <ReturnCell value={r.maxReturn} /></span>
                <span className="text-slate-500">Appears <span className="text-slate-300">{r.appearanceCount}×</span></span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
