"""
Stats route
===========
GET /api/stats — aggregate statistics
"""

from fastapi import APIRouter, Depends
from scripts.db import Database
from api.deps import get_db
from api.schemas import StatsResponse, AnalyticsResponse

router = APIRouter()


@router.get("/stats", response_model=StatsResponse)
async def get_stats(db: Database = Depends(get_db)):
    """Return aggregate statistics across all crawl data."""
    stats = db.get_stats()
    return StatsResponse(**stats)


@router.get("/analytics", response_model=AnalyticsResponse)
async def get_analytics(db: Database = Depends(get_db)):
    """Return rich aggregate analytics across application funnel, daily volume, and crawl metrics."""
    analytics_data = db.get_analytics_summary()
    return AnalyticsResponse(**analytics_data)
