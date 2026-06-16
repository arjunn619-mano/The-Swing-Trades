import { OptionsView } from "@/components/OptionsView";
import { SectionHeading } from "@/components/ui";
import { getOptionTracker } from "@/lib/queries";

export const revalidate = 300;

export default async function OptionsPage() {
  const rows = await getOptionTracker();

  return (
    <div className="space-y-4">
      <SectionHeading
        title="Options"
        subtitle="Stock & index option contracts tracked from the first day their volume cleared 1 lakh. Entry is that day's premium and never changes; Return is the % change in the premium since. Tracked to expiry, then removed (the full daily snapshot lives in the Parquet archive)."
      />
      <OptionsView rows={rows} />
    </div>
  );
}
