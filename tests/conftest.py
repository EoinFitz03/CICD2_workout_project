# tests/conftest.py
import os

# Make sure the app uses the in-memory test DB
os.environ["APP_ENV"] = "test"

import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)
