"""
Job Alerts API Routes
=====================
Manage keyword and location-based job alerts, track active alerts,
and inspect matched live job postings.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from scripts.db import Database
from api.deps import get_db
from api.schemas import JobAlertCreate, JobAlertResponse, ExtractedJobResponse

router = APIRouter()


@router.get("/alerts", response_model=list[JobAlertResponse])
async def list_alerts(db: Database = Depends(get_db)):
    """List all configured job alerts with their live match counts."""
    alerts = db.get_job_alerts()
    return [
        JobAlertResponse(
            id=a["id"],
            keyword=a["keyword"],
            location=a.get("location"),
            frequency=a["frequency"],
            email=a["email"],
            is_active=bool(a["is_active"]),
            created_at=a["created_at"],
            last_sent_at=a.get("last_sent_at"),
            match_count=a.get("match_count", 0),
        )
        for a in alerts
    ]


@router.post("/alerts", response_model=JobAlertResponse, status_code=201)
async def create_alert(alert_in: JobAlertCreate, db: Database = Depends(get_db)):
    """Create a new keyword/location job alert."""
    alert_id = db.create_job_alert(
        keyword=alert_in.keyword,
        email=alert_in.email,
        location=alert_in.location,
        frequency=alert_in.frequency,
    )
    alert = db.get_job_alert(alert_id)
    if not alert:
        raise HTTPException(500, "Failed to retrieve created alert.")

    match_count = db.count_alert_matches(alert["keyword"], alert.get("location"))
    return JobAlertResponse(
        id=alert["id"],
        keyword=alert["keyword"],
        location=alert.get("location"),
        frequency=alert["frequency"],
        email=alert["email"],
        is_active=bool(alert["is_active"]),
        created_at=alert["created_at"],
        last_sent_at=alert.get("last_sent_at"),
        match_count=match_count,
    )


@router.get("/alerts/{alert_id}", response_model=JobAlertResponse)
async def get_alert(alert_id: int, db: Database = Depends(get_db)):
    """Retrieve details for a specific alert."""
    alert = db.get_job_alert(alert_id)
    if not alert:
        raise HTTPException(404, f"Alert #{alert_id} not found.")

    match_count = db.count_alert_matches(alert["keyword"], alert.get("location"))
    return JobAlertResponse(
        id=alert["id"],
        keyword=alert["keyword"],
        location=alert.get("location"),
        frequency=alert["frequency"],
        email=alert["email"],
        is_active=bool(alert["is_active"]),
        created_at=alert["created_at"],
        last_sent_at=alert.get("last_sent_at"),
        match_count=match_count,
    )


@router.patch("/alerts/{alert_id}/toggle")
async def toggle_alert(alert_id: int, db: Database = Depends(get_db)):
    """Toggle active/paused status of a job alert."""
    ok = db.toggle_job_alert(alert_id)
    if not ok:
        raise HTTPException(404, f"Alert #{alert_id} not found.")
    alert = db.get_job_alert(alert_id)
    return {
        "success": True,
        "id": alert_id,
        "is_active": bool(alert["is_active"]) if alert else False,
        "message": f"Alert is now {'active' if alert and alert['is_active'] else 'paused'}.",
    }


@router.delete("/alerts/{alert_id}")
async def delete_alert(alert_id: int, db: Database = Depends(get_db)):
    """Delete a job alert."""
    ok = db.delete_job_alert(alert_id)
    if not ok:
        raise HTTPException(404, f"Alert #{alert_id} not found.")
    return {"success": True, "message": f"Alert #{alert_id} deleted successfully."}


@router.get("/alerts/{alert_id}/matches", response_model=list[ExtractedJobResponse])
async def get_alert_matches(
    alert_id: int,
    limit: int = Query(20, ge=1, le=100),
    db: Database = Depends(get_db),
):
    """Retrieve active jobs currently discovered by the crawler that match this alert."""
    alert = db.get_job_alert(alert_id)
    if not alert:
        raise HTTPException(404, f"Alert #{alert_id} not found.")

    matches = db.get_alert_matches(alert_id, limit=limit)
    return [ExtractedJobResponse(**m) for m in matches]
