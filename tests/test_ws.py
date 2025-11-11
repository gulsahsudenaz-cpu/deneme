"""WebSocket tests"""
import pytest
from fastapi.testclient import TestClient
from app.main import app

@pytest.fixture
def client():
    return TestClient(app)

def test_ws_client_connection(client):
    """Test client WebSocket connection"""
    with client.websocket_connect("/ws/client") as websocket:
        # Test join message
        websocket.send_json({"type": "join", "display_name": "Test User"})
        data = websocket.receive_json()
        assert data["type"] == "joined"
        assert "conversation_id" in data

def test_ws_admin_requires_token(client):
    """Test admin WebSocket requires token"""
    with pytest.raises(Exception):
        with client.websocket_connect("/ws/admin"):
            pass

def test_ws_message_rate_limit(client):
    """Test WebSocket rate limiting"""
    with client.websocket_connect("/ws/client") as websocket:
        websocket.send_json({"type": "join", "display_name": "Test User"})
        websocket.receive_json()  # joined response
        
        # Send multiple messages quickly
        for i in range(10):
            websocket.send_json({"type": "message", "content": f"Message {i}"})
        
        # Should receive rate limit error
        data = websocket.receive_json()
        assert data.get("type") == "error"