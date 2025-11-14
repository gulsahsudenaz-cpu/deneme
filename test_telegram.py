import asyncio
import httpx
import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_DEFAULT_CHAT_ID = os.getenv("TELEGRAM_DEFAULT_CHAT_ID")

async def test_telegram():
    print(f"Bot Token: {TELEGRAM_BOT_TOKEN[:20]}...")
    print(f"Chat ID: {TELEGRAM_DEFAULT_CHAT_ID}")
    
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            # Test bot
            r = await client.get(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getMe")
            print(f"\nBot Status: {r.status_code}")
            if r.status_code == 200:
                bot_info = r.json()
                print(f"Bot Username: @{bot_info['result']['username']}")
            else:
                print(f"Error: {r.text}")
                return
            
            # Test send message
            payload = {
                "chat_id": TELEGRAM_DEFAULT_CHAT_ID,
                "text": "🔐 Test OTP: 123456"
            }
            r = await client.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json=payload)
            print(f"\nSend Message Status: {r.status_code}")
            if r.status_code == 200:
                print("✅ Message sent successfully!")
            else:
                print(f"❌ Error: {r.text}")
    except Exception as e:
        print(f"❌ Exception: {e}")

if __name__ == "__main__":
    asyncio.run(test_telegram())
