"""Kategorileri gezip ürünleri veritabanına yazan CLI.

Kullanım:
    python -m scraper.run_scraper                        # bütün kategoriler
    python -m scraper.run_scraper --category kadin-mont  # tek kategori
    python -m scraper.run_scraper --limit 20             # kategori başına 20 ürün
"""

import argparse
from datetime import date, datetime, timezone
from pathlib import Path

import yaml
from selenium.common.exceptions import WebDriverException
from sqlalchemy import select
from urllib3.exceptions import HTTPError as Urllib3HTTPError

from app.db import SessionLocal
from app.models import Product, ReviewSnippet
from scraper.category_crawler import collect_category_links
from scraper.cleaner import clean_text, content_hash, normalize_color, normalize_gender
from scraper.driver import create_driver, restart_driver
from scraper.product_parser import get_product_html, parse_product_html

CATEGORIES_FILE = Path(__file__).resolve().parent.parent / "data" / "categories.yaml"

# Bir kategoride üst üste bu kadar hata olursa kategoriyi bırak
MAX_CONSECUTIVE_ERRORS = 3

# Bu kadar üründen sonra tarayıcı yenilenir (uzun oturumlarda Chrome takılıyor)
RESTART_EVERY = 50

# Tarayıcı takılınca sayfa kaç kez denenir
FETCH_TRIES = 2

# Tarayıcının takılması hem Selenium'dan hem urllib3'ten gelebiliyor
BROWSER_ERRORS = (WebDriverException, Urllib3HTTPError)


def load_categories():
    # safe_load: dosyadaki metni sadece veri olarak okur, kod çalıştırmaz
    return yaml.safe_load(CATEGORIES_FILE.read_text(encoding="utf-8"))


def clean_product(data):
    for field in ("name", "brand"):
        data[field] = clean_text(data.get(field)) or None

    # Renk ve cinsiyet filtrede kullanılacak: tek biçime indiriliyor
    data["color"] = normalize_color(data.get("color"))
    data["gender"] = normalize_gender(data.get("gender"))

    data["attributes"] = {
        key: clean_text(value) for key, value in (data.get("attributes") or {}).items()
    }

    reviews = []
    for review in data.get("reviews") or []:
        text = clean_text(review.get("text"))
        if text:
            reviews.append({**review, "text": text})
    data["reviews"] = reviews

    return data


def build_reviews(data):
    return [
        ReviewSnippet(
            text=review["text"],
            rating=review.get("rating"),
            published_at=date.fromisoformat(review["date"]) if review.get("date") else None,
        )
        for review in data["reviews"]
    ]


def fill_product(product, data, url, new_hash, category_name):
    category_path = data.get("category_path") or []

    product.url = url
    product.name = data["name"]
    product.brand = data["brand"]
    # Trendyol kategori yolunun sonuna bazen markayı ekliyor ("Defacto Kadın Mont").
    # Filtrede kullanacağımız için categories.yaml'daki kendi adımızı yazıyoruz.
    product.category = category_name
    product.category_path = category_path
    product.price = data["price"]
    product.currency = data["currency"]
    product.color = data["color"]
    product.gender = data["gender"]
    product.rating = data["rating"]
    product.rating_count = data["rating_count"]
    product.review_count = data["review_count"]
    product.attributes = data["attributes"]
    product.image_url = data["image_url"]
    product.content_hash = new_hash
    product.scraped_at = datetime.now(timezone.utc)
    product.reviews = build_reviews(data)

    # İçerik değişti: eski vektör artık bu metni temsil etmiyor (Aşama 4 yeniden hesaplar)
    product.search_text = None
    product.embedding = None
    product.embedded_at = None


def upsert_product(session, data, url, category_name):
    # Kategori adı da imzaya girsin ki kategori değişince ürün güncellensin
    new_hash = content_hash({**data, "_category": category_name})
    existing = session.scalar(
        select(Product).where(Product.trendyol_id == data["trendyol_id"])
    )

    if existing is None:
        product = Product(trendyol_id=data["trendyol_id"])
        fill_product(product, data, url, new_hash, category_name)
        session.add(product)
        return "new"

    if existing.content_hash == new_hash:
        return "unchanged"

    fill_product(existing, data, url, new_hash, category_name)
    return "updated"


def fetch_product_html(driver, link):
    """Sayfayı indirir. Tarayıcı takılırsa yeniden başlatıp bir kez daha dener.

    (html, driver) döndürür; html None ise sayfa alınamadı.
    """
    for attempt in range(1, FETCH_TRIES + 1):
        try:
            return get_product_html(driver, link), driver
        except BROWSER_ERRORS as error:
            print(f"    tarayıcı hatası ({attempt}/{FETCH_TRIES}): {type(error).__name__}")
            driver = restart_driver(driver)

    return None, driver


def scrape_category(driver, session, category, limit=None):
    target = limit or category["target"]
    print(f"\n=== {category['name']} (hedef: {target}) ===")

    try:
        links = collect_category_links(driver, category["url"], target)
    except BROWSER_ERRORS as error:
        print(f"Kategori sayfası alınamadı ({type(error).__name__}), atlanıyor.")
        return {"new": 0, "updated": 0, "unchanged": 0, "hata": 1}, restart_driver(driver)

    print(f"{len(links)} ürün linki toplandı.")

    counts = {"new": 0, "updated": 0, "unchanged": 0, "hata": 0}
    consecutive_errors = 0

    for i, link in enumerate(links, start=1):
        # Chrome uzun oturumlarda takılıyor: belirli aralıklarla baştan açıyoruz
        if i > 1 and i % RESTART_EVERY == 1:
            driver = restart_driver(driver)

        html, driver = fetch_product_html(driver, link)
        if html is None:
            counts["hata"] += 1
            consecutive_errors += 1
            print(f"  {i}/{len(links)} sayfa alınamadı: {link}")
            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                print("Üst üste hata, bu kategori bırakılıyor.")
                break
            continue

        data = parse_product_html(html)
        if data is None or not data.get("trendyol_id"):
            counts["hata"] += 1
            consecutive_errors += 1
            print(f"  {i}/{len(links)} ayrıştırılamadı: {link}")
            continue

        result = upsert_product(session, clean_product(data), link, category["name"])
        # Her üründen sonra kaydet: uzun tarama yarıda kalsa bile ilerleme durur
        session.commit()
        counts[result] += 1
        consecutive_errors = 0
        print(f"  {i}/{len(links)} {result}: {data['name'][:60]}")

    return counts, driver


def main():
    parser = argparse.ArgumentParser(description="Trendyol ürünlerini veritabanına aktarır.")
    parser.add_argument("--category", help="Sadece bu kategori (categories.yaml içindeki name)")
    parser.add_argument("--limit", type=int, help="Kategori başına ürün sayısı (hedefi ezer)")
    args = parser.parse_args()

    categories = load_categories()
    if args.category:
        categories = [c for c in categories if c["name"] == args.category]
        if not categories:
            available = ", ".join(c["name"] for c in load_categories())
            print(f"Kategori bulunamadı: {args.category}")
            print(f"Mevcut kategoriler: {available}")
            return

    totals = {"new": 0, "updated": 0, "unchanged": 0, "hata": 0}
    driver = create_driver()
    try:
        with SessionLocal() as session:
            for category in categories:
                counts, driver = scrape_category(driver, session, category, args.limit)
                for key, value in counts.items():
                    totals[key] += value
    finally:
        driver.quit()

    print(
        f"\nToplam: {totals['new']} yeni, {totals['updated']} güncellendi, "
        f"{totals['unchanged']} değişmedi, {totals['hata']} hata."
    )


if __name__ == "__main__":
    main()
