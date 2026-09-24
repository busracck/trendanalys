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
   - **pgvector 0.8.0** kuruldu (17 Eylül 2026, `postgresql-17-pgvector`). Proje veritabanı ve kullanıcısı: `trendanalys`.
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
- [x] **Adım 2.1:** pgvector eklentisini kur: `sudo apt install postgresql-17-pgvector`
- [x] **Adım 2.2:** Projeye ayrı bir veritabanı kullanıcısı ve veritabanı aç (ikisinin adı da `trendanalys`).
  - `vector` eklentisini yönetici (`postgres`) kullanıcısıyla bir kez aç. Uygulama kullanıcısına yönetici yetkisi verilmez.
  - Bağlantıyı `psql -h localhost -U trendanalys -d trendanalys` ile test et.
  - Sonuç: `vector` 0.8.0 açık. `<=>` testi: aynı vektörler için 0, dik vektörler için 1 (cosine mesafesi = 1 − benzerlik).
- [x] **Adım 2.3:** `.env` ve `.env.example` hazırla.
  - Şimdilik sadece `DATABASE_URL` (`postgresql+psycopg://kullanıcı:şifre@localhost:5432/trendanalys`).
  - `.env` gerçek şifreyi içerir ve repoya girmez. `.env.example` şifresiz örnektir ve repoya girer.
  - `JWT_SECRET` Aşama 5'te, `ANTHROPIC_API_KEY` ve `REVIEWER_MODEL` Ara Aşama'da eklenecek.
- [x] **Adım 2.4:** Paketleri kur ve sürümleriyle `requirements.txt` dosyasına ekle: sqlalchemy, psycopg[binary], pgvector, alembic, pydantic-settings.
- [x] **Adım 2.5:** `app/config.py` (pydantic-settings ile `.env` okuma) ve `app/db.py` (engine, session, `Base`) yaz.
- [x] **Adım 2.6:** `app/models.py` içine ürün tablolarını yaz:
  - `Product`: id, trendyol_id (unique), url, name, brand, category, category_path, price, currency, color, gender, rating, rating_count, review_count, `attributes` (JSONB), image_url, `search_text`, `embedding = mapped_column(Vector(1024))`, `tsv` (generated tsvector, `'turkish'`), content_hash, scraped_at, embedded_at
  - `ReviewSnippet`: product_id, text, rating, date. **Yorum yazanın adı yok (KVKK).**
  - Alanlar `poc/output/products.json` çıktısına göre güncellendi. `description` yok, çünkü ld+json açıklaması sadece SEO metni.
  - Kullanıcı tabloları (`User`, `SearchHistory`, `Favorite`, `RevokedToken`) Aşama 5'te, auth ile birlikte eklenecek.
- [x] **Adım 2.7:** Alembic kur, ilk migrasyonu yaz ve `alembic upgrade head` ile uygula:
  - `CREATE EXTENSION IF NOT EXISTS vector;`
  - `products` ve `review_snippets` tabloları
  - index'ler: `embedding` üzerinde HNSW (`vector_cosine_ops`), `tsv` üzerinde GIN, `price` ve `category` üzerinde B-tree
- [x] **Adım 2.8:** Doğrulama scripti: `poc/load_to_db.py`
  - 19 ürün ve 239 yorum veritabanına yazıldı, `tsv` sütununu PostgreSQL kendisi doldurdu.
  - "yeşil renkli mont" sorgusu SQL'de (`cosine_distance`) `embed_test.py` ile aynı ürünleri getirdi: 1144525931 (0.414), 879026670 (0.469).
- **Çıkış kriteri:** Tablolar ve index'ler migrasyonla oluşuyor, vektör araması SQL'den çalışıyor.
- ✅ **Aşama 2 tamamlandı (21 Eylül 2026).** Migrasyon sürümü `8b6444147f4f`.
- Notlar:
  - `url`, `content_hash` ve `scraped_at` alanları `products.json` içinde yok; scraper Aşama 3'te dolduracak.
  - `build_product_text` şu an hem `poc/embed_test.py` hem `poc/load_to_db.py` içinde. Aşama 4'te `nlp/text_builder.py` altında tek kaynağa inecek.

### Aşama 3: Veri Toplama (Selenium Scraping) — 🔄 Güncellendi
Hedef: ~1000-1500 ürün, doğrudan veritabanına. `search_text` ve `embedding` boş kalır, onları Aşama 4 doldurur.
- [x] **Adım 3.1:** `scraper/` paketi ve `data/categories.yaml`.
  - Giyim & ayakkabı alt kategorileri (elbise, mont, hırka, sweatshirt, t-shirt, şort, bot, sandalet…), her biri için **sade** kategori URL'si ve hedef ürün sayısı.
  - Filtreli (`-x-…-a…-v…`), aramalı (`?q=`) veya sıralamalı (`?sst=`) URL yok.
  - `pyyaml` paketini kur ve `requirements.txt`'e ekle.
- [x] **Adım 3.2:** `scraper/robots.py`: `protego` ile robots.txt'i bir kez indir, `is_allowed(url)` sun. Yasaklı URL reddedilir.
- [x] **Adım 3.3:** `scraper/driver.py`: tek Chrome penceresi, istekler arası 4-8 sn rastgele bekleme, `h1` beklemesi, engel/captcha belirtisinde durdurma. Temel: `poc/open_product.py`.
- [x] **Adım 3.4:** `scraper/category_crawler.py`: `a.product-card` linklerini topla, kategori başına birkaç sayfa gez (`?pi=2`, `?pi=3`), her URL'yi robots kontrolünden geçir. Temel: `poc/crawl_category.py`.
- [x] **Adım 3.5:** `scraper/product_parser.py`: ham HTML `data/raw_html/{trendyol_id}.html` olarak cache'lenir, sonra ayrıştırılır.
  - Hem `Product` hem `ProductGroup` bloklarını oku (temel: `poc/parse_product.py`).
  - `ld+json` bloğu olmayan `/pd/` şablonu için gömülü JSON'dan okuyan yedek ayrıştırıcı. Yaygınlığı önce ölçülür (Aşama 0'da 20 sayfada 1).
- [x] **Adım 3.6:** `scraper/cleaner.py`: HTML etiketi ve emoji temizliği, boşluk normalizasyonu, **Türkçe küçük harf** (`İ→i`, `I→ı`), `content_hash` üretimi.
- [x] **Adım 3.7:** `scraper/run_scraper.py`: CLI (`python -m scraper.run_scraper --category elbise --limit 100`).
  - `trendyol_id` üzerinden upsert. `content_hash` değiştiyse `embedded_at` sıfırlanır (yeniden embedding gerekir).
  - Yorumlar `review_snippets` tablosuna yazılır.
- Not: `polite_sleep` ve robots kontrolü `driver.fetch_page` içinde; ağa çıkan her istek oradan geçtiği için kural atlanamaz. Önbellekten okunan sayfalar beklemez.
- [x] **Adım 3.8:** Tam çalıştırma (22 Eylül 2026): 8 kategori, **898 ürün, 11.959 yorum, 0 hata**.
  - Son turda: 596 yeni, 23 güncellendi, 181 değişmedi.
  - Fiyat ve görsel bütün üründe dolu; renk 117 üründe, yorum 108 üründe yok.
  - `data/raw_html/`: 891 sayfa, 565 MB (repoya girmez).
- **Çıkış kriteri:** Veritabanında hedeflenen sayıda ürün var, tekrar çalıştırma mevcut kayıtları bozmuyor, robots kuralları hiç ihlal edilmedi.
- ✅ **Aşama 3 tamamlandı (22 Eylül 2026).**
- Tarama sırasında çıkan iki sorun ve çözümleri:
  - Chrome uzun oturumlarda takılıyor (`ReadTimeoutError`, chromedriver cevap vermiyor). Bu hata `WebDriverException` değil `urllib3.exceptions.HTTPError` alt sınıfı; ikisi birden yakalanıyor. Ayrıca her 50 üründe tarayıcı yenileniyor ve sayfa 2 kez deneniyor.
  - `category` sütununa kategori yolunun son parçası yazılıyordu, Trendyol oraya bazen markayı ekliyor ("Defacto Kadın Mont"). Artık `categories.yaml`'daki ad yazılıyor; eski 40 kayıt SQL ile düzeltildi.
- Temizlik: `poc/open_product.py`, `poc/crawl_category.py`, `poc/parse_product.py` ve `poc/load_to_db.py` silindi (işlevleri `scraper/` altına taşındı). `poc/embed_test.py` kaldı: model başarısını ölçen tek script o.

### Aşama 4: NLP Pipeline ve Embeddings — 🔄 Güncellendi
- [x] **Adım 4.1:** `nlp/text_builder.py`: `Product` satırından modele verilecek metni üretir.
  - Biçim: `Ad. Kategori: a > b. özellik: değer; ... Yorumlar: ...` (temel: `poc/embed_test.py` içindeki `build_product_text`).
  - `NOISE_ATTRIBUTES` (Menşei, Yıkama Talimatı, Kutu Durumu…) ayıklanır. `ld+json` açıklaması SEO kalıbı olduğu için kullanılmaz.
- [x] **Adım 4.2:** `app/services/embedder.py`: modeli **tek sefer** yükler, `encode_passages` ve `encode_query` sunar.
  - GPU 4 GB olduğu için `max_seq_length` sınırlanır ve küçük batch kullanılır.
- [x] **Adım 4.3:** `nlp/build_embeddings.py`: CLI.
  - sadece `embedded_at IS NULL` olan ürünleri işler
  - batch'ler hâlinde encode eder, `normalize_embeddings=True`
  - her batch'ten sonra `commit`; `search_text`, `embedding`, `embedded_at` dolar
  - metin uzunluklarını (token/karakter) loglar
- [x] **Adım 4.4:** 898 ürün için çalıştır, süreyi ölç. SQL'den örnek arama yap, `poc/embed_test.py` sonuçlarıyla karşılaştır.
- **Çıkış kriteri:** `embedded_at IS NULL` kalan ürün yok, vektör araması 898 ürün üzerinde anlamlı sonuç veriyor.
- ✅ **Aşama 4 tamamlandı (23 Eylül 2026).**
  - 871 ürün **174.6 sn** (0.20 sn/ürün, GTX 1650 Ti). 898/898 ürünün vektörü hazır.
  - Metin uzunlukları: ortanca 1564, en uzun 3063 karakter (~800 token) — 1024'lük `max_seq_length` yetiyor.
  - HNSW index kullanılıyor: `Index Scan using ix_products_embedding_hnsw`, en yakın 5 ürün **~1 ms**.
  - Ölçüm `eval/` altına taşındı (`queries.yaml` + `run_eval.py`), `poc/embed_test.py` silindi.
- **Kalite ölçümü (23 Eylül, 898 ürün):** otomatik puan 2/11 (1. sıra) ve 4/11 (ilk 3), **ama elle bakınca 11 sorgunun 10'unda gelen ürünler doğru.**
  - Etiketler 19 ürünlük havuza göre yapıldığı için puan gerçeği yansıtmıyor. Aşama 7'de 898 ürüne göre yeniden etiketlenecek.
  - **Gerçek hata:** "yeşil renkli mont" → 1. sırada `river green` markalı siyah mont. Renk filtresi şart (Aşama 5, `query_parser`).
  - **Eşik doğrulaması:** alakasız "laptop çantası" sorgusunun en yakın mesafesi 0.454; doğru cevabı 0.491 mesafede olan sorgular var. Sabit eşik kullanılamaz.

### Aşama 5: FastAPI Backend — 🔄 Güncellendi
- [x] **Adım 5.1:** Veri normalizasyonu (filtreler bunsuz çalışmaz).
  - `gender`: `male/female/unisex` ve `Kadın/Erkek/Unisex` karışık → `kadin/erkek/unisex`.
  - `color`: `Siyah / SİYAH / siyah / Siyah-BK27` karışık → bilinen ana renge eşle, bulunamazsa Türkçe küçük harf.
  - `scraper/cleaner.py`'ye `normalize_gender` ve `normalize_color` eklenir (yeni taramalar için), mevcut satırlar Alembic veri migrasyonuyla düzeltilir.
- [x] **Adım 5.2:** `app/services/query_parser.py`:
  - 81 il adını Türkçe ekleriyle yakala ("İzmir'de", "Ankara'ya")
  - fiyat ifadelerini yakala ("1000 TL altı", "500-1000 arası")
  - renk ifadelerini yakala → SQL filtresi (Adım 4.4'teki "river green" hatası bu yüzden)
  - kategori ipuçlarını `categories.yaml` adlarına eşle (elbise, mont, sweatshirt, tişört, bot, spor ayakkabı)
- [x] **Adım 5.3:** `app/services/weather.py`:
  - Open-Meteo'dan anlık veya akşam (19-22) tahminini al (şehir koordinatı için geocoding API, sonuç cache'lenir)
  - 30 dk TTL cache
  - sıcaklık/yağış/rüzgar değerlerini ifadelere çevir ("serin hava, uzun kollu, katmanlı giyim")
- [x] **Adım 5.4:** `app/services/search.py`:
  - filtreler: fiyat, renk, kategori, cinsiyet
  - vektör top-50 (`<=>`) + full-text top-50 (`tsv`, `turkish`) → RRF ile birleştir
  - "neden önerildi" alanını üret
  - sorgu embedding'ini LRU cache'de tut
  - alakasız sorgular için sabit skor eşiği kullanma (Adım 4.4 bulgusu: alakasız sorgunun en yakın mesafesi 0.454, doğru cevabı 0.491 olan sorgu var)
- Adım 5.1-5.4 sonuçları (23 Eylül 2026):
  - Veri normalizasyonu migrasyonu `b46bc16a7e20`: `siyah` 316, `kadin` 621 / `erkek` 262 / `unisex` 15.
  - **Renk filtresi katı olamıyor:** "Ltb ... Yeşil Mont" ürününün `color` sütunu `haki`, 117 üründe renk hiç yok. Filtre renk ailesi (yeşil-haki, beyaz-ekru-krem…) VEYA ürün adı üzerinden çalışıyor.
  - Uçtan uca ilk çalışma başarılı: "yağmurda ıslanmayan kapüşonlu mont" → su geçirmez montlar; "İzmir'de 1500 TL altı elbise" → fiyat ve kategori filtreleri tuttu, hava durumu ifadesi eklendi.
  - **Bilinen eksik:** "kışın giyeceğim" gibi gelecek zaman ifadelerinde bugünün havası kullanılıyor. Aşama 7'de ele alınacak.
- [x] **Adım 5.5:** `app/schemas.py` ve `POST /api/search` (`{query, city?, max_price?, limit}`), `GET /api/products/{id}`, `GET /health`.
- API çalışıyor (24 Eylül 2026): `/health`, `POST /api/search`, `GET /api/products/{id}`, Swagger `/docs`.
  - Pydantic doğrulaması kapıda tutuyor: 2 harften kısa sorgu 422 dönüyor.
  - İlk istek ~25 sn (model o anda yükleniyor). Aşama 6'da açılışta yüklenecek.
  - **Eksik:** `why` alanı sorgunun filtrelerini yazıyor, ürüne özgü değil. Aşama 6'da eşleşen özellikler eklenecek.
- [ ] **Adım 5.6:** Kullanıcı tabloları (Aşama 2'den taşındı) + JWT auth:
  - `User`, `SearchHistory`, `Favorite`, `RevokedToken` (jti, expires_at) — yeni Alembic migrasyonu
  - `.env` ve `.env.example` dosyalarına `JWT_SECRET`
  - `POST /api/auth/register`, `POST /api/auth/login` (30 dk token), `POST /api/auth/logout`, `GET /api/users/me`
- [ ] **Adım 5.7:** Giriş yapmış kullanıcı özellikleri: arama geçmişi, `default_city`, `POST/DELETE /api/favorites/{product_id}`.
- [ ] **Adım 5.8:** `eval/run_eval.py`'yi üç modu karşılaştıracak şekilde genişlet: sadece kelime / sadece vektör / hibrit.
- **Çıkış kriteri:** `POST /api/search` cümleyle arama yapıyor, filtreler ve hava durumu çalışıyor, giriş yapan kullanıcı favori ekleyebiliyor.

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
- [x] **Adım 6.1:** Kurulum: `jinja2` paketi, `app/templates/` ve `app/static/` klasörleri, `GET /` ucu.
  - Model açılışta yüklensin (FastAPI `lifespan`), ilk arama 25 sn beklemesin.
- [x] **Adım 6.2:** `index.html` iskeleti: başlık, arama kutusu, örnek cümle çipleri, şehir alanı, sonuç bölgesi.
- [x] **Adım 6.3:** `style.css`: sade tasarım, ürün kartı ızgarası, mobil uyumu.
- [x] **Adım 6.4:** `app.js`: `fetch` ile `POST /api/search`, yükleniyor durumu, hata durumu, kartları basma.
  - Kart: görsel, ad, marka, fiyat, puan, "neden önerildi", **Trendyol'da gör** linki.
  - Hava durumu rozeti ("İzmir · 18°C · ılık hava").
- Arayüz çalışıyor (24 Eylül 2026): tek sayfa, arama kutusu, örnek çipler, "cümleden anladığım" şeridi, ürün kartları.
  - Tasarım kararı: vurgu rengi hava sıcaklığına göre değişiyor; ayrıştırılan filtreler kullanıcıya gösteriliyor.
  - **GPU uyarısı:** 4 GB VRAM'e modelin tek kopyası sığıyor. `uvicorn` açıkken `build_embeddings`/`run_eval` çalıştırılamaz. `get_model` artık OOM'da CPU'ya düşüyor.
  - **Veri dersi:** "erkek pantolon" sorgusu alakasız sonuç verdi, çünkü katalogda pantolon yoktu. Kategori eklendi (`erkek-pantolon` 100, `kadin-pantolon` yarım). Yeni ürün çekince `build_embeddings` çalıştırmak şart, yoksa ürün aramada görünmez.
- [ ] **Adım 6.5:** "Neden önerildi" metnini ürüne özgü hâle getir (eşleşen özellikler: kapüşonlu, su geçirmez…).
- [ ] **Adım 6.6:** Favori butonu ve giriş/kayıt modalı (Adım 5.6-5.7 bittikten sonra).
- **Çıkış kriteri:** Tarayıcıdan cümle yazılıp ürün kartları görülebiliyor, telefonda da düzgün görünüyor.

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
