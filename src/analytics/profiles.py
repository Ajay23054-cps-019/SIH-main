"""Behavioral profile data structures.

A profile is a flat, JSON-serializable metric dictionary for one CSE in one
period (a quarter, or the full submission window). Flat namespaced keys keep
downstream consumers simple: ``inv_depth_mean``, ``esc_rate``, ...
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

import pandas as pd

PERIOD_ALL = "ALL"


@dataclass
class BehavioralProfile:
    cse_id: str
    period: str  # "2024-Q1" ... or PERIOD_ALL
    metrics: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    n_alerts: int = 0

    @property
    def scalar_metrics(self) -> Dict[str, float]:
        """Only numeric/scalar metrics (nested distributions excluded)."""
        return {
            k: v for k, v in self.metrics.items()
            if isinstance(v, (int, float)) and not isinstance(v, bool)
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cse_id": self.cse_id,
            "period": self.period,
            "n_alerts": self.n_alerts,
            "metrics": self.metrics,
            "warnings": self.warnings,
        }


def quarter_label(ts) -> str:
    """Timestamp -> '2024-Q1'."""
    p = pd.Timestamp(ts).to_period("Q")
    return f"{p.year}-Q{p.quarter}"
