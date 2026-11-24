"""
crwlr REST API
==============
FastAPI application that exposes the full crawl → extract → query pipeline
over HTTP.  Background tasks handle crawling and extraction so API calls
return immediately.

Run:
    uvicorn api.main:app --reload
    # or
    python -m api.main
"""

from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

from scripts.db import Database
from api.routes import crawl, jobs, stats, seeds, auto_apply, alerts

_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "generated_resumes"
_OUTPUT_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Lifespan — open / close the database
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db = Database()
    yield
    app.state.db.close()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="crwlr API",
    description=(
        "REST API for the crwlr job-link discovery and extraction pipeline.\n\n"
        "**Workflow:** POST `/api/crawl` → POST `/api/extract` → GET `/api/jobs`"
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow all origins in dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers
app.include_router(crawl.router,  prefix="/api", tags=["Crawl"])
app.include_router(jobs.router,   prefix="/api", tags=["Jobs"])
app.include_router(stats.router,  prefix="/api", tags=["Stats"])
app.include_router(seeds.router,  prefix="/api", tags=["Seeds"])
app.include_router(auto_apply.router, prefix="/api/auto-apply", tags=["AutoApply"])
app.include_router(alerts.router, prefix="/api", tags=["Alerts"])

# Mount static resumes directory
app.mount("/resumes", StaticFiles(directory=_OUTPUT_DIR), name="resumes")


@app.get("/", tags=["Health"])
async def root():
    return {"status": "ok", "service": "crwlr", "version": "0.1.0"}


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Standalone runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
