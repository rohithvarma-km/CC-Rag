from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth import CurrentUser, get_current_user
from app.config import get_settings
from app.routers import chat, documents, threads

app = FastAPI(title="Agentic RAG")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in get_settings().cors_origins.split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(threads.router)
app.include_router(chat.router)
app.include_router(documents.router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/me")
def me(user: CurrentUser = Depends(get_current_user)):
    return {"id": user.id, "email": user.email}
