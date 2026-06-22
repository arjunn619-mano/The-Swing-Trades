"use client";

import { useMemo, useState } from "react";
import { StarButton } from "@/components/StarButton";
import { ChartLink } from "@/components/ui";
import { dateStr, money, pct } from "@/lib/format";
import type { NewListing } from "@/lib/queries";

type SortKey = "symbol" | "firstSeen" | "entryClose" | "currentClose" | "returnPct" | "bars";
type ReturnFilter = "all" | "positive" | "negative";

const COLUMNS: { key: SortKey | "star" | "name" | "exchange" | "chart"; label: string; align?: "right"; sortable?: boolean }[] = [
  { key: "star", label: "" },
  { key: "symbol", label: "Symbol", sortable: true },
  { key: "name", label: "Name" },
  { key: "exchange", label: "Exch" },
  { key: "firstSeen", label: "Listed / first seen", sortable: true },
  { key: "entryClose", label: "Entry close", align: "right", sortable: true },
  { key: "currentClose", label: "Current close", align: "right", sortable: true },
  { key: "returnPct", label: "Return", align: "right", sortable: true },
  { key: "bars", label: "Days of data", align: "right", sortable: true },
  { key: "chart", label: "Chart", align: "right" },
];

const SORT_OPTIONS = COLUMNS.filter((c) => c.sortable).map((c) => ({ key: c.key as SortKey, label: c.label }));

function value(r: NewListing, key: SortKey): number | string {
  switch (key) {
    case "symbol":
      return r.symbol ?? "";
    case "firstSeen":
      return r.firstSeen ?? "";
    case "entryClose":
      return r.entryClose ?? -Infinity;
    case "currentClose":
      return r.currentClose ?? -Infinity;
    case "returnPct":
      return r.returnPct ?? -Infinity;
    case "bars":
      return r.bars ?? -Infinity;
    default:
      return "";
  }
}

function ReturnCell({ value: v }: { value: number | null }) {
  if (v === null || Number.isNaN(v)) return <span className="text-slate-500">—</span>;
  const tone = v > 0 ? "bg-emerald-500/15 text-emerald-300" : v < 0 ? "bg-rose-500/15 text-rose-300" : "bg-slate-700/40 text-slate-300";
  return <span className={`rounded-md px-1.5 py-0.5 text-xs font-medium ${tone}`}>{v > 0 ? "+" : ""}{pct(v)}</span>;
}

export function NewListingsView({ rows, starredIds }: { rows: NewListing[]; starredIds: number[] }) {
  const [exchange, setExchange] = useState<string>("all");
  const [returnFilter, setReturnFilter] = useState<ReturnFilter>("all");
  const [query, setQuery] = useState<string>("");
  const [sortKey, setSortKey] = useState<SortKey>("firstSeen");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const starred = useMemo(() => new Set(starredIds), [starredIds]);

  const exchangeCounts = useMemo(() => {
    const m = new Map<string, number>();
    for (const r of rows) m.set(r.exchange, (m.get(r.exchange) ?? 0) + 1);
    return m;
  }, [rows]);
  const exchanges = useMemo(() => Array.from(exchangeCounts.keys()).sort(), [exchangeCounts]);

  const exchangeFiltered = useMemo(
    () => (exchange === "all" ? rows : rows.filter((r) => r.exchange === exchange)),
    [rows, exchange]
  );

  const positives = exchangeFiltered.filter((r) => (r.returnPct ?? 0) > 0).length;
  const positivePct = exchangeFiltered.length ? positives / exchangeFiltered.length : 0;

  const filtered = useMemo(() => {
    let out = exchangeFiltered;
    if (returnFilter === "positive") out = out.filter((r) => (r.returnPct ?? 0) > 0);
    else if (returnFilter === "negative") out = out.filter((r) => (r.returnPct ?? 0) < 0);
    const q = query.trim().toLowerCase();
    if (q) out = out.filter((r) => (r.symbol ?? "").toLowerCase().includes(q) || (r.name ?? "").toLowerCase().includes(q));
    return [...out].sort((a, b) => {
      const va = value(a, sortKey);
      const vb = value(b, sortKey);
      const c = typeof va === "string" && typeof vb === "string" ? va.localeCompare(vb) : (va as number) - (vb as number);
      return sortDir === "asc" ? c : -c;
    });
  }, [exchangeFiltered, returnFilter, query, sortKey, sortDir]);

  function toggleSort(key: SortKey) {
    if (key === sortKey) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortKey(key);
      setSortDir("desc");
    }
  }

  if (rows.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-navy-700/60 bg-navy-900/40 p-4 text-center text-sm text-slate-400">
        No new listings right now. Newly-listed stocks appear here automatically as they enter the universe.
      </div>
    );
  }

  const sidebarItems = [
    { key: "all", label: "All exchanges", count: rows.length },
    ...exchanges.map((e) => ({ key: e, label: e, count: exchangeCounts.get(e) ?? 0 })),
  ];
  const returnTabs: { key: ReturnFilter; label: string }[] = [
    { key: "all", label: "All" },
    { key: "positive", label: "Positive" },
    { key: "negative", label: "Negative" },
  ];

  return (
    <div className="flex flex-col gap-4 lg:flex-row">
      <aside className="lg:w-56 lg:shrink-0">
        <div className="mb-2 hidden text-xs uppercase tracking-wide text-slate-400 lg:block">Exchange</div>
        <div className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1 lg:mx-0 lg:flex-col lg:gap-1 lg:overflow-visible lg:px-0 lg:pb-0 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
          {sidebarItems.map((item) => (
            <button
              key={item.key}
              onClick={() => setExchange(item.key)}
              className={`flex shrink-0 items-center gap-2 whitespace-nowrap rounded-md px-3 py-2 text-left text-sm transition-colors lg:w-full lg:justify-between lg:shrink ${
                exchange === item.key ? "bg-navy-700 text-white" : "bg-navy-900/60 text-slate-300 hover:bg-navy-800 lg:bg-transparent"
              }`}
            >
              <span>{item.label}</span>
              <span className={`text-xs ${exchange === item.key ? "text-slate-300" : "text-slate-500"}`}>{item.count}</span>
            </button>
          ))}
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
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3 text-sm">
            <span className="text-slate-400">
              {filtered.length.toLocaleString("en-IN")} of {exchangeFiltered.length.toLocaleString("en-IN")}
            </span>
            <span className="rounded-md bg-navy-800 px-2 py-1 text-xs text-slate-300">
              <span className="font-semibold text-emerald-300">{(positivePct * 100).toFixed(1)}%</span> positive
            </span>
          </div>
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1 md:hidden">
              <select
                value={sortKey}
                onChange={(e) => setSortKey(e.target.value as SortKey)}
                className="rounded-md border border-navy-700/60 bg-navy-900 px-2 py-1 text-xs text-slate-200"
                aria-label="Sort by"
              >
                {SORT_OPTIONS.map((o) => (
                  <option key={o.key} value={o.key}>{o.label}</option>
                ))}
              </select>
              <button
                onClick={() => setSortDir((d) => (d === "asc" ? "desc" : "asc"))}
                className="rounded-md border border-navy-700/60 bg-navy-900 px-2 py-1 text-xs text-slate-300"
                aria-label="Toggle sort direction"
              >
                {sortDir === "asc" ? "▲" : "▼"}
              </button>
            </div>
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
          </div>
        </div>

        {/* Desktop table */}
        <div className="hidden overflow-x-auto rounded-xl border border-navy-700/60 bg-navy-900/40 md:block">
          <table className="w-full min-w-[860px] text-sm">
            <thead>
              <tr className="bg-navy-900/70 text-left text-xs uppercase tracking-wide text-slate-400">
                {COLUMNS.map((c) => {
                  const active = Boolean(c.sortable) && c.key === sortKey;
                  return (
                    <th
                      key={c.key}
                      onClick={c.sortable ? () => toggleSort(c.key as SortKey) : undefined}
                      className={`whitespace-nowrap px-3 py-2 font-medium ${c.align === "right" ? "text-right" : ""} ${
                        c.sortable ? "cursor-pointer select-none hover:text-slate-200" : ""
                      }`}
                    >
                      <span className={`inline-flex items-center gap-1 ${c.align === "right" ? "flex-row-reverse" : ""}`}>
                        {c.label}
                        {active ? <span className="text-slate-500">{sortDir === "asc" ? "▲" : "▼"}</span> : null}
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
                  <td className="whitespace-nowrap px-3 py-2 text-slate-300">{r.exchange}</td>
                  <td className="whitespace-nowrap px-3 py-2 text-slate-300">{dateStr(r.firstSeen)}</td>
                  <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums text-slate-200">{money(r.entryClose)}</td>
                  <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums text-slate-200">{money(r.currentClose)}</td>
                  <td className="whitespace-nowrap px-3 py-2 text-right"><ReturnCell value={r.returnPct} /></td>
                  <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums text-slate-300">{r.bars}</td>
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
                <ReturnCell value={r.returnPct} />
              </div>
              <div className="mt-1 truncate text-xs text-slate-500">{r.name}</div>
              <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
                <span className="text-slate-500">Exch <span className="text-slate-300">{r.exchange}</span></span>
                <span className="text-slate-500">Listed <span className="text-slate-300">{dateStr(r.firstSeen)}</span></span>
                <span className="text-slate-500">Entry <span className="text-slate-300">{money(r.entryClose)}</span></span>
                <span className="text-slate-500">Now <span className="text-slate-300">{money(r.currentClose)}</span></span>
                <span className="text-slate-500">Days <span className="text-slate-300">{r.bars}</span></span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
