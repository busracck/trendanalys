"""Arama kalitesini ölçer: eval/queries.yaml içindeki sorguları veritabanında çalıştırır.

Kullanım:
    python -m eval.run_eval
"""

from pathlib import Path

import yaml
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Product
from app.services.embedder import encode_query

QUERIES_FILE = Path(__file__).resolve().parent / "queries.yaml"
TOP_K = 3


def load_queries():
    return yaml.safe_load(QUERIES_FILE.read_text(encoding="utf-8"))


def search(session, query, limit=TOP_K):
    """Sorguya en yakın ürünleri döndürür. Hesabı PostgreSQL yapar (<=> operatörü)."""
    distance = Product.embedding.cosine_distance(encode_query(query))
    stmt = (
        select(Product.trendyol_id, Product.name, Product.category, distance)
        .order_by(distance)
        .limit(limit)
    )
    return session.execute(stmt).all()


def evaluate(item, rows):
    """Sonucu değerlendirir: (durum metni, 1. sıra doğru mu, ilk 3'te doğru mu)."""
    expected = set(item["expected"])
    found = [row[0] for row in rows]

    if not expected:
        return f"(ilgili ürün yok, en yakın mesafe: {rows[0][3]:.3f})", None, None
    if found[0] in expected:
        return "✅ 1. sıra doğru", True, True
    if expected & set(found):
        return "🟡 doğru ürün ilk 3'te", False, True
    return "❌ doğru ürün ilk 3'te yok", False, False


def main():
    items = load_queries()
    top1 = top3 = scored = 0

    with SessionLocal() as session:
        total = session.scalar(select(Product.id).limit(1))
        if total is None:
            print("Veritabanında ürün yok.")
            return

        for item in items:
            rows = search(session, item["query"])
            status, is_top1, is_top3 = evaluate(item, rows)

            print(f"\nSorgu: {item['query']}  {status}")
            for rank, (trendyol_id, name, category, distance) in enumerate(rows, start=1):
                mark = "✓" if trendyol_id in item["expected"] else " "
                print(f"  {mark} {rank}. ({distance:.3f}) [{category}] {name[:65]}")

            if is_top1 is not None:
                scored += 1
                top1 += int(is_top1)
                top3 += int(is_top3)

    print(f"\n1. sırada doğru: {top1}/{scored} | ilk 3'te doğru: {top3}/{scored}")


if __name__ == "__main__":
    main()
