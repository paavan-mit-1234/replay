"""Eval harness API: suites (prompts), golden cases, prompt versions, and runs.

A suite is a named Prompt. Creating one seeds a default version. You add golden
cases (an input and the answer you want), optionally add new prompt versions to
compare, then kick off a run that replays every case and grades it with a Gemini
judge. Runs execute in the background; the frontend polls for the summary.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from replay import evals
from replay.auth.deps import ManagementContext, get_management_context, management_session
from replay.db.models import EvalResult, EvalRun, GoldenCase, Prompt, PromptVersion
from replay.db.rls import org_session

router = APIRouter()

# Keep strong references to in-flight run tasks so the loop does not garbage
# collect them mid-flight (asyncio only holds weak references to tasks).
_RUN_TASKS: set[asyncio.Task[None]] = set()


def _spawn(coro: Any) -> None:
    task = asyncio.create_task(coro)
    _RUN_TASKS.add(task)
    task.add_done_callback(_RUN_TASKS.discard)


# --- schemas -----------------------------------------------------------------


class SuiteCreate(BaseModel):
    name: str


class SuiteOut(BaseModel):
    id: uuid.UUID
    name: str
    created_at: dt.datetime
    golden_count: int
    version_count: int
    latest_pass_rate: float | None


class GoldenIn(BaseModel):
    input: str
    reference: str


class GoldenOut(BaseModel):
    id: uuid.UUID
    input: str
    reference: str
    created_at: dt.datetime


class VersionIn(BaseModel):
    template: str = "{input}"
    system: str = evals.DEFAULT_SYSTEM
    model: str = evals.DEFAULT_MODEL


class VersionOut(BaseModel):
    id: uuid.UUID
    version: int
    template: str
    system: str
    model: str
    created_at: dt.datetime


class SuiteDetail(BaseModel):
    id: uuid.UUID
    name: str
    goldens: list[GoldenOut]
    versions: list[VersionOut]


class RunOut(BaseModel):
    id: uuid.UUID
    prompt_version_id: uuid.UUID
    version: int | None
    status: str
    summary: dict[str, Any] | None
    created_at: dt.datetime
    finished_at: dt.datetime | None


class ResultOut(BaseModel):
    id: uuid.UUID
    golden_case_id: uuid.UUID
    input: str
    reference: str
    actual: str
    score: int | None
    reason: str | None
    passed: bool
    latency_ms: int | None


class RunDetail(RunOut):
    results: list[ResultOut]


def _txt(value: Any) -> str:
    return evals._case_text(value)


def _version_out(v: PromptVersion) -> VersionOut:
    meta = v.extra or {}
    return VersionOut(
        id=v.id,
        version=v.version,
        template=v.template,
        system=str(meta.get("system") or evals.DEFAULT_SYSTEM),
        model=str(meta.get("model") or evals.DEFAULT_MODEL),
        created_at=v.created_at,
    )


# --- suites ------------------------------------------------------------------


@router.get("/eval-suites", response_model=list[SuiteOut])
async def list_suites(
    session: Annotated[AsyncSession, Depends(management_session)],
) -> list[SuiteOut]:
    prompts = list(
        (await session.execute(select(Prompt).order_by(Prompt.created_at.desc()))).scalars()
    )
    out: list[SuiteOut] = []
    for p in prompts:
        golden_count = (
            await session.execute(
                select(func.count()).select_from(GoldenCase).where(GoldenCase.prompt_id == p.id)
            )
        ).scalar() or 0
        version_count = (
            await session.execute(
                select(func.count())
                .select_from(PromptVersion)
                .where(PromptVersion.prompt_id == p.id)
            )
        ).scalar() or 0
        latest = (
            await session.execute(
                select(EvalRun.summary)
                .join(PromptVersion, PromptVersion.id == EvalRun.prompt_version_id)
                .where(PromptVersion.prompt_id == p.id, EvalRun.status == "done")
                .order_by(EvalRun.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        pass_rate = (
            float(latest["pass_rate"])
            if isinstance(latest, dict) and latest.get("pass_rate") is not None
            else None
        )
        out.append(
            SuiteOut(
                id=p.id,
                name=p.name,
                created_at=p.created_at,
                golden_count=int(golden_count),
                version_count=int(version_count),
                latest_pass_rate=pass_rate,
            )
        )
    return out


@router.post("/eval-suites", response_model=SuiteDetail, status_code=status.HTTP_201_CREATED)
async def create_suite(
    body: SuiteCreate,
    ctx: Annotated[ManagementContext, Depends(get_management_context)],
    session: Annotated[AsyncSession, Depends(management_session)],
) -> SuiteDetail:
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="name required")
    existing = (
        await session.execute(select(Prompt).where(Prompt.name == name))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="suite name in use")
    prompt = Prompt(org_id=ctx.org_id, name=name)
    session.add(prompt)
    await session.flush()
    version = PromptVersion(
        org_id=ctx.org_id,
        prompt_id=prompt.id,
        version=1,
        template="{input}",
        extra={"system": evals.DEFAULT_SYSTEM, "model": evals.DEFAULT_MODEL},
    )
    session.add(version)
    await session.flush()
    return SuiteDetail(id=prompt.id, name=prompt.name, goldens=[], versions=[_version_out(version)])


@router.get("/eval-suites/{suite_id}", response_model=SuiteDetail)
async def get_suite(
    suite_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(management_session)],
) -> SuiteDetail:
    prompt = await session.get(Prompt, suite_id)
    if prompt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="suite not found")
    goldens = list(
        (
            await session.execute(
                select(GoldenCase)
                .where(GoldenCase.prompt_id == suite_id)
                .order_by(GoldenCase.created_at)
            )
        ).scalars()
    )
    versions = list(
        (
            await session.execute(
                select(PromptVersion)
                .where(PromptVersion.prompt_id == suite_id)
                .order_by(PromptVersion.version.desc())
            )
        ).scalars()
    )
    return SuiteDetail(
        id=prompt.id,
        name=prompt.name,
        goldens=[
            GoldenOut(
                id=g.id,
                input=_txt(g.input),
                reference=_txt(g.reference_output),
                created_at=g.created_at,
            )
            for g in goldens
        ],
        versions=[_version_out(v) for v in versions],
    )


@router.delete("/eval-suites/{suite_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_suite(
    suite_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(management_session)],
) -> None:
    await session.execute(delete(Prompt).where(Prompt.id == suite_id))


# --- golden cases ------------------------------------------------------------


@router.post(
    "/eval-suites/{suite_id}/goldens",
    response_model=GoldenOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_golden(
    suite_id: uuid.UUID,
    body: GoldenIn,
    ctx: Annotated[ManagementContext, Depends(get_management_context)],
    session: Annotated[AsyncSession, Depends(management_session)],
) -> GoldenOut:
    prompt = await session.get(Prompt, suite_id)
    if prompt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="suite not found")
    if not body.input.strip() or not body.reference.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="input and reference required"
        )
    golden = GoldenCase(
        org_id=ctx.org_id,
        prompt_id=suite_id,
        input={"input": body.input.strip()},
        reference_output={"text": body.reference.strip()},
    )
    session.add(golden)
    await session.flush()
    return GoldenOut(
        id=golden.id,
        input=body.input.strip(),
        reference=body.reference.strip(),
        created_at=golden.created_at,
    )


@router.delete(
    "/eval-suites/{suite_id}/goldens/{golden_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_golden(
    suite_id: uuid.UUID,
    golden_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(management_session)],
) -> None:
    await session.execute(
        delete(GoldenCase).where(
            GoldenCase.id == golden_id, GoldenCase.prompt_id == suite_id
        )
    )


# --- versions ----------------------------------------------------------------


@router.post(
    "/eval-suites/{suite_id}/versions",
    response_model=VersionOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_version(
    suite_id: uuid.UUID,
    body: VersionIn,
    ctx: Annotated[ManagementContext, Depends(get_management_context)],
    session: Annotated[AsyncSession, Depends(management_session)],
) -> VersionOut:
    prompt = await session.get(Prompt, suite_id)
    if prompt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="suite not found")
    next_version = (
        (
            await session.execute(
                select(func.coalesce(func.max(PromptVersion.version), 0)).where(
                    PromptVersion.prompt_id == suite_id
                )
            )
        ).scalar()
        or 0
    ) + 1
    version = PromptVersion(
        org_id=ctx.org_id,
        prompt_id=suite_id,
        version=next_version,
        template=body.template or "{input}",
        extra={"system": body.system, "model": body.model},
    )
    session.add(version)
    await session.flush()
    return _version_out(version)


# --- runs --------------------------------------------------------------------


class RunStart(BaseModel):
    prompt_version_id: uuid.UUID


@router.post("/evals/run", response_model=RunOut, status_code=status.HTTP_202_ACCEPTED)
async def start_run(
    body: RunStart,
    ctx: Annotated[ManagementContext, Depends(get_management_context)],
    session: Annotated[AsyncSession, Depends(management_session)],
) -> RunOut:
    version = await session.get(PromptVersion, body.prompt_version_id)
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="version not found")
    version_id, version_num = version.id, version.version
    # Commit the queued run in its own transaction so the background task reads a
    # persisted row regardless of when it is scheduled relative to this request.
    async with org_session(ctx.org_id) as run_session:
        run = EvalRun(org_id=ctx.org_id, prompt_version_id=version_id, status="queued")
        run_session.add(run)
        await run_session.flush()
        run_id, created_at = run.id, run.created_at
    # Drive the run on the loop and keep a reference until it completes.
    _spawn(evals.execute_run(ctx.org_id, run_id))
    return RunOut(
        id=run_id,
        prompt_version_id=version_id,
        version=version_num,
        status="queued",
        summary=None,
        created_at=created_at,
        finished_at=None,
    )


@router.get("/evals", response_model=list[RunOut])
async def list_runs(
    session: Annotated[AsyncSession, Depends(management_session)],
    suite_id: uuid.UUID | None = None,
) -> list[RunOut]:
    stmt = (
        select(EvalRun, PromptVersion.version, PromptVersion.prompt_id)
        .join(PromptVersion, PromptVersion.id == EvalRun.prompt_version_id)
        .order_by(EvalRun.created_at.desc())
        .limit(50)
    )
    if suite_id is not None:
        stmt = stmt.where(PromptVersion.prompt_id == suite_id)
    rows = (await session.execute(stmt)).all()
    return [
        RunOut(
            id=run.id,
            prompt_version_id=run.prompt_version_id,
            version=version,
            status=run.status,
            summary=run.summary,
            created_at=run.created_at,
            finished_at=run.finished_at,
        )
        for run, version, _prompt_id in rows
    ]


@router.get("/evals/{run_id}", response_model=RunDetail)
async def get_run(
    run_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(management_session)],
) -> RunDetail:
    run = await session.get(EvalRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found")
    version = await session.get(PromptVersion, run.prompt_version_id)
    rows = list(
        (
            await session.execute(
                select(EvalResult, GoldenCase)
                .join(GoldenCase, GoldenCase.id == EvalResult.golden_case_id)
                .where(EvalResult.eval_run_id == run_id)
                .order_by(GoldenCase.created_at)
            )
        ).all()
    )
    results = [
        ResultOut(
            id=res.id,
            golden_case_id=res.golden_case_id,
            input=_txt(golden.input),
            reference=_txt(golden.reference_output),
            actual=_txt(res.actual_output),
            score=res.scores.get("score") if isinstance(res.scores, dict) else None,
            reason=res.scores.get("reason") if isinstance(res.scores, dict) else None,
            passed=res.passed,
            latency_ms=res.latency_ms,
        )
        for res, golden in rows
    ]
    return RunDetail(
        id=run.id,
        prompt_version_id=run.prompt_version_id,
        version=version.version if version else None,
        status=run.status,
        summary=run.summary,
        created_at=run.created_at,
        finished_at=run.finished_at,
        results=results,
    )
