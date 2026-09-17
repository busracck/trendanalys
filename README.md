# TrendAnalys: Trendyol için Cümleyle Ürün Arama

Trendyol'da arama anahtar kelimeyle çalışıyor. *"İzmir'de serin bir akşam için 1000 TL altı rahat bir elbise"* gibi bir cümleyle arama yapılamıyor.

Bu proje, Trendyol'dan toplanan bir ürün kataloğu üzerinde **anlamsal (semantik) arama** yapan bir sistem geliştiriyor:
- Cümlenin anlamını yorumlar.
- Şehir ve fiyat gibi bilgileri ayıklar.
- Hava durumunu hesaba katar.
- En uygun ürünleri Trendyol linkleriyle listeler.

> **Durum:** Aşama 0 (fizibilite testi) tamamlandı. Ayrıntılı plan ve sonuçlar: [docs/Yol_Haritasi.md](docs/Yol_Haritasi.md)

## Aşama 0'da neler doğrulandı?

| Soru | Sonuç |
|---|---|
| Trendyol'dan kurallara uygun veri çekilebilir mi? | Evet. 20 ürün sayfası engelsiz indirildi. |
| Sayfalardan ürün bilgisi çıkarılabilir mi? | Evet. Ad, fiyat, özellikler, puan ve ürün başına 20 yorum (sayfadaki `ld+json` bloğundan). |
| Model cümleyle arama yapabiliyor mu? | Evet. `BAAI/bge-m3`, daha önce görmediği 11 test sorgusunun 10'unda doğru ürünü 1. sıraya koydu. Yazım hatalı ve İngilizce sorgular da buna dahil. |

Üç model karşılaştırıldı: Türkçe Sentence-BERT, `multilingual-e5-base` ve `bge-m3`. Karşılaştırmanın ayrıntıları yol haritasında.

## Kullanılan teknolojiler

- **Şu an:** Python 3.13, Selenium, Protego (robots.txt), BeautifulSoup, sentence-transformers (`BAAI/bge-m3`), PyTorch (CUDA)
- **Planlanan:** FastAPI, PostgreSQL + pgvector, Open-Meteo, basit bir web arayüzü, Claude API ile kod inceleme ajanı

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

## Deneme scriptleri (`poc/`)

Scriptleri proje kökünden, bu sırayla çalıştırın:

| Sıra | Komut | Ne yapar? |
|---|---|---|
| 1 | `python poc/open_product.py` | Elle seçilmiş 5 ürün sayfasını `poc/output/` klasörüne indirir |
| 2 | `python poc/crawl_category.py` | "Kadın Mont" kategorisinden ürün linklerini toplar ve 15 yeni ürün indirir |
| 3 | `python poc/parse_product.py` | İndirilen sayfaları ayrıştırır ve `poc/output/products.json` dosyasına yazar |
| 4 | `python poc/embed_test.py` | Ürünleri `bge-m3` ile vektöre çevirir, 12 test sorgusunu çalıştırıp başarıyı raporlar |

İlk çalıştırmada `bge-m3` modeli (~2.3 GB) indirilir.

## Veri ve etik

- **Veri repoda yok.** İndirilen sayfalar ve yorumlar yeniden yayınlanmaz, `.gitignore` ile hariç tutulur. Veriyi görmek isteyen scriptleri kendi bilgisayarında çalıştırmalıdır.
- **robots.txt kurallarına uyulur.** Her adres indirilmeden önce [Protego](https://github.com/scrapy/protego) ile kontrol edilir. Arama sonuçları ve yorum sayfaları gibi yasaklı yollara gidilmez. Yorumlar yalnızca ürün sayfasında zaten yer alan yapılandırılmış veriden okunur.
- **Siteye yük bindirilmez.** İstekler arasında 4-8 saniye beklenir. Bir sayfa daha önce indirildiyse tekrar istenmez. Engel ya da captcha belirtisi görülürse script durur, engeli aşma girişiminde bulunulmaz.
- **Kişisel veri saklanmaz.** Yorum yazanların adları kaydedilmez (KVKK).
