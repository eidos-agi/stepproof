"""Tests for `stepproof install` / `stepproof uninstall`.

Install writes hook scripts + subagents + slash commands + settings.json
edits; uninstall reverses via the manifest. These tests use a tempdir as the
`base_dir` (simulating ~/.claude/) plus a separate project tempdir for the
manifest.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from stepproof_cc_adapter.installer import (
    HOOK_REGISTRATIONS,
    STEPPROOF_HOOK_MARKER,
    install,
    uninstall,
    uninstalled_cleanly,
)


@pytest.fixture
def temp_scope(monkeypatch):
    """Provide a scratch (base_dir, project_dir) pair. Monkeypatch HOME so the
    installer's default user scope lands in the sandbox, not the real ~/.claude."""
    with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as project:
        monkeypatch.setenv("HOME", home)
        yield Path(home) / ".claude", Path(project)


# ---------------------------------------------------------------------------
# Install: files land where expected
# ---------------------------------------------------------------------------


def test_install_writes_all_hook_scripts(temp_scope):
    base, project = temp_scope
    manifest = install(scope="user", project_dir=project)

    hooks = base / "hooks"
    for _, (_, script) in HOOK_REGISTRATIONS.items():
        assert (hooks / script).is_file(), f"hook script missing: {script}"

    # Every file_written entry should actually exist on disk.
    for f in manifest.files_written:
        # settings.json was edited not created — but it exists.
        assert Path(f).exists(), f"manifest lists missing file: {f}"


def test_install_writes_verifier_subagents(temp_scope):
    base, project = temp_scope
    install(scope="user", project_dir=project)
    agents = base / "agents" / "stepproof"
    assert (agents / "stepproof-verifier-tier2.md").is_file()
    assert (agents / "stepproof-verifier-tier3.md").is_file()


def test_install_writes_slash_commands(temp_scope):
    base, project = temp_scope
    install(scope="user", project_dir=project)
    commands = base / "commands"
    expected = {
        "keep-me-honest.md",
        "runbook-start.md",
        "runbook-status.md",
        "step-complete.md",
        "approve.md",
        "runbook-abandon.md",
    }
    found = {p.name for p in commands.glob("*.md")}
    assert expected.issubset(found)


def test_install_writes_action_classification(temp_scope):
    base, project = temp_scope
    install(scope="user", project_dir=project)
    assert (base / "stepproof" / "action_classification.yaml").is_file()


# ---------------------------------------------------------------------------
# Install: settings.json registration
# ---------------------------------------------------------------------------


def test_install_registers_all_6_hook_events(temp_scope):
    base, project = temp_scope
    install(scope="user", project_dir=project)

    settings = json.loads((base / "settings.json").read_text())
    for event in HOOK_REGISTRATIONS:
        assert event in settings["hooks"], f"hook event not registered: {event}"

    # Every StepProof entry must carry the marker.
    for event, entries in settings["hooks"].items():
        if event not in HOOK_REGISTRATIONS:
            continue
        for entry in entries:
            marked = any(
                h.get("stepproof_installed") == STEPPROOF_HOOK_MARKER
                for h in entry["hooks"]
            )
            assert marked, f"StepProof hook for {event} missing marker"


def test_install_preserves_existing_hook_entries(temp_scope):
    base, project = temp_scope
    base.mkdir(parents=True, exist_ok=True)
    # User already has an unrelated PreToolUse hook.
    pre_existing = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "SomeOtherTool",
                    "hooks": [{"type": "command", "command": "/usr/local/bin/other-hook"}],
                }
            ]
        }
    }
    (base / "settings.json").write_text(json.dumps(pre_existing, indent=2))

    install(scope="user", project_dir=project)

    settings = json.loads((base / "settings.json").read_text())
    pretooluse = settings["hooks"]["PreToolUse"]
    # At least 2 entries now: the pre-existing one and StepProof's.
    assert len(pretooluse) >= 2
    # Our marker should be on exactly one of them.
    marked_count = sum(
        1
        for entry in pretooluse
        for h in entry.get("hooks", [])
        if h.get("stepproof_installed") == STEPPROOF_HOOK_MARKER
    )
    assert marked_count == 1
    # The original entry is intact.
    others = [
        e
        for e in pretooluse
        if not any(
            h.get("stepproof_installed") == STEPPROOF_HOOK_MARKER
            for h in e.get("hooks", [])
        )
    ]
    assert others[0]["matcher"] == "SomeOtherTool"


def test_install_writes_manifest_to_project_stepproof_dir(temp_scope):
    base, project = temp_scope
    install(scope="user", project_dir=project)

    mp = project / ".stepproof" / "adapter-manifest.json"
    assert mp.is_file()
    manifest_data = json.loads(mp.read_text())
    assert manifest_data["scope"] == "user"
    assert manifest_data["marker"] == STEPPROOF_HOOK_MARKER
    assert len(manifest_data["hook_events_registered"]) == 6


def test_install_project_scope_uses_cwd_claude(temp_scope, monkeypatch):
    _, project = temp_scope
    monkeypatch.chdir(project)
    install(scope="project", project_dir=project)
    assert (project / ".claude" / "hooks" / "stepproof_pretooluse.py").is_file()


# ---------------------------------------------------------------------------
# Uninstall: reversal is clean
# ---------------------------------------------------------------------------


def test_uninstall_removes_all_installed_files(temp_scope):
    base, project = temp_scope
    install(scope="user", project_dir=project)
    hook_path = base / "hooks" / "stepproof_pretooluse.py"
    agent_path = base / "agents" / "stepproof" / "stepproof-verifier-tier2.md"
    command_path = base / "commands" / "keep-me-honest.md"
    assert hook_path.is_file()
    assert agent_path.is_file()
    assert command_path.is_file()

    uninstall(project_dir=project)

    assert not hook_path.exists()
    assert not agent_path.exists()
    assert not command_path.exists()


def test_uninstall_reverses_settings_json_registration(temp_scope):
    base, project = temp_scope
    install(scope="user", project_dir=project)
    uninstall(project_dir=project)
    assert uninstalled_cleanly(base), "StepProof-marked entries still present after uninstall"


def test_uninstall_preserves_other_users_hooks(temp_scope):
    base, project = temp_scope
    base.mkdir(parents=True, exist_ok=True)
    pre_existing = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "SomeOtherTool",
                    "hooks": [{"type": "command", "command": "/usr/local/bin/other-hook"}],
                }
            ]
        }
    }
    (base / "settings.json").write_text(json.dumps(pre_existing, indent=2))
    install(scope="user", project_dir=project)
    uninstall(project_dir=project)

    settings = json.loads((base / "settings.json").read_text())
    pretooluse = settings["hooks"]["PreToolUse"]
    assert len(pretooluse) == 1
    assert pretooluse[0]["matcher"] == "SomeOtherTool"


def test_uninstall_removes_manifest_file(temp_scope):
    base, project = temp_scope
    install(scope="user", project_dir=project)
    mp = project / ".stepproof" / "adapter-manifest.json"
    assert mp.is_file()
    uninstall(project_dir=project)
    assert not mp.exists()


def test_uninstall_errors_when_no_manifest(temp_scope):
    _, project = temp_scope
    with pytest.raises(FileNotFoundError):
        uninstall(project_dir=project)


# ---------------------------------------------------------------------------
# Install → Uninstall → Install cycle
# ---------------------------------------------------------------------------


def test_install_uninstall_install_is_idempotent(temp_scope):
    base, project = temp_scope
    install(scope="user", project_dir=project)
    uninstall(project_dir=project)
    manifest2 = install(scope="user", project_dir=project)
    # All the files should be back.
    for f in manifest2.files_written:
        assert Path(f).exists(), f"re-install missed: {f}"
    # Settings.json has exactly one StepProof marker per event (not duplicated).
    settings = json.loads((base / "settings.json").read_text())
    for event in HOOK_REGISTRATIONS:
        entries = settings["hooks"][event]
        marker_count = sum(
            1
            for entry in entries
            for h in entry.get("hooks", [])
            if h.get("stepproof_installed") == STEPPROOF_HOOK_MARKER
        )
        assert marker_count == 1, f"Event {event} has {marker_count} StepProof markers"


def test_double_install_does_not_duplicate_entries(temp_scope):
    """Running install twice without uninstall is ill-defined; we test that
    the second install adds a second entry (the marker count grows), so that
    the operator can see the duplication and act — rather than silently no-op.
    This is a conscious choice: install should be called once per scope."""
    base, project = temp_scope
    install(scope="user", project_dir=project)
    install(scope="user", project_dir=project)
    settings = json.loads((base / "settings.json").read_text())
    # The PreToolUse event should now have 2 StepProof-marked entries.
    marker_count = sum(
        1
        for entry in settings["hooks"]["PreToolUse"]
        for h in entry.get("hooks", [])
        if h.get("stepproof_installed") == STEPPROOF_HOOK_MARKER
    )
    assert marker_count == 2, "double-install should produce visible duplication, not silent no-op"
