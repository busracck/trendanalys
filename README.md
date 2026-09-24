# TrendAnalys: Trendyol için Cümleyle Ürün Arama

Trendyol'da arama anahtar kelimeyle çalışıyor. *"İzmir'de serin bir akşam için 1000 TL altı rahat bir elbise"* gibi bir cümleyle arama yapılamıyor.

Bu proje, Trendyol'dan toplanan bir ürün kataloğu üzerinde **anlamsal (semantik) arama** yapan bir sistem geliştiriyor:
- Cümlenin anlamını yorumlar.
- Şehir ve fiyat gibi bilgileri ayıklar.
- Hava durumunu hesaba katar.
- En uygun ürünleri Trendyol linkleriyle listeler.

> **Durum:** Aşama 0-3 tamamlandı: fizibilite testi, veritabanı (PostgreSQL + pgvector) ve veri toplama. Veritabanında 898 ürün ve 11.959 yorum var. Sırada vektörlerin toplu hesaplanması (Aşama 4) ve arama servisi (Aşama 5) var. Ayrıntılı plan ve sonuçlar: [docs/Yol_Haritasi.md](docs/Yol_Haritasi.md)

## Aşama 0'da neler doğrulandı?

| Soru | Sonuç |
|---|---|
| Trendyol'dan kurallara uygun veri çekilebilir mi? | Evet. 20 ürün sayfası engelsiz indirildi. |
| Sayfalardan ürün bilgisi çıkarılabilir mi? | Evet. Ad, fiyat, özellikler, puan ve ürün başına 20 yorum (sayfadaki `ld+json` bloğundan). |
| Model cümleyle arama yapabiliyor mu? | Evet. `BAAI/bge-m3`, daha önce görmediği 11 test sorgusunun 10'unda doğru ürünü 1. sıraya koydu. Yazım hatalı ve İngilizce sorgular da buna dahil. |

Üç model karşılaştırıldı: Türkçe Sentence-BERT, `multilingual-e5-base` ve `bge-m3`. Karşılaştırmanın ayrıntıları yol haritasında.

## Kullanılan teknolojiler

- **Şu an:** Python 3.13, Selenium, Protego (robots.txt), BeautifulSoup, PostgreSQL + pgvector, SQLAlchemy, Alembic, sentence-transformers (`BAAI/bge-m3`), PyTorch (CUDA)
- **Planlanan:** FastAPI, Open-Meteo, basit bir web arayüzü, Claude API ile kod inceleme ajanı

## Kurulum

Google Chrome kurulu olmalı. Selenium, gereken sürücüyü kendisi indirir.

```bash
python3 -m venv .venv
source .venv/bin/activate

# torch'u önce kur: NVIDIA GPU (CUDA 12.4) için
pip install torch==2.6.0 --index-url https://download.pytorch.org/whl/cu124
# ...GPU yoksa bunun yerine:
# pip install torch==2.6.0 --index-url https://download.pytorch.org/whl/cpu

pip install -r requirements.txt
```

## Veritabanı

PostgreSQL 17 ve pgvector gerekiyor:

```bash
sudo apt install postgresql-17-pgvector
sudo -u postgres createuser --pwprompt trendanalys
sudo -u postgres createdb --owner=trendanalys trendanalys

cp .env.example .env     # DATABASE_URL satırına kendi şifreni yaz
alembic upgrade head     # tabloları ve index'leri oluşturur
```

## Veri toplama

```bash
python -m scraper.run_scraper                        # categories.yaml'daki bütün kategoriler
python -m scraper.run_scraper --category kadin-mont  # tek kategori
python -m scraper.run_scraper --limit 10             # kategori başına 10 ürün
```

Toplanacak kategoriler `data/categories.yaml` dosyasında tutulur. Scraper istekler arasında 4-8 saniye bekler, indirdiği sayfaları `data/raw_html/` klasöründe saklar ve aynı ürüne ikinci kez rastlayınca içerik imzasına bakıp değişmemişse dokunmaz. Yarıda kesilirse aynı komutla kaldığı yerden devam eder.

Toplanan ürünlerin vektörlerini hesapla (yeni ürün çekildikten sonra her seferinde):

```bash
python -m nlp.build_embeddings
```

İlk çalıştırmada `bge-m3` modeli (~2.3 GB) indirilir.

## Arama kalitesini ölç

```bash
python -m eval.run_eval
```

## Veri ve etik

- **Veri repoda yok.** İndirilen sayfalar ve yorumlar yeniden yayınlanmaz, `.gitignore` ile hariç tutulur. Veriyi görmek isteyen scriptleri kendi bilgisayarında çalıştırmalıdır.
- **robots.txt kurallarına uyulur.** Her adres indirilmeden önce [Protego](https://github.com/scrapy/protego) ile kontrol edilir. Arama sonuçları ve yorum sayfaları gibi yasaklı yollara gidilmez. Yorumlar yalnızca ürün sayfasında zaten yer alan yapılandırılmış veriden okunur.
- **Siteye yük bindirilmez.** İstekler arasında 4-8 saniye beklenir. Bir sayfa daha önce indirildiyse tekrar istenmez. Engel ya da captcha belirtisi görülürse script durur, engeli aşma girişiminde bulunulmaz.
- **Kişisel veri saklanmaz.** Yorum yazanların adları kaydedilmez (KVKK).
