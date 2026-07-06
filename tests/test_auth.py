import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models import User
from app.security import hash_password

PASSWORD = "titan123"

CHECK_IN = {
    "week_start": "2026-07-06",
    "morning_weights_lbs": [182.0, 181.6, None, 181.2, None, None, None],
    "macro_adherent_days": 6,
    "fatigue": {
        "sleep_quality": 4,
        "muscle_soreness": 3,
        "training_motivation": 4,
        "hunger": 3,
        "stress": 2,
    },
    "notes": None,
}


@pytest.fixture()
def client(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
    )
    TestingSession = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = TestingSession()
    password_hash = hash_password(PASSWORD)
    db.add_all(
        [
            User(id="c_1", email="marcus@example.com", password_hash=password_hash,
                 display_name="Marcus T.", role="client", phase="prep", weeks_out=8),
            User(id="c_2", email="devon@example.com", password_hash=password_hash,
                 display_name="Devon R.", role="client", phase="off_season"),
            User(id="coach_1", email="coach@titanmetrics.com", password_hash=password_hash,
                 display_name="Coach Rithish", role="coach"),
        ]
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


def auth_header(client: TestClient, email: str) -> dict:
    res = client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['token']}"}


# ---- Login ----


def test_login_success_returns_token_and_user(client):
    res = client.post("/auth/login", json={"email": "marcus@example.com", "password": PASSWORD})
    assert res.status_code == 200
    body = res.json()
    assert body["token"]
    assert body["user"] == {
        "id": "c_1",
        "email": "marcus@example.com",
        "display_name": "Marcus T.",
        "role": "client",
    }


def test_login_wrong_password_is_401(client):
    res = client.post("/auth/login", json={"email": "marcus@example.com", "password": "nope"})
    assert res.status_code == 401


def test_login_unknown_email_is_401_with_same_message(client):
    wrong_pw = client.post("/auth/login", json={"email": "marcus@example.com", "password": "nope"})
    unknown = client.post("/auth/login", json={"email": "ghost@example.com", "password": PASSWORD})
    assert unknown.status_code == 401
    assert unknown.json()["detail"] == wrong_pw.json()["detail"]  # no user enumeration


# ---- Signup ----

SIGNUP = {"email": "new@example.com", "password": "hypertrophy1", "display_name": "New Guy"}


def test_signup_creates_client_and_logs_in(client):
    res = client.post("/auth/signup", json=SIGNUP)
    assert res.status_code == 201
    body = res.json()
    assert body["token"]
    assert body["user"]["role"] == "client"
    assert body["user"]["display_name"] == "New Guy"

    # The returned token is immediately usable
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {body['token']}"})
    assert me.status_code == 200
    assert me.json()["email"] == "new@example.com"


def test_signup_then_login_works(client):
    client.post("/auth/signup", json=SIGNUP)
    res = client.post(
        "/auth/login", json={"email": "new@example.com", "password": "hypertrophy1"}
    )
    assert res.status_code == 200


def test_signup_duplicate_email_is_400(client):
    client.post("/auth/signup", json=SIGNUP)
    res = client.post("/auth/signup", json={**SIGNUP, "display_name": "Impostor"})
    assert res.status_code == 400
    assert res.json()["detail"] == "Email already in use."


def test_signup_email_is_case_insensitive(client):
    # marcus@example.com is seeded — different casing must still collide
    res = client.post(
        "/auth/signup",
        json={"email": "MARCUS@example.com", "password": "hypertrophy1", "display_name": "M"},
    )
    assert res.status_code == 400


def test_signup_rejects_short_password_and_bad_email(client):
    assert (
        client.post(
            "/auth/signup",
            json={"email": "a@b.com", "password": "short", "display_name": "X"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/auth/signup",
            json={"email": "not-an-email", "password": "hypertrophy1", "display_name": "X"},
        ).status_code
        == 422
    )


# ---- Roster guard ----


def test_roster_requires_auth(client):
    assert client.get("/coach/clients").status_code == 401


def test_roster_rejects_garbage_token(client):
    res = client.get("/coach/clients", headers={"Authorization": "Bearer not-a-jwt"})
    assert res.status_code == 401


def test_roster_forbidden_for_clients(client):
    res = client.get("/coach/clients", headers=auth_header(client, "marcus@example.com"))
    assert res.status_code == 403


def test_roster_ok_for_coach(client):
    res = client.get("/coach/clients", headers=auth_header(client, "coach@titanmetrics.com"))
    assert res.status_code == 200
    assert {c["id"] for c in res.json()} == {"c_1", "c_2"}


# ---- Ownership on writes ----


def test_client_can_submit_own_check_in(client):
    res = client.post(
        "/check-ins",
        json={"client_id": "c_1", **CHECK_IN},
        headers=auth_header(client, "marcus@example.com"),
    )
    assert res.status_code == 201
    assert res.json()["weekly_avg_weight_lbs"] == pytest.approx(181.6, abs=0.01)


def test_client_cannot_submit_for_someone_else(client):
    res = client.post(
        "/check-ins",
        json={"client_id": "c_2", **CHECK_IN},
        headers=auth_header(client, "marcus@example.com"),
    )
    assert res.status_code == 403


def test_check_in_requires_auth(client):
    res = client.post("/check-ins", json={"client_id": "c_1", **CHECK_IN})
    assert res.status_code == 401


# ---- Ownership on reads ----


def test_client_reads_own_report_but_not_others(client):
    marcus = auth_header(client, "marcus@example.com")
    devon = auth_header(client, "devon@example.com")
    coach = auth_header(client, "coach@titanmetrics.com")

    client.post("/check-ins", json={"client_id": "c_1", **CHECK_IN}, headers=marcus)

    assert client.get("/clients/c_1/report", headers=marcus).status_code == 200
    assert client.get("/clients/c_1/report", headers=devon).status_code == 403
    assert client.get("/clients/c_1/report", headers=coach).status_code == 200
    assert client.get("/clients/c_1/progression", headers=devon).status_code == 403
