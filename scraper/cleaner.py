
import hashlib,re
import json

EMOJI_PATTERN = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF]+",
    flags=re.UNICODE,
)


def turkish_lower(text):
    return text.replace("İ", "i").replace("I", "ı").lower()


def clean_text(text):
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)      # HTML etiketlerini boşlukla değiştir
    text = EMOJI_PATTERN.sub("", text)        # emojileri sil
    return " ".join(text.split())             # boşlukları tek boşluğa indir


def content_hash(product):
    payload = json.dumps(product, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()