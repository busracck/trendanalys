"""Vektörü olmayan ürünlerin search_text ve embedding alanlarını doldurur.

Kullanım:
    python -m nlp.build_embeddings              # vektörü eksik bütün ürünler
    python -m nlp.build_embeddings --limit 20   # ilk 20 ürün (deneme)
"""

import argparse
import time
from datetime import datetime, timezone

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Product
from app.services.embedder import encode_passages
from nlp.text_builder import build_product_text

# Kaç üründe bir veritabanına yazılacağı (encode kendi içinde 8'erli batch kullanıyor)
CHUNK_SIZE = 64


def pending_products(session, limit=None):
    stmt = select(Product).where(Product.embedded_at.is_(None)).order_by(Product.id)
    if limit:
        stmt = stmt.limit(limit)
    return session.scalars(stmt).all()


def embed_chunk(chunk):
    texts = [build_product_text(product) for product in chunk]
    vectors = encode_passages(texts, show_progress_bar=False)
    now = datetime.now(timezone.utc)

    for product, text, vector in zip(chunk, texts, vectors):
        product.search_text = text
        product.embedding = vector
        product.embedded_at = now


def main():
    parser = argparse.ArgumentParser(description="Ürün vektörlerini hesaplar.")
    parser.add_argument("--limit", type=int, help="En fazla kaç ürün işlensin")
    args = parser.parse_args()

    started = time.perf_counter()

    with SessionLocal() as session:
        products = pending_products(session, args.limit)
        if not products:
            print("Vektörü eksik ürün yok.")
            return

        print(f"{len(products)} ürünün vektörü hesaplanacak.")
        for start in range(0, len(products), CHUNK_SIZE):
            chunk = products[start : start + CHUNK_SIZE]
            embed_chunk(chunk)
            # Dilim bitince kaydet: yarıda kesilirse buraya kadarki iş durur
            session.commit()
            print(f"  {start + len(chunk)}/{len(products)} tamamlandı")

    seconds = time.perf_counter() - started
    print(f"\n{len(products)} ürün {seconds:.1f} sn sürdü ({seconds / len(products):.2f} sn/ürün).")


if __name__ == "__main__":
    main()
