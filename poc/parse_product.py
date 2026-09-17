import json
from pathlib import Path

from bs4 import BeautifulSoup

OUTPUT_DIR = Path(__file__).parent / "output"


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
        return None
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


if __name__ == "__main__":
    products = []

    for path in sorted(OUTPUT_DIR.glob("*.html")):
        html = path.read_text(encoding="utf-8")
        product = parse_product_html(html)
        if product is None:
            print(f"{path.name}: no Product/ProductGroup ld+json block found.")
            continue

        products.append(product)

        print(
            f"{product['trendyol_id']:<10} | {product['name'][:40]:<40} | "
            f"{product['price']} TL | {len(product['attributes'])} özellik"
            f" | Puan: {product['rating']} ({product['review_count']} Yorum)"
        )


    output_file = OUTPUT_DIR / "products.json"
    

    json_data = json.dumps(products, ensure_ascii=False, indent=2)
    output_file.write_text(json_data, encoding="utf-8")
    
    print(f"\nİşlem tamamlandı! Toplam {len(products)} ürün '{output_file.name}' dosyasına kaydedildi.")


