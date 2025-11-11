"""Telegram integration tests"""
import pytest
from unittest.mock import AsyncMock, patch
from app.telegram import tg_send, notify_new_visitor

@pytest.mark.asyncio
async def test_tg_send():
    """Test Telegram message sending"""
    with patch('httpx.AsyncClient.post') as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"ok": True}
        
        result = await tg_send("123456789", "Test message")
        assert result is True
        mock_post.assert_called_once()

@pytest.mark.asyncio
async def test_notify_new_visitor():
    """Test new visitor notification"""
    with patch('app.telegram.tg_send') as mock_send:
        mock_send.return_value = True
        
        await notify_new_visitor("test-conv-id", "Test User")
        mock_send.assert_called_once()

@pytest.mark.asyncio
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