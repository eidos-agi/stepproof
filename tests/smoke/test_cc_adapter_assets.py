"""Tests for the cc-adapter asset bundle: verifier subagents + slash commands.

These are Markdown files with YAML frontmatter. They get copied into
`.claude/agents/stepproof/` and `.claude/commands/` by `stepproof install`
(Phase 2b s5). The tests here assert they are well-formed at the source —
correct frontmatter, required fields, and security-critical constraints
(verifiers' `disallowedTools` must include all write tools).
"""

from __future__ import annotations

from pathlib import Path

import yaml

ASSETS = (
    Path(__file__).resolve().parents[2]
    / "packages"
    / "stepproof-cc-adapter"
    / "src"
    / "stepproof_cc_adapter"
    / "assets"
)
AGENTS_DIR = ASSETS / "agents"
COMMANDS_DIR = ASSETS / "commands"

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _parse_frontmatter(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{path.name} missing leading frontmatter marker"
    _, frontmatter, body = text.split("---", 2)
    data = yaml.safe_load(frontmatter)
    return data, body.strip()


# ------------------------------------------------------------------
# Verifier subagents (shipped files)
# ------------------------------------------------------------------

EXPECTED_SUBAGENTS = {
    "stepproof-verifier-tier2.md",
    "stepproof-verifier-tier3.md",
}

REQUIRED_WRITE_TOOLS_IN_DISALLOWED = {"Write", "Edit", "NotebookEdit"}


def test_all_verifier_subagents_present():
    names = {p.name for p in AGENTS_DIR.glob("*.md")}
    missing = EXPECTED_SUBAGENTS - names
    assert not missing, f"verifier subagents missing: {missing}"


def test_tier2_subagent_is_readonly_via_disallowed_tools():
    """GUARD-001: verifiers have no write tools. Enforced structurally."""
    data, _ = _parse_frontmatter(AGENTS_DIR / "stepproof-verifier-tier2.md")
    disallowed_raw = data.get("disallowedTools", "")
    disallowed = {x.strip() for x in disallowed_raw.split(",")}
    assert REQUIRED_WRITE_TOOLS_IN_DISALLOWED.issubset(disallowed), (
        f"Tier 2 verifier frontmatter does not block write tools. "
        f"disallowedTools must include at least {REQUIRED_WRITE_TOOLS_IN_DISALLOWED}; "
        f"got {disallowed}"
    )


def test_tier3_subagent_is_readonly_via_disallowed_tools():
    data, _ = _parse_frontmatter(AGENTS_DIR / "stepproof-verifier-tier3.md")
    disallowed = {x.strip() for x in data.get("disallowedTools", "").split(",")}
    assert REQUIRED_WRITE_TOOLS_IN_DISALLOWED.issubset(disallowed)


def test_verifier_subagents_use_correct_models():
    """Tier 2 = Haiku (cheap), Tier 3 = Opus (heavy). Catches accidental model swaps."""
    t2, _ = _parse_frontmatter(AGENTS_DIR / "stepproof-verifier-tier2.md")
    t3, _ = _parse_frontmatter(AGENTS_DIR / "stepproof-verifier-tier3.md")
    assert "haiku" in t2["model"].lower()
    assert "opus" in t3["model"].lower()


def test_verifier_subagents_block_bash_too():
    """Bash is a write tool in practice — verifiers must not have it."""
    for name in EXPECTED_SUBAGENTS:
        data, _ = _parse_frontmatter(AGENTS_DIR / name)
        disallowed = {x.strip() for x in data.get("disallowedTools", "").split(",")}
        assert "Bash" in disallowed, f"{name} allows Bash — not read-only"


def test_verifier_subagents_have_required_metadata():
    for name in EXPECTED_SUBAGENTS:
        data, body = _parse_frontmatter(AGENTS_DIR / name)
        for field in ("name", "description", "model", "disallowedTools"):
            assert field in data, f"{name} frontmatter missing field: {field}"
        assert body, f"{name} has empty body"


# ------------------------------------------------------------------
# Slash commands
# ------------------------------------------------------------------

EXPECTED_COMMANDS = {
    "keep-me-honest.md",
    "runbook-start.md",
    "runbook-status.md",
    "step-complete.md",
    "approve.md",
    "runbook-abandon.md",
}


def test_all_slash_commands_present():
    names = {p.name for p in COMMANDS_DIR.glob("*.md")}
    missing = EXPECTED_COMMANDS - names
    assert not missing, f"slash commands missing: {missing}"


def test_slash_commands_have_required_frontmatter():
    for name in EXPECTED_COMMANDS:
        data, body = _parse_frontmatter(COMMANDS_DIR / name)
        for field in ("name", "description"):
            assert field in data, f"{name} frontmatter missing field: {field}"
        assert body, f"{name} has empty body"


def test_slash_commands_reference_real_mcp_tools_or_endpoints():
    """Each command must name either an mcp__stepproof__ tool or an HTTP endpoint."""
    for name in EXPECTED_COMMANDS:
        _, body = _parse_frontmatter(COMMANDS_DIR / name)
        if name == "approve.md":
            # Phase 2b placeholder; documents the gap explicitly.
            assert "Phase 3" in body or "placeholder" in body.lower()
            continue
        has_ref = ("mcp__stepproof__" in body) or ("/runs/" in body) or ("/policy/" in body)
        assert has_ref, f"{name} doesn't reference an MCP tool or runtime endpoint"


def test_keep_me_honest_command_names_the_mcp_tool():
    """The /keep-me-honest command must call the specific MCP tool, not be vague."""
    _, body = _parse_frontmatter(COMMANDS_DIR / "keep-me-honest.md")
    assert "mcp__stepproof__stepproof_keep_me_honest" in body


def test_step_complete_command_references_evidence_key_value_shape():
    """The command must teach k=v evidence syntax — otherwise the UX collapses."""
    _, body = _parse_frontmatter(COMMANDS_DIR / "step-complete.md")
    assert "key=value" in body or "k=v" in body


def test_all_command_files_use_valid_yaml_frontmatter():
    """A malformed YAML block would break slash-command registration."""
    for name in EXPECTED_COMMANDS:
        try:
            _parse_frontmatter(COMMANDS_DIR / name)
        except yaml.YAMLError as e:
            raise AssertionError(f"{name} has invalid YAML frontmatter: {e}")


def test_all_agent_files_use_valid_yaml_frontmatter():
    for name in EXPECTED_SUBAGENTS:
        try:
            _parse_frontmatter(AGENTS_DIR / name)
        except yaml.YAMLError as e:
            raise AssertionError(f"{name} has invalid YAML frontmatter: {e}")
