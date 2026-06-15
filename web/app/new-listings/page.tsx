import { NewListingsView } from "@/components/NewListingsView";
import { SectionHeading } from "@/components/ui";
import { getNewListings, getStarredIds } from "@/lib/queries";

export const revalidate = 300;

export default async function NewListingsPage() {
  const [rows, starredIds] = await Promise.all([getNewListings(), getStarredIds()]);

  return (
    <div className="space-y-4">
      <SectionHeading
        title="New Listings"
        subtitle="Recently-listed stocks with under ~9 weeks of price history, tracked separately. Entry close is the first available close; Return is the change since listing. They graduate into signals once they have ~15+ days of history."
      />
      <NewListingsView rows={rows} starredIds={starredIds} />
    </div>
  );
}
