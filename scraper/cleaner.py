"""Ham veriyi kaydetmeye hazır hâle getiren yardımcılar."""

import hashlib
import json
import re

EMOJI_PATTERN = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF]+",
    flags=re.UNICODE,
)

# ld+json İngilizce ("female"), /pd/ şablonu Türkçe ("Kadın") veriyor
GENDER_MAP = {
    "female": "kadin",
    "kadın": "kadin",
    "kadin": "kadin",
    "male": "erkek",
    "erkek": "erkek",
    "unisex": "unisex",
}

# Sıra önemli: "kahverengi" daha önce gelmeli, yoksa "kahve" ile eşleşir
COLORS = [
    "kahverengi",
    "kahve",
    "siyah",
    "beyaz",
    "lacivert",
    "bordo",
    "bej",
    "gri",
    "haki",
    "ekru",
    "krem",
    "pembe",
    "yeşil",
    "mavi",
    "kırmızı",
    "sarı",
    "mor",
    "turuncu",
    "vizon",
    "antrasit",
    "gümüş",
    "altın",
]

# Aynı rengin ikinci adı
COLOR_ALIASES = {"kahve": "kahverengi"}


def turkish_lower(text):
    return text.replace("İ", "i").replace("I", "ı").lower()


def clean_text(text):
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)      # HTML etiketlerini boşlukla değiştir
    text = EMOJI_PATTERN.sub("", text)        # emojileri sil
    return " ".join(text.split())             # boşlukları tek boşluğa indir


def normalize_gender(value):
    """'female', 'Kadın' -> 'kadin'. Tanımadığımız değer için None."""
    if not value:
        return None
    return GENDER_MAP.get(turkish_lower(clean_text(value)))


def normalize_color(value):
    """'SİYAH', 'Siyah-BK27' -> 'siyah'. Bilinen renk bulunamazsa temizlenmiş hâli."""
    if not value:
        return None

    text = turkish_lower(clean_text(value))
    for color in COLORS:
        if color in text:
            return COLOR_ALIASES.get(color, color)

    return text or None


def content_hash(product):
    payload = json.dumps(product, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
