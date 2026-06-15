"use client";

import { useState } from "react";

export function StarButton({ instrumentId, initialStarred }: { instrumentId: number; initialStarred: boolean }) {
  const [starred, setStarred] = useState(initialStarred);
  const [busy, setBusy] = useState(false);

  async function toggle() {
    const next = !starred;
    setStarred(next);
    setBusy(true);
    try {
      const res = await fetch("/api/star", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ instrumentId, starred: next }),
      });
      if (!res.ok) setStarred(!next); // revert on failure
    } catch {
      setStarred(!next);
    } finally {
      setBusy(false);
    }
  }

  return (
    <button
      type="button"
      onClick={toggle}
      disabled={busy}
      aria-label={starred ? "Remove star" : "Add star"}
      title={starred ? "Starred" : "Star this stock"}
      className={`text-lg leading-none transition-colors disabled:opacity-50 ${
        starred ? "text-amber-300 hover:text-amber-200" : "text-slate-600 hover:text-slate-300"
      }`}
    >
      {starred ? "★" : "☆"}
    </button>
  );
}
