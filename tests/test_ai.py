import base64
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.routers.ai as ai_router
from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.models import PhysiqueEvaluationRecord, User
from app.schemas import PhysiqueEvaluation
from app.security import hash_password
from app.services.physique_ai import PhysiqueAIError

PASSWORD = "titan123"

# Smallest valid 1x1 PNG.
TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGBg"
    "AAAABQABh6FO1AAAAABJRU5ErkJggg=="
)

FAKE_EVALUATION = PhysiqueEvaluation(
    is_valid_submission=True,
    validity_notes=None,
    overall_score=7,
    strengths=["Strong shoulder-to-waist ratio"],
    weaknesses=["Rear delts lag the front delts"],
    training_adjustments=["Add 3 weekly sets of reverse pec-deck"],
)


@pytest.fixture()
def sessionmaker_(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
    )
    TestingSession = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    return TestingSession


@pytest.fixture()
def client(tmp_path, sessionmaker_, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))

    db = sessionmaker_()
    password_hash = hash_password(PASSWORD)
    db.add(
        User(id="c_1", email="marcus@example.com", password_hash=password_hash,
             display_name="Marcus T.", role="client", phase="prep", weeks_out=8)
    )
    db.add(
        User(id="c_2", email="devon@example.com", password_hash=password_hash,
             display_name="Devon R.", role="client", phase="off_season")
    )
    db.commit()
    db.close()

    def override_get_db():
        session = sessionmaker_()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def auth_header(client: TestClient) -> dict:
    res = client.post(
        "/auth/login", json={"email": "marcus@example.com", "password": PASSWORD}
    )
    return {"Authorization": f"Bearer {res.json()['token']}"}


def pose_files(front=TINY_PNG, side=TINY_PNG, back=TINY_PNG, media="image/png"):
    return {
        "front": ("front.png", front, media),
        "side": ("side.png", side, media),
        "back": ("back.png", back, media),
    }


def test_requires_auth(client):
    res = client.post("/ai/physique-evaluation", files=pose_files())
    assert res.status_code == 401


def test_returns_structured_evaluation(client, monkeypatch):
    monkeypatch.setattr(ai_router, "evaluate_physique", lambda images: FAKE_EVALUATION)
    res = client.post(
        "/ai/physique-evaluation", files=pose_files(), headers=auth_header(client)
    )
    assert res.status_code == 200
    body = res.json()
    assert body["overall_score"] == 7
    assert body["is_valid_submission"] is True
    assert body["training_adjustments"] == ["Add 3 weekly sets of reverse pec-deck"]


def test_service_receives_poses_in_order(client, monkeypatch):
    captured = {}

    def fake_evaluate(images):
        captured["poses"] = [pose for pose, _, _ in images]
        captured["types"] = [mt for _, _, mt in images]
        return FAKE_EVALUATION

    monkeypatch.setattr(ai_router, "evaluate_physique", fake_evaluate)
    client.post("/ai/physique-evaluation", files=pose_files(), headers=auth_header(client))
    assert captured["poses"] == ["front", "side", "back"]
    assert captured["types"] == ["image/png"] * 3

def test_rejects_wrong_content_type(client):
    res = client.post(
        "/ai/physique-evaluation",
        files=pose_files(media="application/pdf"),
        headers=auth_header(client),
    )
    assert res.status_code == 400
    assert "front image" in res.json()["detail"]


def test_rejects_oversized_image(client, monkeypatch):
    monkeypatch.setattr(ai_router, "MAX_IMAGE_BYTES", 10)
    res = client.post(
        "/ai/physique-evaluation", files=pose_files(), headers=auth_header(client)
    )
    assert res.status_code == 413


def test_missing_pose_is_422(client):
    files = pose_files()
    del files["back"]
    res = client.post(
        "/ai/physique-evaluation", files=files, headers=auth_header(client)
    )
    assert res.status_code == 422  # FastAPI validation: missing required file


def test_unconfigured_provider_maps_to_503(client, monkeypatch):
    def fake_evaluate(images):
        raise PhysiqueAIError("AI Physique Coach is not configured", status_code=503)

    monkeypatch.setattr(ai_router, "evaluate_physique", fake_evaluate)
    res = client.post(
        "/ai/physique-evaluation", files=pose_files(), headers=auth_header(client)
    )
    assert res.status_code == 503


# ---- Persistence + history ----


def test_successful_evaluation_is_persisted(client, sessionmaker_, monkeypatch, tmp_path):
    monkeypatch.setattr(ai_router, "evaluate_physique", lambda images: FAKE_EVALUATION)
    res = client.post(
        "/ai/physique-evaluation", files=pose_files(), headers=auth_header(client)
    )
    assert res.status_code == 200

    db = sessionmaker_()
    row = db.query(PhysiqueEvaluationRecord).one()
    assert row.user_id == "c_1"
    assert row.overall_score == 7.0
    assert row.strengths == FAKE_EVALUATION.strengths
    # Images landed on disk at the stored relative paths
    for rel in (row.front_image_path, row.side_image_path, row.back_image_path):
        assert (tmp_path / "uploads" / rel).exists()
    db.close()


def test_failed_evaluation_is_not_persisted(client, sessionmaker_, monkeypatch):
    def fake_evaluate(images):
        raise PhysiqueAIError("provider down", status_code=502)

    monkeypatch.setattr(ai_router, "evaluate_physique", fake_evaluate)
    client.post("/ai/physique-evaluation", files=pose_files(), headers=auth_header(client))

    db = sessionmaker_()
    assert db.query(PhysiqueEvaluationRecord).count() == 0
    db.close()


def _insert_record(db, user_id: str, created_at: str, score: float = 6.0):
    db.add(
        PhysiqueEvaluationRecord(
            user_id=user_id,
            created_at=created_at,
            front_image_path="x/f.png",
            side_image_path="x/s.png",
            back_image_path="x/b.png",
            is_valid_submission=1,
            validity_notes=None,
            overall_score=score,
            strengths=["s"],
            weaknesses=["w"],
            training_adjustments=["t"],
        )
    )


def test_history_is_own_records_newest_first(client, sessionmaker_):
    now = datetime.now(timezone.utc)
    db = sessionmaker_()
    _insert_record(db, "c_1", (now - timedelta(days=14)).isoformat(), score=5.0)
    _insert_record(db, "c_1", (now - timedelta(days=7)).isoformat(), score=6.5)
    _insert_record(db, "c_2", (now - timedelta(days=3)).isoformat(), score=9.0)
    db.commit()
    db.close()

    res = client.get("/ai/evaluations", headers=auth_header(client))
    assert res.status_code == 200
    scores = [item["overall_score"] for item in res.json()]
    assert scores == [6.5, 5.0]  # newest first, c_2's record excluded


def test_history_requires_auth(client):
    assert client.get("/ai/evaluations").status_code == 401


# ---- Rate limiting ----


def test_daily_limit_blocks_third_evaluation(client, sessionmaker_, monkeypatch):
    monkeypatch.setattr(ai_router, "evaluate_physique", lambda images: FAKE_EVALUATION)
    headers = auth_header(client)

    for _ in range(settings.ai_daily_evaluation_limit):
        res = client.post("/ai/physique-evaluation", files=pose_files(), headers=headers)
        assert res.status_code == 200

    res = client.post("/ai/physique-evaluation", files=pose_files(), headers=headers)
    assert res.status_code == 429
    assert "Daily limit reached" in res.json()["detail"]


def test_old_evaluations_do_not_count_toward_limit(client, sessionmaker_, monkeypatch):
    monkeypatch.setattr(ai_router, "evaluate_physique", lambda images: FAKE_EVALUATION)
    stale = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    db = sessionmaker_()
    for _ in range(5):
        _insert_record(db, "c_1", stale)
    db.commit()
    db.close()

    res = client.post(
        "/ai/physique-evaluation", files=pose_files(), headers=auth_header(client)
    )
    assert res.status_code == 200


def test_limit_is_per_user(client, sessionmaker_, monkeypatch):
    monkeypatch.setattr(ai_router, "evaluate_physique", lambda images: FAKE_EVALUATION)
    recent = datetime.now(timezone.utc).isoformat()
    db = sessionmaker_()
    for _ in range(settings.ai_daily_evaluation_limit):
        _insert_record(db, "c_2", recent)  # Devon exhausted his limit
    db.commit()
    db.close()

    # Marcus is unaffected
    res = client.post(
        "/ai/physique-evaluation", files=pose_files(), headers=auth_header(client)
    )
    assert res.status_code == 200
