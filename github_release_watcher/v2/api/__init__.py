from .auth import router as auth_router
from .events import router as events_router
from .jobs import router as jobs_router
from .repos import router as repos_router
from .settings import router as settings_router
from .storage import router as storage_router

__all__ = [
    "auth_router",
    "events_router",
    "jobs_router",
    "repos_router",
    "settings_router",
    "storage_router",
]
