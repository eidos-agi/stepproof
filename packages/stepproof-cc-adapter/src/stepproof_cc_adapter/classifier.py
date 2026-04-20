"""Client-side action classification for the Claude Code adapter.

Deterministic per ADR-0001 — no LLM in this path. The classifier maps a
(tool_name, tool_input, environment) triple into a ClassifyResult carrying
action_type, ring, and optional deny-with-reason.

The YAML shape is documented at src/stepproof_cc_adapter/assets/stepproof/action_classification.yaml.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


@lru_cache(maxsize=256)
def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Translate a shell-style glob (with `**`) to a compiled regex.

    Semantics:
      `**`  — any run of characters including `/`
      `*`   — any run of characters except `/`
      `?`   — a single character except `/`
      other regex metachars are escaped.
    """
    parts: list[str] = []
    i = 0
    while i < len(pattern):
        c = pattern[i]
        if c == "*" and i + 1 < len(pattern) and pattern[i + 1] == "*":
            parts.append(".*")
            i += 2
            # Swallow a trailing "/" after "**" so "**/x" matches "x" too.
            if i < len(pattern) and pattern[i] == "/":
                i += 1
        elif c == "*":
            parts.append("[^/]*")
            i += 1
        elif c == "?":
            parts.append("[^/]")
            i += 1
        elif c in r".+^$(){}|\\":
            parts.append("\\" + c)
            i += 1
        else:
            parts.append(c)
            i += 1
    return re.compile("^" + "".join(parts) + "$")


def _glob_match(pattern: str, path: str) -> bool:
    return bool(_glob_to_regex(pattern).match(path))


@dataclass
class ClassifyResult:
    action_type: str
    ring: int
    deny: bool = False
    deny_reason: str = ""
    matched_rule: str = ""

    def to_policy_input(self) -> dict[str, Any]:
        return {
            "action_type": self.action_type,
            "ring": self.ring,
        }


DEFAULT_CLASSIFICATION_YAML = (
    Path(__file__).parent / "assets" / "stepproof" / "action_classification.yaml"
)


def load_classification(path: Path | str | None = None) -> dict[str, Any]:
    """Load a classification YAML. Defaults to the shipped asset."""
    p = Path(path) if path else DEFAULT_CLASSIFICATION_YAML
    with p.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _apply_env_overrides(rule: dict[str, Any], environment: str | None) -> dict[str, Any]:
    """Merge rule['env_overrides'][environment] on top of the base rule."""
    overrides = rule.get("env_overrides", {})
    if environment and environment in overrides:
        merged = dict(rule)
        merged.update(overrides[environment])
        return merged
    return rule


def classify_bash(
    command: str, classification: dict[str, Any], environment: str | None
) -> ClassifyResult | None:
    """Match a Bash command against the ordered bash_patterns list."""
    for rule in classification.get("bash_patterns", []):
        pattern = rule.get("match", "")
        if not pattern:
            continue
        if re.search(pattern, command):
            applied = _apply_env_overrides(rule, environment)
            return ClassifyResult(
                action_type=applied.get("action_type", "shell.exec"),
                ring=int(applied.get("ring", 3)),
                deny=bool(applied.get("deny", False)),
                deny_reason=applied.get("deny_reason", ""),
                matched_rule=f"bash:{pattern}",
            )
    return None


def classify_path(
    file_path: str, classification: dict[str, Any]
) -> ClassifyResult | None:
    """Match a Write/Edit target path against path_classifications."""
    for rule in classification.get("path_classifications", []):
        glob = rule.get("glob", "")
        if not glob:
            continue
        if _glob_match(glob, file_path):
            # Check when_not_glob escape hatch (e.g., .env.* but not .env.sample).
            exclusions = rule.get("when_not_glob", [])
            if any(_glob_match(ex, file_path) for ex in exclusions):
                # This path is explicitly not classified by this rule.
                continue
            return ClassifyResult(
                action_type=rule.get("action_type", "filesystem.write"),
                ring=int(rule.get("ring", 1)),
                deny=bool(rule.get("deny", False)),
                deny_reason=rule.get("deny_reason", ""),
                matched_rule=f"path:{glob}",
            )
    return None


def classify_mcp_tool(
    tool_name: str, classification: dict[str, Any]
) -> ClassifyResult | None:
    """Match an MCP tool name against mcp_tools (regex-style keys)."""
    for pattern, rule in classification.get("mcp_tools", {}).items():
        try:
            if re.fullmatch(pattern, tool_name):
                return ClassifyResult(
                    action_type=rule.get("action_type", f"mcp.{tool_name}"),
                    ring=int(rule.get("ring", 3)),
                    matched_rule=f"mcp:{pattern}",
                )
        except re.error:
            continue
    return None


def classify(
    tool_name: str,
    tool_input: dict[str, Any] | None = None,
    environment: str | None = None,
    classification: dict[str, Any] | None = None,
) -> ClassifyResult:
    """Classify a single Claude Code tool call.

    Precedence:
      1. MCP-tool match (mcp__* names).
      2. Direct-tool match (Bash → command patterns, Write/Edit → path).
      3. tools[tool_name] lookup.
      4. Fallback: Ring 3 (conservative) — unknown tools are production-facing
         by default per ADR-0002.
    """
    tool_input = tool_input or {}
    classification = classification or load_classification()

    # MCP tools have dotted/prefixed names.
    if tool_name.startswith("mcp__"):
        mcp_result = classify_mcp_tool(tool_name, classification)
        if mcp_result is not None:
            return mcp_result

    # Bash → pattern-based promotion/demotion.
    if tool_name == "Bash":
        cmd = (tool_input.get("command") or "").lstrip()
        bash_result = classify_bash(cmd, classification, environment)
        if bash_result is not None:
            return bash_result
        # Fall through to default Bash entry (Ring 3) below.

    # Write/Edit → path-based classification first, then default.
    if tool_name in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
        if path:
            path_result = classify_path(path, classification)
            if path_result is not None:
                return path_result

    # Direct tool match.
    tool_entry = classification.get("tools", {}).get(tool_name)
    if tool_entry is not None:
        return ClassifyResult(
            action_type=tool_entry.get("action_type", f"tool.{tool_name.lower()}"),
            ring=int(tool_entry.get("ring", 3)),
            matched_rule=f"tool:{tool_name}",
        )

    # Unknown tool — conservative default.
    return ClassifyResult(
        action_type=f"tool.{tool_name.lower()}",
        ring=3,
        matched_rule="default:unknown",
    )
