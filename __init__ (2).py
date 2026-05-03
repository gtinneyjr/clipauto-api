from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.routers import youtube, clips, publishing, auth
from app.services.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    await start_scheduler()
    yield
    await stop_scheduler()


app = FastAPI(
    title="ClipAuto API",
    description="Automated YouTube → Short-form clip pipeline",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://yourfrontend.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router,       prefix="/auth",      tags=["Auth"])
app.include_router(youtube.router,    prefix="/youtube",   tags=["YouTube"])
app.include_router(clips.router,      prefix="/clips",     tags=["Clips"])
app.include_router(publishing.router, prefix="/publish",   tags=["Publishing"])


@app.get("/health")
async def health():
    return {"status": "ok"}
