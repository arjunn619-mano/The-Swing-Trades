"use client";

import { useMemo, useState } from "react";
import { StarButton } from "@/components/StarButton";
import { ChartLink } from "@/components/ui";
import { dateStr, money, pct } from "@/lib/format";
import type { TrackerRow } from "@/lib/queries";

type SortKey = "symbol" | "firstSeenDate" | "entryClose" | "currentClose" | "dayN" | "latestReturn" | "appearanceCount";
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
  { key: "appearanceCount", label: "Appears", align: "right", sortable: true },
  { key: "chart", label: "Chart", align: "right" },
];

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

export function TrackerView({ rows, starredIds }: { rows: TrackerRow[]; starredIds: number[] }) {
  const [strategy, setStrategy] = useState<string>("all");
  const [returnFilter, setReturnFilter] = useState<ReturnFilter>("all");
  const [sortKey, setSortKey] = useState<SortKey>("firstSeenDate");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const starred = useMemo(() => new Set(starredIds), [starredIds]);

  const strategyCounts = useMemo(() => {
    const m = new Map<string, number>();
    for (const r of rows) m.set(r.strategy, (m.get(r.strategy) ?? 0) + 1);
    return m;
  }, [rows]);
  const strategies = useMemo(() => Array.from(strategyCounts.keys()).sort(), [strategyCounts]);

  // Strategy-filtered set (the % positive metric reflects the strategy selection, not the return filter).
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
    return [...out].sort((a, b) => {
      const va = value(a, sortKey);
      const vb = value(b, sortKey);
      const c = typeof va === "string" && typeof vb === "string" ? va.localeCompare(vb) : (va as number) - (vb as number);
      return sortDir === "asc" ? c : -c;
    });
  }, [strategyFiltered, returnFilter, sortKey, sortDir]);

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
        No tracked stocks yet. Entries appear after the first scan finds qualifying stocks.
      </div>
    );
  }

  const sidebarItems = [
    { key: "all", label: "All strategies", count: rows.length },
    ...strategies.map((s) => ({ key: s, label: s, count: strategyCounts.get(s) ?? 0 })),
  ];
  const returnTabs: { key: ReturnFilter; label: string }[] = [
    { key: "all", label: "All" },
    { key: "positive", label: "Positive" },
    { key: "negative", label: "Negative" },
  ];

  return (
    <div className="flex flex-col gap-4 lg:flex-row">
      <aside className="lg:w-56 lg:shrink-0">
        <div className="mb-2 text-xs uppercase tracking-wide text-slate-400">Strategy</div>
        <div className="flex flex-col gap-1">
          {sidebarItems.map((item) => (
            <button
              key={item.key}
              onClick={() => setStrategy(item.key)}
              className={`flex items-center justify-between rounded-md px-3 py-2 text-left text-sm transition-colors ${
                strategy === item.key ? "bg-navy-700 text-white" : "text-slate-300 hover:bg-navy-800"
              }`}
            >
              <span>{item.label}</span>
              <span className={`text-xs ${strategy === item.key ? "text-slate-300" : "text-slate-500"}`}>{item.count}</span>
            </button>
          ))}
        </div>
      </aside>

      <div className="min-w-0 flex-1 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3 text-sm">
            <span className="text-slate-400">
              {filtered.length.toLocaleString("en-IN")} of {strategyFiltered.length.toLocaleString("en-IN")} entries
            </span>
            <span className="rounded-md bg-navy-800 px-2 py-1 text-xs text-slate-300">
              <span className="font-semibold text-emerald-300">{(positivePct * 100).toFixed(1)}%</span> positive
              <span className="text-slate-500"> ({positives}/{strategyFiltered.length})</span>
            </span>
          </div>
          <div className="flex gap-0.5 rounded-lg border border-navy-700/60 bg-navy-900/60 p-0.5">
            {returnTabs.map((t) => (
              <button
                key={t.key}
                onClick={() => setReturnFilter(t.key)}
                className={`rounded-md px-3 py-1 text-sm transition-colors ${
                  returnFilter === t.key ? "bg-navy-700 text-white" : "text-slate-400 hover:text-slate-200"
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>

        <div className="overflow-x-auto rounded-xl border border-navy-700/60 bg-navy-900/40">
          <table className="w-full min-w-[900px] text-sm">
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
                  <td className="whitespace-nowrap px-3 py-2 text-slate-300">{r.strategy}</td>
                  <td className="whitespace-nowrap px-3 py-2 text-slate-300">{dateStr(r.firstSeenDate)}</td>
                  <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums text-slate-200">{money(r.entryClose)}</td>
                  <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums text-slate-200">{money(r.currentClose)}</td>
                  <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums text-slate-300">{r.dayN ?? "—"}/100</td>
                  <td className="whitespace-nowrap px-3 py-2 text-right"><ReturnCell value={r.latestReturn} /></td>
                  <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums text-slate-300">{r.appearanceCount}×</td>
                  <td className="whitespace-nowrap px-3 py-2 text-right"><ChartLink exchange={r.exchange} ticker={r.symbol} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
