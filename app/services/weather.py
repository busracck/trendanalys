"""Open-Meteo'dan hava durumu alır ve arama cümlesine eklenecek ifadeye çevirir.

Servise ulaşılamazsa None döner: arama hava durumu olmadan da çalışmalı.
"""

import time
from functools import lru_cache

import httpx

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

TIMEOUT = 10
CACHE_TTL = 30 * 60  # 30 dakika

# {"izmir": (kayıt_zamanı, veri)}
_cache = {}


@lru_cache(maxsize=128)
def get_coordinates(city):
    """Şehir adından (enlem, boylam). Koordinatlar değişmediği için kalıcı cache."""
    try:
        response = httpx.get(
            GEOCODING_URL,
            params={"name": city, "count": 1, "country": "TR", "language": "tr"},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        results = response.json().get("results")
    except httpx.HTTPError as error:
        print(f"Geocoding başarısız ({city}): {type(error).__name__}")
        return None

    if not results:
        return None

    return results[0]["latitude"], results[0]["longitude"]


def get_weather(city):
    """Şehrin anlık havası: {'temperature', 'precipitation', 'wind'}. Bulunamazsa None."""
    if not city:
        return None

    cached = _cache.get(city)
    if cached and time.time() - cached[0] < CACHE_TTL:
        return cached[1]

    coordinates = get_coordinates(city)
    if coordinates is None:
        return None

    try:
        response = httpx.get(
            FORECAST_URL,
            params={
                "latitude": coordinates[0],
                "longitude": coordinates[1],
                "current": "temperature_2m,precipitation,wind_speed_10m",
                "timezone": "Europe/Istanbul",
            },
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        current = response.json()["current"]
    except (httpx.HTTPError, KeyError) as error:
        print(f"Hava durumu alınamadı ({city}): {type(error).__name__}")
        return None

    weather = {
        "temperature": current["temperature_2m"],
        "precipitation": current["precipitation"],
        "wind": current["wind_speed_10m"],
    }
    _cache[city] = (time.time(), weather)
    return weather


def describe_weather(weather):
    """Sayıları arama cümlesine eklenebilecek ifadeye çevirir."""
    if not weather:
        return ""

    temperature = weather["temperature"]
    if temperature < 5:
        parts = ["çok soğuk hava", "kalın mont", "kaban"]
    elif temperature < 12:
        parts = ["soğuk hava", "mont", "kazak"]
    elif temperature < 18:
        parts = ["serin hava", "uzun kollu", "katmanlı giyim"]
    elif temperature < 25:
        parts = ["ılık hava"]
    else:
        parts = ["sıcak hava", "ince kumaş", "kısa kollu"]

    if weather["precipitation"] > 0:
        parts += ["yağmurlu", "su geçirmez"]
    if weather["wind"] > 20:
        parts.append("rüzgarlı")

    return ", ".join(parts)
