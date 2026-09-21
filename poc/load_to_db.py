import json
from datetime import date, datetime, timezone
from pathlib import Path

from sentence_transformers import SentenceTransformer
from sqlalchemy import delete, select

from app.db import SessionLocal
from app.models import Product, ReviewSnippet



PRODUCTS_FILE = Path(__file__).parent / "output" / "products.json"


NOISE_ATTRIBUTES = {
    "Menşei",
    "Yıkama Talimatı",
    "Kutu Durumu",
    "Ürün Güvenliği Bilgisi",
    "Sürdürülebilirlik Detayı",
    "Persona",
    "Paket İçeriği",
    "Materyal Bileşeni",
}


def build_product_text(product):
    # e.g. "Ürün adı. Kategori: Kadın > Kadın Giyim. Kumaş Tipi: Dokuma; ... Yorumlar: ..."
    parts = [product["name"]]
    if product["category_path"]:
        parts.append("Kategori: " + " > ".join(product["category_path"]))

    attributes = [
        f"{k}: {v}" for k, v in product["attributes"].items() if k not in NOISE_ATTRIBUTES
    ]
    if attributes:
        parts.append("; ".join(attributes))

    if product["reviews"]:
        parts.append("Yorumlar: " + " ".join(r["text"] for r in product["reviews"]))

    return ". ".join(parts)



def main():
    products = json.loads(PRODUCTS_FILE.read_text(encoding="utf-8"))
    texts = [build_product_text(p) for p in products]

    print(f"{len(products)} ürün okundu.")
    print(f"İlk ürün: {products[0]['name']}")
    print(f"Metnin başı: {texts[0][:200]}")

    model = SentenceTransformer("BAAI/bge-m3")
    embeddings = model.encode(texts, normalize_embeddings=True)

    with SessionLocal() as session:
        session.execute(delete(ReviewSnippet))
        session.execute(delete(Product))
        for product, text, embedding in zip(products, texts, embeddings):
            category_path = product["category_path"]
            p = Product(
                trendyol_id=product["trendyol_id"],
                name=product["name"],
                brand=product["brand"],
                category=category_path[-1] if category_path else None,
                category_path=category_path,
                price=product["price"],
                currency=product["currency"],
                color=product["color"],
                gender=product["gender"],
                rating=product["rating"],
                rating_count=product["rating_count"],
                review_count=product["review_count"],
                attributes=product["attributes"],
                image_url=product["image_url"],
                search_text=text,
                embedding=embedding,
                embedded_at=datetime.now(timezone.utc),
                reviews=[
                    ReviewSnippet(
                        text=r["text"],
                        rating=r["rating"],
                        published_at=date.fromisoformat(r["date"]) if r.get("date") else None,
                    )
                    for r in product["reviews"]
                ],
            )
            session.add(p)

        session.commit()

    review_count = sum(len(p["reviews"]) for p in products)
    print(f"{len(products)} ürün ve {review_count} yorum veritabanına yazıldı.")

    query="yeşil renkli mont"
    query_vector = model.encode(query, normalize_embeddings=True)
    distance = Product.embedding.cosine_distance(query_vector)
    stmt = select(Product.trendyol_id, Product.name, distance).order_by(distance).limit(3)
    with SessionLocal() as session:
        rows = session.execute(stmt).all()

        print(f"\nSorgu: {query}")
        for trendyol_id, name, mesafe in rows:
            print(f"  ({mesafe:.3f}) [{trendyol_id}] {name}")

if __name__ == "__main__":
    main()

