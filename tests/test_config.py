import pytest
from pydantic import ValidationError

from app.config import DEV_JWT_SECRET, Settings


def make_settings(**overrides):
    # _env_file=None keeps developer .env files out of test runs
    return Settings(_env_file=None, **overrides)


def test_development_defaults_are_permissive():
    s = make_settings()
    assert s.env == "development"
    assert s.jwt_secret == DEV_JWT_SECRET
    assert s.cors_origin_list == ["http://localhost:8081"]


def test_production_rejects_dev_jwt_secret():
    with pytest.raises(ValidationError, match="TITAN_JWT_SECRET must be overridden"):
        make_settings(env="production", cors_origins="https://app.titanmetrics.com")


def test_production_rejects_short_jwt_secret():
    with pytest.raises(ValidationError, match="at least 32 bytes"):
        make_settings(
            env="production",
            jwt_secret="too-short",
            cors_origins="https://app.titanmetrics.com",
        )


def test_production_rejects_wildcard_cors():
    with pytest.raises(ValidationError, match="exact origins"):
        make_settings(env="production", jwt_secret="x" * 48, cors_origins="*")


def test_production_accepts_hardened_config():
    s = make_settings(
        env="production",
        jwt_secret="x" * 48,
        cors_origins="https://app.titanmetrics.com, https://coach.titanmetrics.com",
    )
    assert s.cors_origin_list == [
        "https://app.titanmetrics.com",
        "https://coach.titanmetrics.com",
    ]
