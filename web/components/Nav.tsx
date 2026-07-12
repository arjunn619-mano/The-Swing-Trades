"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import { dateStr } from "@/lib/format";

const LINKS = [
  { href: "/", label: "Overview", short: "Home", icon: "home" },
  { href: "/tracker", label: "Tracker", short: "Tracker", icon: "tracker" },
  { href: "/options", label: "Options", short: "Options", icon: "options" },
  { href: "/new-listings", label: "New Listings", short: "New", icon: "new" },
  { href: "/strategies", label: "Strategies", short: "Strats", icon: "strategies" },
  { href: "/starred", label: "Starred", short: "Starred", icon: "starred" },
];

function isActive(pathname: string, href: string) {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(href + "/");
}

function Icon({ name, className = "h-5 w-5" }: { name: string; className?: string }) {
  const p = {
    className,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round",
    strokeLinejoin: "round",
  } as React.SVGProps<SVGSVGElement>;
  switch (name) {
    case "home":
      return (
        <svg {...p}>
          <path d="M3 10.5 12 3l9 7.5" />
          <path d="M5 9.5V21h14V9.5" />
        </svg>
      );
    case "tracker":
      return (
        <svg {...p}>
          <path d="M4 7h16M4 12h16M4 17h16" />
        </svg>
      );
    case "options":
      return (
        <svg {...p}>
          <path d="M12 4l8 16H4z" />
        </svg>
      );
    case "new":
      return (
        <svg {...p}>
          <path d="M12 5v14M5 12h14" />
        </svg>
      );
    case "strategies":
      return (
        <svg {...p}>
          <circle cx="12" cy="12" r="8" />
          <circle cx="12" cy="12" r="3" />
        </svg>
      );
    case "starred":
      return (
        <svg {...p}>
          <path d="M12 4l2.6 5.3 5.8.8-4.2 4.1 1 5.8L12 17.8 6.9 20l1-5.8-4.2-4.1 5.8-.8z" />
        </svg>
      );
    default:
      return null;
  }
}

function FreshnessChip({ date, status }: { date: string | null; status: string | null }) {
  const ok = status === "success";
  const dot = status == null ? "bg-slate-500" : ok ? "bg-emerald-400" : "bg-amber-400";
  const title = date
    ? `Last successful scan: ${dateStr(date)}${status ? ` (${status})` : ""}`
    : "No scans recorded yet";
  return (
    <span
      title={title}
      className="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-navy-700/60 bg-navy-900/60 px-2 py-1 text-xs"
    >
      <span className={`h-2 w-2 shrink-0 rounded-full ${dot}`} />
      <span className="hidden text-slate-500 sm:inline">as of</span>
      <span className="tabular-nums text-slate-200">{date ? dateStr(date) : "no scans"}</span>
    </span>
  );
}

function RefreshButton() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  async function refresh() {
    if (busy) return;
    setBusy(true);
    try {
      await fetch("/api/revalidate", { method: "POST" }); // bust the ISR cache, then re-render
    } catch {
      /* refresh is best-effort — a failed revalidate still falls back to router.refresh() */
    }
    router.refresh();
    setTimeout(() => setBusy(false), 600); // brief spin so the tap always feels responsive
  }
  return (
    <button
      type="button"
      onClick={refresh}
      disabled={busy}
      title="Refresh — pull the latest scanned data"
      aria-label="Refresh data"
      className="inline-flex shrink-0 items-center justify-center rounded-md border border-navy-700/60 bg-navy-900/60 p-1.5 text-slate-300 transition-colors hover:bg-navy-800 hover:text-white disabled:opacity-60"
    >
      <svg
        className={`h-4 w-4 ${busy ? "animate-spin" : ""}`}
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={1.8}
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M21 12a9 9 0 1 1-2.64-6.36" />
        <path d="M21 3v6h-6" />
      </svg>
    </button>
  );
}

export function Nav({
  lastScanDate,
  lastScanStatus,
}: {
  lastScanDate: string | null;
  lastScanStatus: string | null;
}) {
  const pathname = usePathname();
  return (
    <>
      {/* Top bar — brand + (desktop) links + freshness chip (all screens) */}
      <header className="sticky top-0 z-20 border-b border-navy-700/60 bg-navy-950/80 backdrop-blur">
        <div className="mx-auto flex max-w-[1800px] items-center justify-between gap-3 px-4 py-3 sm:px-6">
          <Link href="/" className="shrink-0">
            <span className="text-base font-semibold text-slate-100">The Swing Trades</span>
          </Link>
          <div className="flex min-w-0 items-center gap-2">
            <nav className="hidden min-w-0 gap-1 overflow-x-auto text-sm md:flex [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
              {LINKS.map((l) => {
                const active = isActive(pathname, l.href);
                return (
                  <Link
                    key={l.href}
                    href={l.href}
                    aria-current={active ? "page" : undefined}
                    className={`whitespace-nowrap rounded-md px-2.5 py-1 transition-colors ${
                      active ? "bg-navy-700 text-white" : "text-slate-300 hover:bg-navy-800 hover:text-white"
                    }`}
                  >
                    {l.label}
                  </Link>
                );
              })}
            </nav>
            <FreshnessChip date={lastScanDate} status={lastScanStatus} />
            <RefreshButton />
          </div>
        </div>
      </header>

      {/* Mobile bottom tab bar — every destination one thumb-tap away */}
      <nav className="fixed inset-x-0 bottom-0 z-30 border-t border-navy-700/60 bg-navy-950/95 backdrop-blur md:hidden">
        <div className="mx-auto grid max-w-[1800px] grid-cols-6">
          {LINKS.map((l) => {
            const active = isActive(pathname, l.href);
            return (
              <Link
                key={l.href}
                href={l.href}
                aria-current={active ? "page" : undefined}
                className={`flex flex-col items-center gap-0.5 py-2 text-[10px] transition-colors ${
                  active ? "text-sky-300" : "text-slate-400 hover:text-slate-200"
                }`}
              >
                <Icon name={l.icon} className={`h-5 w-5 ${active ? "" : "opacity-80"}`} />
                <span className="leading-none">{l.short}</span>
              </Link>
            );
          })}
        </div>
      </nav>
    </>
  );
}
