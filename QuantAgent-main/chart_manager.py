"""chart_manager

Minimal chart storage helper.

Charts are stored under:
  output/charts/{pattern,trend}/

Naming convention:
  {symbol}_{timeframe}_{start_date}_{end_date}_{horizon}_{agent}_{timestamp}.png

This module intentionally has no extra features (no cleanup, no indexing).
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Literal

from freshness_config import parse_iso_datetime


AgentType = Literal["pattern", "trend"]


def ensure_chart_dirs() -> None:
    os.makedirs(os.path.join("output", "charts", "pattern"), exist_ok=True)
    os.makedirs(os.path.join("output", "charts", "trend"), exist_ok=True)


def make_chart_path(
    *,
    symbol: str,
    timeframe: str,
    start_datetime: str,
    end_datetime: str,
    horizon: str,
    agent: AgentType,
    timestamp: str | None = None,
) -> str:
    ensure_chart_dirs()

    start_dt = parse_iso_datetime(start_datetime)
    end_dt = parse_iso_datetime(end_datetime)
    start_date = start_dt.strftime("%Y%m%d")
    end_date = end_dt.strftime("%Y%m%d")

    ts = timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{symbol}_{timeframe}_{start_date}_{end_date}_{horizon}_{agent}_{ts}.png"
    return os.path.join("output", "charts", agent, filename)
