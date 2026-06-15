import type { Metadata, Viewport } from "next";
import "./globals.css";
import { Disclaimer, Nav } from "@/components/ui";

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

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <Nav />
        <main className="mx-auto max-w-[1800px] px-4 py-6 sm:px-6">{children}</main>
        <Disclaimer />
      </body>
    </html>
  );
}
