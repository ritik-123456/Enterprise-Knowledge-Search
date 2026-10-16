import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.rag import router as rag_router
from app.api.auth import router as auth_router
from app.api.chats import router as chats_router

app = FastAPI(
    title="Enterprise Knowledge Search",
    description="AI-powered enterprise document search API",
    version="0.1.0",
)

allowed_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://localhost:5174",
    "https://enterprise-knowledge-search.vercel.app",
]

frontend_env_url = os.getenv("FRONTEND_URL")
if frontend_env_url and frontend_env_url.strip():
    allowed_origins.append(frontend_env_url.strip().rstrip("/"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?|https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

app.include_router(auth_router, prefix="/api")
app.include_router(rag_router, prefix="/api")
app.include_router(chats_router, prefix="/api")



@app.get("/")
def root():
    return {
        "message": "Enterprise Knowledge Search API",
        "docs": "/docs",
    }


@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "service": "enterprise-knowledge-search",
    }
# Cross-page chunking & sync updated



