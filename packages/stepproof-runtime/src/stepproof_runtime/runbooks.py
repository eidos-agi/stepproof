"""Runbook template loader — YAML on disk → in-memory dict.

Templates are read-only after boot. Declared plans (via
``keep_me_honest``) are added at runtime into the same in-memory
registry. Template persistence lives in the YAML files on disk;
declared plans are ephemeral (they die with the runtime) — the run
that references them persists in its own directory via ``store``.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from .models import RunbookTemplate


_TEMPLATES: dict[str, RunbookTemplate] = {}


def runbooks_dir() -> Path:
    raw = os.getenv("STEPPROOF_RUNBOOKS_DIR")
    if raw:
        return Path(raw).expanduser()
    # Default: scan .stepproof/runbooks/ in cwd (the repo Claude Code is pointed at)
    local = Path.cwd() / ".stepproof" / "runbooks"
    if local.exists():
        return local
    # Fallback: examples/ in the stepproof repo itself
    return Path("examples")


def _load_file(path: Path) -> RunbookTemplate:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return RunbookTemplate.model_validate(data)


async def sync_from_disk() -> list[str]:
    """Load every *.yaml in STEPPROOF_RUNBOOKS_DIR into the in-memory
    registry. Returns the list of template_ids loaded.
    """
    d = runbooks_dir()
    if not d.exists():
        return []
    loaded: list[str] = []
    for path in sorted(d.glob("*.yaml")):
        try:
            template = _load_file(path)
        except Exception:
            continue
        _TEMPLATES[template.template_id] = template
        loaded.append(template.template_id)
    return loaded


async def list_templates() -> list[RunbookTemplate]:
    return sorted(_TEMPLATES.values(), key=lambda t: t.template_id)


async def get_template(template_id: str) -> RunbookTemplate | None:
    return _TEMPLATES.get(template_id)


def register_template(template: RunbookTemplate) -> None:
    """Add a template to the registry (used for declared plans)."""
    _TEMPLATES[template.template_id] = template


def clear_registry() -> None:
    """Test-only helper to reset in-memory state."""
    _TEMPLATES.clear()
