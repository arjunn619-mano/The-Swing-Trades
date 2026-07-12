"""News source adapters (BSE / NSE exchange feeds + narrative RSS) behind one seam, each
returning parsed RawNewsItem plus a typed SourceHealth so a silent break is detected + alerted,
never producing zero news silently."""
