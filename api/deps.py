"""
FastAPI dependencies — shared across all route modules.
"""

from fastapi import Request
from scripts.db import Database


def get_db(request: Request) -> Database:
    """Return the application-wide Database instance."""
    return request.app.state.db
