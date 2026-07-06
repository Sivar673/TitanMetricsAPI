from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import ai, auth, coach, tracking

app = FastAPI(title="Titan Metrics API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth.router)
app.include_router(tracking.router)
app.include_router(tracking.workouts_router)
app.include_router(coach.router)
app.include_router(ai.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
