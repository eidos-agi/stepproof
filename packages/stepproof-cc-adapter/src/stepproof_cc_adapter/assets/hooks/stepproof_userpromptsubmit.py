#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6.0"]
# ///
"""StepProof UserPromptSubmit hook.

Cheap early reminder: when the user's prompt mentions a pattern that would
almost certainly be denied (raw psql on prod, rm -rf, etc.), surface a soft
nudge via additionalContext BEFORE Claude processes the prompt. This is
not enforcement — just a heads-up that saves a round-trip through
PreToolUse denial for commonly-missed cases.

Exits 0 on any failure.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

CLASSIFICATION_PATH = os.getenv(
    "STEPPROOF_CLASSIFICATION",
    str(Path(__file__).resolve().parents[1] / "action_classification.yaml"),
)


def _load_bash_patterns() -> list[dict]:
    try:
        import yaml

        with open(CLASSIFICATION_PATH, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        return cfg.get("bash_patterns") or []
    except Exception:
        return []


def _detect_risky_intent(prompt: str, patterns: list[dict]) -> list[dict]:
    """Return the subset of rules whose match would likely fire.

    The bash_patterns are `^`-anchored for command matching. For prompt-text
    matching (this hook's job), mentions may be mid-sentence, so we strip the
    `^` prefix and search anywhere in the prompt.
    """
    hits: list[dict] = []
    for rule in patterns:
        pat = rule.get("match", "")
        if not pat:
            continue
        # Unanchor the pattern so "let me just psql" matches the psql rule.
        if pat.startswith("^"):
            pat = pat[1:]
        try:
            if re.search(pat, prompt):
                if rule.get("deny") or int(rule.get("ring", 0)) >= 2:
                    hits.append(rule)
        except re.error:
            continue
    return hits


def main() -> None:
    try:
        event = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    try:
        prompt = event.get("prompt") or ""
        if not prompt:
            sys.exit(0)

        patterns = _load_bash_patterns()
        hits = _detect_risky_intent(prompt, patterns)
        if not hits:
            sys.exit(0)

        # Build a concise nudge. Don't dump regexes; name the action class.
        seen_classes: set[str] = set()
        actions: list[str] = []
        for r in hits:
            ac = r.get("action_type", "risky")
            if ac in seen_classes:
                continue
            seen_classes.add(ac)
            ring = r.get("ring", 3)
            denied = " (DENY)" if r.get("deny") else ""
            actions.append(f"{ac} (Ring {ring}){denied}")

        context = (
            "[StepProof] Your prompt references an action that the PreToolUse "
            "gate will likely intercept: " + ", ".join(actions) + ". "
            "If you intend this, wrap the work in an active runbook via "
            "stepproof_keep_me_honest first. Otherwise choose the sanctioned tool."
        )
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "UserPromptSubmit",
                        "additionalContext": context,
                    }
                }
            )
        )
        sys.exit(0)
    except Exception:
        sys.exit(0)


if __name__ == "__main__":
    main()
