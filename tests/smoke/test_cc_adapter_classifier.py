"""Unit tests for the cc-adapter classifier.

Covers:
  - Ring 0 short-circuit for read-only tools
  - Bash pattern promotion (psql → database.write → Ring 2)
  - Env override (psql + production → Ring 3)
  - Path glob classification (.env → deny, migrations/ → Ring 2)
  - Unknown tool → Ring 3 (conservative default)
  - MCP tool regex match
  - Deny with reason
  - Graceful fallback when no rule matches
"""

from __future__ import annotations

from stepproof_cc_adapter.classifier import (
    ClassifyResult,
    classify,
    load_classification,
)


def test_read_is_ring_0():
    r = classify("Read", {"file_path": "/tmp/x"})
    assert r.ring == 0
    assert r.action_type == "tool.read"


def test_grep_is_ring_0():
    r = classify("Grep", {"pattern": "foo"})
    assert r.ring == 0


def test_bash_ls_demoted_to_ring_0():
    """Generic Bash is Ring 3, but `ls` pattern demotes to Ring 0."""
    r = classify("Bash", {"command": "ls -la /tmp"})
    assert r.ring == 0
    assert r.action_type == "shell.read"


def test_bash_git_status_demoted_to_ring_0():
    r = classify("Bash", {"command": "git status"})
    assert r.ring == 0


def test_bash_psql_is_ring_2_in_staging():
    r = classify("Bash", {"command": "psql -c 'SELECT 1'"}, environment="staging")
    assert r.ring == 2
    assert r.action_type == "database.write"


def test_bash_psql_promotes_to_ring_3_in_production():
    r = classify("Bash", {"command": "psql -c 'SELECT 1'"}, environment="production")
    assert r.ring == 3


def test_bash_cerebro_migrate_production_is_ring_3():
    r = classify("Bash", {"command": "cerebro-migrate-production --apply"})
    assert r.ring == 3
    assert r.action_type == "database.write"


def test_bash_railway_deploy_is_ring_3():
    r = classify("Bash", {"command": "railway deploy --env prod"})
    assert r.ring == 3
    assert r.action_type == "deploy.production"


def test_bash_rm_rf_root_denied():
    r = classify("Bash", {"command": "rm -rf /"})
    assert r.deny is True
    assert "rm -rf" in r.deny_reason.lower() or "root" in r.deny_reason.lower()


def test_write_dotenv_denied():
    r = classify("Write", {"file_path": ".env"})
    assert r.deny is True
    assert ".env" in r.deny_reason


def test_write_dotenv_sample_allowed():
    """Sample env files are legitimate write targets."""
    r = classify("Write", {"file_path": ".env.sample"})
    assert r.deny is False


def test_write_migration_file_is_ring_2():
    r = classify("Write", {"file_path": "migrations/0042_add_connector.sql"})
    assert r.ring == 2
    assert r.action_type == "database.migration"


def test_write_docs_is_ring_1():
    r = classify("Write", {"file_path": "docs/NEW.md"})
    assert r.ring == 1


def test_write_unclassified_path_uses_tool_default():
    """A Write to an unclassified path falls back to the tool-level entry (Ring 1)."""
    r = classify("Write", {"file_path": "some/random/file.py"})
    assert r.ring == 1
    assert r.action_type == "filesystem.write"


def test_mcp_stepproof_is_ring_0():
    r = classify("mcp__stepproof__stepproof_keep_me_honest", {})
    assert r.ring == 0
    assert r.action_type == "stepproof.meta"


def test_mcp_railguey_deploy_is_ring_3():
    r = classify("mcp__railguey__railguey_deploy", {})
    assert r.ring == 3
    assert r.action_type == "deploy.production"


def test_unknown_tool_defaults_to_ring_3():
    """Conservative by design per ADR-0002 — unclassified actions surface for explicit classification."""
    r = classify("SomeToolWeveNeverSeen", {})
    assert r.ring == 3


def test_bash_default_is_ring_3():
    """A Bash command that matches no pattern stays at the tool default (Ring 3)."""
    r = classify("Bash", {"command": "some_totally_custom_binary --flag"})
    assert r.ring == 3


def test_classify_result_policy_input_shape():
    r = ClassifyResult(action_type="test.type", ring=2)
    assert r.to_policy_input() == {"action_type": "test.type", "ring": 2}


def test_classification_yaml_loads():
    cfg = load_classification()
    assert cfg["version"] == 1
    assert "tools" in cfg
    assert "bash_patterns" in cfg
    assert "path_classifications" in cfg


# ---------------------------------------------------------------------------
# Evasion-path tests (from GPT-5.2 code review). These are regressions we
# would not have caught with toy inputs only.
# ---------------------------------------------------------------------------


def test_evasion_sudo_psql_still_classified():
    r = classify("Bash", {"command": "sudo psql -c 'DROP TABLE x'"}, environment="production")
    assert r.ring == 3
    assert r.action_type == "database.write"


def test_evasion_absolute_path_psql():
    r = classify("Bash", {"command": "/usr/bin/psql -c 'SELECT 1'"}, environment="staging")
    assert r.ring == 2
    assert r.action_type == "database.write"


def test_evasion_env_prefixed_psql():
    r = classify(
        "Bash",
        {"command": "env PGPASSWORD=secret psql -c 'SELECT 1'"},
        environment="staging",
    )
    assert r.ring == 2


def test_evasion_command_builtin_psql():
    r = classify("Bash", {"command": "command psql -c 'SELECT 1'"}, environment="staging")
    assert r.ring == 2


def test_evasion_backslash_escaped_psql():
    r = classify("Bash", {"command": "\\psql -c 'SELECT 1'"}, environment="staging")
    assert r.ring == 2


def test_evasion_sudo_cerebro_migrate_production():
    r = classify("Bash", {"command": "sudo cerebro-migrate-production --apply"})
    assert r.ring == 3


def test_evasion_rm_rf_double_dash():
    r = classify("Bash", {"command": "rm -rf -- /"})
    assert r.deny is True


def test_evasion_rm_separated_flags():
    r = classify("Bash", {"command": "rm -r -f /"})
    assert r.deny is True


def test_evasion_rm_home_dir():
    r = classify("Bash", {"command": "rm -rf ~"})
    assert r.deny is True


def test_non_evasion_rm_local_file_not_denied():
    """Narrow rule: only root/home/$HOME/.. paths deny. Local rm is allowed."""
    r = classify("Bash", {"command": "rm -rf build/artifacts"})
    assert r.deny is False
