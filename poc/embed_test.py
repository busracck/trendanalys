import json
from pathlib import Path

from sentence_transformers import SentenceTransformer

MODEL_NAME = "BAAI/bge-m3"
QUERY_PREFIX = ""
PASSAGE_PREFIX = ""

PRODUCTS_FILE = Path(__file__).parent / "output" / "products.json"

# Held-out queries (not used while tuning the product text) -> ids of the correct products.
# The ground truth was derived from product names/attributes in products.json.
EXPECTED = {
    "spor salonuna giderken giyeceğim ayakkabı": {"42713792"},
    "göz makyajı için bir şey": {"1016742922"},
    "kapüşonlu şişme mont": {"1071479043", "1073371103", "1100119387", "849095967"},
    "düğmeli mont": {"977379012", "987847941"},
    "yeşil renkli mont": {"1144525931", "879026670"},
    "süet ceket": {"450350040"},
    "erkek arkadaşıma hediye alacağım tişört": {"946802869"},
    "yağmur geçirmeyen kaban": {"1073371103", "1100119387", "856865482", "977379012", "985084456"},
    "deri cekt": {"1080965079", "450350040"},  # typo on purpose
    "white sneakers": {"42713792"},  # English on purpose
    "içi peluşlu sıcak tutan mont": {"1080965079", "879026670", "977379012"},
    "laptop çantası": set(),  # no such product: the top score should be low
}

# Attributes that don't describe how a product looks or is used
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

TOP_K = 3


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


products = json.loads(PRODUCTS_FILE.read_text(encoding="utf-8"))
product_texts = [build_product_text(p) for p in products]

model = SentenceTransformer(MODEL_NAME)
print(f"Model: {MODEL_NAME} | device: {model.device} | max_seq_length: {model.max_seq_length}\n")

# Encode all products once; each query is compared against these vectors
passage_embeddings = model.encode(
    [PASSAGE_PREFIX + text for text in product_texts], normalize_embeddings=True
)

top1_correct = 0
top3_correct = 0
scored_queries = 0

for query, expected in EXPECTED.items():
    query_embedding = model.encode(QUERY_PREFIX + query, normalize_embeddings=True)
    # similarity() returns a 1 x N table; [0] takes the single row of N scores
    scores = model.similarity(query_embedding, passage_embeddings)[0]
    top_scores, top_indices = scores.topk(TOP_K)
    top_ids = [products[i]["trendyol_id"] for i in top_indices.tolist()]

    if not expected:
        status = f"(ilgili ürün yok, en yüksek skor: {top_scores[0].item():.3f})"
    else:
        scored_queries += 1
        if top_ids[0] in expected:
            top1_correct += 1
            top3_correct += 1
            status = "✅ 1. sıra doğru"
        elif expected & set(top_ids):
            top3_correct += 1
            status = "🟡 doğru ürün ilk 3'te"
        else:
            status = "❌ doğru ürün ilk 3'te yok"

    print(f"Sorgu: {query}  {status}")
    for rank, (score, idx) in enumerate(zip(top_scores, top_indices), start=1):
        product = products[idx.item()]
        mark = "✓" if product["trendyol_id"] in expected else " "
        # Some products share the same name (e.g. two MEECY coats), so show the id too
        print(f"  {mark} {rank}. ({score.item():.3f}) [{product['trendyol_id']}] {product['name']}")
    print()

print(f"1. sırada doğru: {top1_correct}/{scored_queries} | ilk 3'te doğru: {top3_correct}/{scored_queries}")
