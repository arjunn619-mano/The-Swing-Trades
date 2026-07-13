import { NewListingsView } from "@/components/NewListingsView";
import { SectionHeading } from "@/components/ui";
import { getNewListings, getStarredIds } from "@/lib/queries";

export const revalidate = 300;

export default async function NewListingsPage() {
  const [rows, starredIds] = await Promise.all([getNewListings(), getStarredIds()]);

  return (
    <div className="space-y-4">
      <SectionHeading
        title="New Listings (IPOs)"
        subtitle="A permanent record of every mainboard stock listed since tracking began, newest first — entries stay here for good (they no longer age out after a few weeks). Entry close is the first available close; Return is the growth since listing."
      />
      <NewListingsView rows={rows} starredIds={starredIds} />
    </div>
  );
}
