import sys
from pathlib import Path

import pytest

# Make `harness` and `scorers` importable when running pytest from the
# blueprint-bench/ directory without installing the package.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def make_task(tmp_path: Path):
    """Build a minimal task directory under tmp_path.

    Returns a factory `make_task(with_tests=False, with_oracle=False)` so
    tests can opt into the optional fixtures they need. Without flags, the
    starter contains just a single source file — enough to give Sandbox.build
    a baseline commit.
    """

    def _make(*, with_tests: bool = False, with_oracle: bool = False) -> Path:
        task = tmp_path / "task"
        starter = task / "starter"
        starter.mkdir(parents=True)
        (starter / "hello.py").write_text("print('hi')\n")
        if with_tests:
            (starter / "tests").mkdir()
            (starter / "tests" / "test_hello.py").write_text(
                "def test_x():\n    assert 1\n"
            )
        if with_oracle:
            oracle = task / "oracle" / "tests"
            oracle.mkdir(parents=True)
            (oracle / "test_oracle.py").write_text(
                "def test_o():\n    assert 1\n"
            )
        return task

    return _make
