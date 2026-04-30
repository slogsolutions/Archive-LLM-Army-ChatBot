from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import ALLOWED_ORIGINS

# DB
from app.core.database import Base, engine

# MODELS (IMPORTANT: must import all so SQLAlchemy creates tables)
from app.models.user import User
from app.models.hq import HeadQuarter
from app.models.unit import Unit
from app.models.branch import Branch
from app.models.document import Document
from app.models.document_chunks import DocumentChunk
from app.models.rag_log import RAGLog  # noqa: F401 — registers table with SQLAlchemy
# from Archive.backend.app.api.routes import chat
from app.api.routes import chat

# ROUTES
from app.api.routes import auth, users, hq, unit, branch
from app.api.routes import documents
from app.api.routes import logs


app = FastAPI(title="Army Archive System")


@app.on_event("startup")
async def warm_embedder():
    import asyncio
    from app.rag.hw_config import print_summary
    print_summary()

    loop = asyncio.get_event_loop()
    from app.rag.embedding.embedder import get_model
    print("[STARTUP] Pre-loading embedding model…")
    await loop.run_in_executor(None, get_model)
    print("[STARTUP] Embedding model ready ✅")

# =========================
# CORS (for React later)
# =========================
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# ROUTES
# =========================
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(users.router, prefix="/users", tags=["users"])
app.include_router(hq.router, prefix="/hq", tags=["hq"])
app.include_router(unit.router, prefix="/unit", tags=["unit"])
app.include_router(branch.router, prefix="/branch", tags=["branch"])
app.include_router(documents.router, prefix="/documents", tags=["documents"])
app.include_router(chat.router, prefix="/chat", tags=["chat"])
app.include_router(logs.router, prefix="/logs", tags=["logs"])


# =========================
# HEALTH CHECKS
# =========================
@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/test")
def test():
    return {"message": "API working"}


# =========================
# CREATE TABLES (DEV ONLY)
# =========================
# Base.metadata.create_all(bind=engine)