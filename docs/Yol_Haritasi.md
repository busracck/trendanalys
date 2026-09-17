# Proje Yol Haritası — Trendyol Semantik Arama & Reviewer Agent

`Python & FastAPI` · `PostgreSQL & pgvector` · `Hugging Face (Sentence-BERT)` · `Selenium` · `Claude API Reviewer Agent`

## Amaç
Trendyol'da "İzmir'de serin bir akşam için 1000 TL altı rahat bir elbise" gibi **cümleyle arama** yapılamıyor, sadece anahtar kelimeyle arama çalışıyor. Bu proje, Trendyol'dan toplanan bir ürün kataloğu üzerinde çalışan bir **akıllı arama motoru**:

- cümleyi anlamca yorumlar,
- şehir ve fiyat bilgisini çıkarır,
- o şehrin hava durumunu hesaba katar,
- en uygun ürünleri Trendyol linkleriyle getirir.

Sonuçlar **web arayüzünde** görüntülenir.

---

## Kararlar
| Konu | Karar |
|---|---|
| Arayüz | Basit web arayüzü (FastAPI + Jinja2 + vanilla JS). Swagger `/docs` geliştirme için kullanılır. Terminal: scraper, embedding scripti, reviewer çıktısı. |
| Veri kaynağı | Sadece `robots.txt`'in izin verdiği sayfalar: kategori sayfaları (sayfalama dahil) → ürün linkleri → ürün detay sayfası |
| Embedding modeli | `BAAI/bge-m3` (çok dilli, 1024 boyut, 8192 token). Adım 0.4'teki testle seçildi, yedek: `intfloat/multilingual-e5-base` |
| Arama | Hibrit: pgvector cosine (`<=>`) + PostgreSQL full-text (`turkish`) → RRF birleştirme |
| Hava durumu | Open-Meteo (ücretsiz, anahtarsız) + 81 il koordinat JSON'u |
| Reviewer Agent | ruff + bandit → Claude API (`git diff` + `review_guidelines.md`). 17 Eylül 2026'da ertelendi: Aşama 5'ten sonra yazılacak. |

## Kısıtlar ve tespitler
1. **Trendyol robots.txt** (15 Eylül 2026'da ham dosyadan doğrulandı)
   - ❌ **Yasak:**
     - `/sr`, `?q=`, `&q=` (arama sonuçları)
     - `/yorumlar`, `/reviews` (yorum sayfaları)
     - `/get/api/review/`, `/gw/` (API yolları)
     - `?sst=`, `&sst=` (sıralama)
     - özellik filtreli kategori URL'leri (`-x-…-a…-v…`) ve bunların sayfalaması
   - ✅ **İzinli:**
     - ürün detay sayfaları (`…-p-123456`)
     - sade kategori sayfaları (`/kadin-giyim-x-g1-c82`) ve **sayfalamaları** (`?pi=2`)
     - marka kategorileri (`/bershka-kadin-elbise-x-b486-g1-c56`)
   - ⚠️ **Düzeltme:** İlk sürümde `pi=` yasak yazılmıştı. Ham dosyada `pi=` sadece yabancı dil yollarında (`/de/`, `/en/`…) ve özellik filtreli URL'lerde yasak.
   - **Yorumlar:** `/yorumlar` sayfası yasak. Ama yorumu olan ürünlerin detay sayfasındaki `ld+json` bloğunda **20 yorum** (metin, puan, tarih) hazır geliyor. Orijinal plandaki "en az 50 yorum" hedefi yerine bu 20 yorum kullanılacak.
2. **Model değişikliği:**
   - `all-MiniLM-L6-v2` sadece İngilizce için eğitilmiş.
   - `dbmdz/bert-base-turkish-cased` cümle benzerliği için eğitilmemiş.
   - İlk plan Türkçe Sentence-BERT'ti (`emrecan/...`), ama Adım 0.4'te arama için zayıf kaldı. Seçilen model: **`BAAI/bge-m3`** (çok dilli, arama için eğitilmiş).
3. **Robots kontrolü:** Python'un `urllib.robotparser` modülü `*` joker karakterlerini desteklemiyor. Trendyol'un kuralları joker karakterli olduğu için **`protego`** kütüphanesi kullanılacak.
4. **Mesafe operatörü:** Normalize edilmiş vektörlerle `<->` (L2) yerine `<=>` (cosine) ve HNSW index kullanılacak.
5. **Makine:**
   - Proje `.venv` ortamı **Python 3.13.5** ile kurulu (sistem `python3`).
   - **PostgreSQL 17.10** çalışıyor (küme `main`, port 5432). `kitana` sistem kullanıcısı için veritabanı rolü yok. Yönetici işlemleri `sudo -u postgres ...` ile yapılır.
   - Paket kurmadan önce ortamı aktif et: `source .venv/bin/activate`. Aktif değilse Debian sistem `pip`'ini engeller (`externally-managed-environment`).
   - **pgvector kurulu değil:** `sudo apt install postgresql-17-pgvector` (Debian paketi 0.8.0)
   - **GPU:** GeForce GTX 1650 Ti (4 GB), sürücü 550.163.01. 14 Eylül'deki ilk kontrolde `nvidia-smi` sürücüye bağlanamamıştı, 17 Eylül'de çalışıyor. Embedding'ler GPU'da hesaplanabilir; ~1500 ürün için CPU da yeterli.
6. **Etik ve KVKK:**
   - istekler arası 4-8 sn bekleme
   - engel/captcha görülürse scraper durur, atlatma denenmez
   - yorumcu adları saklanmaz
   - veri yeniden yayınlanmaz

---

## Sistem akışı
```
[Selenium scraper] → data/raw_html (cache) → parser + temizlik → PostgreSQL (products)
                                                                      ↓
                                               build_embeddings.py → embedding Vector(1024)

Kullanıcı (web arayüzü) ── "İzmir'de serin bir akşam, 1000 TL altı elbise"
   → query_parser: şehir=İzmir, max_fiyat=1000, kategori ipucu=elbise
   → weather: Open-Meteo (akşam saatleri tahmini, 30 dk cache) → "14°C, serin, rüzgarlı"
   → zenginleştirilmiş sorgu metni → embedder → sorgu vektörü
   → hibrit SQL: fiyat filtresi + vektör (<=>) top-50 + full-text top-50 → RRF → top-10
   → ürün kartları: görsel, fiyat, puan, "neden önerildi", Trendyol linki
```

## Klasör yapısı
```
TrendAnalys/
├── app/            main.py, config.py, db.py, models.py, schemas.py
│   ├── api/        search.py, auth.py, products.py, users.py
│   ├── services/   embedder.py, query_parser.py, weather.py, search.py, security.py
│   ├── templates/  index.html
│   └── static/     app.js, style.css
├── scraper/        driver.py, robots.py, category_crawler.py, product_parser.py, cleaner.py, run_scraper.py
├── nlp/            build_embeddings.py, text_builder.py
├── agents/         reviewer.py, review_guidelines.md
├── eval/           queries.yaml, run_eval.py
├── poc/            Aşama 0 deneme scriptleri
├── data/           iller.json, categories.yaml, raw_html/ (gitignore)
├── alembic/  tests/  docs/
└── .pre-commit-config.yaml  requirements.txt  .env.example  .gitignore  README.md
```

---

## Aşamalar

### Aşama 0: Fizibilite Testi — 🆕 Yeni
Büyük yatırımdan önce en riskli iki varsayım doğrulanır.

- [x] **Adım 0.1:** Sanal ortamı kur. Selenium ile tek bir ürün sayfasını aç (robots kontrolüyle birlikte) ve ham HTML'i kaydet.
- [x] **Adım 0.2:** Kaydedilen HTML'den ad, marka, fiyat, açıklama, özellikler ve görünen yorumları ayrıştır. Sayfada gömülü JSON varsa onu tercih et.
- [x] **Adım 0.3:** Adım 0.1 ve 0.2'yi 5 farklı ürün sayfasıyla tekrarla. Engel/captcha çıkıyor mu kontrol et.
  - Sonuç: engel yok. Parser `Product` ve `ProductGroup` bloklarını okuyor; puan ve 20 yorum da alınıyor (yazar adı hariç). Çıktı: `poc/output/products.json`.
- [x] **Adım 0.3-c:** Mini crawler: tek bir kategori sayfasından ürün linklerini otomatik topla ve 20 ürüne tamamla.
  - Sonuç: Kadın Mont kategorisinin ilk sayfasında 36 ürün kartı (`a.product-card`) bulundu, 15'i engelsiz indirildi. 20 sayfadan 19'u ayrıştırıldı, toplam 239 yorum.
  - ⚠️ 1 ürün `/pd/` adresine yönlendirildi. Bu şablonda `ld+json` yok, veri sayfaya gömülü JSON'da duruyor. Bkz. Aşama 3.
- [x] **Adım 0.4:** 20 ürünle embedding modelini dene. 5 test cümlesinin sonuçları mantıklı mı bak.
  - Kurulum: torch 2.6.0+cu124 (GPU çalışıyor), sentence-transformers 6.0.1.
  - İlk deneme (17 Eylül): `emrecan/bert-base-turkish-cased-mean-nli-stsb-tr` "soğukta sıcak tutan mont" cümlesini "yazlık ince keten elbise"ye (0.44), "kışlık kalın şişme kaban"dan (0.30) daha yakın buldu ❌. Sebepleri:
    - Tokenizer giyim kelimelerini parçalıyor (`mon ##t`, `kaba ##n`).
    - 75 token sınırı var.
  - Karşılaştırılacak modeller (arama tarzı testle, yani kısa sorgu ↔ ürün metni):
    - `intfloat/multilingual-e5-base` (768 boyut, 512 token, `query:` / `passage:` önekleri gerekir)
    - `BAAI/bge-m3` (1024 boyut, 8192 token)
  - Model değişirse Aşama 2'deki `Vector(...)` boyutu da buna göre güncellenir.
  - **Ürün arama testi** (`poc/embed_test.py`, 19 ürün, 5 sorgu; ürün metni = ad + kategori + özellikler):
    - `emrecan`: **3/5**. Su geçirmez mont ve elbise sorgularında yanlış, maskara sorgusunda çok net doğru.
    - `e5-base`: **4/5**. Maskara 2. sırada kaldı; skorlar birbirine çok yakın (0.81-0.86).
    - `bge-m3`: **4/5**. Su geçirmez mont sorgusunda 1. sıraya "Su **Yolu** Desenli" montu koydu (kelime benzerliği tuzağı), 2. ve 3. sırada doğru ürünler var. Maskara sorgusunda net doğru, skorlar daha ayrışık.
    - İlk iki sıra: e5 ve bge-m3 berabere (MRR ikisinde de 0.9). Not: e5 ile bge-m3 **aynı tokenizer'ı** kullandığı halde farklı sonuç verdi. Yani farkı parçalama değil, asıl eğitim yaratıyor.
    - Sırada: ürün metnindeki gürültülü özellikleri çıkarmak (Menşei, Kutu Durumu, Yıkama Talimatı…) ve yorumları eklemek. Sonra e5 ile bge-m3 daha fazla sorguyla tekrar karşılaştırılacak.
    - **Yorum uzunluğu:** Ürün başına 20 yorum ortalama ~410, en fazla 910 token tutuyor. Özelliklerle birlikte e5'in 512 token sınırı ürünlerin yaklaşık yarısında yorumları keser; bge-m3'ün 8192 sınırı hepsini alır.
    - **Temizlenmiş metin + yorumlar, 7 sorgu:**
      - `bge-m3`: **6/7** (MRR 0.90). Tek hata "beyaz mont" sorgusu: marka adlarındaki *Bianco* (İtalyanca "beyaz") ve *Blanco* (İspanyolca "beyaz") onu yanılttı, gerçekten beyaz olan ürün 3. sırada kaldı.
      - `e5-base`: **5/7** (MRR 0.79). Yorumlar eklenince "deri ceket" sorgusunda kötüleşti; muhtemel sebep 512 token sınırında kesilme.
    - ✅ **Karar: `BAAI/bge-m3`** (1024 boyut). e5, hız sorun olursa yedek seçenek.
    - Ders: Renk gibi yapılandırılmış bilgiler yalnızca vektöre bırakılmamalı; sorgudan yakalanıp özellik filtresi olarak uygulanmalı (bkz. Aşama 5).
    - **Görülmemiş sorularla doğrulama** (12 sorgu: doğal cümle, yazım hatası, İngilizce, olmayan ürün): bge-m3 **1. sırada 10/11, ilk 3'te 11/11**. Tek kaçan "süet ceket" sorgusu: süet mont 2. sırada kaldı, fark sadece 0.004.
    - ⚠️ Olmayan ürün sorgusu ("laptop çantası") en yüksek skor olarak 0.495 aldı. Bu, bazı doğru eşleşmelerin skorundan (0.448) yüksek. Yani sabit bir skor eşiğiyle "sonuç yok" kararı verilemez (bkz. Aşama 5).
- ✅ **Aşama 0 tamamlandı (17 Eylül 2026):** scraping engelsiz çalışıyor ve seçilen model anlamlı sonuç veriyor.
- **Çıkış kriteri:** Scraping engelsiz çalışıyor ve model anlamlı sonuç veriyor. Değilse kategori/model kararı burada revize edilir.

### Aşama 1: Ortam ve Git — ✅ Tamamlandı (Reviewer Agent ertelendi)
- [x] `requirements.txt` ilk sürümü: selenium, protego, beautifulsoup4, sentence-transformers (sürümleri sabitlenmiş). torch GPU/CPU'ya göre ayrı kurulur, nasıl kurulacağı dosyanın başında yazıyor.
- Diğer paketler ilgili aşamada eklenir: fastapi, uvicorn, sqlalchemy, psycopg[binary], pgvector, alembic, pydantic-settings, httpx, pyjwt, passlib[bcrypt], anthropic, rich, ruff, bandit, pytest.
- [x] `git init`: yerel repo kuruldu, ilk commit `1367c72` (Aşama 0 kodları).
- [x] GitHub reposu: https://github.com/busracck/trendanalys (public). Giriş `gh auth login` ile yapıldı, `main` dalı `origin/main`'i takip ediyor.
- [x] `README.md` ilk sürümü: amaç, Aşama 0 sonuçları, kurulum, `poc/` scriptlerinin sırası, veri ve etik notları. Ayrıntılı sürümü Aşama 7'de yazılacak.
- [x] `.gitignore` hazırla: `.venv/`, `.env`, `__pycache__/`, `poc/output/`, `data/raw_html/`. İndirilen veri repoya girmez ("veri yeniden yayınlanmaz" kuralı). Model önbelleği `~/.cache` altında olduğu için zaten proje dışında.
- ⏸️ **Ertelendi (17 Eylül 2026):** Sistem henüz uçtan uca çalışmıyordu ve incelenecek gerçek kod azdı. Önce arama sistemi çalıştırılacak.
  - `.env.example` → Adım 2.3
  - Reviewer Agent maddeleri → Aşama 5'ten sonraki **Ara Aşama**

### Aşama 2: Veritabanı ve Vektör Mimarisi — 🔄 Güncellendi
- [ ] **Adım 2.1:** pgvector eklentisini kur: `sudo apt install postgresql-17-pgvector`
- [ ] **Adım 2.2:** Projeye ayrı bir veritabanı kullanıcısı ve veritabanı aç (ikisinin adı da `trendanalys`).
  - `vector` eklentisini yönetici (`postgres`) kullanıcısıyla bir kez aç. Uygulama kullanıcısına yönetici yetkisi verilmez.
  - Bağlantıyı `psql -h localhost -U trendanalys -d trendanalys` ile test et.
- [ ] **Adım 2.3:** `.env` ve `.env.example` hazırla.
  - Şimdilik sadece `DATABASE_URL` (`postgresql+psycopg://kullanıcı:şifre@localhost:5432/trendanalys`).
  - `.env` gerçek şifreyi içerir ve repoya girmez. `.env.example` şifresiz örnektir ve repoya girer.
  - `JWT_SECRET` Aşama 5'te, `ANTHROPIC_API_KEY` ve `REVIEWER_MODEL` Ara Aşama'da eklenecek.
- [ ] **Adım 2.4:** Paketleri kur ve sürümleriyle `requirements.txt` dosyasına ekle: sqlalchemy, psycopg[binary], pgvector, alembic, pydantic-settings.
- [ ] **Adım 2.5:** `app/config.py` (pydantic-settings ile `.env` okuma) ve `app/db.py` (engine, session, `Base`) yaz.
- [ ] **Adım 2.6:** `app/models.py` içine ürün tablolarını yaz:
  - `Product`: id, trendyol_id (unique), url, name, brand, category, category_path, price, currency, color, gender, rating, rating_count, review_count, `attributes` (JSONB), image_url, `search_text`, `embedding = mapped_column(Vector(1024))`, `tsv` (generated tsvector, `'turkish'`), content_hash, scraped_at, embedded_at
  - `ReviewSnippet`: product_id, text, rating, date. **Yorum yazanın adı yok (KVKK).**
  - Alanlar `poc/output/products.json` çıktısına göre güncellendi. `description` yok, çünkü ld+json açıklaması sadece SEO metni.
  - Kullanıcı tabloları (`User`, `SearchHistory`, `Favorite`, `RevokedToken`) Aşama 5'te, auth ile birlikte eklenecek.
- [ ] **Adım 2.7:** Alembic kur, ilk migrasyonu yaz ve `alembic upgrade head` ile uygula:
  - `CREATE EXTENSION IF NOT EXISTS vector;`
  - `products` ve `review_snippets` tabloları
  - index'ler: `embedding` üzerinde HNSW (`vector_cosine_ops`), `tsv` üzerinde GIN, `price` ve `category` üzerinde B-tree
- [ ] **Adım 2.8:** Doğrulama scripti yaz:
  - `poc/output/products.json` içindeki ürünleri embedding'leriyle veritabanına yaz.
  - SQL'de `<=>` ile bir sorguya en yakın 3 ürünü getir. Sonuç `embed_test.py` ile aynı çıkmalı.
- **Çıkış kriteri:** Tablolar ve index'ler migrasyonla oluşuyor, vektör araması SQL'den çalışıyor.

### Aşama 3: Veri Toplama (Selenium Scraping) — 🔄 Güncellendi
- [ ] `data/categories.yaml` hazırla: giyim & ayakkabı alt kategorileri (elbise, mont, hırka, sweatshirt, t-shirt, şort, bot, sandalet…). Hedef ~1000-1500 ürün.
- [ ] `scraper/robots.py` yaz: `protego` ile her URL'yi kontrol et, yasaklı URL'yi reddet.
- [ ] `scraper/driver.py` yaz:
  - tek sekme
  - istekler arası 4-8 sn rastgele bekleme
  - 403 veya captcha görülürse scraper'ı durdur
- [ ] `scraper/category_crawler.py` yaz:
  - sade kategori sayfalarından ürün linklerini (`-p-` içeren href'ler) topla
  - kategori başına birkaç sayfa gez (`?pi=2`, `?pi=3`)
  - `sst=` ve özellik filtresi kullanma
  - her URL'yi yine robots kontrolünden geçir
- [ ] `scraper/product_parser.py` yaz: ham HTML'i `data/raw_html/{trendyol_id}.html` olarak cache'le, sonra ayrıştır.
  - Hem `Product` hem `ProductGroup` bloklarını oku. Temel olarak Aşama 0'daki `poc/parse_product.py` kullanılır.
  - `ld+json` bloğu olmayan `/pd/` şablonu için sayfaya gömülü JSON'dan okuyan bir yedek ayrıştırıcı ekle. Önce bu şablonun ne kadar yaygın olduğunu ölç (Aşama 0'da 20 sayfadan 1'inde görüldü).
- [ ] `scraper/cleaner.py` yaz:
  - HTML tag'lerini ve emojileri temizle, boşlukları normalize et
  - **Türkçe küçük harf** fonksiyonu ekle (`İ→i`, `I→ı`)
- [ ] Veritabanına `trendyol_id` üzerinden upsert yap. `content_hash` değişirse `embedded_at` alanını sıfırla.
- [ ] CLI hazırla: `python -m scraper.run_scraper --category elbise --limit 100`

### Aşama 4: NLP Pipeline ve Embeddings — 🔄 Güncellendi
- [ ] `app/services/embedder.py` yaz: model (`BAAI/bge-m3`) uygulama açılışında tek sefer yüklenir.
- [ ] `nlp/text_builder.py` yaz:
  - Metin formatı: `Ad | Kategori | Marka | Özellikler | kısa yorum parçaları`. `ld+json` içindeki açıklama sadece SEO kalıbı olduğu için kullanılmaz.
  - Gürültülü özellikleri çıkar (`NOISE_ATTRIBUTES`: Menşei, Yıkama Talimatı, Kutu Durumu…) ve yorumları ekle. Temel olarak `poc/embed_test.py` içindeki `build_product_text` kullanılır.
  - Uzunluk: bge-m3'ün sınırı 8192 token, 20 yorum (en fazla ~910 token) rahatça sığar. Yine de metin uzunluklarını logla.
- [ ] `nlp/build_embeddings.py` yaz:
  - sadece `embedded_at IS NULL` olan ürünleri işle
  - 32'lik batch'ler ve `normalize_embeddings=True` kullan
  - toplu `UPDATE` yap

### Aşama 5: FastAPI Backend — 🔄 Güncellendi
- [ ] `app/services/query_parser.py` yaz:
  - 81 il adını Türkçe ekleriyle yakala ("İzmir'de", "Ankara'ya")
  - fiyat ifadelerini yakala ("1000 TL altı", "500-1000 arası")
  - kategori ipuçlarını sözlükten bul
  - renk ifadelerini (beyaz, siyah, bej…) yakalayıp `Renk` özelliğine filtre olarak uygula. Adım 0.4'te bge-m3, "beyaz mont" sorgusunda Bianco/Blanco marka adlarına kanmıştı.
- [ ] `app/services/weather.py` yaz:
  - Open-Meteo'dan anlık veya akşam (19-22) tahminini al
  - sonucu 30 dk TTL cache'de tut
  - sıcaklık/yağış/rüzgar değerlerini ifadelere çevir (ör. "serin hava, uzun kollu, katmanlı giyim")
- [ ] `app/services/search.py` yaz:
  - fiyat/kategori filtresi uygula
  - vektör top-50 ve full-text top-50 sonuçlarını RRF ile birleştir
  - "neden önerildi" alanını üret
  - sorgu embedding'ini LRU cache'de tut
  - alakasız sorgular için sabit skor eşiği kullanma (Adım 0.4'teki "laptop çantası" bulgusu). "Sonuç yok" kararını kategori eşleşmesine ve kelime araması sinyaline göre ver.
- [ ] Pydantic şemalarını `app/schemas.py` dosyasına yaz (`from_attributes=True`). Aşama 2'den taşındı.
- [ ] `POST /api/search` endpoint'ini yaz: `{query, city?, max_price?, limit}`
- [ ] Kullanıcı tablolarını yeni bir Alembic migrasyonuyla ekle (Aşama 2'den taşındı):
  - `User`: id, email, password_hash, default_city, created_at
  - `SearchHistory`, `Favorite`, `RevokedToken` (jti, expires_at)
- [ ] JWT auth endpoint'lerini yaz (`.env` ve `.env.example` dosyalarına `JWT_SECRET` ekle):
  - `POST /api/auth/register`
  - `POST /api/auth/login` (30 dk token)
  - `POST /api/auth/logout` (jti → RevokedToken)
  - `GET /api/users/me`
- [ ] Giriş yapmış kullanıcı özelliklerini ekle:
  - arama geçmişi
  - `default_city`
  - `POST/DELETE /api/favorites/{product_id}`
- [ ] `GET /api/products/{id}` ve `GET /health` endpoint'lerini ekle.

### Ara Aşama: Senior Reviewer Agent — ⏸️ Aşama 1'den taşındı
Aşama 5 bittikten sonra yapılır. Anthropic API anahtarı gerekir (Claude aboneliğinden ayrı, kullanım başına ücretli). Yazarken `claude-api` skill'i yüklenir.
- [ ] `.env` ve `.env.example` dosyalarına `ANTHROPIC_API_KEY` ve `REVIEWER_MODEL` ekle.
- [ ] `agents/review_guidelines.md` yaz. Projeye özel kurallar:
  - kod içinde gizli anahtar olmaz
  - SQL string birleştirme yapılmaz
  - scraper rate limiter ve robots kontrolünü atlamaz
  - endpoint'lerde `response_model` kullanılır
  - model her istekte yeniden yüklenmez
- [ ] `agents/reviewer.py` yaz:
  1. `git diff --cached` veya `--range main...HEAD` ile diff'i al.
  2. `ruff` ve `bandit` çalıştır.
  3. Diff + guidelines + lint bulgularını Claude API'ye gönder. Model `REVIEWER_MODEL` ile ayarlanır, varsayılan `claude-sonnet-5`. Büyük diff'leri dosya bazında böl.
  4. Yapılandırılmış çıktı al: `severity: blocker|major|minor`, dosya, satır, mesaj.
  5. Sonucu `rich` ile renkli olarak terminale yaz.
  6. `blocker` varsa çıkış kodu 1 döndür. API anahtarı yoksa sadece uyarı ver.
- [ ] `.pre-commit-config.yaml` hazırla: ruff, ardından local hook `python agents/reviewer.py --staged`.
- [ ] İlk tarama: `python agents/reviewer.py --range <ilk-commit>..HEAD`. Blocker ve major bulguları düzelt.

### Aşama 6: Web Arayüzü — 🆕 Yeni
- [ ] `GET /` adresinden `templates/index.html` sayfasını sun.
- [ ] Arama bölümünü yap:
  - arama kutusu ve örnek cümle çipleri
  - şehir seçimi
  - hava durumu rozeti ("İzmir · 14°C · serin")
- [ ] Ürün kartlarını yap: görsel, ad, marka, fiyat, puan, "neden önerildi", **Trendyol'da gör** linki, favori butonu.
- [ ] Giriş/kayıt modalını ve arama geçmişi panelini ekle.
- [ ] Mobil uyumluluğu sağla (vanilla JS, build aracı yok).

### Aşama 7: Değerlendirme, Optimizasyon ve Dokümantasyon — 🔄 Güncellendi
- [ ] `eval/queries.yaml` hazırla: 30-40 gerçekçi cümle ve her biri için elle işaretlenmiş alakalı ürünler.
- [ ] `eval/run_eval.py` yaz:
  - üç modu karşılaştır: **sadece kelime** / **sadece vektör** / **hibrit + hava durumu**
  - Recall@5 ve MRR ölç
- [ ] Reviewer Agent ile son tarama: Ara Aşama'daki taramadan sonra yazılan kod (Aşama 6 dahil). Blocker ve major bulguları refactor et.
- [ ] Performans testi yap:
  - p50/p95 ölç (hedef: CPU'da arama p95 < 300 ms)
  - darboğazı raporla (embedding / DB / hava durumu)
- [ ] Swagger açıklamalarını tamamla (`summary`, `response_model`, `examples`).
- [ ] README yaz: kurulum, mimari şema, eval tablosu, ekran görüntüleri, scraping etiği.
