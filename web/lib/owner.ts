// Client-side "owner mode". The dashboard is a public, login-less page; this PIN is the owner's
// lightweight proof-of-self for the only write action (editing the watchlist stars). The owner types
// it once; it's kept in this browser's localStorage and sent to /api/star over HTTPS, where it's
// checked against OWNER_PIN. It is NOT a credential for anything sensitive — it only gates cosmetic
// star toggles — so losing it means, at most, someone could flip stars.
const KEY = "owner_pin";

export function getOwnerPin(): string | null {
  try {
    return localStorage.getItem(KEY);
  } catch {
    return null; // storage blocked (private window, etc.)
  }
}

export function setOwnerPin(pin: string | null): void {
  try {
    if (pin) localStorage.setItem(KEY, pin);
    else localStorage.removeItem(KEY);
  } catch {
    /* storage unavailable — the PIN simply won't be remembered */
  }
}

// Return the stored PIN, prompting once if we don't have one yet. null = cancelled / not the owner.
export function ensureOwnerPin(): string | null {
  const existing = getOwnerPin();
  if (existing) return existing;
  if (typeof window === "undefined") return null;
  const entered = window.prompt("Enter the owner PIN to edit your watchlist (remembered on this device only):");
  const pin = entered?.trim() || null;
  if (pin) setOwnerPin(pin);
  return pin;
}
