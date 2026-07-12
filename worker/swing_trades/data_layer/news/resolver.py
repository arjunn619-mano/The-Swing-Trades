"""Deterministic resolver: map a news item's identity (ISIN, BSE scrip code, or free-text
company name) to EXACTLY ONE Dhan instrument, or REJECT.

Why reject-if-ambiguous: a wrong ticker permanently poisons a 100-trading-day tracker window,
while a miss only costs one observation. So when in doubt, drop it.

No LLM ever emits a ticker — the LLM returns only a company NAME, resolved here against the Dhan
instrument master (a gazetteer). ISIN and BSE scrip resolve EXACTLY; names resolve by
normalized-exact match first, then rapidfuzz token_set_ratio with BOTH a confidence floor and a
clear margin over the best DIFFERENT-company runner-up.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Optional

from rapidfuzz import fuzz, process

from ..models import UniverseInstrument

# Name-match gates. High floor + margin-over-a-different-company keeps false resolutions rare.
FUZZY_MIN_SCORE = 92.0
FUZZY_MIN_MARGIN = 5.0

# Trailing legal-form tokens stripped during normalization (leading "THE" is also dropped).
# Deliberately conservative — words like INDUSTRIES / SUGARS / CEMENTS distinguish real companies
# and are kept.
_SUFFIX_TOKENS = frozenset({"LTD", "LIMITED", "PVT", "PRIVATE", "CORPORATION"})


def normalize_name(name: Optional[str]) -> str:
    """Uppercase, strip punctuation to spaces, drop a leading 'THE' and trailing legal-form tokens."""
    s = re.sub(r"[^A-Z0-9 ]", " ", (name or "").upper())
    toks = s.split()
    if toks and toks[0] == "THE":
        toks = toks[1:]
    while toks and toks[-1] in _SUFFIX_TOKENS:
        toks.pop()
    return " ".join(toks)


@dataclass(frozen=True)
class ResolveResult:
    instrument: Optional[UniverseInstrument]
    method: str            # isin | bse_scrip | name_exact | name_fuzzy | reject
    score: float           # 100.0 for exact matches; token_set_ratio for fuzzy; 0.0 for reject
    reason: str = ""

    @property
    def ok(self) -> bool:
        return self.instrument is not None


class InstrumentResolver:
    """Built once from the resolvable universe (list of UniverseInstrument). Pure + deterministic."""

    def __init__(self, universe: Iterable[UniverseInstrument]):
        self._by_isin: dict[str, UniverseInstrument] = {}
        self._by_scrip: dict[str, UniverseInstrument] = {}
        self._norm_to_isins: dict[str, set[str]] = {}
        for u in universe:
            if not u.isin:
                continue
            isin = u.isin.strip().upper()
            self._by_isin.setdefault(isin, u)
            # BSE scrip: the explicit bse_scrip_code, plus security_id when the chosen listing IS BSE.
            for scrip in (u.bse_scrip_code, u.security_id if u.exchange_pref == "BSE" else None):
                if scrip:
                    self._by_scrip.setdefault(str(scrip).strip(), u)
            for nm in (u.symbol_name, u.nse_symbol):
                norm = normalize_name(nm)
                if norm:
                    self._norm_to_isins.setdefault(norm, set()).add(isin)
        self._norm_choices = list(self._norm_to_isins.keys())

    def resolve(
        self,
        *,
        isin: Optional[str] = None,
        bse_scrip: Optional[str] = None,
        name: Optional[str] = None,
    ) -> ResolveResult:
        if isin:
            u = self._by_isin.get(isin.strip().upper())
            if u:
                return ResolveResult(u, "isin", 100.0)
        if bse_scrip:
            u = self._by_scrip.get(str(bse_scrip).strip())
            if u:
                return ResolveResult(u, "bse_scrip", 100.0)
        if name:
            return self._resolve_name(name)
        return ResolveResult(None, "reject", 0.0, "no isin/scrip/name provided")

    def _resolve_name(self, name: str) -> ResolveResult:
        norm = normalize_name(name)
        if not norm:
            return ResolveResult(None, "reject", 0.0, "empty normalized name")

        # Exact normalized match — accept only if it points to a single ISIN.
        exact = self._norm_to_isins.get(norm)
        if exact:
            if len(exact) == 1:
                return ResolveResult(self._by_isin[next(iter(exact))], "name_exact", 100.0)
            return ResolveResult(None, "reject", 100.0, f"ambiguous exact name -> {len(exact)} ISINs")

        if not self._norm_choices:
            return ResolveResult(None, "reject", 0.0, "empty gazetteer")

        matches = process.extract(norm, self._norm_choices, scorer=fuzz.token_set_ratio, limit=5)
        if not matches:
            return ResolveResult(None, "reject", 0.0, "no fuzzy candidate")

        best_name, best_score, _ = matches[0]
        if best_score < FUZZY_MIN_SCORE:
            return ResolveResult(None, "reject", best_score, f"below floor {best_score:.0f}<{FUZZY_MIN_SCORE:.0f}")

        best_isins = self._norm_to_isins[best_name]
        if len(best_isins) != 1:
            return ResolveResult(None, "reject", best_score, f"best name -> {len(best_isins)} ISINs")
        best_isin = next(iter(best_isins))

        # Margin must be over the best DIFFERENT-company runner-up — same-ISIN name variants
        # (e.g. ticker vs long name) must not manufacture a false "ambiguous" reject.
        runner_score = 0.0
        for nm, sc, _ in matches[1:]:
            if best_isin not in self._norm_to_isins[nm]:
                runner_score = sc
                break
        if best_score - runner_score < FUZZY_MIN_MARGIN:
            return ResolveResult(None, "reject", best_score, f"ambiguous vs different co (margin {best_score - runner_score:.0f})")

        return ResolveResult(self._by_isin[best_isin], "name_fuzzy", best_score)
