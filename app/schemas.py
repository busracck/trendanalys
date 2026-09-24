from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    """Arama isteği. Şehir ve fiyat cümlenin içinde de yazılabilir."""

    query: str = Field(
        min_length=2,
        max_length=300,
        description="Aranacak cümle. Şehir, bütçe, renk ve kategori cümleden çıkarılır.",
    )
    city: str | None = Field(
        default=None, description="Hava durumu için şehir. Verilirse cümledeki şehri ezer."
    )
    max_price: int | None = Field(
        default=None, gt=0, description="Üst fiyat sınırı (TL). Cümledeki bütçeyi ezer."
    )
    limit: int = Field(default=10, ge=1, le=50, description="Kaç ürün dönsün")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"query": "İzmir'de serin bir akşam için 1500 TL altı elbise", "limit": 5},
                {"query": "yağmurda ıslanmayan kapüşonlu mont"},
            ]
        }
    }


class ProductOut(BaseModel):
    """Arama sonucundaki tek ürün."""

    trendyol_id: str
    name: str
    brand: str | None = None
    price: float | None = None
    currency: str | None = None
    color: str | None = None
    category: str | None = None
    rating: float | None = None
    image_url: str | None = None
    url: str | None = None
    why: str = ""


class FiltersOut(BaseModel):
    """Cümleden çıkarılan bilgiler. Arayüz bunları kullanıcıya gösterir."""

    text: str = ""
    city: str | None = None
    min_price: int | None = None
    max_price: int | None = None
    color: str | None = None
    gender: str | None = None
    category: str | None = None
    unavailable: str | None = None


class SearchResponse(BaseModel):
    """Arama cevabı: bulunan ürünler, cümleden çıkarılanlar ve hava durumu."""

    query: str
    city: str | None = None
    weather: str = ""
    temperature: float | None = None
    message: str = ""
    filters: FiltersOut
    results: list[ProductOut]
