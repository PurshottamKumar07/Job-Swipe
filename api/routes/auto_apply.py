"""
Auto-Apply API Routes
=====================
Controls the Playwright auto-apply engine, profile management,
skill matching reviews, and CAPTCHA/human-in-the-loop interactions.
"""

import json
import asyncio
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from scripts.db import Database
from scripts.resume_builder import ResumeBuilder
from scripts.auto_apply import AutoApplyEngine
from api.deps import get_db
from api.schemas import (
    AutoApplyStartRequest,
    AutoApplyActionRequest,
    AutoApplyMatchResponse,
    AutoApplySessionResponse,
    AutoApplyLogResponse,
    ProfileUpdateRequest,
    TailorResumeResponse,
    GenerateResumeResponse,
)

router = APIRouter()

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_PROFILE_PATH = _REPO_ROOT / "profile.json"
_OUTPUT_DIR = _REPO_ROOT / "generated_resumes"
_OUTPUT_DIR.mkdir(exist_ok=True)

# Global active engine instance
_active_engine: AutoApplyEngine | None = None
_active_task: asyncio.Task | None = None


def get_engine(db: Database = Depends(get_db)) -> AutoApplyEngine:
    global _active_engine
    if _active_engine is None:
        _active_engine = AutoApplyEngine(db=db, profile_path=_PROFILE_PATH)
    else:
        _active_engine.db = db
    return _active_engine


# ---------------------------------------------------------------------------
# Profile Management
# ---------------------------------------------------------------------------

@router.get("/profile")
async def get_profile():
    """Retrieve user's master profile.json."""
    if not _PROFILE_PATH.exists():
        raise HTTPException(404, "profile.json does not exist yet.")
    with open(_PROFILE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@router.put("/profile")
async def update_profile(req: ProfileUpdateRequest, engine: AutoApplyEngine = Depends(get_engine)):
    """Update user's master profile.json with schema validation."""
    data = req.model_dump()
    with open(_PROFILE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    engine.profile = data
    engine.resume_builder.profile = data
    engine.llm.profile = data
    return {"success": True, "message": "Profile updated successfully."}


# ---------------------------------------------------------------------------
# Skill Matching & Tailoring
# ---------------------------------------------------------------------------

@router.post("/match/{job_id}", response_model=AutoApplyMatchResponse)
async def match_job_skills(job_id: int, db: Database = Depends(get_db)):
    """Calculate match score and skill breakdown for a specific job."""
    job = db.get_extracted_job_by_id(job_id)
    if not job:
        raise HTTPException(404, f"Job #{job_id} not found.")

    builder = ResumeBuilder(_PROFILE_PATH)
    title = job.get("title") or "Software Engineer"
    desc = job.get("description") or ""
    company = job.get("company") or "Company"

    match_data = builder.match_job(title, desc)
    cover_letter = builder.generate_cover_letter(title, company, match_data["matched_skills"])

    return AutoApplyMatchResponse(
        job_id=job_id,
        job_title=title,
        company=company,
        match_score=match_data["match_score"],
        matched_skills=match_data["matched_skills"],
        missing_skills=match_data["missing_skills"],
        all_user_skills=match_data["all_user_skills"],
        recommended_projects=match_data["recommended_projects"],
        cover_letter_preview=cover_letter,
    )


@router.post("/tailor/{job_id}", response_model=TailorResumeResponse)
async def tailor_resume_content(job_id: int, db: Database = Depends(get_db)):
    """
    Use Qwen2.5-3B-Instruct to craft tailored summary, experience bullets,
    and cover letter based on the target job requirements.
    """
    job = db.get_extracted_job_by_id(job_id)
    if not job:
        raise HTTPException(404, f"Job #{job_id} not found.")

    builder = ResumeBuilder(_PROFILE_PATH)
    title = job.get("title") or "Software Engineer"
    desc = job.get("description") or ""
    company = job.get("company") or "Company"

    match_data = builder.match_job(title, desc)
    matched_skills = match_data.get("matched_skills") or match_data.get("all_user_skills")[:6]

    ai_data = await builder.tailor_with_ai(
        job_title=title,
        company=company,
        job_description=desc,
        active_skills=matched_skills,
    )

    return TailorResumeResponse(
        job_id=job_id,
        job_title=title,
        company=company,
        match_score=match_data["match_score"],
        matched_skills=match_data["matched_skills"],
        missing_skills=match_data["missing_skills"],
        tailored_summary=ai_data["summary"],
        tailored_experience=ai_data["experience"],
        cover_letter=ai_data["cover_letter"],
        model_used=builder.llm.model,
    )


@router.post("/generate-resume/{job_id}", response_model=GenerateResumeResponse)
async def generate_resume_document(
    job_id: int,
    use_ai: bool = Query(True, description="Use Qwen2.5-3B-Instruct to tailor summary and bullets"),
    db: Database = Depends(get_db),
):
    """
    Generate tailored .tex, .html, and compile PDF resume for a specific job.
    Returns download URLs for the generated PDF and LaTeX files.
    """
    job = db.get_extracted_job_by_id(job_id)
    if not job:
        raise HTTPException(404, f"Job #{job_id} not found.")

    builder = ResumeBuilder(_PROFILE_PATH)
    title = job.get("title") or "Software Engineer"
    desc = job.get("description") or ""
    company = job.get("company") or "Company"

    match_data = builder.match_job(title, desc)
    matched_skills = match_data.get("matched_skills") or match_data.get("all_user_skills")[:6]

    docs = await builder.generate_documents(
        job_id=job_id,
        job_title=title,
        company=company,
        active_skills=matched_skills,
        selected_projects=match_data.get("recommended_projects"),
        job_description=desc,
        use_ai=use_ai,
    )

    pdf_filename = docs["pdf_filename"]
    tex_filename = docs["tex_filename"]

    return GenerateResumeResponse(
        job_id=job_id,
        job_title=title,
        company=company,
        pdf_filename=pdf_filename,
        pdf_url=f"/api/auto-apply/resumes/{pdf_filename}",
        tex_filename=tex_filename,
        tex_url=f"/api/auto-apply/resumes/{tex_filename}",
        summary_used=docs["summary_used"],
        cover_letter=docs["cover_letter"],
    )


@router.get("/resumes/{filename}")
async def download_resume_document(filename: str):
    """Download or preview a generated PDF, LaTeX, or HTML resume."""
    # Prevent path traversal
    safe_name = Path(filename).name
    target_path = _OUTPUT_DIR / safe_name
    if not target_path.exists():
        raise HTTPException(404, f"File {safe_name} not found.")

    media_type = "application/pdf" if safe_name.endswith(".pdf") else "text/plain"
    return FileResponse(path=target_path, filename=safe_name, media_type=media_type)



# ---------------------------------------------------------------------------
# Session Control
# ---------------------------------------------------------------------------

@router.post("/start")
async def start_auto_apply(
    req: AutoApplyStartRequest,
    engine: AutoApplyEngine = Depends(get_engine),
):
    """Start an automated application batch session."""
    global _active_task

    if engine.status in ("running", "paused_skill_review", "paused_captcha"):
        raise HTTPException(400, "An auto-apply session is already active.")

    async def _runner():
        try:
            await engine.run_session(job_ids=req.job_ids, max_apps=req.max_applications)
        except Exception as e:
            print(f"[auto_apply error] {e}")
            await engine.log("error", f"Session aborted: {e}")
            engine.status = "failed"

    _active_task = asyncio.create_task(_runner())

    return {
        "success": True,
        "message": f"Auto-Apply session initiated for up to {req.max_applications} jobs.",
    }


@router.post("/single/{job_id}")
async def apply_single_job(
    job_id: int,
    engine: AutoApplyEngine = Depends(get_engine),
):
    """Trigger auto-apply for one specific job."""
    global _active_task

    if engine.status in ("running", "paused_skill_review", "paused_captcha"):
        raise HTTPException(400, "An auto-apply session is already active.")

    async def _runner():
        try:
            await engine.run_session(job_ids=[job_id], max_apps=1)
        except Exception as e:
            print(f"[auto_apply error] {e}")
            await engine.log("error", f"Single job apply error: {e}")
            engine.status = "failed"

    _active_task = asyncio.create_task(_runner())

    return {
        "success": True,
        "message": f"Auto-Apply started for Job #{job_id}.",
    }


@router.get("/session", response_model=AutoApplySessionResponse)
async def get_session_status(db: Database = Depends(get_db), engine: AutoApplyEngine = Depends(get_engine)):
    """Retrieve active session state, current job, pause reason, and daily count."""
    sess = None
    if engine.session_id:
        sess = db.get_auto_apply_session(engine.session_id)
    if not sess:
        sess = db.get_latest_auto_apply_session()

    applied_today = db.count_applications_today()
    daily_cap = engine.profile.get("settings", {}).get("max_daily_applications", 15)

    current_job_dict = None
    if engine.current_job:
        current_job_dict = engine.current_job
    elif sess and sess.get("current_job_id"):
        current_job_dict = db.get_extracted_job_by_id(sess["current_job_id"])

    parsed_pause_data = None
    if sess and sess.get("pause_data"):
        try:
            parsed_pause_data = json.loads(sess["pause_data"])
        except Exception:
            pass

    return AutoApplySessionResponse(
        id=sess.get("id") if sess else None,
        status=engine.status if engine.status != "idle" else (sess.get("status") if sess else "idle"),
        started_at=sess.get("started_at") if sess else None,
        finished_at=sess.get("finished_at") if sess else None,
        total_jobs=sess.get("total_jobs", 0) if sess else 0,
        applied_jobs=sess.get("applied_jobs", 0) if sess else 0,
        failed_jobs=sess.get("failed_jobs", 0) if sess else 0,
        skipped_jobs=sess.get("skipped_jobs", 0) if sess else 0,
        current_job_id=sess.get("current_job_id") if sess else None,
        current_job=current_job_dict,
        pause_data=parsed_pause_data,
        daily_applied_today=applied_today,
        daily_cap=daily_cap,
    )


@router.post("/action")
async def resume_session_action(
    req: AutoApplyActionRequest,
    engine: AutoApplyEngine = Depends(get_engine),
):
    """Submit user feedback for paused state (approve skills, solve captcha, or skip)."""
    if engine.status not in ("paused_skill_review", "paused_captcha"):
        raise HTTPException(400, f"Cannot perform action; engine is in state '{engine.status}'.")

    engine.resume_from_user(action=req.action, approved_skills=req.approved_skills)
    return {
        "success": True,
        "action": req.action,
        "message": f"Action '{req.action}' submitted. Resuming automation...",
    }


@router.post("/stop")
async def stop_session(engine: AutoApplyEngine = Depends(get_engine)):
    """Request running session to gracefully stop."""
    if engine.status not in ("running", "paused_skill_review", "paused_captcha"):
        return {"success": True, "message": "No active session to stop."}

    engine.request_stop()
    return {"success": True, "message": "Stop requested. Automation will finish or halt current task."}


@router.get("/logs", response_model=list[AutoApplyLogResponse])
async def list_logs(limit: int = Query(50, ge=1, le=200), db: Database = Depends(get_db)):
    """List recent auto-apply logs."""
    logs = db.get_auto_apply_logs(limit=limit)
    return [AutoApplyLogResponse(**l) for l in logs]
