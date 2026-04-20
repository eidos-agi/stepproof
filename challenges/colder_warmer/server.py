#!/usr/bin/env python3
"""Test-only MCP server: a bounded guessing game that verifies Claude
solved 6 rounds for real before it can be marked complete.

The game:
  - 6 rounds.
  - Each round picks a random category (number / color / city), and a
    random value from that category's 3-option pool.
  - Claude sees the category and its 3 options but NOT which one is
    correct.
  - Claude submits a guess. The MCP replies only "correct" or "wrong" —
    never hints, never leaks the answer.
  - A round advances only when Claude guesses correctly.
  - After 6 rounds complete, the MCP writes
    ``<state_dir>/game-complete.txt`` with a summary. That file is what
    the StepProof ``verify_file_exists`` verifier checks to confirm the
    agent actually finished.

Claude cannot produce ``game-complete.txt`` any other way; only this MCP
writes it, and only after ``rounds_done == 6``. So if Claude claims
completion early, the file doesn't exist, the verifier fails, and the
run does not advance. That's the whole StepProof thesis in one test.

Categories (3 options each):
    number  — one of [1, 2, 3], feedback: "too low" / "too high" / "correct"
             (the colder/warmer direction proves Claude is reading the hint,
             not just elim-guessing)
    color   — one of ["red", "green", "blue"], feedback: "wrong" / "correct"
    city    — one of ["Tokyo", "Paris", "Cairo"], feedback: "wrong" / "correct"

State file: ``<state_dir>/game-state.json``.

This script is launched by Claude Code as a stdio MCP per the test's
``.mcp.json``. It is not installed system-wide.
"""

from __future__ import annotations

import json
import os
import random
import uuid
from pathlib import Path

from mcp.server.fastmcp import FastMCP


POOLS: dict[str, list] = {
    "number": [1, 2, 3],
    "color": ["red", "green", "blue"],
    "city": ["Tokyo", "Paris", "Cairo"],
}
CATEGORIES = tuple(POOLS.keys())
# Overridable via COLDER_WARMER_ROUNDS so one MCP binary serves any N-round test.
TOTAL_ROUNDS = int(os.environ.get("COLDER_WARMER_ROUNDS", "6"))


def _state_dir() -> Path:
    override = os.environ.get("STEPPROOF_STATE_DIR")
    base = Path(override) if override else Path.cwd() / ".stepproof"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _state_path() -> Path:
    return _state_dir() / "game-state.json"


def _complete_path() -> Path:
    return _state_dir() / "game-complete.txt"


def _round_marker_path(round_num: int) -> Path:
    """Per-round marker file. The MCP writes it on the correct guess;
    the StepProof verifier reads it to confirm the round was actually
    solved. Claude cannot fabricate it because its allowed_tools are
    scoped to this MCP's tools only — no Write/Edit access."""
    return _state_dir() / f"round-{round_num}-done.txt"


def _load() -> dict | None:
    p = _state_path()
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save(state: dict) -> None:
    _state_path().write_text(json.dumps(state, indent=2), encoding="utf-8")


def _pick_challenge(seed: int) -> dict:
    rng = random.Random(seed)
    category = rng.choice(list(POOLS.keys()))
    answer = rng.choice(POOLS[category])
    return {
        "category": category,
        "options": POOLS[category],
        "_answer": answer,
    }


def _normalize(value) -> str:
    return str(value).strip().lower()


mcp = FastMCP("colder-warmer")


@mcp.tool()
async def start_game() -> dict:
    """Begin a new 6-round guessing game. Returns the session_id.

    Call ``get_challenge`` next to see round 1.
    """
    session_id = str(uuid.uuid4())
    # Deterministic per-round challenges so a session is replayable.
    rounds = [_pick_challenge(seed=hash((session_id, i))) for i in range(TOTAL_ROUNDS)]
    state = {
        "session_id": session_id,
        "total_rounds": TOTAL_ROUNDS,
        "rounds_done": 0,
        "current_round": 0,
        "attempts_this_round": 0,
        "history": [],
        "rounds": rounds,
    }
    _save(state)
    return {
        "session_id": session_id,
        "total_rounds": TOTAL_ROUNDS,
        "pools": POOLS,
        "instructions": (
            "Call get_challenge to see round 1. For each round, call "
            "submit_answer with the session_id and your guess. You will "
            "only be told 'correct' or 'wrong' — never the right answer. "
            "A round advances only on a correct guess. After 6 correct "
            "guesses, the game writes game-complete.txt which the "
            "StepProof verifier will check."
        ),
    }


@mcp.tool()
async def get_challenge(session_id: str) -> dict:
    """Return the current round's category and the 3 options to choose from."""
    state = _load()
    if state is None or state["session_id"] != session_id:
        return {"error": "Unknown session. Call start_game first."}
    if state["rounds_done"] >= state["total_rounds"]:
        return {"status": "complete", "rounds_done": state["rounds_done"]}
    idx = state["current_round"]
    ch = state["rounds"][idx]
    return {
        "round": idx + 1,
        "total_rounds": state["total_rounds"],
        "category": ch["category"],
        "options": ch["options"],
        "attempts_this_round": state["attempts_this_round"],
    }


@mcp.tool()
async def submit_answer(session_id: str, answer: str) -> dict:
    """Submit a guess for the current round.

    Returns a ``result``:
      - ``correct`` — round advances.
      - ``wrong`` — for color/city rounds, no hint.
      - ``too_low`` / ``too_high`` — for number rounds, the colder/warmer
        direction. Never reveals the answer.

    On the 6th correct guess, ``game-complete.txt`` is written atomically
    to the state dir. The StepProof ``verify_file_exists`` verifier reads
    that file to confirm the agent actually finished before advancing the
    StepProof run. Claude cannot produce this file any other way.
    """
    state = _load()
    if state is None or state["session_id"] != session_id:
        return {"error": "Unknown session. Call start_game first."}
    if state["rounds_done"] >= state["total_rounds"]:
        return {"result": "already_complete"}

    idx = state["current_round"]
    ch = state["rounds"][idx]
    state["attempts_this_round"] = state["attempts_this_round"] + 1

    expected = _normalize(ch["_answer"])
    got = _normalize(answer)
    correct = expected == got

    result_str: str
    if correct:
        result_str = "correct"
    elif ch["category"] == "number":
        try:
            guess_n = int(got)
            ans_n = int(expected)
            result_str = "too_low" if guess_n < ans_n else "too_high"
        except ValueError:
            result_str = "wrong"
    else:
        result_str = "wrong"

    state["history"].append(
        {
            "round": idx + 1,
            "category": ch["category"],
            "attempt": state["attempts_this_round"],
            "guess": str(answer),
            "result": result_str,
        }
    )

    if correct:
        round_num = idx + 1
        _round_marker_path(round_num).write_text(
            f"round {round_num} category={ch['category']} guess={answer} "
            f"solved_on_attempt={state['attempts_this_round']}\n",
            encoding="utf-8",
        )
        state["rounds_done"] += 1
        state["current_round"] += 1
        state["attempts_this_round"] = 0

    _save(state)

    if state["rounds_done"] >= state["total_rounds"]:
        summary_lines = [
            f"game session {session_id} complete: {TOTAL_ROUNDS}/{TOTAL_ROUNDS}"
        ]
        for h in state["history"]:
            if h["result"] == "correct":
                summary_lines.append(
                    f"round {h['round']}: {h['category']}={h['guess']} "
                    f"(solved in {h['attempt']} attempt(s))"
                )
        _complete_path().write_text(
            "\n".join(summary_lines) + "\n", encoding="utf-8"
        )
        return {
            "result": "correct",
            "status": "complete",
            "rounds_done": state["rounds_done"],
            "completion_marker": str(_complete_path()),
        }

    return {"result": result_str}


@mcp.tool()
async def get_status(session_id: str) -> dict:
    """Report how many rounds are done. No answers leaked."""
    state = _load()
    if state is None or state["session_id"] != session_id:
        return {"error": "Unknown session."}
    return {
        "session_id": session_id,
        "rounds_done": state["rounds_done"],
        "total_rounds": state["total_rounds"],
        "current_round": state["current_round"] + 1 if state["rounds_done"] < state["total_rounds"] else None,
        "attempts_current_round": state["attempts_this_round"],
    }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
