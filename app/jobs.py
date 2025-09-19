from __future__ import annotations
import threading
from uuid import uuid4, UUID
from typing import Dict, Optional, List
from dataclasses import dataclass, field
from .models import JobResult, JobStatusPayload

@dataclass
class Job:
    job_id: UUID
    source_id: str
    status: str = "queued"  # queued|running|completed|failed
    progress: float = 0.0
    message: Optional[str] = None
    result: Optional[JobResult] = None
    chunk_seconds: Optional[int] = None
    webhook_url: Optional[str] = None

class JobStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._jobs: Dict[UUID, Job] = {}

    def create(self, source_id: str, chunk_seconds: Optional[int], webhook_url: Optional[str]) -> UUID:
        job_id = uuid4()
        with self._lock:
            self._jobs[job_id] = Job(job_id=job_id, source_id=source_id, chunk_seconds=chunk_seconds, webhook_url=webhook_url)
        return job_id

    def set_running(self, job_id: UUID, msg: Optional[str] = None):
        with self._lock:
            j = self._jobs.get(job_id)
            if j:
                j.status = "running"
                if msg:
                    j.message = msg

    def update_progress(self, job_id: UUID, progress: float, msg: Optional[str] = None):
        with self._lock:
            j = self._jobs.get(job_id)
            if j:
                j.progress = max(0.0, min(1.0, progress))
                if msg:
                    j.message = msg

    def complete(self, job_id: UUID, chunks: List[str], total_duration_sec: Optional[float], chunk_seconds: Optional[int]):
        with self._lock:
            j = self._jobs.get(job_id)
            if j:
                j.status = "completed"
                j.progress = 1.0
                j.result = JobResult(chunks=chunks, total_duration_sec=total_duration_sec, chunk_seconds=chunk_seconds)

    def fail(self, job_id: UUID, error: str):
        with self._lock:
            j = self._jobs.get(job_id)
            if j:
                j.status = "failed"
                j.message = error

    def get_payload(self, job_id: UUID) -> Optional[JobStatusPayload]:
        with self._lock:
            j = self._jobs.get(job_id)
            if not j:
                return None
            return JobStatusPayload(
                job_id=j.job_id,
                source_id=j.source_id,
                status=j.status, progress=j.progress, message=j.message, result=j.result
            )

job_store = JobStore()
