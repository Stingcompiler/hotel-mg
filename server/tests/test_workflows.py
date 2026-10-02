"""The GitHub workflows parse. A carriage return inside windows-release.yml (from a «\r» in a path) made GitHub
refuse the file: the release and the installer check did not run at all, and a pull request looked green without
them (2026-10-02)."""

from pathlib import Path

import yaml

WORKFLOWS = sorted((Path(__file__).resolve().parents[2] / ".github" / "workflows").glob("*.yml"))


def test_every_workflow_parses_and_has_no_stray_control_characters():
    assert WORKFLOWS
    for path in WORKFLOWS:
        text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
        assert not [c for c in text if ord(c) < 32 and c not in "\n\t"], path.name
        assert "jobs" in yaml.safe_load(text), path.name
