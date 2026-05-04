from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.core.database import init_db
from app.api.routes import router
from contextlib import asynccontextmanager
from pathlib import Path


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="Pax Venture", description="Business Simulation Game", version="0.1.0", lifespan=lifespan)

# CORS — open for dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(router, prefix="/api/v1")

# Serve frontend static files in production
frontend_dist = Path(__file__).parent.parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")


@app.get("/health")
async def health():
    return {"status": "ok", "game": "Pax Venture"}
