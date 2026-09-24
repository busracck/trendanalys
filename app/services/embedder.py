"""bge-m3 modelini tek sefer yükler ve metinleri vektöre çevirir."""

from functools import lru_cache

import torch
from sentence_transformers import SentenceTransformer

MODEL_NAME = "BAAI/bge-m3"

# Modelin varsayılanı 8192; en uzun ürün metnimiz ~800 token, 1024 yeterli ve GPU belleğini korur
MAX_SEQ_LENGTH = 1024

# 4 GB VRAM için güvenli batch boyutu
BATCH_SIZE = 8


@lru_cache(maxsize=1)
def get_model():
    """Modeli ilk çağrıda yükler, sonraki çağrılarda aynı nesneyi döndürür.

    GPU'da yer yoksa (ör. sunucu zaten bir kopya tutuyorsa) CPU'ya düşer:
    yavaş ama çalışır.
    """
    try:
        model = SentenceTransformer(MODEL_NAME)
    except torch.OutOfMemoryError:
        print("GPU belleği yetmedi, model CPU'da çalışacak (daha yavaş).")
        model = SentenceTransformer(MODEL_NAME, device="cpu")

    model.max_seq_length = MAX_SEQ_LENGTH
    return model


def encode_passages(texts, show_progress_bar=True):
    """Ürün metinlerini vektöre çevirir (N x 1024)."""
    return get_model().encode(
        texts,
        batch_size=BATCH_SIZE,
        normalize_embeddings=True,
        show_progress_bar=show_progress_bar,
    )


def encode_query(query):
    """Tek bir arama cümlesini vektöre çevirir (1024)."""
    return get_model().encode(query, normalize_embeddings=True)
