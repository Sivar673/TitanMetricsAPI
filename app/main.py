from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import Base, engine
from app.routers import auth, coach, tracking

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Titan Metrics API", version="0.1.0")

# Dev CORS: the Expo web preview runs on a different origin (localhost:8081).
# Lock this down to real origins before deploying.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(tracking.router)
app.include_router(tracking.workouts_router)
app.include_router(coach.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
