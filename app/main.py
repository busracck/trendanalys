"""FastAPI uygulaması: web sayfası, arama ve ürün uçları."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Product
from app.schemas import FiltersOut, ProductOut, SearchRequest, SearchResponse
from app.services.embedder import get_model
from app.services.search import search

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Sunucu açılırken: model belleğe alınır, ilk arama hızlı olur
    get_model()
    yield
    # yield sonrası kapanışta çalışır; şimdilik bir işimiz yok


app = FastAPI(
    title="TrendAnalys",
    description=(
        "Trendyol ürünlerinde **cümleyle** arama.\n\n"
        "Anahtar kelime yerine tam cümle alır; şehri, bütçeyi, rengi ve kategoriyi "
        "cümleden çıkarır, şehrin havasını hesaba katar ve anlamca en yakın ürünleri döndürür.\n\n"
        "Katalog: 1097 giyim ve ayakkabı ürünü. Arama `bge-m3` vektörleri ve pgvector ile yapılır."
    ),
    version="1.0.0",
    lifespan=lifespan,
    openapi_tags=[
        {"name": "arama", "description": "Cümleyle ürün arama"},
        {"name": "ürün", "description": "Tek ürün bilgisi"},
        {"name": "sistem", "description": "Sağlık kontrolü ve web sayfası"},
    ],
)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


def get_session():
    """Her istek için bir veritabanı oturumu açar, istek bitince kapatır."""
    with SessionLocal() as session:
        yield session


# Kategori adlarının kullanıcıya gösterilecek hâli
CATEGORY_LABELS = {"t-shirt": "tişört", "spor-ayakkabi": "spor ayakkabı"}


@app.get("/", tags=["sistem"], include_in_schema=False)
def index(request: Request, session: Session = Depends(get_session)):
    """Ana sayfa. Katalogda hangi türlerin olduğunu veritabanından okur."""
    rows = session.scalars(select(Product.category).distinct()).all()
    slugs = {row.removeprefix("kadin-").removeprefix("erkek-") for row in rows if row}
    categories = sorted(CATEGORY_LABELS.get(slug, slug) for slug in slugs)

    return templates.TemplateResponse(
        request, "index.html", {"categories": categories}
    )


@app.get("/health", tags=["sistem"], summary="Sunucu ayakta mı?")
def health():
    """Servisin çalıştığını doğrular. Veritabanına ya da modele dokunmaz."""
    return {"status": "ok"}


@app.post(
    "/api/search",
    response_model=SearchResponse,
    tags=["arama"],
    summary="Cümleyle ürün ara",
    response_description="Bulunan ürünler, cümleden çıkarılan filtreler ve hava durumu",
)
def search_products(request: SearchRequest, session: Session = Depends(get_session)):
    """Cümleyi ayrıştırır, hava durumunu ekler ve anlamca en yakın ürünleri döndürür.

    Katalogda olmayan bir tür istenirse (çanta, şapka…) sonuç listesi boş döner
    ve `message` alanında sebebi yazar.
    """
    result = search(
        session,
        request.query,
        limit=request.limit,
        city=request.city,
        max_price=request.max_price,
    )
    weather = result["weather"]
    return SearchResponse(
        query=request.query,
        city=result["parsed"]["city"],
        weather=result["weather_text"],
        temperature=weather["temperature"] if weather else None,
        message=result["message"],
        filters=FiltersOut(**result["parsed"]),
        results=result["results"],
    )


@app.get(
    "/api/products/{trendyol_id}",
    response_model=ProductOut,
    tags=["ürün"],
    summary="Tek ürünü getir",
    responses={404: {"description": "Bu numarada ürün yok"}},
)
def get_product(trendyol_id: str, session: Session = Depends(get_session)):
    """Trendyol ürün numarasıyla tek bir ürünün bilgilerini döndürür."""
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
