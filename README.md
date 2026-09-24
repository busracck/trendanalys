# TrendAnalys — Trendyol için cümleyle ürün arama

Trendyol'da arama anahtar kelimeyle çalışır. *"İzmir'de serin bir akşam için 1500 TL altı elbise"* diye aratamazsınız.

Bu proje onu yapıyor: cümleyi anlıyor, şehri ve bütçeyi cümleden çıkarıyor, o şehrin havasını hesaba katıyor ve anlamca en yakın ürünleri Trendyol linkleriyle listeliyor.

![TrendAnalys arayüzü](docs/ekran-goruntusu.png)

Veri: Trendyol'dan `robots.txt` kurallarına uyularak toplanmış **1097 ürün**, **14.456 yorum**, 451 marka, 7 ürün türü (elbise, mont, sweatshirt, tişört, pantolon, bot, spor ayakkabı).

## Neden anlamsal arama?

Kullanıcı "yağmurda ıslanmayan mont" yazar; ürünün adında "su geçirmez" yazar. Kelime araması bu ikisini eşleştiremez, anlamsal arama eşleştirir.

Bunu ölçtük. 10 etiketli sorgu, 1097 ürün, ilk 5 sonuç:

| yöntem | 1. sıra doğru | Precision@5 | Recall@5 | MRR |
|---|---|---|---|---|
| kelime araması (PostgreSQL full-text) | %80 | %54 | %60 | 0.90 |
| **anlamsal arama (pgvector + bge-m3)** | **%90** | **%74** | **%80** | **0.93** |
| hibrit (RRF 1:1) | %70 | %70 | %76 | 0.81 |
| hibrit (RRF 10:1) | %90 | %70 | %76 | 0.93 |

Anlamsal arama her metrikte önde. En büyük farkı yazım hatalı ("deri cekt"), İngilizce ("white sneakers") ve dolaylı anlatımlı ("yağmurda ıslanmayan") sorgularda açıyor.

**Hibrit arama kaldırıldı.** İki yöntemi RRF ile birleştirmek kulağa daha gelişmiş geliyordu ama ölçüm aksini söyledi: kelime kolu her ağırlıkta doğru ürünleri aşağı itti. Varsayılan arama artık yalnızca vektör + SQL filtreleri. Karşılaştırma kodu duruyor, kararı tekrar sınamak isteyen `python -m eval.run_eval` çalıştırabilir.

## Nasıl çalışıyor?

```
Selenium scraper ──> data/raw_html (önbellek) ──> parser + temizlik ──> PostgreSQL
                                                                            │
                                                     build_embeddings ──> embedding Vector(1024)

Kullanıcı: "İzmir'de serin bir akşam için 1500 TL altı elbise"
   │
   ├─ query_parser ──> şehir: izmir · bütçe: ≤1500 · kategori: elbise
   ├─ weather ──────> Open-Meteo: 21°C "ılık hava, rüzgarlı"
   ├─ embedder ─────> "serin bir akşam için elbise, ılık hava, rüzgarlı" -> 1024 boyutlu vektör
   └─ search ───────> SQL: fiyat/kategori filtresi + vektör araması (<=>, HNSW index)
                      └─> ürün kartları + "neden önerildi" + Trendyol linki
```

Cümleden çıkarılan her bilgi arayüzde gösteriliyor ("cümleden anladığım" şeridi). Kullanıcı sonucu neden aldığını görüyor.

**Neden bazı bilgiler filtreye alınıyor?** Fiyat ve renk vektöre bırakılamıyor: model "1000 TL altı"nı anlamıyor, "yeşil" arayana `river green` markalı siyah montu getiriyor. Bunlar SQL filtresi olarak çalışıyor. Renk filtresi de katı değil: "Yeşil Mont" adlı ürünün renk sütununda `haki` yazabiliyor, 117 üründe renk hiç yok — filtre renk ailesi (yeşil-haki) veya ürün adı üzerinden eşleştiriyor.

## Performans

11 sorgu × 3 tur, model CPU'da, 1097 ürünlük katalog:

| adım | ortanca | p95 |
|---|---|---|
| cümle ayrıştırma | 0.2 ms | 0.2 ms |
| embedding (sorgu → vektör) | 71 ms | 81 ms |
| SQL (vektör araması + filtreler) | 2.9 ms | 6 ms |
| **toplam arama** | **6 ms** | **80 ms** |

Toplam ortanca embedding'den küçük, çünkü sorgu vektörleri LRU önbellekte tutuluyor: aynı cümle ikinci kez arandığında model hiç çalışmıyor. Yeni bir cümle ~80 ms, tekrar eden cümle ~6 ms sürüyor.

Darboğaz embedding (toplam sürenin ~%90'ı). Vektör araması HNSW index sayesinde 3 ms'de bitiyor. Ölçüm `python -m eval.benchmark` ile tekrarlanabilir.

## Teknolojiler

| Katman | Ne kullanıldı |
|---|---|
| Veri toplama | Selenium, Protego (robots.txt), BeautifulSoup |
| Veritabanı | PostgreSQL 17 + pgvector (HNSW, `vector_cosine_ops`), SQLAlchemy, Alembic |
| Model | `BAAI/bge-m3` (çok dilli, 1024 boyut), sentence-transformers, PyTorch |
| API | FastAPI, Pydantic |
| Arayüz | Jinja2, vanilla JS (build aracı yok) |
| Dış servis | Open-Meteo (anahtarsız, 30 dk önbellek) |

Model seçimi de ölçümle yapıldı: Türkçe Sentence-BERT ve `multilingual-e5-base` ile karşılaştırıldı, bge-m3 kazandı. Ayrıntılar [docs/Yol_Haritasi.md](docs/Yol_Haritasi.md) dosyasında.

## Kurulum

Gereken: Python 3.13, PostgreSQL 17, Google Chrome.

```bash
python3 -m venv .venv
source .venv/bin/activate

# torch'u önce kur: NVIDIA GPU (CUDA 12.4) için
pip install torch==2.6.0 --index-url https://download.pytorch.org/whl/cu124
# GPU yoksa: pip install torch==2.6.0 --index-url https://download.pytorch.org/whl/cpu

pip install -r requirements.txt
```

Veritabanı:

```bash
sudo apt install postgresql-17-pgvector
sudo -u postgres createuser --pwprompt trendanalys
sudo -u postgres createdb --owner=trendanalys trendanalys

cp .env.example .env     # DATABASE_URL satırına kendi şifreni yaz
alembic upgrade head     # tablolar, index'ler ve vector eklentisi
```

## Kullanım

```bash
# 1. Veri topla (kategoriler data/categories.yaml dosyasında)
python -m scraper.run_scraper                        # hepsi, ~10 dk/kategori
python -m scraper.run_scraper --category kadin-mont  # tek kategori

# 2. Vektörleri hesapla (her yeni üründen sonra şart)
python -m nlp.build_embeddings

# 3. Sunucuyu başlat
uvicorn app.main:app --reload     # http://127.0.0.1:8000

# 4. Arama kalitesini ölç
python -m eval.run_eval
python -m eval.label              # test sorgularını elle etiketle
```

İlk çalıştırmada `bge-m3` modeli (~2.3 GB) indirilir. 4 GB'lık bir GPU'da modelin **tek kopyası** sığar: `uvicorn` açıkken `build_embeddings` veya `run_eval` çalıştırılamaz, model CPU'ya düşer.

## Kod inceleme ajanı

`agents/reviewer.py` commit öncesi değişikliği inceler: önce `ruff` ve `bandit` (kesin bulgular), sonra diff + proje kuralları bir LLM'e gönderilir.

```bash
python -m agents.reviewer              # çalışma alanındaki değişiklikler
python -m agents.reviewer --staged     # commit'e hazırlananlar
python -m agents.reviewer --staged --engelle   # blocker varsa commit'i durdur
```

Sağlayıcı `.env` ile seçilir ve kod tarafında hiçbir şey değişmez:

| sağlayıcı | not |
|---|---|
| `ollama` (varsayılan) | Yerel, ücretsiz, anahtarsız. Kod bilgisayardan çıkmaz |
| `gemini` | `GEMINI_API_KEY` ister |
| `claude` | `ANTHROPIC_API_KEY` ister |

Uzak sağlayıcı kota ya da yoğunluk nedeniyle cevap vermezse (429/503) iki kez tekrar denenir, sonra `REVIEWER_FALLBACK` sağlayıcısına düşülür.

**Model karşılaştırması.** Bilerek 5 kural ihlali içeren bir dosya hazırlandı (robots baypası, SQL enjeksiyonu, koda gömülü API anahtarı, düşürülmüş bekleme süresi, KVKK ihlali). `qwen3:4b` ikisini yakaladı, üçünü kaçırdı, bir tane de yanlış bulgu üretti. Bu yüzden blocker bulgusu varsayılan olarak commit'i **durdurmuyor**: yanılma payı olan bir aracın yolu kapatması, aracın tamamen kapatılmasına yol açar. `--engelle` bayrağı güçlü bir model kullanıldığında devreye alınır.

`agents/review_guidelines.md` projeye özel 19 kuralı içerir: robots kontrolü atlanamaz, bekleme süresi düşürülemez, yorum yazarı saklanmaz, SQL string birleştirmeyle kurulmaz, model her istekte yüklenmez…

## Veri ve etik

- **Veri repoda yok.** İndirilen sayfalar ve yorumlar yeniden yayınlanmaz, `.gitignore` ile hariç tutulur. Ürün görselleri kopyalanmaz, Trendyol'un sunucusundan yüklenir.
- **robots.txt kurallarına uyulur.** Her adres indirilmeden önce [Protego](https://github.com/scrapy/protego) ile kontrol edilir; kontrol ağa çıkan tek fonksiyonun (`driver.fetch_page`) içindedir, atlanamaz. Arama sonuçları (`/sr`) ve yorum sayfaları (`/yorumlar`) gibi yasaklı yollara gidilmez.
- **Siteye yük bindirilmez.** İstekler arasında 4-8 saniye beklenir, indirilen sayfalar önbelleğe alınır, aynı ürün iki kez istenmez.
- **Engel görülürse durulur.** Sayfa yüklenmezse scraper durur, atlatma denenmez.
- **Kişisel veri saklanmaz.** Yorumlar ürün sayfasının yapılandırılmış verisinden okunur, yorum yazanların adları kaydedilmez (KVKK).

## Bilinen sınırlar

- **Ölçüm 10 sorguluk.** Yön gösterir ama küçük bir örneklem; sorgu sayısı artırılmalı.
- **Katalog 7 türle sınırlı.** Kullanıcı olmayan bir tür sorarsa sistem alakasız ürün göstermek yerine "katalogda çanta yok" der.
- **Zaman ifadeleri.** "Kışın giyeceğim mont" denildiğinde bugünün havası kullanılıyor, gelecek mevsim değil.
- **Eşleşme açıklaması kelime temelli.** "Neden önerildi" satırı kullanıcının kelimelerinin ürün adında geçip geçmediğine bakıyor; anlamsal eşleşmenin *hangi* kavramdan geldiğini söyleyemiyor.
- **Marka/model kodu aramaları** ("Puma 372605") test edilmedi; orada kelime araması daha iyi olabilir.

## Proje geçmişi

Fizibilite testinden başlayarak her aşamanın kararları, ölçümleri ve yanlış çıkan varsayımları [docs/Yol_Haritasi.md](docs/Yol_Haritasi.md) dosyasında kayıtlı.
