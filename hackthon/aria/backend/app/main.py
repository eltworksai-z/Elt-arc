import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agents.session import configure_sdk
from app.api import evals, knowledge, sessions, system
from app.core.config import get_settings
from app.core.db import init_db
from app.memory.temporal_store import seed_history_if_empty
from app.rag.index import sync_manuals_folder

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("aria")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    init_db()
    configure_sdk()
    seeded = seed_history_if_empty()
    if seeded:
        logger.info("Seeded %d simulated history incidents", seeded)
    try:
        indexed = await sync_manuals_folder()
        if indexed:
            logger.info("Indexed manuals: %s", [d["title"] for d in indexed])
    except Exception:
        logger.exception("Manual indexing failed; continuing without new documents")
    if not settings.has_api_key:
        logger.warning("OPENAI_API_KEY is not set. Voice, agent and embedding features are disabled until it is added.")
    yield


app = FastAPI(title="ARIA backend", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in get_settings().cors_origins.split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)
for router in (system.router, sessions.router, knowledge.router, evals.router):
    app.include_router(router)
