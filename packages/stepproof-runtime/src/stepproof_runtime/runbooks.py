"""YAML runbook template loader."""

from __future__ import annotations

import json
import os
from pathlib import Path

import yaml

from .db import connect
from .models import RunbookTemplate


def runbooks_dir() -> Path:
    raw = os.getenv("STEPPROOF_RUNBOOKS_DIR", "examples")
    return Path(raw).expanduser()


def _load_file(path: Path) -> RunbookTemplate:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return RunbookTemplate.model_validate(data)


async def sync_from_disk() -> list[str]:
    """Load every *.yaml in STEPPROOF_RUNBOOKS_DIR into the database.

    Returns the list of template_ids that were upserted.
    """
    d = runbooks_dir()
    if not d.exists():
        return []

    loaded: list[str] = []
    async with connect() as conn:
        for path in sorted(d.glob("*.yaml")):
            template = _load_file(path)
            await conn.execute(
                """
                INSERT INTO runbook_templates
                  (template_id, version, name, description, risk_level,
                   allowed_environments, requires_human_signoff, shadow, steps, source_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(template_id) DO UPDATE SET
                  version = excluded.version,
                  name = excluded.name,
                  description = excluded.description,
                  risk_level = excluded.risk_level,
                  allowed_environments = excluded.allowed_environments,
                  requires_human_signoff = excluded.requires_human_signoff,
                  shadow = excluded.shadow,
                  steps = excluded.steps,
                  source_path = excluded.source_path
                """,
                (
                    template.template_id,
                    template.version,
                    template.name,
                    template.description,
                    template.risk_level,
                    json.dumps(template.allowed_environments),
                    1 if template.requires_human_signoff else 0,
                    1 if template.shadow else 0,
                    json.dumps([s.model_dump(mode="json") for s in template.steps]),
                    str(path),
                ),
            )
            loaded.append(template.template_id)
        await conn.commit()
    return loaded


async def list_templates() -> list[RunbookTemplate]:
    async with connect() as conn:
        cursor = await conn.execute("SELECT * FROM runbook_templates ORDER BY template_id")
        rows = await cursor.fetchall()
    return [_row_to_template(row) for row in rows]


async def get_template(template_id: str) -> RunbookTemplate | None:
    async with connect() as conn:
        cursor = await conn.execute(
            "SELECT * FROM runbook_templates WHERE template_id = ?", (template_id,)
        )
        row = await cursor.fetchone()
    if row is None:
        return None
    return _row_to_template(row)


def _row_to_template(row) -> RunbookTemplate:
    return RunbookTemplate.model_validate(
        {
            "template_id": row["template_id"],
            "version": row["version"],
            "name": row["name"],
            "description": row["description"] or "",
            "risk_level": row["risk_level"],
            "allowed_environments": json.loads(row["allowed_environments"]),
            "requires_human_signoff": bool(row["requires_human_signoff"]),
            "shadow": bool(row["shadow"]),
            "steps": json.loads(row["steps"]),
        }
    )
