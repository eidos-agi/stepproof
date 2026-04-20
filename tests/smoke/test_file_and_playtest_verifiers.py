"""Tests for verify_file_exists and verify_playtest_log — the verifiers that
force real on-disk artifacts for design docs and playtest logs. Used by the
stepproof-test validation scenario to make evidence-fabrication impossible."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from stepproof_runtime.verifiers import dispatch


# ----- verify_file_exists -----


@pytest.mark.asyncio
async def test_file_exists_passes_for_real_file():
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "spec.md"
        f.write_text("# Spec\n\nThis has more than one line.\nAnd another one.\n")
        r = await dispatch(
            "verify_file_exists",
            {"path": str(f), "min_lines": 2},
            {},
        )
    assert r.status.value == "pass"


@pytest.mark.asyncio
async def test_file_exists_fails_for_missing_file():
    r = await dispatch(
        "verify_file_exists",
        {"path": "/tmp/definitely-not-a-real-file-xyz.txt", "min_lines": 1},
        {},
    )
    assert r.status.value == "fail"


@pytest.mark.asyncio
async def test_file_exists_fails_when_too_few_lines():
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "a.md"
        f.write_text("# title only\n")
        r = await dispatch(
            "verify_file_exists",
            {"path": str(f), "min_lines": 10},
            {},
        )
    assert r.status.value == "fail"


@pytest.mark.asyncio
async def test_file_exists_fails_on_missing_path():
    r = await dispatch("verify_file_exists", {}, {})
    assert r.status.value == "fail"


# ----- verify_playtest_log -----


@pytest.mark.asyncio
async def test_playtest_log_passes_for_valid_jsonl():
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "playtest.jsonl"
        f.write_text(
            '{"move": 1, "guess": "crane", "outcome": "miss"}\n'
            '{"move": 2, "guess": "slate", "outcome": "miss"}\n'
            '{"move": 3, "guess": "ghost", "outcome": "win"}\n'
        )
        r = await dispatch(
            "verify_playtest_log",
            {"playtest_log_path": str(f), "min_entries": 3},
            {},
        )
    assert r.status.value == "pass"


@pytest.mark.asyncio
async def test_playtest_log_fails_on_empty_stubs():
    """Submitting entries with no gameplay fields must fail — can't fake it."""
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "fake.jsonl"
        f.write_text('{"_": 1}\n{"_": 2}\n{"_": 3}\n')
        r = await dispatch(
            "verify_playtest_log",
            {"playtest_log_path": str(f), "min_entries": 3},
            {},
        )
    assert r.status.value == "fail"
    assert "gameplay data" in r.reason.lower() or "substantive" in r.reason.lower()


@pytest.mark.asyncio
async def test_playtest_log_fails_on_invalid_jsonl():
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "bad.jsonl"
        f.write_text("this is not json\n")
        r = await dispatch(
            "verify_playtest_log",
            {"playtest_log_path": str(f), "min_entries": 1},
            {},
        )
    assert r.status.value == "fail"
    assert "invalid jsonl" in r.reason.lower()


@pytest.mark.asyncio
async def test_playtest_log_fails_for_missing_file():
    r = await dispatch(
        "verify_playtest_log",
        {"playtest_log_path": "/tmp/not-a-real-log.jsonl", "min_entries": 1},
        {},
    )
    assert r.status.value == "fail"
