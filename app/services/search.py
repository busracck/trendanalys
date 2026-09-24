"""Arama servisi: cümleyi alır, filtreleri uygular, vektör + kelime aramasını birleştirir."""

from functools import lru_cache

from sqlalchemy import func, or_, select

from app.models import Product
from app.services.embedder import encode_query
from app.services.query_parser import parse_query
from scraper.cleaner import turkish_lower
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


def to_or_query(text):
    """Kelimeleri VEYA ile bağlar.

    plainto_tsquery bütün kelimelerin aynı anda geçmesini ister; uzun cümlelerde
    bu hiç sonuç vermiyor ("spor salonuna giderken giyeceğim ayakkabı" -> 0 ürün).
    VEYA ile arayıp sıralamayı ts_rank'e bırakıyoruz: çok kelime eşleşen üste çıkar.
    """
    words = [word for word in text.split() if len(word) > 2]
    return " or ".join(words)


def keyword_candidates(session, text, conditions, limit=CANDIDATE_LIMIT):
    """Kelime araması (PostgreSQL full-text, turkish)."""
    or_query = to_or_query(text)
    if not or_query:
        return []

    tsquery = func.websearch_to_tsquery("turkish", or_query)
    rank = func.ts_rank(Product.tsv, tsquery)
    stmt = (
        select(Product.id, rank)
        .where(Product.tsv.op("@@")(tsquery), *conditions)
        .order_by(rank.desc())
        .limit(limit)
    )
    return [row[0] for row in session.execute(stmt)]


def reciprocal_rank_fusion(rankings, weights=None, k=RRF_K):
    """Birden çok sıralamayı birleştirir: her liste için puan agirlik / (k + sıra).

    Skorlar değil sıralar toplandığı için iki aramanın ölçeklerinin farklı olması sorun olmaz.
    `weights` verilmezse listeler eşit sayılır.
    """
    if weights is None:
        weights = [1.0] * len(rankings)

    scores = {}
    for ranking, weight in zip(rankings, weights):
        for position, product_id in enumerate(ranking, start=1):
            scores[product_id] = scores.get(product_id, 0) + weight / (k + position)
    return sorted(scores, key=scores.get, reverse=True)


# Eşleşme ararken atlanacak, ayırt edici olmayan kelimeler
STOP_WORDS = {
    "için", "bir", "bana", "kadar", "gibi", "olan", "daha", "çok", "arıyorum",
    "lazım", "istiyorum", "giyeceğim", "giyilecek", "alacağım", "şey",
}

# Türkçe ekler yüzünden tam eşleşme aramıyoruz: kelimenin ilk harfleri yeterli
STEM_LENGTH = 5
MAX_MATCHES = 3


def matching_terms(product, text):
    """Kullanıcının kelimelerinden ürün adında/özelliklerinde geçenleri bulur."""
    haystack = turkish_lower(
        " ".join([product.name or "", " ".join((product.attributes or {}).values())])
    )

    matches = []
    for word in turkish_lower(text).split():
        if len(word) < 4 or word in STOP_WORDS:
            continue
        if word[:STEM_LENGTH] in haystack and word not in matches:
            matches.append(word)

    return matches[:MAX_MATCHES]


def explain(product, parsed, weather_text):
    """Ürün kartındaki "neden önerildi" satırı. Her ürün için ayrı hesaplanır."""
    reasons = []

    matches = matching_terms(product, parsed["text"])
    if matches:
        reasons.append(", ".join(matches))
    else:
        # Ortak kelime yok ama vektör yakın buldu: anlamsal aramanın işi tam olarak bu
        reasons.append("kelime eşleşmesi yok, anlamca yakın")

    if parsed["max_price"] and product.price is not None:
        reasons.append(f"{int(product.price)} TL")
    if parsed["color"] and product.color:
        reasons.append(product.color)
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

    # Katalogda hiç olmayan bir tür istendiyse alakasız ürün göstermek yerine dürüst cevap
    if parsed["unavailable"]:
        return {
            "parsed": parsed,
            "weather": None,
            "weather_text": "",
            "message": f"Katalogda {parsed['unavailable']} yok. Bu arama 1097 giyim ve ayakkabı ürünü üzerinde çalışıyor.",
            "results": [],
        }

    weather = get_weather(parsed["city"])
    weather_text = describe_weather(weather)

    # Hava durumu ifadesi arama metnine ekleniyor: "serin hava, katmanlı giyim"
    search_text = f"{parsed['text']}, {weather_text}" if weather_text else parsed["text"]
    vector = _cached_vector(search_text)

    conditions = build_filters(parsed)
    # Yalnızca vektör: eval/run_eval ölçümünde kelime kolunu eklemek sonucu bozuyordu
    # (vektör P@5 %74, hibrit %70; ağırlık artırmak bile fark kapatmadı, 23 Eylül 2026).
    ids = vector_candidates(session, vector, conditions)

    # Filtreler hiç sonuç bırakmadıysa fiyat dışındakileri gevşet
    if not ids and conditions:
        price_only = build_filters({**parsed, "color": None, "category": None, "gender": None})
        ids = vector_candidates(session, vector, price_only)

    ids = ids[:limit]
    if not ids:
        return {
            "parsed": parsed,
            "weather": weather,
            "weather_text": weather_text,
            "message": "Bu cümleye uyan ürün bulunamadı.",
            "results": [],
        }

    products = session.scalars(select(Product).where(Product.id.in_(ids))).all()
    by_id = {product.id: product for product in products}
    ordered = [by_id[product_id] for product_id in ids if product_id in by_id]

    return {
        "parsed": parsed,
        "weather": weather,
        "weather_text": weather_text,
        "message": "",
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
