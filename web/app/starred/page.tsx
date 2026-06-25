import { StarButton } from "@/components/StarButton";
import { TrackerView } from "@/components/TrackerView";
import { ChartLink, EmptyState, SectionHeading } from "@/components/ui";
import { money } from "@/lib/format";
import { getStarred, getStarredTracker } from "@/lib/queries";

export const dynamic = "force-dynamic"; // always reflect the current starred set

export default async function StarredPage() {
  const [tracked, starred] = await Promise.all([getStarredTracker(), getStarred()]);
  const trackedIds = new Set(tracked.map((r) => r.instrumentId));
  const untracked = starred.filter((s) => !trackedIds.has(s.instrumentId));
  const starredIds = starred.map((s) => s.instrumentId);

  return (
    <div className="space-y-6">
      <SectionHeading
        title="Starred"
        subtitle="Your saved stocks, synced across your devices. Tap the star on any stock in the Tracker or New Listings to add or remove it here."
      />

      {starred.length === 0 ? (
        <EmptyState>No starred stocks yet — tap the ☆ next to any stock to save it here.</EmptyState>
      ) : (
        <div className="space-y-6">
          {/* Tracked starred stocks — identical layout to the Tracker page */}
          {tracked.length > 0 ? <TrackerView rows={tracked} starredIds={starredIds} /> : null}

          {/* Starred stocks with no tracker entry yet — kept so nothing silently disappears */}
          {untracked.length > 0 ? (
            <div className="space-y-2">
              <div className="text-xs font-medium uppercase tracking-wide text-slate-500">
                Starred · not tracked by any strategy yet
              </div>
              <div className="hidden overflow-x-auto rounded-xl border border-navy-700/60 bg-navy-900/40 md:block">
                <table className="w-full min-w-[480px] text-sm">
                  <thead>
                    <tr className="bg-navy-900/70 text-left text-xs uppercase tracking-wide text-slate-400">
                      <th className="px-3 py-2" />
                      <th className="px-3 py-2 font-medium">Symbol</th>
                      <th className="px-3 py-2 font-medium">Name</th>
                      <th className="px-3 py-2 font-medium">Exch</th>
                      <th className="px-3 py-2 text-right font-medium">Last close</th>
                      <th className="px-3 py-2 text-right font-medium">Chart</th>
                    </tr>
                  </thead>
                  <tbody>
                    {untracked.map((r) => (
                      <tr key={r.instrumentId} className="border-t border-navy-700/40 hover:bg-navy-800/40">
                        <td className="px-3 py-2"><StarButton instrumentId={r.instrumentId} initialStarred /></td>
                        <td className="whitespace-nowrap px-3 py-2 font-semibold text-slate-100">{r.symbol}</td>
                        <td className="whitespace-nowrap px-3 py-2 text-slate-400">{r.name}</td>
                        <td className="whitespace-nowrap px-3 py-2 text-slate-300">{r.exchange}</td>
                        <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums text-slate-200">{money(r.lastClose)}</td>
                        <td className="whitespace-nowrap px-3 py-2 text-right"><ChartLink exchange={r.exchange} ticker={r.symbol} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {/* Mobile cards */}
              <div className="space-y-2 md:hidden">
                {untracked.map((r) => (
                  <div key={r.instrumentId} className="flex items-center justify-between rounded-lg border border-navy-700/60 bg-navy-900/40 p-3">
                    <div className="flex min-w-0 items-center gap-2">
                      <StarButton instrumentId={r.instrumentId} initialStarred />
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="truncate font-semibold text-slate-100">{r.symbol}</span>
                          <ChartLink exchange={r.exchange} ticker={r.symbol} />
                        </div>
                        <div className="truncate text-xs text-slate-500">{r.name}</div>
                      </div>
                    </div>
                    <div className="text-right tabular-nums text-slate-200">{money(r.lastClose)}</div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}
