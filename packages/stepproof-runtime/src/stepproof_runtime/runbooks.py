"""Runbook template loader — YAML on disk, read fresh every time.

No caching. Disk reads are microseconds, YAML files are tiny.
New runbooks are available immediately without restarts.

Declared plans (via ``keep_me_honest``) live in a separate in-memory
dict — they're ephemeral and die with the runtime.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from .models import RunbookTemplate


# Declared plans only — ephemeral, added at runtime via keep_me_honest
_DECLARED: dict[str, RunbookTemplate] = {}


def runbooks_dir() -> Path:
    raw = os.getenv("STEPPROOF_RUNBOOKS_DIR")
    if raw:
        return Path(raw).expanduser()
    local = Path.cwd() / ".stepproof" / "runbooks"
    if local.exists():
        return local
    return Path("examples")


def _load_file(path: Path) -> RunbookTemplate:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return RunbookTemplate.model_validate(data)


def _load_all_from_disk() -> dict[str, RunbookTemplate]:
    """Read every *.yaml in the runbooks dir. Fresh every call."""
    d = runbooks_dir()
    if not d.exists():
        return {}
    templates: dict[str, RunbookTemplate] = {}
    for path in sorted(d.glob("*.yaml")):
        try:
            template = _load_file(path)
            templates[template.template_id] = template
        except Exception:
            continue
    return templates


async def sync_from_disk() -> list[str]:
    """Compatibility shim — returns template_ids on disk."""
    return list(_load_all_from_disk().keys())


async def list_templates() -> list[RunbookTemplate]:
    all_templates = _load_all_from_disk()
    all_templates.update(_DECLARED)
    return sorted(all_templates.values(), key=lambda t: t.template_id)


async def get_template(template_id: str) -> RunbookTemplate | None:
    # Check declared plans first (ephemeral, from keep_me_honest)
    if template_id in _DECLARED:
        return _DECLARED[template_id]
    # Then read fresh from disk
    all_disk = _load_all_from_disk()
    return all_disk.get(template_id)


def register_template(template: RunbookTemplate) -> None:
    """Add a declared plan to the ephemeral registry."""
    _DECLARED[template.template_id] = template


def clear_registry() -> None:
    """Test-only helper to reset in-memory state."""
    _DECLARED.clear()
