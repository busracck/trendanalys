"""Arama servisi: cümleyi alır, filtreleri uygular, vektör + kelime aramasını birleştirir."""

from functools import lru_cache

from sqlalchemy import func, or_, select

from app.models import Product
from app.services.embedder import encode_query
from app.services.query_parser import parse_query
from app.services.weather import describe_weather, get_weather

# Her iki aramadan kaç aday alınacağı
CANDIDATE_LIMIT = 50

# RRF sabiti: büyük değer sıralamalar arasındaki farkı yumuşatır (literatürde 60 kullanılır)
RRF_K = 60

# Satıcılar aynı rengi farklı adlandırıyor; birbirine yakın olanlar aynı ailede
COLOR_FAMILIES = {
    "yeşil": ["yeşil", "haki"],
    "beyaz": ["beyaz", "ekru", "krem"],
    "gri": ["gri", "antrasit"],
    "kahverengi": ["kahverengi", "vizon", "bej"],
    "mavi": ["mavi", "lacivert"],
    "kırmızı": ["kırmızı", "bordo"],
}


@lru_cache(maxsize=256)
def _cached_vector(text):
    """Aynı cümle tekrar aranırsa model yeniden çalışmasın."""
    return encode_query(text)


def build_filters(parsed):
    """parse_query çıktısını SQL koşullarına çevirir."""
    conditions = []

    if parsed["min_price"] is not None:
        conditions.append(Product.price >= parsed["min_price"])
    if parsed["max_price"] is not None:
        conditions.append(Product.price <= parsed["max_price"])
    if parsed["color"]:
        # Renk verisi güvenilmez: "Yeşil Mont" adlı ürünün color sütunu "haki" olabiliyor,
        # 117 üründe hiç yok. Bu yüzden renk ailesi VEYA ürün adı üzerinden eşleştiriyoruz.
        family = COLOR_FAMILIES.get(parsed["color"], [parsed["color"]])
        conditions.append(
            or_(Product.color.in_(family), Product.name.ilike(f"%{parsed['color']}%"))
        )
    if parsed["category"]:
        # "mont" -> hem kadin-mont hem erkek-mont
        conditions.append(Product.category.like(f"%{parsed['category']}%"))
    if parsed["gender"]:
        # unisex ürünler her cinsiyete uyar
        conditions.append(Product.gender.in_([parsed["gender"], "unisex"]))

    return conditions


def vector_candidates(session, vector, conditions, limit=CANDIDATE_LIMIT):
    """Anlamca en yakın ürünler (pgvector <=>)."""
    distance = Product.embedding.cosine_distance(vector)
    stmt = select(Product.id, distance).where(*conditions).order_by(distance).limit(limit)
    return [row[0] for row in session.execute(stmt)]


def keyword_candidates(session, text, conditions, limit=CANDIDATE_LIMIT):
    """Kelime araması (PostgreSQL full-text, turkish)."""
    tsquery = func.plainto_tsquery("turkish", text)
    rank = func.ts_rank(Product.tsv, tsquery)
    stmt = (
        select(Product.id, rank)
        .where(Product.tsv.op("@@")(tsquery), *conditions)
        .order_by(rank.desc())
        .limit(limit)
    )
    return [row[0] for row in session.execute(stmt)]


def reciprocal_rank_fusion(rankings, k=RRF_K):
    """Birden çok sıralamayı birleştirir: her liste için puan 1/(k + sıra).

    Skorlar değil sıralar toplandığı için iki aramanın ölçeklerinin farklı olması sorun olmaz.
    """
    scores = {}
    for ranking in rankings:
        for position, product_id in enumerate(ranking, start=1):
            scores[product_id] = scores.get(product_id, 0) + 1 / (k + position)
    return sorted(scores, key=scores.get, reverse=True)


def explain(product, parsed, weather_text):
    """Ürün kartında gösterilecek "neden önerildi" satırı."""
    reasons = []
    if parsed["category"]:
        reasons.append(f"kategori: {product.category}")
    if parsed["color"] and product.color:
        reasons.append(f"renk: {product.color}")
    if parsed["max_price"]:
        reasons.append(f"{parsed['max_price']} TL altı")
    if weather_text:
        reasons.append(weather_text)
    return " · ".join(reasons)


def search(session, query, limit=10, city=None, max_price=None):
    """Cümleyle arama yapar ve ürünleri döndürür."""
    parsed = parse_query(query)
    if city:
        parsed["city"] = city
    if max_price:
        parsed["max_price"] = max_price

    weather = get_weather(parsed["city"])
    weather_text = describe_weather(weather)

    # Hava durumu ifadesi arama metnine ekleniyor: "serin hava, katmanlı giyim"
    search_text = f"{parsed['text']}, {weather_text}" if weather_text else parsed["text"]
    vector = _cached_vector(search_text)

    conditions = build_filters(parsed)
    ids = reciprocal_rank_fusion(
        [
            vector_candidates(session, vector, conditions),
            keyword_candidates(session, parsed["text"], conditions),
        ]
    )

    # Filtreler hiç sonuç bırakmadıysa fiyat dışındakileri gevşet
    if not ids and conditions:
        price_only = build_filters({**parsed, "color": None, "category": None, "gender": None})
        ids = reciprocal_rank_fusion(
            [
                vector_candidates(session, vector, price_only),
                keyword_candidates(session, parsed["text"], price_only),
            ]
        )

    ids = ids[:limit]
    if not ids:
        return {"parsed": parsed, "weather": weather, "weather_text": weather_text, "results": []}

    products = session.scalars(select(Product).where(Product.id.in_(ids))).all()
    by_id = {product.id: product for product in products}
    ordered = [by_id[product_id] for product_id in ids if product_id in by_id]

    return {
        "parsed": parsed,
        "weather": weather,
        "weather_text": weather_text,
        "results": [
            {
                "trendyol_id": product.trendyol_id,
                "name": product.name,
                "brand": product.brand,
                "price": float(product.price) if product.price is not None else None,
                "currency": product.currency,
                "color": product.color,
                "category": product.category,
                "rating": float(product.rating) if product.rating is not None else None,
                "image_url": product.image_url,
                "url": product.url,
                "why": explain(product, parsed, weather_text),
            }
            for product in ordered
        ],
    }
