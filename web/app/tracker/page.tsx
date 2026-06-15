import { TrackerView } from "@/components/TrackerView";
import { SectionHeading } from "@/components/ui";
import { getStarredIds, getTrackerEntries } from "@/lib/queries";

export const revalidate = 300;

export default async function TrackerPage() {
  const [rows, starredIds] = await Promise.all([getTrackerEntries(), getStarredIds()]);

  return (
    <div className="space-y-4">
      <SectionHeading
        title="Tracker"
        subtitle="Every (stock × strategy) entry, observed for 100 trading days from its first-seen date. Entry price is the first-seen close and never changes; Return is the % change from entry close to current close."
      />
      <TrackerView rows={rows} starredIds={starredIds} />
    </div>
  );
}
