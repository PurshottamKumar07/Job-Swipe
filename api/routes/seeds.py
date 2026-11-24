"""
Seeds route
===========
GET /api/seeds — read current seed URLs
PUT /api/seeds — replace seed URLs
"""

import os
from fastapi import APIRouter, Depends
from api.schemas import SeedsUpdate, SeedsResponse

router = APIRouter()

_SEEDS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "seeds.txt",
)


@router.get("/seeds", response_model=SeedsResponse)
async def get_seeds():
    """Read the current seed URLs from seeds.txt."""
    urls: list[str] = []
    if os.path.exists(_SEEDS_PATH):
        with open(_SEEDS_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    urls.append(line)
    return SeedsResponse(urls=urls, file_path=_SEEDS_PATH)


@router.put("/seeds", response_model=SeedsResponse)
async def update_seeds(body: SeedsUpdate):
    """Replace the contents of seeds.txt with the provided URLs."""
    with open(_SEEDS_PATH, "w", encoding="utf-8") as f:
        f.write("# Seed URLs for crwlr (one per line)\n")
        f.write("# Updated via API\n\n")
        for url in body.urls:
            f.write(url.strip() + "\n")
    return SeedsResponse(urls=body.urls, file_path=_SEEDS_PATH)
