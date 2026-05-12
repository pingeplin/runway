import sys
from pathlib import Path

# Make `harness` and `scorers` importable when running pytest from the
# blueprint-bench/ directory without installing the package.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
