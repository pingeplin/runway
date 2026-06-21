"""Tests for the per-family default model resolution in ``analysis/assemble.py``.

``assemble.py`` lives under ``analysis/`` (a script, not part of the installed
package), so we load it by path. Only the pure ``_resolve_model`` helper is
exercised — no run cells, no extractor, no network.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_ASSEMBLE = Path(__file__).resolve().parents[1] / "analysis" / "assemble.py"


def _load_assemble():
    spec = importlib.util.spec_from_file_location("assemble_under_test", _ASSEMBLE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_default_models_are_the_two_pinned_families():
    asm = _load_assemble()
    # The two cross-family extractors the design pins (fix #1, >=2 families).
    assert asm._resolve_model("anthropic", "") == "claude-sonnet-4-6"
    assert asm._resolve_model("openai", "") == "gpt-5.4"


def test_explicit_model_overrides_the_default():
    asm = _load_assemble()
    assert asm._resolve_model("openai", "gpt-4o-mini") == "gpt-4o-mini"
    assert asm._resolve_model("anthropic", "claude-haiku-4-5") == "claude-haiku-4-5"
