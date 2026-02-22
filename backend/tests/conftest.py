"""Shared test fixtures for GrayScope backend tests."""

import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.core.database import get_db
from app.models import Base

# ── File-based SQLite for test isolation ─────────────────────────
TEST_DATABASE_URL = "sqlite:///./test_grayscope.db"

engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    """Create all tables once for the test session."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    import os
    if os.path.exists("./test_grayscope.db"):
        os.remove("./test_grayscope.db")


@pytest.fixture(autouse=True)
def clean_tables():
    """Truncate all tables between tests for isolation."""
    yield
    db = TestSessionLocal()
    for table in reversed(Base.metadata.sorted_tables):
        db.execute(table.delete())
    db.commit()
    db.close()


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def db():
    """Database session for direct DB access in tests."""
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()


# ── Helper fixtures ──────────────────────────────────────────────

@pytest.fixture
def create_project(client):
    """Helper to create a project and return the response data."""
    def _create(name="test-project", description="A test project"):
        res = client.post("/api/v1/projects", json={"name": name, "description": description})
        assert res.status_code == 201
        return res.json()["data"]
    return _create


@pytest.fixture
def create_repo(client, create_project):
    """Helper to create a project + repo and return both."""
    def _create(project_name="test-project", repo_name="test-repo", git_url="https://github.com/test/test.git"):
        proj = create_project(name=project_name)
        pid = proj["project_id"]
        res = client.post(f"/api/v1/projects/{pid}/repos", json={
            "name": repo_name,
            "git_url": git_url,
        })
        assert res.status_code == 201
        return proj, res.json()["data"]
    return _create


@pytest.fixture
def create_task(client, create_repo):
    """Helper to create a project + repo + task."""
    def _create(analyzers=None, task_type="full"):
        proj, repo = create_repo()
        if analyzers is None:
            analyzers = ["branch_path", "boundary_value"]
        res = client.post("/api/v1/analysis/tasks", json={
            "project_id": proj["project_id"],
            "repo_id": repo["repo_id"],
            "task_type": task_type,
            "analyzers": analyzers,
            "target": {"path": "test_samples/"},
        })
        assert res.status_code == 201
        return proj, repo, res.json()["data"]
    return _create
