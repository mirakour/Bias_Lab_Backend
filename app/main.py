from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.db import engine, Base
from app.utils.config import CORS_ORIGINS
from app.routes.articles import router as articles_router
from app.routes.narrative import router as narratives_router
from app.routes.highlights import router as highlights_router
from app.routes.analyze import router as analyze_router

app = FastAPI()

origins = [
    "https://biaslab.netlify.app",
    "http://localhost:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    return {"status": "ok"}

app.include_router(articles_router)
app.include_router(narratives_router)
app.include_router(highlights_router)
app.include_router(analyze_router)

@app.on_event("startup")
async def on_startup():
    # Create tables (dev-only)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
