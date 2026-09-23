"""Bir ürünü modele verilecek tek bir metne çevirir."""

# Yorum metinleri uzun olabiliyor; ilk 15'i ürünü anlatmaya yetiyor
MAX_REVIEWS = 15

# Ürünün görünüşünü ya da kullanımını anlatmayan özellikler
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
    """Örnek: "Ürün adı. Kategori: Kadın > Kadın Mont. Kalıp: Oversize. Yorumlar: ..." """
    parts = [product.name]

    if product.category_path:
        parts.append("Kategori: " + " > ".join(product.category_path))

    attributes = [
        f"{key}: {value}"
        for key, value in (product.attributes or {}).items()
        if key not in NOISE_ATTRIBUTES
    ]
    if attributes:
        parts.append("; ".join(attributes))

    if product.reviews:
        texts = [review.text for review in product.reviews[:MAX_REVIEWS]]
        parts.append("Yorumlar: " + " ".join(texts))

    return ". ".join(parts)
