"""The eval harness: replay a prompt version against a suite of golden cases and
score each output with an LLM judge (Gemini). Runs in the background so the API
can return immediately; progress is read back from the eval_runs row.

A suite is a Prompt. A version is a PromptVersion whose template may contain an
``{input}`` placeholder and whose metadata carries the system prompt and model.
Each GoldenCase holds an input and a reference output to grade against.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import time
import uuid
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from replay import assist
from replay.db.models import EvalResult, EvalRun, GoldenCase, PromptVersion
from replay.db.rls import org_session
from replay.vault.keys import get_active_secret

logger = logging.getLogger("replay.evals")

DEFAULT_SYSTEM = "You are a helpful assistant. Answer the user clearly and concisely."
DEFAULT_MODEL = "gemini-2.5-flash"
PASS_SCORE = 60

JUDGE_SYSTEM = (
    "You are a strict but fair grader. Compare a model's ANSWER to a REFERENCE "
    "answer for the same question. Judge whether the answer is correct and "
    "complete relative to the reference, ignoring wording and style differences. "
    "Respond with ONLY a JSON object, no markdown, of the form "
    '{"score": <0-100 integer>, "reason": "<one short sentence>"}. '
    "Score 100 means fully equivalent, 0 means wrong or empty."
)


def render_input(template: str, case_input: str) -> str:
    if "{input}" in template:
        return template.replace("{input}", case_input)
    if template.strip():
        return f"{template}\n\n{case_input}"
    return case_input


def _case_text(value: Any) -> str:
    """Pull display text out of a golden case input or reference JSON blob."""
    if isinstance(value, dict):
        for key in ("input", "text", "content", "prompt"):
            v = value.get(key)
            if isinstance(v, str):
                return v
        return json.dumps(value)
    return str(value)


def parse_judge(reply: str) -> tuple[int, str]:
    """Extract a 0-100 score and a reason from the judge reply, tolerant of
    code fences or stray prose around the JSON object.
    """
    cleaned = reply.strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        cleaned = cleaned[start : end + 1]
    try:
        data = json.loads(cleaned)
        score = int(data.get("score", 0))
        reason = str(data.get("reason", ""))
    except (json.JSONDecodeError, ValueError, TypeError):
        return 0, "could not parse judge response"
    return max(0, min(100, score)), reason


async def execute_run(org_id: uuid.UUID, run_id: uuid.UUID) -> None:
    """Run every golden case for the run's prompt version and grade the outputs.

    Best effort end to end: any failure marks the run failed rather than raising.
    """
    try:
        async with org_session(org_id) as session:
            run = await session.get(EvalRun, run_id)
            if run is None:
                return
            version = await session.get(PromptVersion, run.prompt_version_id)
            if version is None:
                await _finish(session, run, "failed", {"error": "prompt version missing"})
                return
            meta = version.extra or {}
            system = str(meta.get("system") or DEFAULT_SYSTEM)
            model = str(meta.get("model") or DEFAULT_MODEL)
            template = version.template
            goldens = list(
                (
                    await session.execute(
                        select(GoldenCase)
                        .where(GoldenCase.prompt_id == version.prompt_id)
                        .order_by(GoldenCase.created_at)
                    )
                ).scalars()
            )
            run.status = "running"

        async with org_session(org_id) as session:
            secret = await get_active_secret(session, "gemini")
        if not secret:
            async with org_session(org_id) as session:
                run = await session.get(EvalRun, run_id)
                if run is not None:
                    await _finish(session, run, "failed", {"error": "no gemini key"})
            return
        if not goldens:
            async with org_session(org_id) as session:
                run = await session.get(EvalRun, run_id)
                if run is not None:
                    await _finish(
                        session, run, "done", {"cases": 0, "passed": 0, "pass_rate": 0.0}
                    )
            return

        scores: list[int] = []
        passed_count = 0
        for golden in goldens:
            case_input = _case_text(golden.input)
            reference = _case_text(golden.reference_output)
            user = render_input(template, case_input)
            started = time.monotonic()
            actual = await assist.complete(secret, system, user, model)
            latency_ms = int((time.monotonic() - started) * 1000)
            judge_user = f"QUESTION:\n{case_input}\n\nREFERENCE:\n{reference}\n\nANSWER:\n{actual}"
            score, reason = parse_judge(await assist.complete(secret, JUDGE_SYSTEM, judge_user))
            passed = score >= PASS_SCORE
            scores.append(score)
            passed_count += int(passed)
            async with org_session(org_id) as session:
                session.add(
                    EvalResult(
                        org_id=org_id,
                        eval_run_id=run_id,
                        golden_case_id=golden.id,
                        actual_output={"text": actual},
                        scores={"score": score, "reason": reason},
                        passed=passed,
                        latency_ms=latency_ms,
                    )
                )

        n = len(goldens)
        summary = {
            "cases": n,
            "passed": passed_count,
            "pass_rate": round(passed_count / n, 4) if n else 0.0,
            "avg_score": round(sum(scores) / n, 1) if n else 0.0,
        }
        async with org_session(org_id) as session:
            run = await session.get(EvalRun, run_id)
            if run is not None:
                await _finish(session, run, "done", summary)
    except Exception:  # noqa: BLE001
        logger.exception("eval run %s failed", run_id)
        try:
            async with org_session(org_id) as session:
                await session.execute(
                    update(EvalRun)
                    .where(EvalRun.id == run_id)
                    .values(status="failed", finished_at=dt.datetime.now(dt.UTC))
                )
        except Exception:  # noqa: BLE001
            logger.exception("could not mark eval run %s failed", run_id)


async def _finish(
    session: AsyncSession, run: EvalRun, status: str, summary: dict[str, Any]
) -> None:
    run.status = status
    run.summary = summary
    run.finished_at = dt.datetime.now(dt.UTC)
