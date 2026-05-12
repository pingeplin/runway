import importlib.util
from pathlib import Path


def test_module_importable():
    # Sanity check only — the public API isn't built yet.
    spec = importlib.util.find_spec("normalizer")
    assert spec is not None


def test_pipeline_modules_exist():
    # Confirms the agent didn't delete the conventional layout.
    pkg = Path(__file__).resolve().parent.parent / "src" / "normalizer"
    assert (pkg / "reader.py").exists()
    assert (pkg / "columns.py").exists()
    assert (pkg / "writer.py").exists()
