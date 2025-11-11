"""Tests for authentication"""
import pytest
from httpx import AsyncClient
from app.main import app

@pytest.mark.asyncio
async def test_request_otp():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.post("/api/admin/request_otp")
        assert response.status_code == 200
        data = response.json()
        assert "sent" in data

@pytest.mark.asyncio
async def test_admin_login_invalid_code():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.post("/api/admin/login", json={"code": "000000"})
        assert response.status_code == 400

@pytest.mark.asyncio
async def test_health_check():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ["ok", "degraded"]
