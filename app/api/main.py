"""FastAPI application entrypoint."""

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from app.api.routes import router
from app.rag.node import get_default_retriever_pipeline


logger = logging.getLogger(__name__)


load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Warm retrieval resources before serving user requests."""
    try:
        pipeline = get_default_retriever_pipeline()
        pipeline.warm_dense_resources()
        pipeline.warm_lexical_index()
    except Exception as exc:
        logger.warning("Retriever warm-up failed during startup: %s", exc)
    yield

app = FastAPI(
    title="Government Document Helpdesk API",
    description="HTTP boundary for the Government Document Helpdesk application.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
