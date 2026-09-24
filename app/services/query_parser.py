import json
import re
from pathlib import Path
from functools import lru_cache
from functools import lru_cache


from scraper.cleaner import COLORS, COLOR_ALIASES, turkish_lower

CITIES_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "iller.json"

SUFFIXES = "deki|daki|teki|taki|den|dan|ten|tan|nin|nın|de|da|te|ta|ye|ya|li|lı|in|ın|e|a|i|ı"

PRICE_PATTERNS = [
    # 500-1000 arası / 500 ile 1000 arası
    (r"(\d+)\s*(?:-|ile|ila)\s*(\d+)\s*(?:tl|lira)?\s*(?:aras\w*)?", "range"),
    # en fazla 1500 / maksimum 1500
    (r"(?:en fazla|en çok|maksimum|max)\s*(\d+)\s*(?:tl|lira)?", "max"),
    # 1000 tl altı / 1000'e kadar / 1000 tl aşağısı
    (r"(\d+)\s*(?:tl|lira)?\s*['’]?\w*\s*(?:alt\w*|kadar|aşağ\w*)", "max"),
    # en az 500 / minimum 500
    (r"(?:en az|minimum|min)\s*(\d+)\s*(?:tl|lira)?", "min"),
    # 1000 tl üzeri / 1000 tl'den fazla
    (r"(\d+)\s*(?:tl|lira)?\s*['’]?\w*\s*(?:üzer\w*|üst\w*|fazla)", "min"),
]

GENDER_WORDS = {
    "kadın": "kadin",
    "kadin": "kadin",
    "bayan": "kadin",
    "kız": "kadin",
    "erkek": "erkek",
    "bay": "erkek",
    "unisex": "unisex",
}

# Tür -> eş anlamlı kelimeler. Sıra önemli: "spor ayakkabı", "ayakkabı"dan önce gelmeli.
# Katalogda olmayan ürün türleri. Kullanıcı bunları sorduğunda alakasız ürün
# göstermek yerine "katalogda yok" demek için kullanılır.
UNAVAILABLE_KEYWORDS = {
    "çanta": ["çanta"],
    "şapka": ["şapka", "bere", "kasket"],
    "atkı": ["atkı", "eldiven", "kaşkol"],
    "çorap": ["çorap"],
    "kemer": ["kemer"],
    "gözlük": ["gözlük"],
    "saat": ["kol saati"],
    "takı": ["kolye", "küpe", "yüzük", "bileklik"],
    "iç giyim": ["iç çamaşırı", "sütyen", "külot", "boxer"],
    "mayo": ["mayo", "bikini"],
    "etek": ["etek"],
    "gömlek": ["gömlek"],
    "kazak": ["kazak", "hırka"],
    "şort": ["şort"],
    "takım elbise": ["takım elbise", "smokin"],
    "pijama": ["pijama", "gecelik"],
    "terlik": ["terlik", "sandalet"],
    "topuklu ayakkabı": ["topuklu", "stiletto"],
    "kozmetik": ["parfüm", "ruj", "maskara", "makyaj"],
}

CATEGORY_KEYWORDS = {
    "elbise": ["elbise", "abiye"],
    "mont": ["mont", "kaban", "parka", "anorak"],
    "sweatshirt": ["sweatshirt", "sweat", "hoodie"],
    "t-shirt": ["tişört", "t-shirt", "tshirt"],
    "bot": ["bot", "çizme"],
    "spor-ayakkabi": ["spor ayakkabı", "sneaker", "koşu ayakkabı"],
}

@lru_cache(maxsize=1)
def load_cities():

    cities = json.loads(CITIES_FILE.read_text(encoding="utf-8"))
    return sorted((turkish_lower(c) for c in cities), key=len, reverse=True)


def find_city(text):
    lowered = turkish_lower(text)
    for city in load_cities():
        pattern = rf"\b{re.escape(city)}(?:'?(?:{SUFFIXES}))?\b"
        if re.search(pattern, lowered):
            remaining = re.sub(pattern, " ", lowered)
            return city, " ".join(remaining.split())
    return None, text


def find_price(text):
    lowered = turkish_lower(text)
    for pattern, kind in PRICE_PATTERNS:
        match = re.search(pattern, lowered)
        if not match:
            continue

        # Fiyat ifadesi cümleden çıkarılıyor: modelin işine yaramıyor
        remaining = " ".join(re.sub(pattern, " ", lowered).split())
        if kind == "range":
            return int(match.group(1)), int(match.group(2)), remaining
        if kind == "max":
            return None, int(match.group(1)), remaining
        return int(match.group(1)), None, remaining

    return None, None, text


def find_color(text):
    lowered = turkish_lower(text)
    for color in COLORS:
        if color in lowered:
            return COLOR_ALIASES.get(color, color)
    return None


def find_gender(text):
    lowered = turkish_lower(text)
    for word, gender in GENDER_WORDS.items():
        if word in lowered:
            return gender
    return None


def find_category(text):
    lowered = turkish_lower(text)
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return category
    return None


def parse_query(text):
    """Cümleyi arama metni + filtrelere ayırır."""
    city, remaining = find_city(text)
    min_price, max_price, remaining = find_price(remaining)

    return {
        "text": remaining,
        "city": city,
        "min_price": min_price,
        "max_price": max_price,
        "color": find_color(remaining),
        "gender": find_gender(remaining),
        "category": find_category(remaining),
        # Kategori tanınmadıysa: acaba katalogda hiç olmayan bir tür mü istendi?
        "unavailable": None if find_category(remaining) else find_unavailable(remaining),
    }


def find_unavailable(text):
    """Katalogda olmayan bir ürün türü isteniyorsa adını döndürür."""
    lowered = turkish_lower(text)
    for label, keywords in UNAVAILABLE_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return label
    return None
