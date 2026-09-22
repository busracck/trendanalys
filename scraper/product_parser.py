import re
from pathlib import Path
import json

from bs4 import BeautifulSoup

from scraper.driver import fetch_page

RAW_HTML_DIR = Path(__file__).resolve().parent.parent / "data" / "raw_html"
PD_STATE_MARKER = 'window["__envoy__SHARED_PROPS"]='


def extract_ld_json(soup):
    blocks = []
    for tag in soup.find_all("script", {"type": "application/ld+json"}):
        if not tag.string:
            continue
        try:
            blocks.append(json.loads(tag.string))
        except json.JSONDecodeError as e:
            print(f"Skipping invalid ld+json block: {e}")
    return blocks


def find_block_by_type(blocks, block_types):
    for block in blocks:
        if block.get("@type") in block_types:
            return block
    return None


def parse_attributes(product_block):
    attributes = {}
    for prop in product_block.get("additionalProperty", []):
        name = prop.get("name")
        value = prop.get("unitText") or prop.get("value")
        if name and value:
            attributes[name] = value
    return attributes


def parse_category_path(webpage_block):
    if webpage_block is None:
        return []
    items = webpage_block.get("breadcrumb", {}).get("itemListElement", [])
    names = []
    for item in items:
        inner = item.get("item")
        name = inner.get("name") if isinstance(inner, dict) else item.get("name")
        if name:
            names.append(name)
    return names[1:-1]


def parse_product_html(html):
    soup = BeautifulSoup(html, "html.parser")
    blocks = extract_ld_json(soup)

    product = find_block_by_type(blocks, ["Product", "ProductGroup"])
    if product is None:
        return parse_pd_html(html)

    webpage = find_block_by_type(blocks, ["WebPage"])

    offers = product.get("offers", {})
    price = offers.get("price")
    images = product.get("image", {}).get("contentUrl", [])
    if isinstance(images, str):
        images = [images]

    ratings= product.get("aggregateRating", {})

    return {
        "trendyol_id": product.get("sku"),
        "name": product.get("name"),
        "brand": product.get("brand", {}).get("name"),
        "price": float(price) if price else None,
        "currency": offers.get("priceCurrency"),
        "color": product.get("color"),
        "gender": product.get("audience", {}).get("suggestedGender"),
        "image_url": images[0] if images else None,
        "category_path": parse_category_path(webpage),
        "attributes": parse_attributes(product),
        "rating": ratings.get("ratingValue"),
        "rating_count": ratings.get("ratingCount"),
        "review_count": ratings.get("reviewCount"),
        "reviews": parse_reviews(product)

    }


def parse_reviews(product_block):
    reviews = []
    for review in product_block.get("review", []):
        text = review.get("reviewBody")
        
        # Eğer yorum metni boşsa (None veya boş string) bu yorumu atla
        if not text:
            continue
            
        reviews.append({
            "text": text,
            "rating": review.get("reviewRating", {}).get("ratingValue"),
            "date": review.get("datePublished")
            # "author" KVKK gereği kasıtlı olarak alınmamıştır.
        })
    return reviews


def extract_product_id(url):
    match = re.search(r"-p-(\d+)", url)
    return match.group(1) if match else None


def get_product_html(driver, url):
    product_id = extract_product_id(url)
    if product_id is None:
        return None

    path = RAW_HTML_DIR / f"{product_id}.html"
    if path.exists():
        return path.read_text(encoding="utf-8")

    html = fetch_page(driver, url)
    if html is None:
        return None

    RAW_HTML_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return html


def extract_embedded_state(html):
    """/pd/ şablonunda sayfaya gömülü JSON'u çıkarır."""
    start = html.find(PD_STATE_MARKER)
    if start == -1:
        return None

    start += len(PD_STATE_MARKER)
    end = html.find("</script>", start)
    if end == -1:
        return None

    try:
        return json.loads(html[start:end].strip().rstrip(";"))
    except json.JSONDecodeError:
        return None


def parse_pd_html(html):
    state = extract_embedded_state(html)
    if state is None:
        return None

    product = state.get("product") or {}
    price_info = (
        product.get("merchantListing", {})
        .get("winnerVariant", {})
        .get("price", {})
    )

    rating_score = product.get("ratingScore", {})
    images = product.get("images") or []

    hierarchy = product.get("category", {}).get("hierarchy", "")

    return {
        "trendyol_id": str(product.get("id")),
        "name": product.get("name"),
        "brand": product.get("brand", {}).get("name"),
        "price": price_info.get("discountedPrice", {}).get("value"),
        "currency": price_info.get("currency"),
        "color": None,
                "gender": product.get("gender", {}).get("name"),
        "image_url": images[0] if images else None,
        "category_path": hierarchy.split("/") if hierarchy else [],
        "attributes": {
            a["key"]["name"]: a["value"]["name"] for a in product.get("attributes", [])
        },
        "rating": rating_score.get("averageRating"),
        "rating_count": rating_score.get("totalCount"),
        "review_count": rating_score.get("commentCount"),
        "reviews": [],

    }
