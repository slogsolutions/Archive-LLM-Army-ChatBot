from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# DB
from app.core.database import Base, engine

# MODELS (IMPORTANT: must import all)
from app.models.user import User
from app.models.hq import HeadQuarter
from app.models.unit import Unit
from app.models.branch import Branch

# ROUTES
from app.api.routes import auth, users, hq, unit, branch

app = FastAPI(title="Army Archive System")

# =========================
# CORS (for React later)
# =========================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # later restrict
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
Base.metadata.create_all(bind=engine)