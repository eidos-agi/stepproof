"""`stepproof install` / `stepproof uninstall` logic.

Wires the Claude Code harness to the StepProof adapter:

  <base_dir>/hooks/              — 6 uv hook scripts
  <base_dir>/agents/stepproof/   — 2 verifier subagents
  <base_dir>/commands/           — 6 slash commands
  <base_dir>/stepproof/          — action_classification.yaml
  <base_dir>/settings.json       — edited to register the 6 hooks
  <project_dir>/.stepproof/adapter-manifest.json — records what was
                                                    installed, enables
                                                    clean uninstall.

Default scope is user (`~/.claude/`) — aligns with the user-level MCP
server registration already in `~/.claude.json`.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ASSETS_ROOT = Path(__file__).resolve().parent / "assets"

# Hook event → (matcher regex, script filename).
# Matcher "" means "fire on every event of this type" (e.g., SessionStart has no
# per-tool variations). PreToolUse uses a targeted matcher to avoid paying the
# hook cost on unrelated tools.
HOOK_REGISTRATIONS: dict[str, tuple[str, str]] = {
    "PreToolUse": (
        "Bash|Write|Edit|MultiEdit|NotebookEdit|mcp__.*",
        "stepproof_pretooluse.py",
    ),
    "SessionStart": ("", "stepproof_sessionstart.py"),
    "SessionEnd": ("", "stepproof_sessionend.py"),
    "PreCompact": ("", "stepproof_precompact.py"),
    "UserPromptSubmit": ("", "stepproof_userpromptsubmit.py"),
    "PermissionRequest": ("", "stepproof_permissionrequest.py"),
}

# A stable marker the installer embeds in each hook registration so uninstall
# can identify StepProof's entries unambiguously without touching others.
STEPPROOF_HOOK_MARKER = "stepproof-cc-adapter"


@dataclass
class Manifest:
    """Records every file written and every settings.json entry added."""

    scope: str  # "user" | "project"
    base_dir: str
    installed_at: str
    files_written: list[str] = field(default_factory=list)
    hook_events_registered: list[str] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(
            {
                "scope": self.scope,
                "base_dir": self.base_dir,
                "installed_at": self.installed_at,
                "files_written": self.files_written,
                "hook_events_registered": self.hook_events_registered,
                "marker": STEPPROOF_HOOK_MARKER,
            },
            indent=2,
        )


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _resolve_base_dir(scope: str) -> Path:
    if scope == "user":
        return Path.home() / ".claude"
    elif scope == "project":
        return Path.cwd() / ".claude"
    raise ValueError(f"Unknown scope: {scope!r} (expected 'user' or 'project')")


def _copy_tree(src_dir: Path, dst_dir: Path, manifest: Manifest) -> None:
    """Copy every file from src_dir into dst_dir, recording each write."""
    dst_dir.mkdir(parents=True, exist_ok=True)
    for item in src_dir.iterdir():
        if item.is_file():
            dst = dst_dir / item.name
            shutil.copy2(item, dst)
            manifest.files_written.append(str(dst))


def _load_settings(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _register_hooks(settings_path: Path, hooks_dir: Path, manifest: Manifest) -> None:
    """Add StepProof's 6 hook entries into settings.json under `hooks`.

    Preserves any existing hook entries (does not replace). Entries tagged with
    STEPPROOF_HOOK_MARKER so uninstall can find and remove them precisely.
    """
    settings = _load_settings(settings_path)
    settings.setdefault("hooks", {})
    for event, (matcher, script) in HOOK_REGISTRATIONS.items():
        script_path = hooks_dir / script
        entry = {
            "matcher": matcher,
            "hooks": [
                {
                    "type": "command",
                    "command": f"uv run --script {script_path}",
                    "stepproof_installed": STEPPROOF_HOOK_MARKER,
                }
            ],
        }
        settings["hooks"].setdefault(event, []).append(entry)
        manifest.hook_events_registered.append(event)
    _atomic_write_json(settings_path, settings)
    manifest.files_written.append(str(settings_path))


def install(scope: str = "user", project_dir: Path | None = None) -> Manifest:
    """Install the cc-adapter.

    Args:
        scope: "user" (default, writes to ~/.claude/) or "project" (<cwd>/.claude/).
        project_dir: where to write the adapter-manifest.json. Defaults to cwd.

    Returns:
        The manifest describing everything installed.
    """
    base = _resolve_base_dir(scope)
    project = (project_dir or Path.cwd()).resolve()
    manifest = Manifest(scope=scope, base_dir=str(base), installed_at=_utcnow_iso())

    # 1. Copy hook scripts.
    _copy_tree(ASSETS_ROOT / "hooks", base / "hooks", manifest)

    # 2. Copy verifier subagents under agents/stepproof/ to avoid colliding with
    #    other agents the user may already have.
    _copy_tree(ASSETS_ROOT / "agents", base / "agents" / "stepproof", manifest)

    # 3. Copy slash commands.
    _copy_tree(ASSETS_ROOT / "commands", base / "commands", manifest)

    # 4. Copy the action_classification.yaml reference. The uv hook scripts
    #    read from the default packaged location via STEPPROOF_CLASSIFICATION,
    #    but keeping a copy in <base>/stepproof/ lets operators tune per-scope.
    stepproof_cfg_dir = base / "stepproof"
    stepproof_cfg_dir.mkdir(parents=True, exist_ok=True)
    cls_src = ASSETS_ROOT / "action_classification.yaml"
    cls_dst = stepproof_cfg_dir / "action_classification.yaml"
    shutil.copy2(cls_src, cls_dst)
    manifest.files_written.append(str(cls_dst))

    # 5. Register hooks in settings.json.
    _register_hooks(base / "settings.json", base / "hooks", manifest)

    # 6. Write the manifest into the project's .stepproof dir.
    (project / ".stepproof").mkdir(parents=True, exist_ok=True)
    (project / ".stepproof" / "adapter-manifest.json").write_text(
        manifest.to_json() + "\n", encoding="utf-8"
    )

    return manifest


def _unregister_hooks(settings_path: Path) -> None:
    """Remove all StepProof-tagged hook entries from settings.json."""
    if not settings_path.exists():
        return
    settings = _load_settings(settings_path)
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return
    for event, entries in list(hooks.items()):
        kept = []
        for entry in entries:
            hks = entry.get("hooks") or []
            # Drop a registration if ANY of its hooks carries our marker.
            if any(
                h.get("stepproof_installed") == STEPPROOF_HOOK_MARKER
                for h in hks
                if isinstance(h, dict)
            ):
                continue
            kept.append(entry)
        if kept:
            hooks[event] = kept
        else:
            del hooks[event]
    if not hooks:
        settings.pop("hooks", None)
    _atomic_write_json(settings_path, settings)


def uninstall(project_dir: Path | None = None) -> dict[str, Any]:
    """Reverse a prior install using the project's adapter-manifest.json.

    Returns a summary dict (files removed, events unregistered).
    """
    project = (project_dir or Path.cwd()).resolve()
    manifest_path = project / ".stepproof" / "adapter-manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"No StepProof adapter manifest at {manifest_path}. "
            "Run `stepproof install` first or supply --project-dir."
        )

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise ValueError(f"Corrupt manifest at {manifest_path}: {e}")

    base = Path(manifest.get("base_dir") or "")
    settings_path = base / "settings.json"

    # 1. Remove hook registrations from settings.json first (minimizes the
    #    window where a dangling hook could reference a now-missing script).
    _unregister_hooks(settings_path)

    # 2. Remove every file in files_written — except settings.json itself
    #    (which we edited in place, not created).
    files_removed: list[str] = []
    for f in manifest.get("files_written", []):
        fp = Path(f)
        if fp == settings_path:
            continue
        if fp.exists():
            try:
                fp.unlink()
                files_removed.append(str(fp))
            except Exception:
                pass

    # 3. Remove empty directories we may have created (best-effort).
    for subdir in ("hooks", "commands", "stepproof", "agents/stepproof", "agents"):
        d = base / subdir
        if d.exists() and not any(d.iterdir()):
            try:
                d.rmdir()
            except OSError:
                pass

    # 4. Finally, remove the manifest file itself.
    manifest_path.unlink()

    return {
        "scope": manifest.get("scope"),
        "base_dir": manifest.get("base_dir"),
        "files_removed": files_removed,
        "events_unregistered": manifest.get("hook_events_registered", []),
    }


def uninstalled_cleanly(base_dir: Path) -> bool:
    """Sanity check — no StepProof-marked hook entries remain in settings.json."""
    settings_path = base_dir / "settings.json"
    if not settings_path.exists():
        return True
    settings = _load_settings(settings_path)
    hooks = settings.get("hooks") or {}
    for event, entries in hooks.items():
        for entry in entries:
            hks = entry.get("hooks") or []
            for h in hks:
                if isinstance(h, dict) and h.get("stepproof_installed") == STEPPROOF_HOOK_MARKER:
                    return False
    return True


# Environment hook (used by the CLI) ---------------------------------------


def install_scope_from_env() -> str:
    return os.getenv("STEPPROOF_INSTALL_SCOPE", "user")
