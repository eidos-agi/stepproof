"""StepProof Claude Code adapter.

Ships the body of StepProof: uv PreToolUse hook, action classification,
lifecycle hooks (SessionStart/End/PreCompact/UserPromptSubmit/PermissionRequest),
verifier subagent definitions with disallowedTools, and slash commands.

See docs/ADAPTER_BRIDGE.md for the full design.
"""

__version__ = "0.0.1"
