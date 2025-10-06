import sys
import os
import pytest
from fastapi.testclient import TestClient

# Add the project root to the Python path to resolve import issues
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from main import app

client = TestClient(app)

def test_health_check():
    """Tests if the /health endpoint is working correctly."""
    response = client.get("/health")
    assert response.status_code == 200
    json_response = response.json()
    assert json_response["status"] == "healthy"
    assert "models" in json_response
    assert "yolo" in json_response["models"]
