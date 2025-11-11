# Private Support Chat (FastAPI + PostgreSQL)

## 🎉 Versiyon 2.0.0 - Production Ready!

> ✅ **Yapı dokümantasyona uygun hale getirildi!**

### ✨ Özellikler
- 1:1 **özel** sohbet (NO ROOMS)
- Ziyaretçi → Admin WS, Admin → Ziyaretçi WS
- Telegram OTP girişi ve **reply** köprüsü
- Admin silerse DB'den **kalıcı silme** ve canlı yayında kapatma
- Rate limit, origin kontrolü, içerik temizlik, CSP
- 🔒 Gelişmiş güvenlik (IP whitelist, token rotation, brute force protection)
- ⚡ Optimize edilmiş performans (parallel broadcast, cache invalidation)
- 📊 Gelişmiş health check ve monitoring hazır

## Çalıştırma
1. `.env` dosyasını `.env.example`'dan kopyalayın ve değiştirin.
2. `docker build -t support-chat .`
3. `docker run --env-file .env -p 8000:8000 support-chat`

## Railway
- Railway'de Postgres hizmeti oluşturun ve `DATABASE_URL`'u `.env` içine yazın.
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_DEFAULT_CHAT_ID`, `TELEGRAM_WEBHOOK_SECRET` değerlerini ekleyin.
- Telegram webhook'u ayarlayın:
  ```
  curl -X POST "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/setWebhook"     -H "Content-Type: application/json"     -d "{"url": "https://<YOUR_DOMAIN>/telegram/webhook", "secret_token": "$TELEGRAM_WEBHOOK_SECRET"}"
  ```

## 🔒 Güvenlik Notları
- **ODA YOK**: Her şey `conversation_id` ile adreslenir.
- WS sadece `ALLOWED_ORIGINS` içinden gelen **Origin** ile kabul edilir.
- Admin WS **token** zorunlu (query'de `?token=`).
- Mesaj uzunluğu varsayılan **2000** karakter ile sınırlı.
- ✅ **OTP brute force protection** (5 deneme / 15 dakika)
- ✅ **Session token rotation** (otomatik yenileme)
- ✅ **IP whitelist** (admin WebSocket)
- ✅ **Telegram IP validation** (resmi IP aralıkları)
- ✅ **Sensitive data masking** (log filtreleme)

## Gelecek (AI)
- `app/ws.py` içindeki yayın akışına `BotAdapter` eklenerek AI cevap modülü takılabilir (varsayılan kapalı).

