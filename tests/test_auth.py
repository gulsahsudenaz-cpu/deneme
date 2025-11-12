"""Tests for authentication"""
import pytest
from datetime import datetime, timedelta
from fastapi import HTTPException
from httpx import AsyncClient
from app.main import app

@pytest.mark.anyio("asyncio")
async def test_request_otp(monkeypatch):
    async def fake_create_otp():
        return "123456", datetime.utcnow() + timedelta(minutes=5)
    
    async def fake_tg_send(chat_id, text):
        return 1
    
    monkeypatch.setattr("app.main.create_otp", fake_create_otp)
    monkeypatch.setattr("app.telegram.tg_send", fake_tg_send)
    
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.post("/api/admin/request_otp")
        assert response.status_code == 200
        data = response.json()
        assert data["sent"] is True

@pytest.mark.anyio("asyncio")
async def test_admin_login_invalid_code(monkeypatch):
    async def fake_verify(code, ip, user_agent):
        raise HTTPException(status_code=400, detail="Invalid or expired code")
    
    monkeypatch.setattr("app.main.verify_otp_and_issue_session", fake_verify)
    
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.post("/api/admin/login", json={"code": "000000"})
        assert response.status_code == 400

@pytest.mark.anyio("asyncio")
async def test_health_check():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ["ok", "degraded"]
