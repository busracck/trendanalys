"""Test sorgularını elle etiketlemek için yardımcı.

    python -m eval.label                   # queries.yaml'daki sorguları sırayla gözden geçir
    python -m eval.label --atla 5          # ilk 5 sorguyu atla (kaldığın yerden devam)
    python -m eval.label --yeni "cümle"    # yeni sorgu ekle ve etiketle
    python -m eval.label --sadece-yeni     # sadece etiketi boş olan sorgulara sor

Her sorgu için üç modun (kelime, vektör, hibrit) getirdiği adaylar birleştirilip
gösterilir. 1097 ürünün hepsine bakmak yerine bu havuza bakmak yeterlidir:
doğru cevapların büyük kısmı en az bir modun ilk sıralarında çıkar.
"""

import argparse
from pathlib import Path

import yaml
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Product
from app.services.query_parser import parse_query
from app.services.search import build_filters
from eval.run_eval import MODES, QUERIES_FILE, load_queries, run_mode

POOL_PER_MODE = 8

HEADER = """# Arama kalitesini ölçen test sorguları.
# expected: doğru kabul edilen trendyol_id listesi.
#
# Etiketler `python -m eval.label` ile, üç modun adayları havuzlanarak seçildi.
"""


def build_pool(session, query):
    """Üç modun ilk sonuçlarını birleştirip tekrarsız aday listesi döndürür."""
    parsed = parse_query(query)
    conditions = build_filters(parsed)

    pool = []
    for mode in MODES:
        for product_id in run_mode(session, mode, parsed, conditions)[:POOL_PER_MODE]:
            if product_id not in pool:
                pool.append(product_id)

    rows = session.execute(
        select(
            Product.id,
            Product.trendyol_id,
            Product.name,
            Product.category,
            Product.price,
            Product.color,
        ).where(Product.id.in_(pool))
    ).all()
    by_id = {row[0]: row[1:] for row in rows}
    return parsed, [by_id[product_id] for product_id in pool if product_id in by_id]


def ask(query, candidates, current):
    """Adayları gösterir, kullanıcının seçtiği numaraları trendyol_id'ye çevirir."""
    print(f"\n{'=' * 70}\nSORGU: {query}")
    for index, (trendyol_id, name, category, price, color) in enumerate(candidates, start=1):
        mark = "*" if trendyol_id in current else " "
        # Renk adı üründe yazmayabiliyor ("Ltb ... Yeşil Mont" -> color: haki),
        # bu yüzden sütunu ayrıca gösteriyoruz
        print(f" {mark}{index:3}. [{category:18}] {color or '-':12} {price:>8} TL  {name[:52]}")

    print("\n  Doğru olanların numaraları (örn: 1 3 4)")
    print("  Enter = mevcut etiketi koru · '-' = hiçbiri · 'q' = çık ve kaydet")
    answer = input("  > ").strip()

    if answer.lower() == "q":
        return None
    if answer == "":
        return current
    if answer == "-":
        return []

    chosen = []
    for part in answer.split():
        if part.isdigit() and 1 <= int(part) <= len(candidates):
            chosen.append(candidates[int(part) - 1][0])
        else:
            print(f"  '{part}' atlandı (geçersiz numara)")
    return chosen


def save(items):
    body = yaml.safe_dump(items, allow_unicode=True, sort_keys=False, default_flow_style=False)
    QUERIES_FILE.write_text(HEADER + "\n" + body, encoding="utf-8")
    print(f"\n{len(items)} sorgu kaydedildi: {QUERIES_FILE}")


def main():
    parser = argparse.ArgumentParser(description="Test sorgularını etiketler.")
    parser.add_argument("--yeni", help="Yeni sorgu ekle")
    parser.add_argument("--sadece-yeni", action="store_true", help="Sadece etiketi boş olanları sor")
    parser.add_argument("--atla", type=int, default=0, help="İlk N sorguyu atla")
    args = parser.parse_args()

    items = load_queries()
    if args.yeni:
        items.append({"query": args.yeni, "expected": []})

    with SessionLocal() as session:
        for number, item in enumerate(items, start=1):
            if number <= args.atla:
                continue
            if args.sadece_yeni and item["expected"]:
                continue

            print(f"\n[{number}/{len(items)}]", end="")

            parsed, candidates = build_pool(session, item["query"])
            if not candidates:
                print(f"\nSORGU: {item['query']}\n  Aday bulunamadı (katalogda karşılığı yok).")
                item["expected"] = []
                continue

            print(f"\n  ayrıştırma: {parsed['city']=} {parsed['max_price']=} "
                  f"{parsed['color']=} {parsed['category']=}")
            chosen = ask(item["query"], candidates, item["expected"])
            if chosen is None:
                break
            item["expected"] = chosen

    save(items)


if __name__ == "__main__":
    main()
