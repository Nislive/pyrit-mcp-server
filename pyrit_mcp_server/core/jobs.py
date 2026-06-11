"""Async job manager for long-running attack operations."""

from __future__ import annotations

import asyncio
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Job:
    job_id: str
    status: JobStatus
    strategy: str
    objective: str
    created_at: str
    result: Any = None
    error: str | None = None


class JobManager:
    """In-memory job store for background attack execution."""

    _jobs: dict[str, Job] = {}
    _tasks: dict[str, asyncio.Task] = {}  # noqa: RUF012

    @classmethod
    def create(cls, *, strategy: str, objective: str) -> str:
        job_id = str(uuid.uuid4())[:8]
        cls._jobs[job_id] = Job(
            job_id=job_id,
            status=JobStatus.PENDING,
            strategy=strategy,
            objective=objective,
            created_at=datetime.now(tz=timezone.utc).isoformat(),
        )
        return job_id

    @classmethod
    def start(cls, job_id: str, coro: Any) -> None:
        """Schedule a coroutine as a background task for the given job."""
        job = cls._jobs[job_id]
        job.status = JobStatus.RUNNING

        async def _wrapper() -> None:
            try:
                result = await coro
                job.result = result
                job.status = JobStatus.COMPLETED
            except Exception as e:
                job.error = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
                job.status = JobStatus.FAILED

        cls._tasks[job_id] = asyncio.create_task(_wrapper())

    @classmethod
    def get(cls, job_id: str) -> dict[str, Any]:
        if job_id not in cls._jobs:
            return {"status": "error", "error": f"Job '{job_id}' not found"}
        job = cls._jobs[job_id]
        out: dict[str, Any] = {
            "job_id": job.job_id,
            "status": job.status.value,
            "strategy": job.strategy,
            "objective": job.objective,
            "created_at": job.created_at,
        }
        if job.status == JobStatus.COMPLETED:
            out["result"] = job.result
        if job.status == JobStatus.FAILED:
            out["error"] = job.error
        return out

    @classmethod
    def list_all(cls) -> list[dict[str, Any]]:
        return [
            {
                "job_id": j.job_id,
                "status": j.status.value,
                "strategy": j.strategy,
                "objective": j.objective[:80],
                "created_at": j.created_at,
            }
            for j in cls._jobs.values()
        ]
