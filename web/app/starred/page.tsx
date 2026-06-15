import { StarButton } from "@/components/StarButton";
import { EmptyState, SectionHeading } from "@/components/ui";
import { money } from "@/lib/format";
import { getStarred } from "@/lib/queries";

export const dynamic = "force-dynamic"; // always reflect the current starred set

export default async function StarredPage() {
  const rows = await getStarred();

  return (
    <div className="space-y-4">
      <SectionHeading
        title="Starred"
        subtitle="Your saved stocks, synced across your devices. Tap the star on any stock in the Tracker or New Listings to add or remove it here."
      />
      {rows.length === 0 ? (
        <EmptyState>No starred stocks yet — tap the ☆ next to any stock to save it here.</EmptyState>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-navy-700/60 bg-navy-900/40">
          <table className="w-full min-w-[560px] text-sm">
            <thead>
              <tr className="bg-navy-900/70 text-left text-xs uppercase tracking-wide text-slate-400">
                <th className="px-3 py-2" />
                <th className="px-3 py-2 font-medium">Symbol</th>
                <th className="px-3 py-2 font-medium">Name</th>
                <th className="px-3 py-2 font-medium">Exch</th>
                <th className="px-3 py-2 text-right font-medium">Last close</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.instrumentId} className="border-t border-navy-700/40 hover:bg-navy-800/40">
                  <td className="px-3 py-2">
                    <StarButton instrumentId={r.instrumentId} initialStarred />
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 font-semibold text-slate-100">{r.symbol}</td>
                  <td className="whitespace-nowrap px-3 py-2 text-slate-400">{r.name}</td>
                  <td className="whitespace-nowrap px-3 py-2 text-slate-300">{r.exchange}</td>
                  <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums text-slate-200">{money(r.lastClose)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
