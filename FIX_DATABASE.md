# 🚨 ACİL: Veritabanı Migration Hatası Çözümü

## Hata
```
column "message_type" of relation "messages" does not exist
```

## Neden
`migrations/002_add_file_support.sql` dosyası Railway PostgreSQL'de çalıştırılmamış.

## Çözüm (Railway'de)

### Yöntem 1: Railway CLI ile
```bash
# Railway CLI yükle
npm i -g @railway/cli

# Login
railway login

# Projeye bağlan
railway link

# PostgreSQL'e bağlan
railway run psql $DATABASE_URL

# Migration'ı çalıştır
\i migrations/002_add_file_support.sql
```

### Yöntem 2: Railway Dashboard ile
1. Railway Dashboard → PostgreSQL servisine git
2. "Connect" → "psql" sekmesini aç
3. Aşağıdaki SQL'i çalıştır:

```sql
-- Migration: Add file support to messages table
ALTER TABLE messages 
ADD COLUMN IF NOT EXISTS message_type VARCHAR(16) DEFAULT 'text',
ADD COLUMN IF NOT EXISTS file_path VARCHAR(512),
ADD COLUMN IF NOT EXISTS file_size INTEGER,
ADD COLUMN IF NOT EXISTS file_mime VARCHAR(64);

CREATE INDEX IF NOT EXISTS idx_msg_type ON messages(message_type);

UPDATE messages SET message_type = 'text' WHERE message_type IS NULL;

ALTER TABLE messages ALTER COLUMN message_type SET NOT NULL;
```

### Yöntem 3: Otomatik Migration (Kod Değişikliği)

`app/main.py` startup fonksiyonunda zaten var:
```python
@app.on_event("startup")
async def startup():
    await init_db()
    # Run database migrations
    from app.db import run_migrations
    await run_migrations()  # ← Bu çalışmalı
```

**Kontrol et:** `app/db.py` içinde `run_migrations()` fonksiyonu doğru çalışıyor mu?

## Doğrulama

Migration başarılı olduysa:
```sql
-- Kolon var mı kontrol et
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'messages' 
AND column_name IN ('message_type', 'file_path', 'file_size', 'file_mime');
```

Sonuç:
```
 column_name  | data_type
--------------+-----------
 message_type | varchar
 file_path    | varchar
 file_size    | integer
 file_mime    | varchar
```

## Sonraki Adımlar

Migration çalıştıktan sonra:
1. Railway'de uygulamayı yeniden başlat
2. Tarayıcıda sayfayı yenile (Ctrl+F5)
3. Dosya yüklemeyi tekrar dene

## Kalıcı Çözüm

`app/db.py` içindeki `run_migrations()` fonksiyonunu kontrol et ve düzelt:

```python
async def run_migrations():
    """Run SQL migrations from migrations/ directory"""
    migrations_dir = Path("migrations")
    if not migrations_dir.exists():
        logger.warning("Migrations directory not found")
        return
    
    # Get all .sql files sorted by name
    migration_files = sorted(migrations_dir.glob("*.sql"))
    
    async with session_scope() as session:
        for migration_file in migration_files:
            logger.info(f"Running migration: {migration_file.name}")
            try:
                sql = migration_file.read_text()
                # Split by semicolon and execute each statement
                for statement in sql.split(';'):
                    statement = statement.strip()
                    if statement:
                        await session.execute(text(statement))
                await session.commit()
                logger.info(f"Migration {migration_file.name} completed")
            except Exception as e:
                logger.error(f"Migration {migration_file.name} failed: {e}")
                # Don't raise - continue with other migrations
```

## Hızlı Test

Railway'de migration çalıştıktan sonra:
```bash
curl https://deneme-sohbet.up.railway.app/health/detailed
```

Response'da hata olmamalı.
