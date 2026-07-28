"""In-memory async job status store with pipeline run association."""
from __future__ import annotations

import threading
import uuid
from datetime import datetime
from typing import Any, Optional


class JobStore:
    def __init__(self):
        self._jobs: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def create(
        self,
        job_type: str,
        params: Optional[dict] = None,
        *,
        pipeline_run_id: Optional[str] = None,
        step_run_id: Optional[str] = None,
    ) -> str:
        job_id = str(uuid.uuid4())
        with self._lock:
            self._jobs[job_id] = {
                "id": job_id,
                "type": job_type,
                "status": "pending",
                "progress": 0.0,
                "message": "",
                "params": params or {},
                "result": None,
                "error": None,
                "pipeline_run_id": pipeline_run_id,
                "step_run_id": step_run_id,
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            }
        return job_id

    def update(self, job_id: str, **fields) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job.update(fields)
            job["updated_at"] = datetime.utcnow().isoformat()

    def get(self, job_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None

    def list_all(
        self,
        *,
        pipeline_run_id: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        with self._lock:
            jobs = list(self._jobs.values())
        if pipeline_run_id:
            jobs = [j for j in jobs if j.get("pipeline_run_id") == pipeline_run_id]
        jobs.sort(key=lambda j: j.get("created_at", ""), reverse=True)
        total = len(jobs)
        start = (page - 1) * page_size
        return [dict(j) for j in jobs[start : start + page_size]], total

    def list_by_run_id(self, pipeline_run_id: str) -> list[dict[str, Any]]:
        items, _ = self.list_all(pipeline_run_id=pipeline_run_id, page=1, page_size=1000)
        return items


job_store = JobStore()
