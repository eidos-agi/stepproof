"""Tests for `stepproof init` — per-project .stepproof/ scaffolding.

Mirrors .visionlog conventions: frontmatter-style config.yaml with a stable
UUID, tracked artifact subdirectories (runbooks, overrides, plans), ephemeral
subdirectories gitignored.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
import yaml


# The `stepproof` entrypoint is installed into the workspace venv. For tests
# we invoke the cli module directly so we don't depend on PATH ordering.
CLI_CMD = [sys.executable, "-m", "stepproof_runtime.cli"]


def _run(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [*CLI_CMD, *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


def _parse_config(cfg_path: Path) -> dict:
    """Parse frontmatter-style config.yaml (same shape as .visionlog)."""
    text = cfg_path.read_text()
    # Split on the second '---' — frontmatter is between first and second.
    parts = text.split("---", 2)
    assert len(parts) >= 3, f"config.yaml missing frontmatter block: {text[:200]}"
    return yaml.safe_load(parts[1])


@pytest.fixture
def tmp_project():
    with tempfile.TemporaryDirectory() as td:
        yield Path(td)


# ---------------------------------------------------------------------------
# 1. Creates the standard layout
# ---------------------------------------------------------------------------


def test_init_creates_standard_layout(tmp_project: Path):
    res = _run("init", "--name", "demo", cwd=tmp_project)
    assert res.returncode == 0, res.stderr

    sp = tmp_project / ".stepproof"
    assert sp.is_dir()
    assert (sp / "config.yaml").is_file()
    assert (sp / "runbooks").is_dir()
    assert (sp / "overrides").is_dir()
    assert (sp / "plans").is_dir()
    assert (sp / "sessions").is_dir()


# ---------------------------------------------------------------------------
# 2. config.yaml uses .visionlog-style frontmatter with id/project/created
# ---------------------------------------------------------------------------


def test_config_has_visionlog_style_frontmatter(tmp_project: Path):
    _run("init", "--name", "demo", cwd=tmp_project)
    cfg = _parse_config(tmp_project / ".stepproof" / "config.yaml")

    assert "id" in cfg, "config missing id field (should match .visionlog convention)"
    assert "project" in cfg
    assert "created" in cfg
    assert "version" in cfg


# ---------------------------------------------------------------------------
# 3. Project id is a valid UUID
# ---------------------------------------------------------------------------


def test_project_id_is_uuid(tmp_project: Path):
    _run("init", "--name", "demo", cwd=tmp_project)
    cfg = _parse_config(tmp_project / ".stepproof" / "config.yaml")

    uuid_pattern = re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        re.IGNORECASE,
    )
    assert uuid_pattern.match(cfg["id"]), f"id is not a UUID: {cfg['id']!r}"


# ---------------------------------------------------------------------------
# 4. --name flag sets the project name
# ---------------------------------------------------------------------------


def test_name_flag_is_respected(tmp_project: Path):
    _run("init", "--name", "MyCoolProject", cwd=tmp_project)
    cfg = _parse_config(tmp_project / ".stepproof" / "config.yaml")
    assert cfg["project"] == "MyCoolProject"


# ---------------------------------------------------------------------------
# 5. Without --name, project name defaults to directory basename
# ---------------------------------------------------------------------------


def test_name_defaults_to_directory_basename(tmp_project: Path):
    named_dir = tmp_project / "cool_thing"
    named_dir.mkdir()
    _run("init", cwd=named_dir)
    cfg = _parse_config(named_dir / ".stepproof" / "config.yaml")
    assert cfg["project"] == "cool_thing"


# ---------------------------------------------------------------------------
# 6. Re-running init preserves the stable UUID
# ---------------------------------------------------------------------------


def test_reinit_preserves_uuid(tmp_project: Path):
    _run("init", "--name", "demo", cwd=tmp_project)
    cfg1 = _parse_config(tmp_project / ".stepproof" / "config.yaml")

    res = _run("init", "--name", "demo", cwd=tmp_project)
    assert res.returncode == 0
    # Should leave config alone.
    assert "already exists" in res.stdout

    cfg2 = _parse_config(tmp_project / ".stepproof" / "config.yaml")
    assert cfg1["id"] == cfg2["id"], "re-init must preserve the project UUID"


# ---------------------------------------------------------------------------
# 7. --force regenerates a new UUID
# ---------------------------------------------------------------------------


def test_force_regenerates_uuid(tmp_project: Path):
    _run("init", "--name", "demo", cwd=tmp_project)
    cfg1 = _parse_config(tmp_project / ".stepproof" / "config.yaml")

    _run("init", "--name", "demo", "--force", cwd=tmp_project)
    cfg2 = _parse_config(tmp_project / ".stepproof" / "config.yaml")
    assert cfg1["id"] != cfg2["id"]


# ---------------------------------------------------------------------------
# 8. Tracked subdirectories get README.md sentinels
# ---------------------------------------------------------------------------


def test_tracked_dirs_have_readme_sentinels(tmp_project: Path):
    _run("init", "--name", "demo", cwd=tmp_project)
    sp = tmp_project / ".stepproof"
    for name in ("runbooks", "overrides", "plans"):
        readme = sp / name / "README.md"
        assert readme.is_file(), f"{name}/README.md missing (required to track empty dirs in git)"
        body = readme.read_text()
        assert body.strip(), f"{name}/README.md is empty"


# ---------------------------------------------------------------------------
# 9. Ephemeral subdirs are gitignored but tracked dirs are not
# ---------------------------------------------------------------------------


def test_gitignore_rules_track_artifacts_ignore_runtime_state(tmp_project: Path):
    _run("init", "--name", "demo", cwd=tmp_project)
    gi = (tmp_project / ".gitignore").read_text()

    # Ephemeral MUST be ignored.
    for pattern in (
        ".stepproof/sessions/",
        ".stepproof/audit-buffer.jsonl",
        ".stepproof/adapter-manifest.json",
        ".stepproof/runtime.db",
    ):
        assert pattern in gi, f".gitignore missing {pattern!r}"

    # Tracked dirs MUST NOT be ignored (no blanket .stepproof/ rule).
    forbidden_lines = []
    for line in gi.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            continue
        if stripped in (".stepproof/", ".stepproof/*", "**/.stepproof/"):
            forbidden_lines.append(stripped)
    assert not forbidden_lines, (
        f".gitignore has blanket .stepproof rule(s): {forbidden_lines}. "
        "This would ignore tracked config.yaml, runbooks/, overrides/, plans/."
    )


# ---------------------------------------------------------------------------
# 10. init is idempotent on the .gitignore — no duplicate blocks on re-run
# ---------------------------------------------------------------------------


def test_init_is_idempotent_on_gitignore(tmp_project: Path):
    _run("init", "--name", "demo", cwd=tmp_project)
    first = (tmp_project / ".gitignore").read_text()

    _run("init", "--name", "demo", cwd=tmp_project)
    _run("init", "--name", "demo", cwd=tmp_project)
    final = (tmp_project / ".gitignore").read_text()

    # Exactly one copy of the runtime-state section.
    assert final.count(".stepproof/sessions/") == 1, (
        "re-running init duplicated the gitignore block"
    )
    assert first == final, "re-running init modified the .gitignore"
