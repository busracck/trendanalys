"""Veritabanı tabloları: ürünler ve ürün sayfasından alınan yorumlar."""

from datetime import date, datetime
from decimal import Decimal

from pgvector.sqlalchemy import Vector
from sqlalchemy import Computed, DateTime, ForeignKey, Index, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    trendyol_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    url: Mapped[str | None] = mapped_column(Text)

    name: Mapped[str] = mapped_column(Text)
    brand: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(Text, index=True)
    category_path: Mapped[list[str] | None] = mapped_column(ARRAY(Text))

    price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), index=True)
    currency: Mapped[str | None] = mapped_column(String(3))
    color: Mapped[str | None] = mapped_column(Text)
    gender: Mapped[str | None] = mapped_column(Text)

    rating: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    rating_count: Mapped[int | None] = mapped_column()
    review_count: Mapped[int | None] = mapped_column()

    attributes: Mapped[dict] = mapped_column(JSONB, default=dict)
    image_url: Mapped[str | None] = mapped_column(Text)

    # Modele verilen metin: poc/embed_test.py içindeki build_product_text çıktısı
    search_text: Mapped[str | None] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024))
    # search_text değiştikçe PostgreSQL bu sütunu kendisi günceller
    tsv: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('turkish', coalesce(search_text, ''))", persisted=True),
    )

    content_hash: Mapped[str | None] = mapped_column(String(64))
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # Boşsa: bu ürünün vektörü henüz hesaplanmadı
    embedded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    reviews: Mapped[list["ReviewSnippet"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index(
            "ix_products_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_products_tsv", "tsv", postgresql_using="gin"),
    )

    def __repr__(self) -> str:
        return f"<Product {self.trendyol_id} {self.name[:40]}>"


class ReviewSnippet(Base):
    """Ürün sayfasındaki yorumlar. Yorumu yazanın adı saklanmaz (KVKK)."""

    __tablename__ = "review_snippets"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    text: Mapped[str] = mapped_column(Text)
    rating: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    published_at: Mapped[date | None] = mapped_column()

    product: Mapped["Product"] = relationship(back_populates="reviews")
