"""Arama süresini ölçer ve hangi adımın ne kadar sürdüğünü gösterir.

    python -m eval.benchmark            # 3 tur, eval/queries.yaml sorgularıyla
    python -m eval.benchmark --tur 10   # daha çok tekrar

Ölçüm ısınma turundan sonra yapılır: model yüklenmesi ve hava durumu isteği
ilk çağrıda gerçekleşir, sonraki aramalarda önbellekten gelir.
"""

import argparse
import statistics
import time

from app.db import SessionLocal
from app.services.embedder import encode_query
from app.services.query_parser import parse_query
from app.services.search import build_filters, search, vector_candidates
from eval.run_eval import load_queries


def percentile(values, ratio):
    ordered = sorted(values)
    index = min(int(len(ordered) * ratio), len(ordered) - 1)
    return ordered[index]


def timed(function):
    started = time.perf_counter()
    result = function()
    return result, (time.perf_counter() - started) * 1000


def main():
    parser = argparse.ArgumentParser(description="Arama süresini ölçer.")
    parser.add_argument("--tur", type=int, default=3, help="Her sorgu kaç kez çalıştırılsın")
    args = parser.parse_args()

    queries = [item["query"] for item in load_queries()]
    steps = {"ayrıştırma": [], "embedding": [], "SQL": [], "toplam": []}

    with SessionLocal() as session:
        # Isınma: model yüklenir, hava durumu önbelleğe girer
        search(session, queries[0], limit=10)

        for _ in range(args.tur):
            for query in queries:
                _, total = timed(lambda: search(session, query, limit=10))
                steps["toplam"].append(total)

                # Aynı işi adım adım ölçüyoruz
                parsed, parse_ms = timed(lambda: parse_query(query))
                vector, embed_ms = timed(lambda: encode_query(parsed["text"]))
                conditions = build_filters(parsed)
                _, sql_ms = timed(lambda: vector_candidates(session, vector, conditions))

                steps["ayrıştırma"].append(parse_ms)
                steps["embedding"].append(embed_ms)
                steps["SQL"].append(sql_ms)

    count = len(steps["toplam"])
    print(f"\n{len(queries)} sorgu x {args.tur} tur = {count} arama\n")
    print(f"{'adım':14} {'ortanca':>10} {'p95':>10}")
    print("-" * 36)
    for name, values in steps.items():
        print(f"{name:14} {statistics.median(values):>9.1f}ms {percentile(values, 0.95):>9.1f}ms")


if __name__ == "__main__":
    main()
