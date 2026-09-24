"""renk ve cinsiyet normalizasyonu

Aşama 3'te toplanan satırlarda renk ve cinsiyet karışık biçimlerde kaldı
("Siyah / SİYAH / Siyah-BK27", "female / Kadın"). Filtreler tek biçim beklediği
için mevcut kayıtlar burada düzeltiliyor. Yeni kayıtları scraper/cleaner.py
zaten normalize ediyor.

Not: eşleme listeleri bilerek bu dosyaya kopyalandı. Migrasyon geçmişin
fotoğrafıdır; uygulama kodu değişse de bu adım aynı sonucu vermeli.

Revision ID: b46bc16a7e20
Revises: 8b6444147f4f
Create Date: 2026-09-23

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b46bc16a7e20"
down_revision: Union[str, Sequence[str], None] = "8b6444147f4f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

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

COLOR_ALIASES = {"kahve": "kahverengi"}


def turkish_lower(text):
    return text.replace("İ", "i").replace("I", "ı").lower()


def normalize_color(value):
    text = turkish_lower(" ".join(value.split()))
    for color in COLORS:
        if color in text:
            return COLOR_ALIASES.get(color, color)
    return text or None


def upgrade() -> None:
    bind = op.get_bind()

    colors = bind.execute(
        sa.text("select distinct color from products where color is not null")
    ).scalars()
    for old in colors:
        new = normalize_color(old)
        if new != old:
            bind.execute(
                sa.text("update products set color = :new where color = :old"),
                {"new": new, "old": old},
            )

    genders = bind.execute(
        sa.text("select distinct gender from products where gender is not null")
    ).scalars()
    for old in genders:
        new = GENDER_MAP.get(turkish_lower(old))
        if new != old:
            bind.execute(
                sa.text("update products set gender = :new where gender = :old"),
                {"new": new, "old": old},
            )


def downgrade() -> None:
    # Orijinal yazımlar kaybolduğu için geri alınamaz; veri kaybı yok, sadece biçim değişti.
    pass
