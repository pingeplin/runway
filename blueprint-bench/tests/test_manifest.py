import json
from pathlib import Path

from harness import manifest


def test_manifest_captures_plugin_version_and_args(tmp_path):
    plugin_dir = tmp_path / "plugin"
    (plugin_dir / ".claude-plugin").mkdir(parents=True)
    (plugin_dir / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "blueprint", "version": "9.9.9"})
    )

    harness_dir = tmp_path / "harness"
    harness_dir.mkdir()

    mf = manifest.build(
        run_id="test-run",
        plugin_dir=plugin_dir,
        harness_dir=harness_dir,
        args={"modes": ["naked"]},
    )

    dest = tmp_path / "manifest.json"
    mf.write(dest)
    data = json.loads(dest.read_text())
    assert data["run_id"] == "test-run"
    assert data["plugin_version"] == "9.9.9"
    assert data["args"]["modes"] == ["naked"]
    # plugin_sha falls back to "unknown" when the plugin dir isn't a git repo.
    assert data["plugin_sha"] == "unknown"


def test_manifest_handles_missing_plugin_json(tmp_path):
    plugin_dir = tmp_path / "plugin"
    plugin_dir.mkdir()
    harness_dir = tmp_path / "harness"
    harness_dir.mkdir()

    mf = manifest.build("r", plugin_dir, harness_dir, args={})
    assert mf.plugin_version == "unknown"
    assert mf.plugin_sha == "unknown"
