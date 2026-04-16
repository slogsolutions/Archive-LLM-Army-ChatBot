from fastapi import FastAPI
from app.api.routes import auth

app = FastAPI()


# Routes
app.include_router(auth.router, prefix="/auth", tags=["auth"])


# endPoints
@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/test")
def test():
    return{"tested"}


from app.core.database import Base, engine
from app.models.user import User

Base.metadata.create_all(bind=engine)    