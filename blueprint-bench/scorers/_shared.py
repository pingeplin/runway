"""Helpers shared across scorers."""
from __future__ import annotations

from pathlib import Path


def discover_sources(wt: Path) -> list[Path]:
    """Agent's SUT: every .py under wt/src/ (starter-project convention)."""
    src = wt / "src"
    if not src.is_dir():
        return []
    return sorted(p for p in src.rglob("*.py") if "__pycache__" not in p.parts)
