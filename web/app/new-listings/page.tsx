import { Badge, DataTable, SectionHeading } from "@/components/ui";
import { dateStr, money } from "@/lib/format";
import { getNewListings, type NewListing } from "@/lib/queries";

export const revalidate = 3600;

export default async function NewListingsPage() {
  const rows = await getNewListings();

  return (
    <div className="space-y-4">
      <SectionHeading
        title="New Listings"
        subtitle="Recently-listed stocks with under ~9 weeks of price history. They're tracked separately because the indicators (RSI, Supertrend) need ~15+ days before they can generate signals."
      />
      <DataTable<NewListing>
        rows={rows}
        empty="No new listings right now. Newly-listed stocks appear here automatically as they enter the universe."
        columns={[
          { key: "sym", label: "Symbol", render: (r) => <span className="font-semibold text-slate-100">{r.symbol}</span> },
          { key: "name", label: "Name", render: (r) => <span className="text-slate-400">{r.name}</span> },
          { key: "exch", label: "Exch", render: (r) => <Badge tone="slate">{r.exchange}</Badge> },
          { key: "bars", label: "Days of data", align: "right", render: (r) => <span className="text-slate-200">{r.bars}</span> },
          { key: "first", label: "First bar", render: (r) => <span className="text-slate-300">{dateStr(r.firstBar)}</span> },
          { key: "last", label: "Last bar", render: (r) => <span className="text-slate-300">{dateStr(r.lastBar)}</span> },
          { key: "close", label: "Last close", align: "right", render: (r) => <span className="text-slate-200">{money(r.lastClose)}</span> },
        ]}
      />
    </div>
  );
}
