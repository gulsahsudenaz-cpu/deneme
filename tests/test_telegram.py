"""Telegram integration tests"""
import uuid
import pytest
from unittest.mock import AsyncMock, Mock, patch
from contextlib import asynccontextmanager
from app.telegram import tg_send, notify_new_visitor

@pytest.mark.anyio("asyncio")
async def test_tg_send_success():
    """Test Telegram message sending"""
    mock_response = Mock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"ok": True, "result": {"message_id": 42}}
    
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    
    async def fake_client(*args, **kwargs):
        return mock_client
    
    with patch("app.telegram.httpx.AsyncClient") as mock_cls:
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_client
        mock_ctx.__aexit__.return_value = False
        mock_cls.return_value = mock_ctx
        
        result = await tg_send("123456789", "Test message")
        assert result == 42
        mock_client.post.assert_called_once()

@pytest.mark.anyio("asyncio")
async def test_notify_new_visitor(monkeypatch):
    """Test new visitor notification"""
    called = {}
    async def fake_tg_send(chat_id, text, reply_to_message_id=None):
        called["chat_id"] = chat_id
        called["text"] = text
        return 100
    
    @asynccontextmanager
    async def fake_session_scope():
        class DummySession:
            def add(self, obj):
                self.added = obj
        yield DummySession()
    
    monkeypatch.setattr("app.telegram.tg_send", fake_tg_send)
    monkeypatch.setattr("app.telegram.session_scope", fake_session_scope)
    
    await notify_new_visitor(uuid.uuid4(), "Test User")
    assert "chat_id" in called

@pytest.mark.anyio("asyncio")
async def test_telegram_webhook_validation():
    """Test Telegram webhook secret validation"""
    from fastapi.testclient import TestClient
    from app.main import app
    
    client = TestClient(app)
    
    # Test without secret header
    response = client.post("/telegram/webhook", json={"message": {"text": "test"}})
    assert response.status_code == 403
    
    # Test with wrong secret
    response = client.post(
        "/telegram/webhook", 
        json={"message": {"text": "test"}},
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-secret"}
    )
    assert response.status_code == 403
