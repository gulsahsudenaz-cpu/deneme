"""Internationalization support"""
from typing import Dict

TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "tr": {
        "new_visitor": "🟢 Yeni ziyaretçi: {name}\nKonuşma ID: {conv_id}\nBu mesaja reply atarak yanıtlayabilirsin.",
        "visitor_message": "👤 {name}: {content}\n(Conv: {conv_id})",
        "admin_login_code": "🔐 Admin giriş kodu: {code}\nGeçerlilik: {ttl} dk",
        "conversation_deleted": "Sohbet sonlandırıldı",
        "message_too_long": "Mesaj çok uzun (max {max} karakter)",
        "rate_limited": "Çok hızlı mesaj gönderiyorsunuz. Lütfen bekleyin.",
        "invalid_code": "Kod hatalı veya süresi geçti",
        "too_many_attempts": "Çok fazla deneme. Lütfen daha sonra tekrar deneyin.",
    },
    "en": {
        "new_visitor": "🟢 New visitor: {name}\nConversation ID: {conv_id}\nReply to this message to respond.",
        "visitor_message": "👤 {name}: {content}\n(Conv: {conv_id})",
        "admin_login_code": "🔐 Admin login code: {code}\nValid for: {ttl} min",
        "conversation_deleted": "Conversation ended",
        "message_too_long": "Message too long (max {max} characters)",
        "rate_limited": "You're sending messages too fast. Please wait.",
        "invalid_code": "Invalid or expired code",
        "too_many_attempts": "Too many attempts. Please try again later.",
    }
}

def t(key: str, lang: str = "tr", **kwargs) -> str:
    """Translate key with optional parameters"""
    translations = TRANSLATIONS.get(lang, TRANSLATIONS["tr"])
    text = translations.get(key, key)
    return text.format(**kwargs) if kwargs else text
