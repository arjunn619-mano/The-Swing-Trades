import { Badge, DataTable, ReturnBadge, SectionHeading } from "@/components/ui";
import { dateStr, money } from "@/lib/format";
import { getTrackerEntries, type TrackerRow } from "@/lib/queries";

export const revalidate = 3600;

export default async function TrackerPage() {
  const rows = await getTrackerEntries();

  return (
    <div className="space-y-4">
      <SectionHeading
        title="Tracker"
        subtitle="Every (stock × strategy) entry, observed for 100 trading days from its first-seen date. Entry price is the first-seen close and never changes."
      />
      <DataTable<TrackerRow>
        rows={rows}
        empty="No tracked stocks yet. Entries appear after the first scan finds qualifying stocks."
        columns={[
          { key: "sym", label: "Symbol", render: (r) => <span className="font-semibold text-slate-100">{r.symbol}</span> },
          { key: "name", label: "Name", render: (r) => <span className="text-slate-400">{r.name}</span> },
          { key: "strat", label: "Strategy", render: (r) => <span className="text-slate-300">{r.strategy}</span> },
          { key: "first", label: "First seen", render: (r) => <span className="text-slate-300">{dateStr(r.firstSeenDate)}</span> },
          { key: "entry", label: "Entry close", align: "right", render: (r) => <span className="text-slate-200">{money(r.entryClose)}</span> },
          { key: "dayn", label: "Day", align: "right", render: (r) => <span className="text-slate-300">{r.dayN ?? "—"}/100</span> },
          { key: "ret", label: "Return", align: "right", render: (r) => <ReturnBadge value={r.latestReturn} /> },
          { key: "app", label: "Appears", align: "right", render: (r) => <span className="text-slate-300">{r.appearanceCount}×</span> },
          { key: "status", label: "Status", render: (r) => <Badge tone={r.status === "completed" ? "blue" : "green"}>{r.status}</Badge> },
        ]}
      />
    </div>
  );
}
