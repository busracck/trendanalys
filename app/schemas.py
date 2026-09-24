from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=300)
    city: str | None = None
    max_price: int | None = Field(default=None, gt=0)
    limit: int = Field(default=10, ge=1, le=50)


class ProductOut(BaseModel):
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


class SearchResponse(BaseModel):
    query: str
    city: str | None = None
    weather: str = ""
    results: list[ProductOut]
