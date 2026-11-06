"""Server-Auslastung mit Verlauf – nur für den Super-Admin (admin.<Plattform-Domain>)."""
from dataclasses import asdict
from datetime import UTC

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_current_super_admin_principal
from app.config import settings
from app.db import get_db
from app.schemas.server_metrics import (
    ServerMetricPointResponse,
    ServerMetricsRange,
    ServerMetricsResponse,
    ServerSnapshotResponse,
)
from app.services import server_metrics

router = APIRouter(tags=["platform"])


@router.get("/platform/server-metrics", response_model=ServerMetricsResponse)
async def get_server_metrics(
    range_key: ServerMetricsRange = Query(default="24h", alias="range"),
    actor: Actor = Depends(get_current_super_admin_principal),
    db: AsyncSession = Depends(get_db),
) -> ServerMetricsResponse:
    snapshot = await server_metrics.live_snapshot(disk_path=settings.server_metrics_disk_path)
    bucket, points = await server_metrics.history(db, range_key)
    return ServerMetricsResponse(
        range=range_key,
        bucket_minutes=int(bucket.total_seconds() // 60),
        interval_seconds=settings.server_metrics_interval_seconds,
        retention_days=settings.server_metrics_retention_days,
        current=ServerSnapshotResponse(**asdict(snapshot)) if snapshot is not None else None,
        points=[
            ServerMetricPointResponse(**{**asdict(point), "at": point.at.replace(tzinfo=UTC)}) for point in points
        ],
    )
