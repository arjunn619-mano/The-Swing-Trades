import { Badge, Card } from "@/components/ui";
import type { Storage } from "@/lib/queries";

// Storage gauge for the Neon Postgres DB, vs the Free plan's 0.5 GB cap.
// Server component — uses native <details> so it needs no client JS.
export function StorageStatus({ storage }: { storage: Storage }) {
  if (!storage.ok) {
    return (
      <Card className="bg-navy-900/40">
        <div className="flex items-center justify-between gap-2">
          <div className="text-sm font-medium text-slate-200">Data size (logical)</div>
          <Badge tone="slate">no reading</Badge>
        </div>
        <p className="mt-1 text-xs text-slate-500">
          Couldn&apos;t read storage right now — showing nothing rather than a misleading 0%.
        </p>
      </Card>
    );
  }

  const { usedBytes, usedPretty, capBytes, tables } = storage;
  const pct = capBytes ? usedBytes / capBytes : 0;
  const pctText = (pct * 100).toFixed(pct < 0.1 ? 1 : 0);
  const level = pct >= 0.9 ? "red" : pct >= 0.7 ? "amber" : "green";
  const barColor = level === "red" ? "bg-rose-500" : level === "amber" ? "bg-amber-400" : "bg-emerald-500";
  const pill =
    level === "red"
      ? { tone: "red" as const, label: "Near cap" }
      : level === "amber"
        ? { tone: "amber" as const, label: "Getting full" }
        : { tone: "green" as const, label: "Healthy" };

  return (
    <Card className="space-y-2 bg-navy-900/40">
      <div className="flex items-center justify-between gap-2">
        <div className="text-sm font-medium text-slate-200">Data size (logical)</div>
        <Badge tone={pill.tone}>{pill.label}</Badge>
      </div>

      <div className="h-2.5 w-full overflow-hidden rounded-full bg-navy-700">
        <div className={`h-full rounded-full ${barColor}`} style={{ width: `${Math.min(100, Math.max(pct * 100, 2))}%` }} />
      </div>

      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5 text-xs">
        <span className="text-slate-300">
          <span className="font-semibold text-slate-100">{usedPretty}</span> / 0.5 GB
        </span>
        <span className="tabular-nums text-slate-400">{pctText}% of Neon Free (0.5 GB / project)</span>
      </div>

      <p className="text-xs text-slate-500">
        Logical data size (Neon&apos;s “Data size”) — the figure counted against the Free plan&apos;s 0.5 GB limit. It excludes
        retained history/WAL and branch deltas, so the actual billed storage can be higher; the exact number is in the{" "}
        <a href="https://console.neon.tech/" target="_blank" rel="noopener noreferrer" className="text-sky-400 hover:text-sky-300">
          Neon Console
        </a>
        .
      </p>

      <details className="pt-1">
        <summary className="cursor-pointer select-none text-xs font-medium uppercase tracking-wide text-slate-400 hover:text-slate-200">
          Per-table breakdown
        </summary>
        <div className="mt-2 overflow-x-auto rounded-lg border border-navy-700/60">
          <table className="w-full min-w-[460px] text-xs">
            <thead>
              <tr className="bg-navy-900/70 text-left uppercase tracking-wide text-slate-500">
                <th className="px-3 py-1.5 font-medium">Table</th>
                <th className="px-3 py-1.5 font-medium">Size</th>
                <th className="px-3 py-1.5 text-right font-medium">Heap / Idx</th>
                <th className="px-3 py-1.5 text-right font-medium">Est. rows</th>
              </tr>
            </thead>
            <tbody>
              {tables.map((t) => {
                const share = usedBytes ? t.totalBytes / usedBytes : 0;
                return (
                  <tr key={t.name} className="border-t border-navy-700/40">
                    <td className="px-3 py-1.5 font-medium text-slate-200">{t.name}</td>
                    <td className="px-3 py-1.5">
                      <div className="flex items-center gap-2">
                        <span className="tabular-nums text-slate-300">{t.totalPretty}</span>
                        <span className="hidden h-1.5 w-16 overflow-hidden rounded-full bg-navy-700 sm:block">
                          <span
                            className="block h-full rounded-full bg-sky-500/70"
                            style={{ width: `${Math.min(100, Math.max(share * 100, 1))}%` }}
                          />
                        </span>
                      </div>
                    </td>
                    <td className="px-3 py-1.5 text-right tabular-nums text-slate-500">
                      {t.heapPretty} / {t.indexesPretty}
                    </td>
                    <td className="px-3 py-1.5 text-right tabular-nums text-slate-400">
                      {t.rows === null ? "—" : t.rows.toLocaleString("en-IN")}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="mt-1.5 text-[11px] leading-relaxed text-slate-600">
          Row counts are estimates from table stats and lag bulk inserts/deletes. The top {tables.length} tables sum to less
          than the total data size — the rest is smaller tables, indexes, catalogs, and not-yet-vacuumed free space.
        </p>
      </details>
    </Card>
  );
}
