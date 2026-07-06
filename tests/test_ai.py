import base64

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.routers.ai as ai_router
from app.database import Base, get_db
from app.main import app
from app.models import User
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
def client(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
    )
    TestingSession = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = TestingSession()
    db.add(
        User(id="c_1", email="marcus@example.com", password_hash=hash_password(PASSWORD),
             display_name="Marcus T.", role="client", phase="prep", weeks_out=8)
    )
    db.commit()
    db.close()

    def override_get_db():
        session = TestingSession()
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
