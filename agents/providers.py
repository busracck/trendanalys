"""LLM sağlayıcıları. Hepsi aynı imzayı sunar: ask(prompt) -> metin.

Sağlayıcı `.env` içindeki REVIEWER_PROVIDER ile seçilir:
    ollama  — yerel, ücretsiz, anahtar istemez (varsayılan)
    gemini  — GEMINI_API_KEY ister
    claude  — ANTHROPIC_API_KEY ister

Hata ayıklarken: sağlayıcı HTTP hatası verirse cevabın gövdesi mesaja eklenir
(model adı eskimişse orada yazar).
"""

import json
import re
import time

import httpx

OLLAMA_URL = "http://localhost:11434/api/chat"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
CLAUDE_URL = "https://api.anthropic.com/v1/messages"

TIMEOUT = 300
MAX_TOKENS = 4000

# Geçici sunucu hataları: sıra bekleme (429) ve yoğunluk (503)
RETRY_CODES = ("429", "503")
RETRY_WAITS = (5, 15)

# Düşünen modeller (qwen3 gibi) cevabın başına <think>...</think> koyuyor
THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)


class ProviderError(RuntimeError):
    """Sağlayıcıya ulaşılamadı ya da cevap anlaşılamadı."""


def _clean(text):
    text = THINK_BLOCK.sub("", text)
    # Model cevabı ```json ... ``` bloğuna sarmış olabilir
    fenced = re.search(r"```(?:json)?\s*(.+?)```", text, re.DOTALL)
    return (fenced.group(1) if fenced else text).strip()


def ask_ollama(prompt, model, settings):
    try:
        response = httpx.post(
            OLLAMA_URL,
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "think": False,
                "format": "json",
                "options": {"temperature": 0.1, "num_ctx": 8192},
            },
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        return _clean(response.json()["message"]["content"])
    except httpx.HTTPError as error:
        raise ProviderError(
            f"Ollama'ya ulaşılamadı ({type(error).__name__}). Servis çalışıyor mu: ollama serve"
        ) from error


def ask_gemini(prompt, model, settings):
    if not settings.GEMINI_API_KEY:
        raise ProviderError(".env dosyasında GEMINI_API_KEY yok.")

    try:
        response = httpx.post(
            GEMINI_URL.format(model=model),
            headers={"x-goog-api-key": settings.GEMINI_API_KEY},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.1,
                    "maxOutputTokens": MAX_TOKENS,
                    "responseMimeType": "application/json",
                },
            },
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        return _clean(response.json()["candidates"][0]["content"]["parts"][0]["text"])
    except httpx.HTTPStatusError as error:
        raise ProviderError(
            f"Gemini {error.response.status_code}: {error.response.text[:300]}"
        ) from error
    except (httpx.HTTPError, KeyError, IndexError) as error:
        raise ProviderError(f"Gemini çağrısı başarısız: {type(error).__name__}") from error


def ask_claude(prompt, model, settings):
    if not settings.ANTHROPIC_API_KEY:
        raise ProviderError(".env dosyasında ANTHROPIC_API_KEY yok.")

    try:
        response = httpx.post(
            CLAUDE_URL,
            headers={
                "x-api-key": settings.ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": MAX_TOKENS,
                "temperature": 0.1,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        return _clean(response.json()["content"][0]["text"])
    except httpx.HTTPStatusError as error:
        raise ProviderError(
            f"Claude {error.response.status_code}: {error.response.text[:300]}"
        ) from error
    except (httpx.HTTPError, KeyError, IndexError) as error:
        raise ProviderError(f"Claude çağrısı başarısız: {type(error).__name__}") from error


PROVIDERS = {
    "ollama": ask_ollama,
    "gemini": ask_gemini,
    "claude": ask_claude,
}

# Sağlayıcı seçilip model belirtilmezse kullanılacak varsayılanlar
DEFAULT_MODELS = {
    "ollama": "qwen3:4b",
    # "latest" takma adı: sürüm eskidiğinde kod bozulmaz
    "gemini": "gemini-flash-latest",
    "claude": "claude-sonnet-5",
}


def ask(prompt, settings):
    """Seçili sağlayıcıya sorar, cevabı JSON olarak çözer.

    Uzak sağlayıcı çalışmazsa (kota, yoğunluk, ağ) REVIEWER_FALLBACK'e düşer.
    """
    try:
        return _ask_one(prompt, settings, settings.REVIEWER_PROVIDER)
    except ProviderError as error:
        fallback = settings.REVIEWER_FALLBACK
        if not fallback or fallback == settings.REVIEWER_PROVIDER:
            raise
        print(f"{settings.REVIEWER_PROVIDER} kullanılamadı ({str(error)[:80]}…)")
        print(f"Yedek sağlayıcıya geçiliyor: {fallback}")
        return _ask_one(prompt, settings, fallback)


def _ask_one(prompt, settings, provider):
    if provider not in PROVIDERS:
        raise ProviderError(
            f"Bilinmeyen sağlayıcı: {provider}. Seçenekler: {', '.join(PROVIDERS)}"
        )

    # Model adı yalnızca asıl sağlayıcı için geçerli; yedek kendi varsayılanını kullanır
    model = (
        settings.REVIEWER_MODEL
        if provider == settings.REVIEWER_PROVIDER and settings.REVIEWER_MODEL
        else DEFAULT_MODELS[provider]
    )

    # Geçici hatalarda birkaç kez bekleyip tekrar dene
    for wait in (*RETRY_WAITS, None):
        try:
            raw = PROVIDERS[provider](prompt, model, settings)
            break
        except ProviderError as error:
            gecici = any(code in str(error) for code in RETRY_CODES)
            if wait is None or not gecici:
                raise
            print(f"Sağlayıcı meşgul, {wait} sn sonra tekrar denenecek...")
            time.sleep(wait)

    try:
        return json.loads(raw)
    except json.JSONDecodeError as error:
        raise ProviderError(f"Model geçerli JSON döndürmedi:\n{raw[:400]}") from error
