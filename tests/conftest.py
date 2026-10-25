import os
import uuid
# app import hone se PEHLE test DB aur test Redis set karna zaroori hai
os.environ["DATABASE_URL"] = (
    "postgresql+asyncpg://whiteboard:whiteboard@localhost:5432/whiteboard_test"
)
os.environ["REDIS_URL"] = "redis://localhost:6379/1"
import pytest
import redis as redis_sync
from fastapi.testclient import TestClient
from main import app
@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c
@pytest.fixture(autouse=True)
def clear_rate_limits():
    r = redis_sync.Redis.from_url(os.environ["REDIS_URL"])
    for key in r.scan_iter("rl:*"):
        r.delete(key)
    yield
@pytest.fixture
def new_user(client):
    def make():
        email = f"{uuid.uuid4().hex[:10]}@test.com"
        password = "secret123"
        r = client.post("/auth/register", json={"email": email, "password": password})
        assert r.status_code == 201
        r = client.post("/auth/login", json={"email": email, "password": password})
        token = r.json()["access_token"]
        return {
            "email": email,
            "password": password,
            "token": token,
            "headers": {"Authorization": f"Bearer {token}"},
        }
    return make