"""
Unit and integration tests for the Auto-Apply system.
"""

import os
import sys
from pathlib import Path

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import pytest
from fastapi.testclient import TestClient

from api.main import app
from scripts.db import Database
from scripts.resume_builder import ResumeBuilder
from scripts.llm_assistant import LLMAssistant

# Ensure database is attached to app state for test client
app.state.db = Database()
client = TestClient(app)


def test_resume_builder_skill_matching():
    builder = ResumeBuilder()
    title = "Senior Python & FastAPI Engineer"
    jd = "Looking for a backend developer experienced with Python, FastAPI, Docker, PostgreSQL, and Kubernetes."
    match = builder.match_job(title, jd)

    assert match["match_score"] > 50
    assert "Python" in match["matched_skills"]
    assert "FastAPI" in match["matched_skills"]
    assert "Kubernetes" in match["missing_skills"]
    assert len(match["recommended_projects"]) > 0


def test_resume_builder_latex_and_html_generation():
    builder = ResumeBuilder()
    active_skills = ["Python", "FastAPI", "React", "Docker", "C# & .NET"]
    latex = builder.generate_latex_resume("Backend Developer & Engineer", "AT&T / Johnson & Johnson", active_skills)
    assert "\\begin{document}" in latex
    assert "Backend Developer \\& Engineer" in latex
    assert "AT\\&T / Johnson \\& Johnson" in latex
    assert "C\\# \\& .NET" in latex

    html = builder.generate_html_resume("Backend Developer", "Acme Corp", active_skills)
    assert "<!DOCTYPE html>" in html
    assert "Acme Corp" in html


def test_resume_builder_html_xss_prevention():
    builder = ResumeBuilder()
    malicious_title = '<script>alert("pwned")</script>'
    malicious_company = 'Acme <img src=x onerror=alert(1)> & Co.'
    malicious_skill = '<b>SQL Injection</b>'
    html = builder.generate_html_resume(malicious_title, malicious_company, [malicious_skill])
    assert "<script>" not in html
    assert "&lt;script&gt;alert(&quot;pwned&quot;)&lt;/script&gt;" in html
    assert "<img" not in html
    assert "&lt;img src=x onerror=alert(1)&gt; &amp; Co." in html
    assert "<b>SQL" not in html
    assert "&lt;b&gt;SQL Injection&lt;/b&gt;" in html


def test_llm_assistant_qa_bank():
    import asyncio
    assistant = LLMAssistant()
    ans1 = asyncio.run(assistant.answer_question("Are you legally authorized to work in India?"))
    assert ans1.lower() in ["yes", "true"]

    ans2 = asyncio.run(assistant.answer_question("Will you require visa sponsorship now or in the future?"))
    assert ans2.lower() in ["no", "false"]

    ans3 = asyncio.run(assistant.answer_question("How many years of experience do you have with Python?"))
    assert "2" in ans3


def test_auto_apply_api_profile():
    res = client.get("/api/auto-apply/profile")
    assert res.status_code == 200
    data = res.json()
    assert "personal" in data
    assert "skills" in data
    assert "qa_bank" in data


def test_auto_apply_api_profile_validation():
    # Invalid body: skills is not a list
    res_bad = client.put("/api/auto-apply/profile", json={"skills": "not-a-list"})
    assert res_bad.status_code == 422

    # Valid body
    res_good = client.get("/api/auto-apply/profile")
    current_data = res_good.json()
    res_put = client.put("/api/auto-apply/profile", json=current_data)
    assert res_put.status_code == 200
    assert res_put.json()["success"] is True


def test_auto_apply_api_session_status():
    res = client.get("/api/auto-apply/session")
    assert res.status_code == 200
    data = res.json()
    assert "status" in data
    assert "daily_applied_today" in data
    assert "daily_cap" in data


def test_job_alerts_crud_api():
    # 1. Create alert
    payload = {
        "keyword": "Python",
        "location": "Remote",
        "frequency": "Instant",
        "email": "test@example.com",
    }
    create_res = client.post("/api/alerts", json=payload)
    assert create_res.status_code == 201
    alert = create_res.json()
    alert_id = alert["id"]
    assert alert["keyword"] == "Python"
    assert alert["is_active"] is True

    # 2. List alerts
    list_res = client.get("/api/alerts")
    assert list_res.status_code == 200
    alerts = list_res.json()
    assert any(a["id"] == alert_id for a in alerts)

    # 3. Toggle alert
    toggle_res = client.patch(f"/api/alerts/{alert_id}/toggle")
    assert toggle_res.status_code == 200
    assert toggle_res.json()["is_active"] is False

    # 4. Get matches
    matches_res = client.get(f"/api/alerts/{alert_id}/matches?limit=5")
    assert matches_res.status_code == 200
    assert isinstance(matches_res.json(), list)

    # 5. Delete alert
    del_res = client.delete(f"/api/alerts/{alert_id}")
    assert del_res.status_code == 200
    assert del_res.json()["success"] is True


def test_analytics_api():
    res = client.get("/api/analytics")
    assert res.status_code == 200
    data = res.json()
    assert "total_jobs" in data
    assert "funnel" in data
    assert "applied" in data["funnel"]
    assert "interview" in data["funnel"]
    assert "daily_applications" in data
    assert "salary_stats" in data
    assert "top_companies" in data
    assert "top_locations" in data


def test_qwen_llm_assistant_configuration():
    assistant = LLMAssistant()
    assert assistant.model == "Qwen/Qwen2.5-3B-Instruct"


def test_resume_builder_ai_tailoring():
    import asyncio
    builder = ResumeBuilder()
    active_skills = ["Python", "FastAPI", "Docker"]
    ai_data = asyncio.run(builder.tailor_with_ai(
        job_title="Senior Python Backend Engineer",
        company="TechCorp",
        job_description="Seeking a Python developer experienced with FastAPI, Docker, and PostgreSQL microservices.",
        active_skills=active_skills,
    ))
    assert "summary" in ai_data
    assert "experience" in ai_data
    assert "cover_letter" in ai_data
    assert "TechCorp" in ai_data["cover_letter"]


def test_api_tailor_and_download_resume():
    # Insert a dummy job into DB
    db = Database()
    job_id = db.insert_extracted_job(
        source_url="https://example.com/jobs/qwen-engineer",
        title="AI Engineer (Qwen)",
        company="DeepTech AI",
        description="Looking for an AI engineer to work with Qwen2.5 and open-source LLMs.",
        apply_url="https://example.com/apply/qwen",
    )

    # 1. Test POST /api/auto-apply/tailor/{job_id}
    tailor_res = client.post(f"/api/auto-apply/tailor/{job_id}")
    assert tailor_res.status_code == 200
    t_data = tailor_res.json()
    assert t_data["job_id"] == job_id
    assert t_data["model_used"] == "Qwen/Qwen2.5-3B-Instruct"
    assert "tailored_summary" in t_data
    assert "cover_letter" in t_data

    # 2. Test POST /api/auto-apply/generate-resume/{job_id}
    gen_res = client.post(f"/api/auto-apply/generate-resume/{job_id}?use_ai=true")
    assert gen_res.status_code == 200
    g_data = gen_res.json()
    assert g_data["job_id"] == job_id
    assert g_data["pdf_filename"].endswith(".pdf") or g_data["pdf_filename"].endswith(".html")
    assert "/api/auto-apply/resumes/" in g_data["pdf_url"]

    # 3. Test GET /api/auto-apply/resumes/{filename}
    filename = g_data["pdf_filename"]
    dl_res = client.get(f"/api/auto-apply/resumes/{filename}")
    assert dl_res.status_code == 200
    assert len(dl_res.content) > 0


