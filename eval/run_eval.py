"""Arama kalitesini ölçer ve üç modu karşılaştırır.

    python -m eval.run_eval              # özet tablo
    python -m eval.run_eval --detay      # her sorgunun sonuçlarını da yazar

Üç mod da aynı filtreleri kullanır; fark yalnızca ürünleri nasıl bulduklarıdır:
    kelime  : PostgreSQL full-text (Trendyol'un yaptığına en yakın)
    vektör  : pgvector <=> (yalnızca anlam)
    hibrit  : vektör (hava durumu eklenmiş) + kelime, RRF ile birleştirilmiş
"""

import argparse
from pathlib import Path

import yaml
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Product
from app.services.embedder import encode_query
from app.services.query_parser import parse_query
from app.services.search import (
    build_filters,
    keyword_candidates,
    reciprocal_rank_fusion,
    vector_candidates,
)
from app.services.weather import describe_weather, get_weather

QUERIES_FILE = Path(__file__).resolve().parent / "queries.yaml"
TOP_K = 5
MODES = ("kelime", "vektör", "hibrit", "hibrit-3x", "hibrit-10x")


def load_queries():
    return yaml.safe_load(QUERIES_FILE.read_text(encoding="utf-8"))


def run_mode(session, mode, parsed, conditions):
    """Bir modun bulduğu ürün id'lerini sırayla döndürür."""
    if mode == "kelime":
        return keyword_candidates(session, parsed["text"], conditions)

    if mode == "vektör":
        return vector_candidates(session, encode_query(parsed["text"]), conditions)

    # hibrit: hava durumu ifadesi arama metnine eklenir, iki liste RRF ile birleşir.
    # "-3x" / "-10x": vektör kolunun ağırlığı (deney).
    weights = {"hibrit": [1.0, 1.0], "hibrit-3x": [3.0, 1.0], "hibrit-10x": [10.0, 1.0]}[mode]

    weather_text = describe_weather(get_weather(parsed["city"]))
    text = f"{parsed['text']}, {weather_text}" if weather_text else parsed["text"]
    return reciprocal_rank_fusion(
        [
            vector_candidates(session, encode_query(text), conditions),
            keyword_candidates(session, parsed["text"], conditions),
        ],
        weights=weights,
    )


def score(found_ids, expected):
    """(1. sıra doğru mu, Precision@5, Recall@5, MRR) döndürür."""
    top = found_ids[:TOP_K]
    hits = [index for index, product_id in enumerate(top, start=1) if product_id in expected]

    top1 = bool(hits and hits[0] == 1)
    precision = len(hits) / TOP_K
    # Payda min(doğru sayısı, 5): 13 doğru cevabı olan bir sorguda ilk 5'te
    # 5 doğru bulmak %100 sayılmalı, %38 değil.
    recall = len(hits) / min(len(expected), TOP_K)
    mrr = 1 / hits[0] if hits else 0.0
    return top1, precision, recall, mrr


def main():
    parser = argparse.ArgumentParser(description="Arama kalitesini ölçer.")
    parser.add_argument("--detay", action="store_true", help="Her sorgunun sonuçlarını yaz")
    args = parser.parse_args()

    items = load_queries()
    totals = {mode: {"top1": 0, "precision": 0.0, "recall": 0.0, "mrr": 0.0} for mode in MODES}
    scored = 0

    with SessionLocal() as session:
        for item in items:
            expected = set(item["expected"])
            parsed = parse_query(item["query"])
            conditions = build_filters(parsed)

            if args.detay:
                print(f"\n--- {item['query']}")

            for mode in MODES:
                ids = run_mode(session, mode, parsed, conditions)
                # id -> trendyol_id çevirisi, karşılaştırma etiketlerle aynı dilde olsun
                rows = session.execute(
                    select(Product.id, Product.trendyol_id, Product.name).where(
                        Product.id.in_(ids[:TOP_K])
                    )
                ).all()
                by_id = {row[0]: (row[1], row[2]) for row in rows}
                found = [by_id[i][0] for i in ids[:TOP_K] if i in by_id]

                if args.detay:
                    print(f"  {mode}:")
                    for rank, product_id in enumerate(ids[:TOP_K], start=1):
                        if product_id not in by_id:
                            continue
                        trendyol_id, name = by_id[product_id]
                        mark = "✓" if trendyol_id in expected else " "
                        print(f"    {mark} {rank}. {name[:60]}")

                if not expected:
                    continue

                top1, precision, recall, mrr = score(found, expected)
                totals[mode]["top1"] += int(top1)
                totals[mode]["precision"] += precision
                totals[mode]["recall"] += recall
                totals[mode]["mrr"] += mrr

            if expected:
                scored += 1

    print(f"\n{scored} etiketli sorgu, ilk {TOP_K} sonuç\n")
    print(f"{'mod':10} {'1. sıra':>9} {'Precision@5':>13} {'Recall@5':>10} {'MRR':>8}")
    print("-" * 54)
    for mode in MODES:
        result = totals[mode]
        print(
            f"{mode:10} {result['top1'] / scored:>8.0%} "
            f"{result['precision'] / scored:>13.0%} "
            f"{result['recall'] / scored:>10.0%} {result['mrr'] / scored:>8.2f}"
        )


if __name__ == "__main__":
    main()
