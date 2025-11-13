# Premium Destek Sistemi – Derin Analiz

## 1. Mimari Özet
- Tek FastAPI uygulaması hem web istemcisini, hem admin panelini, hem de Telegram webhook’unu aynı süreçte barındırıyor; giriş noktaları `app/main.py:1-180` bölümündeki middleware zinciri ve statik servis montajları (`app/main.py:137-139`).
- WebSocket yöneticisi (`app/ws.py:38-124`) hâlâ tüm mesajlaşmayı üstlenmek için tasarlanmış ancak Railway’de WebSocket kısıtı nedeniyle istemciler HTTP polling’e düşüyor (`static/js/client.js:189-230`, `static/js/admin.js:319-329`). Kod tabanı bu iki model arasında tutarsız.
- Veri katmanı SQLAlchemy + async session ile tanımlanmış (`app/db.py`, `app/models.py`). Mesaj/konuşma kayıtlarının yanına Telegram reply-chain’i için `TelegramLink` tablosu eklenmiş (`app/models.py:71-82`).
- Cache katmanı Redis opsiyonel, yoksa hibrit bellek (`app/cache.py`). Rate limiter sınıfları mevcut (`app/rate_limit.py`) olsa da HTTP middleware tarafında devre dışı bırakılmış durumda (`app/main.py:86-119`).

## 2. Index (Ziyaretçi) Katmanı
- `templates/index.html` ziyaretçi adını alıp sohbet arayüzünü açıyor; metin girişi, dosya yükleme ve durum göstergeleri çizgi film gibi (`templates/index.html:55-105`).
- Frontend tamamen HTTP polling moduna geçirilmiş: `connect('join')` ziyaretçiyi `/api/visitor/join` ile yaratıyor ve 8 saniyede bir `/api/visitor/messages/{conversation_id}` çağrısı yapılıyor (`static/js/client.js:189-268`).
- Mesaj gönderimi `/api/visitor/send` REST çağrısına indirgenmiş (`static/js/client.js:275-295`); gönderim başarılıysa mesaj lokalde anında gösteriliyor.
- Dosya yükleme `uploadFile()` ile FormData üzerinden `/api/visitor/upload`’a gidiyor (`static/js/client.js:297-383`). İstemci tarafta tip/boyut kısıtları var fakat sunucu tarafındaki kaydetme hatası (bkz. Bölüm 5) yüzünden yükleme tamamlanamıyor.
- Polling sırasında sadece mesaj sayısı değiştiyse tüm sohbet yeniden çiziliyor (`static/js/client.js:248-267`). Bu yaklaşım yeni mesajların kaçırılmasına yol açmasa da gereksiz DOM yıkımı ve kaydırma sıfırlamasına sebep oluyor.

## 3. Admin Katmanı
- Admin arayüzü OTP ile açılıyor (`templates/admin.html:22-41`). OTP isteme/giriş akışı `reqOtpBtn` ve `loginForm` handler’ları ile `/api/admin/request_otp` ve `/api/admin/login` uçlarına bağlı (`static/js/admin.js:369-420`).
- `api()` yardımcı fonksiyonu her istekte `Authorization: Bearer {token}` gönderiyor ve backend’in döndürdüğü `X-New-Token` başlığını okuyup localStorage’ı güncelliyor (`static/js/admin.js:140-160`). **Ancak** burada `connectWSWithToken()` isimli, artık var olmayan bir fonksiyon çağrılıyor (`static/js/admin.js:155-158`). İlk token rotasyonunda tarayıcı “ReferenceError: connectWSWithToken is not defined” hatası veriyor ve tüm istek zinciri (sohbet listesi + mesajlar) kırılıyor. Bu nedenle ziyaretçi metinleri admin panelinde hiç görünmüyor.
- HTTP polling 5 saniyede bir tüm sohbet listesini ve seçili konuşmanın ilk 50 mesajını çekiyor (`static/js/admin.js:319-366`). Yeni mesajları anlamak için sadece toplam mesaj sayısına bakıldığı için paket boyu değişmeyen güncellemeler (örn. düzenlenmiş mesaj) yakalanamıyor.
- `addMsg()` fonksiyonu yalnızca düz metin balonları çiziyor (`static/js/admin.js:277-309`). REST API’den gelen `message_type`, `file_url`, `file_size` gibi parametreler fonksiyon imzasında olmadığı için medya içerikleri admin tarafında hiç gösterilmiyor.
- Dosya yükleme UI’de mevcut olsa da (buton + input `templates/admin.html:144-160`) backend tarafında kaydetme hatası nedeniyle (bkz. Bölüm 5) hiçbir medya kaydı oluşmuyor.

## 4. Telegram Entegrasyonu
- Telegram gönderimleri tek bir `sendMessage` çağrısına indirgenmiş (`app/telegram.py:24-45`). Yeni ziyaretçi ve ziyaretçi mesaj bildirimleri sadece metinsel özetler içeriyor (`app/telegram.py:47-79`), dosya linki veya Telegram’a upload yok.
- Admin OTP’leri de aynı `tg_send` üzerinden gidiyor (`app/main.py:487-503`). `tg_send` başarısız olursa istisna yakalanıp sadece `sent=False` dönülüyor; frontend nedenini bilemiyor, loglarda saklı kalıyor.
- Webhook `/telegram/webhook` path’inde, hem secret header hem de Telegram IP aralığı filtreleriyle korunuyor (`app/telegram.py:80-104`). Ancak IPv6 aralıkları ve Cloudflare/LB katmanları göz önüne alınmamış; gerçek Telegram trafiği bile engellenebilir.
- Reply-to mesajdan konuşma eşleşmesi `TelegramLink` tablosuna dayanıyor (`app/telegram.py:114-148`). `notify_new_visitor` sırasında link yaratılmazsa adminlerin Telegram cevabı sisteme düşmüyor.

## 5. Metin / Medya Akışındaki Bloklar
1. **Admin tarafında JS kırılması:** `static/js/admin.js` içinde tanımsız `connectWSWithToken()` çağrısı (satırlar 155-158) JavaScript yürütmesini durdurduğu için `/api/admin/conversations` sonuçları hiç işlenmiyor. Bu da “index’ten admin’e yazı gitmiyor” gözlemini açıklıyor.
2. **Dosya kaydetme fonksiyonu hata veriyor:** `app/file_handler.py` içinde `file_path.relative_to(Path.cwd())` satırı (`app/file_handler.py:69-70`) göreceli yol ile mutlak yol karşılaştırdığı için `ValueError` fırlatıyor. Sonuçta `/api/visitor/upload` ve `/api/admin/upload` uçları “File upload failed” hatası üretip hiçbir dosyayı diske yazamıyor (`app/main.py:418-486`, `app/main.py:581-650`).
3. **Medya gösterimi eksik:** Admin UI, REST API’nin gönderdiği `file_url`/`message_type` alanlarını tamamen yok sayıyor (`static/js/admin.js:277-309`), bu yüzden dosyalar hiç görünmüyor. Ziyaretçi tarafı aynı bilgileri render ediyor (`static/js/client.js:86-170`), dolayısıyla problem sadece admin UI.
4. **Telegram’a medya gitmiyor:** Hem `notify_visitor_message` hem de `notify_new_visitor` yalnızca metin içerik gönderiyor (`app/telegram.py:58-79`). Dosyanın public URL’si bile Telegram mesajına eklenmiyor, dolayısıyla “ses/resim Telegram’a gitmiyor” beklentisi karşılanamaz.
5. **Rate limit ve doğrulama eksikliği:** `visitor_upload` tarafında herhangi bir hız kısıtı yok ve dosya kaydı fail ettiği için kullanıcı sadece hata görüyor; Telegram bildirim planlanan fakat `_schedule_background_task` ile gönderildiği için istisna log’da kalıyor (`app/main.py:461-470`, `app/main.py:1256-1269`).

## 6. OTP Akışı ve Eksikleri
- OTP üretimi/saklama `create_otp()` ve hashli tablo üzerinden (`app/auth.py:15-48`). `/api/admin/request_otp` çağrısı OTP’yi üretip Telegram’a göndermeye çalışıyor (`app/main.py:487-503`).
- Telegram çağrısı başarısız olduğunda API yanıtı `{"sent": false}` oluyor fakat admin UI yalnızca genel bir “OTP istenemedi” mesajı gösterebiliyor; hata nedeni (ör. yanlış bot token, Telegram’ın Railway’den istekleri reddetmesi) UI’ye ulaşmıyor.
- Akışta ek güvenlik tedbiri yok: rate limit middleware devre dışı olduğu için OTP uç noktası brute-force’a açık, istemci tarafında da herhangi bir Captcha bulunmuyor.
- Oturum doğrulaması her istekte token rotasyonu yaptığı için (`app/auth.py:101-113`) admin paneli saniyede birçok defa yeni token üretmek zorunda kalıyor; frontende tanımsız fonksiyon kaldığından dolayı bu mekanizma pratikte tamamen kırık.

## 7. Güvenlik Tespitleri
- **HTTP rate limit kapalı:** RateLimitMiddleware koşullu kısımlar yorum satırı, fonksiyon doğrudan `call_next` dönüyor (`app/main.py:86-119`). Ziyaretçi upload, OTP, admin login gibi uçlar sınırsız istek alabiliyor.
- **Dosya servislemesi herkese açık:** Upload dizini doğrudan `/files` altında kimlik doğrulamasız sunuluyor (`app/main.py:137-139`). Dosya adları UUID olsa da path’i tahmin eden herkes medya indirebilir.
- **CSRF ve token saklama:** Admin token’ı localStorage’da tutuluyor ve her istekte otomatik gönderiliyor (`static/js/admin.js:140-160`). Bir XSS ile token anında çalınabilir; CSP’de `'unsafe-inline'` bulunması (`app/main.py:82-83`) da bu riski büyütüyor.
- **İçerden veri sızıntısı:** `visitor_upload` veya `admin_upload`’da dosya imzaları doğrulanmıyor; dosya tipine sadece MIME üzerinden bakılıyor (`app/file_handler.py:30-38`), saldırgan içerik enjeksiyonu yapabilir.
- **Telegram IP filtreleri eksik:** `app/telegram.py:80-104` IPv4 bloklarına sabitlenmiş. Telegram’ın IPv6 veya CDN kullanması halinde webhook tamamen çalışmaz, bu da OTP akışını durdurur.
- **Request boyutu kontrolü Content-Length’e güveniyor:** Saldırgan header’ı kaldırırsa middleware (`app/main.py:30-60`) gövdeyi tamamen okumak zorunda kalıyor ve bellek tüketimi artıyor.

## 8. Performans ve Ölçeklenebilirlik
- **Polling maliyeti:** Ziyaretçiler 8 sn’de bir, adminler 5 sn’de bir tam liste çekiyor (`static/js/client.js:225-230`, `static/js/admin.js:319-329`). Aktif sohbet sayısı arttıkça DB ve ağ yükü katlanıyor; delta veya uzun-polling yok.
- **Token rotasyonu I/O’su:** Her admin isteği `AdminSession` tablosunda yeni token yazıyor (`app/auth.py:101-113`). Polling sıklığı düşünüldüğünde sürekli yazma/flush işlemi var, bu da Postgres üzerinde gereksiz baskı yaratıyor.
- **Cache invalidasyonu agresif:** Her mesaj/değişiklik sonrası `cache.delete_by_pattern("conversations:*")` çağrılıyor (`app/main.py:341-574`). Bu, yüksek trafik altında cache’i anlamsız hale getiriyor.
- **Dosya kaydetme bug’ı:** `relative_to` hatası yüzünden upload geri dönüşleri her seferinde 500 üretip tekrar deneme/spam’e yol açıyor; işçi thread’leri boşa harcanıyor.
- **Backpressure yok:** WebSocket tarafı hâlâ çalışıyor gibi broadcast yapıyor (`app/ws.py:96-122`), fakat fiilen hiçbir istemci bağlı değil; yine de her mesajda JSON serileştirme masrafı var.

## 9. Adaptasyon & Operasyonel Dayanıklılık
- HTTP fallback tasarlanmış olsa da kod tabanı yarım bırakılmış: WebSocket spesifik fonksiyon isimleri hâlâ frontende dokunuyor (`static/js/admin.js:155-158`), hataya sebep oluyor.
- `_schedule_background_task` içinde hatalar sadece log’a yazılıyor (`app/main.py:1256-1269`); Telegram bildirimleri veya cleanup görevleri sessizce başarısız olabiliyor.
- Health endpoint’leri var (`app/main.py:212-304`) fakat Railway tarafında container “healthy” olmazsa sistem tamamen açılmıyor; loglarda görülen hatalar için merkezi alarm/telemetri bulunmuyor.
- Dosya sistemi temizliği yok; yüklenen dosyalar (kaydedilebilse bile) hiçbir zaman silinmiyor, depolama dolması uzun vadede kaçınılmaz.

## 10. Test ve Gözlemlenebilirlik
- Test paketi yalnızca auth & Telegram helper’larını kapsıyor (`tests/test_auth.py`, `tests/test_telegram.py`, `tests/test_ws.py`). HTTP fallback, admin JS, dosya upload/servis akışı ve OTP GUI için test yok.
- Loglar maskeleme filtresine sahip (`app/logger.py:6-36`) ancak frontende yansıtılmadığı için kritik hatalar (ör. `connectWSWithToken`) sadece tarayıcı konsolunda kalıyor.
- İzleme tarafında `app/monitoring.py` metrik üretse de hiçbir yerde toplanmıyor; `/health/detailed` endpoint’ini manuel çağırmak gerekiyor.

## 11. Öncelikli Aksiyonlar
1. **Admin JS düzeltmeleri:** `connectWSWithToken` çağrısını kaldırıp token güncellemeyi sadece localStorage seviyesinde bırakın; `addMsg` fonksiyonunu `message_type`/`file_url` alanlarını render edecek şekilde genişletin (`static/js/admin.js`).
2. **Dosya kaydetme bug’ını giderin:** `file_path.resolve().relative_to(Path.cwd())` kullanarak göreceli-yol hatasını düzeltin ve upload uçlarını tekrar test edin (`app/file_handler.py:69-70`).
3. **Telegram/OTP görünürlüğü:** `/api/admin/request_otp` yanıtına hata mesajını ekleyin ve admin UI’de gösterin; Telegram’a medya gönderebilmek için `sendDocument` v.b. uçlar üzerinden public file URL’lerini paylaşın (`app/telegram.py:58-79`).
4. **Rate limit ve güvenlik sertleştirmesi:** HTTP rate limit middleware’ini yeniden etkinleştirin, `/files` montajını en azından imzalı URL veya admin-token ile koruyun, CSP’den `'unsafe-inline'` ifadelerini kaldırın (`app/main.py:61-139`).
5. **Polling stratejisini optimize edin:** Minimum olarak `If-None-Match`/`ETag` veya cursor bazlı incremental fetch uygulayın; idealde WebSocket/SSE desteğini Railway dışı ortamda kullanın.
6. **Operasyonel izleme:** `_schedule_background_task` içindeki hataları merkezi bir queue’ya raporlayın, health check sonuçlarını izleyin ve admin panelde kritik hatalar için kullanıcıya görünür uyarılar sağlayın.

Bu maddeler hayata geçirilmeden ziyaretçi → admin → Telegram zinciri hem fonksiyonel hem de güvenlik açısından riskli kalmaya devam edecektir.
