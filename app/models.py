from pydantic import BaseModel, Field, HttpUrl
from typing import List, Optional, Literal, Dict, Union
from uuid import UUID

class IngestYouTubeRequest(BaseModel):
    source_id: str = Field(..., description="Grouping ID for chunks (e.g., source_audio_123)")
    url: HttpUrl
    chunk_seconds: Optional[int] = Field(default=None, ge=5, le=120)
    webhook_url: Optional[str] = None

class IngestResponse(BaseModel):
    job_id: UUID
    status: Literal["queued"] = "queued"

class JobResult(BaseModel):
    chunks: List[str]
    total_duration_sec: Optional[float] = None
    chunk_seconds: Optional[int] = None

class JobStatusPayload(BaseModel):
    job_id: UUID
    source_id: str
    status: Literal["queued","running","completed","failed"]
    progress: float = 0.0
    message: Optional[str] = None
    result: Optional[JobResult] = None

class ChunkMeta(BaseModel):
    index: int
    startSec: int
    endSec: int
    durationSec: int
    gcsUri: Optional[str] = None

class WebhookPayload(BaseModel):
    job_id: UUID
    source_id: str
    status: Literal["completed","failed"]
    chunks: Optional[List[str]] = None
    error: Optional[str] = None
    meta: Dict[str, Union[str, int, float, None]] = {}
    # Extended fields for Prisma alignment
    totalDurationSeconds: Optional[int] = None
    chunkSeconds: Optional[int] = None
    originalUri: Optional[str] = None  # e.g., the YouTube URL
    chunksMeta: Optional[List[ChunkMeta]] = None
