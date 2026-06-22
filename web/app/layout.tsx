import type { Metadata, Viewport } from "next";
import "./globals.css";
import { Disclaimer } from "@/components/ui";
import { Nav } from "@/components/Nav";
import { getOverview } from "@/lib/queries";

// Keep the nav freshness chip on the same ISR cadence as the pages.
export const revalidate = 300;

export const metadata: Metadata = {
  title: "The Swing Trades",
  description:
    "End-of-day NSE/BSE swing screener — tracks qualifying stocks for 100 trading days and measures strategy edge vs. the market.",
  manifest: "/manifest.json",
  applicationName: "The Swing Trades",
  appleWebApp: { capable: true, title: "Swing Trades", statusBarStyle: "black-translucent" },
};

export const viewport: Viewport = {
  themeColor: "#0a0f1f",
  width: "device-width",
  initialScale: 1,
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const overview = await getOverview();
  return (
    <html lang="en">
      <body className="min-h-screen">
        <Nav lastScanDate={overview.lastScanDate} lastScanStatus={overview.lastScanStatus} />
        <main className="mx-auto max-w-[1800px] px-4 pb-24 pt-6 sm:px-6 md:pb-6">{children}</main>
        <Disclaimer />
      </body>
    </html>
  );
}
