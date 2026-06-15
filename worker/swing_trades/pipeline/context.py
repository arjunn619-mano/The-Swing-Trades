"""The context handed to each strategy's evaluate()."""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import List

from .features import InstrumentFeatures


@dataclass
class ScanContext:
    trade_date: _dt.date
    features: List[InstrumentFeatures] = field(default_factory=list)
