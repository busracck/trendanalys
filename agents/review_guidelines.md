# Kod inceleme kuralları

Bu dosya TrendAnalys projesine özel kuralları içerir. Reviewer Agent, incelediği
değişikliği bu kurallara göre değerlendirir.

## Önem dereceleri

- **blocker** — commit edilmemeli. Güvenlik açığı, veri kaybı, etik kural ihlali.
- **major** — çalışır ama düzeltilmeli. Hatalı davranış, ciddi performans sorunu.
- **minor** — iyileştirme önerisi. İsimlendirme, tekrar eden kod, eksik yorum.

## Etik ve yasal kurallar (ihlali her zaman blocker)

1. **robots.txt kontrolü atlanamaz.** Trendyol'a giden her istek
   `scraper/driver.fetch_page` üzerinden geçer; robots kontrolü ve `polite_sleep`
   orada. Bu fonksiyonu baypas eden, `driver.get` çağıran yeni kod blocker'dır.
2. **İstekler arası bekleme düşürülemez.** `MIN_DELAY = 4`, `MAX_DELAY = 8`.
   Küçültmek siteye yük bindirir ve verdiğimiz sözü bozar.
3. **Engel aşma girişimi olmaz.** Captcha çözme, proxy döndürme, user-agent
   sahteciliği, `robots.txt`'i yok sayma: hepsi blocker.
4. **Yorum yazanların adları saklanmaz** (KVKK). `ReviewSnippet` modeline yazar
   adı, kullanıcı adı ya da profil linki eklenmesi blocker'dır.
5. **İndirilen veri repoya girmez.** `data/raw_html/` ve benzeri yolların
   `.gitignore` dışına çıkarılması blocker'dır.

## Güvenlik

6. **Kod içinde gizli bilgi olmaz.** Şifre, API anahtarı, token: hepsi `.env`
   dosyasından `app/config.py` üzerinden okunur. Koda gömülmesi blocker'dır.
7. **SQL string birleştirmeyle kurulmaz.** SQLAlchemy ifadeleri ya da
   `text(...)` + parametre kullanılır. Kullanıcıdan gelen değerin f-string ile
   SQL'e konması blocker'dır.
8. **Kullanıcı girdisi doğrulanır.** API uçlarında Pydantic modeli kullanılır;
   sınırsız `limit` ya da doğrulanmamış metin kabul edilmez.

## Proje mimarisi

9. **Model her istekte yüklenmez.** `app/services/embedder.get_model`
   `@lru_cache` ile korunuyor; yeni bir `SentenceTransformer(...)` çağrısı major'dır.
10. **Katmanlar karışmaz.** `scraper/` veri toplar, `nlp/` metin ve vektör üretir,
    `app/services/` arama mantığını taşır, `app/main.py` yalnızca HTTP uçlarıdır.
    Endpoint içine iş mantığı yazmak major'dır.
11. **Veritabanı oturumu sızdırılmaz.** Uçlar `Depends(get_session)` kullanır,
    scriptler `with SessionLocal() as session:` bloğu açar.
12. **Yeni ürün eklenince vektör de gerekir.** Ürün içeriğini değiştiren kod
    `search_text`, `embedding` ve `embedded_at` alanlarını sıfırlamalı; yoksa
    arama eski metne göre çalışır (major).

## Dayanıklılık

13. **Dış servis çökerse uygulama çökmez.** Open-Meteo çağrıları `try/except`
    ile sarılır ve `None` döner; hava durumu olmadan arama çalışmaya devam eder.
14. **Ağ hataları yakalanır.** Selenium'un takılması hem `WebDriverException`
    hem `urllib3.exceptions.HTTPError` olarak gelebiliyor; ikisi birden yakalanmalı.
15. **Sonsuz döngü olmaz.** Ağa istek atan döngülerde üst sınır bulunur
    (`MAX_PAGES` gibi).

## Okunabilirlik

16. Fonksiyonlar tek iş yapar, isimler ne yaptığını söyler.
17. Sabitler dosyanın üstünde, fonksiyonların dışında durur.
18. Yorumlar "ne" değil "neden" anlatır. Sayısal bir sabitin nereden geldiği
    (ölçüm, sınır, kural) yazılır.
19. Kullanılmayan import, değişken ve fonksiyon bırakılmaz.
