"""WebSocket helper tests"""
import uuid
import pytest
from app.ws import sanitize, WSManager
from app.rate_limit import ws_rate_limiter
from app.config import settings

class DummyWebSocket:
    def __init__(self):
        self.closed_with = None
        self.sent_payloads = []
    
    async def close(self, code=1000, reason=""):
        self.closed_with = (code, reason)
    
    async def send_json(self, data):
        self.sent_payloads.append(data)

@pytest.mark.anyio("asyncio")
async def test_ws_manager_register_replaces_existing():
    manager = WSManager()
    conv_id = uuid.uuid4()
    ws1 = DummyWebSocket()
    ws2 = DummyWebSocket()
    
    assert await manager.register_client(conv_id, ws1) is True
    assert await manager.register_client(conv_id, ws2) is True
    assert manager.clients[conv_id] is ws2
    assert ws1.closed_with[0] == 1000

def test_sanitize_escapes_html_and_limits_length():
    raw = "<script>alert(1)</script>" + "x" * 5000
    cleaned = sanitize(raw)
    assert "&lt;script&gt;" in cleaned
    assert len(cleaned) <= settings.MAX_MESSAGE_LEN

def test_rate_limiter_blocks_after_burst():
    ident = "test-client"
    ws_rate_limiter.ws_buckets.pop(ident, None)
    assert ws_rate_limiter.allow_ws(ident, 1, 2)
    assert ws_rate_limiter.allow_ws(ident, 1, 2)
    assert ws_rate_limiter.allow_ws(ident, 1, 2) is False
    ws_rate_limiter.ws_buckets.pop(ident, None)
