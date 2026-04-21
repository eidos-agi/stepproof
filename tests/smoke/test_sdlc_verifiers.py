"""Smoke tests for verify_git_commit and verify_pytest_passed — the two
verifiers the rb-stepproof-dev SDLC runbook depends on."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from stepproof_runtime.verifiers import verify_git_commit, verify_pytest_passed


# --- verify_git_commit ---------------------------------------------------


@pytest.fixture
def tmp_git_repo(tmp_path: Path) -> tuple[Path, str]:
    """A fresh git repo with one commit. Returns (repo_path, commit_sha)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    env = {
        "GIT_AUTHOR_NAME": "Smoke",
        "GIT_AUTHOR_EMAIL": "smoke@example.com",
        "GIT_COMMITTER_NAME": "Smoke",
        "GIT_COMMITTER_EMAIL": "smoke@example.com",
        "HOME": str(tmp_path),
        "PATH": "/usr/bin:/bin:/usr/local/bin",
    }
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, env=env)
    (repo / "README.md").write_text("hello\n")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True, env=env)
    subprocess.run(
        ["git", "commit", "-q", "-m", "feat: initial commit"],
        cwd=repo,
        check=True,
        env=env,
    )
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True
    ).stdout.strip()
    return repo, sha


async def test_verify_git_commit_passes_for_real_sha(tmp_git_repo):
    repo, sha = tmp_git_repo
    r = await verify_git_commit(
        {"commit_sha": sha, "repo_path": str(repo)}, context={}
    )
    assert r["status"] == "pass"
    assert r["artifacts"]["commit_sha"] == sha


async def test_verify_git_commit_fails_for_missing_sha():
    r = await verify_git_commit({}, context={})
    assert r["status"] == "fail"
    assert "commit_sha" in r["reason"].lower()


async def test_verify_git_commit_fails_for_nonexistent_sha(tmp_git_repo):
    repo, _ = tmp_git_repo
    r = await verify_git_commit(
        {"commit_sha": "0" * 40, "repo_path": str(repo)}, context={}
    )
    assert r["status"] == "fail"


async def test_verify_git_commit_checks_subject_match(tmp_git_repo):
    repo, sha = tmp_git_repo
    r = await verify_git_commit(
        {
            "commit_sha": sha,
            "repo_path": str(repo),
            "expected_subject_contains": "initial",
        },
        context={},
    )
    assert r["status"] == "pass"

    r = await verify_git_commit(
        {
            "commit_sha": sha,
            "repo_path": str(repo),
            "expected_subject_contains": "does-not-appear",
        },
        context={},
    )
    assert r["status"] == "fail"


# --- verify_pytest_passed ------------------------------------------------


async def test_verify_pytest_passed_on_green_output(tmp_path: Path):
    out = tmp_path / "pytest.out"
    out.write_text(
        "tests/smoke/test_foo.py ...\n"
        "============================= 145 passed in 12.34s ==============================\n"
    )
    r = await verify_pytest_passed(
        {"pytest_output_path": str(out), "min_passed": 100}, context={}
    )
    assert r["status"] == "pass"
    assert r["artifacts"]["passed"] == 145


async def test_verify_pytest_passed_fails_on_failure_line(tmp_path: Path):
    out = tmp_path / "pytest.out"
    out.write_text("============================= 2 failed, 143 passed in 10s ==\n")
    r = await verify_pytest_passed(
        {"pytest_output_path": str(out)}, context={}
    )
    assert r["status"] == "fail"
    assert "failure" in r["reason"].lower()


async def test_verify_pytest_passed_fails_below_min(tmp_path: Path):
    out = tmp_path / "pytest.out"
    out.write_text("============================= 3 passed in 1s ==\n")
    r = await verify_pytest_passed(
        {"pytest_output_path": str(out), "min_passed": 145}, context={}
    )
    assert r["status"] == "fail"
    assert "≥145" in r["reason"] or "145" in r["reason"]


async def test_verify_pytest_passed_fails_when_no_summary(tmp_path: Path):
    out = tmp_path / "pytest.out"
    out.write_text("random output with no pytest summary\n")
    r = await verify_pytest_passed(
        {"pytest_output_path": str(out)}, context={}
    )
    assert r["status"] == "fail"


async def test_verify_pytest_passed_fails_on_missing_path():
    r = await verify_pytest_passed({}, context={})
    assert r["status"] == "fail"
    assert "pytest_output_path" in r["reason"].lower()
