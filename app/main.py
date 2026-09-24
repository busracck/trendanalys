"""FastAPI uygulaması: arama ve ürün uçları."""

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Product
from app.schemas import ProductOut, SearchRequest, SearchResponse
from app.services.search import search

app = FastAPI(
    title="TrendAnalys",
    description="Trendyol ürünlerinde cümleyle arama",
    version="0.1.0",
)


def get_session():
    """Her istek için bir veritabanı oturumu açar, istek bitince kapatır."""
    with SessionLocal() as session:
        yield session


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/search", response_model=SearchResponse)
def search_products(request: SearchRequest, session: Session = Depends(get_session)):
    result = search(
        session,
        request.query,
        limit=request.limit,
        city=request.city,
        max_price=request.max_price,
    )
    return SearchResponse(
        query=request.query,
        city=result["parsed"]["city"],
        weather=result["weather_text"],
        results=result["results"],
    )


@app.get("/api/products/{trendyol_id}", response_model=ProductOut)
def get_product(trendyol_id: str, session: Session = Depends(get_session)):
    product = session.scalar(select(Product).where(Product.trendyol_id == trendyol_id))
    if product is None:
        raise HTTPException(status_code=404, detail="Ürün bulunamadı")

    return ProductOut(
        trendyol_id=product.trendyol_id,
        name=product.name,
        brand=product.brand,
        price=float(product.price) if product.price is not None else None,
        currency=product.currency,
        color=product.color,
        category=product.category,
        rating=float(product.rating) if product.rating is not None else None,
        image_url=product.image_url,
        url=product.url,
    )
