import logging
from typing import Optional

import torch
from transformers import pipeline, Pipeline

logger = logging.getLogger(__name__)

MODEL_NAME = "blanchefort/rubert-base-cased-sentiment"

LABEL_MAP = {
    "NEGATIVE": "negative",
    "NEUTRAL":  "neutral",
    "POSITIVE": "positive",
    "LABEL_0":  "negative",
    "LABEL_1":  "neutral",
    "LABEL_2":  "positive",
}

_pipe: Optional[Pipeline] = None


def _get_pipeline() -> Pipeline:
    global _pipe
    if _pipe is None:
        device = 0 if torch.cuda.is_available() else -1
        logger.info(f"Loading {MODEL_NAME} on {'GPU' if device == 0 else 'CPU'}")
        _pipe = pipeline(
            "text-classification",
            model=MODEL_NAME,
            tokenizer=MODEL_NAME,
            device=device,
            truncation=True,
            max_length=512,
        )
        logger.info("Model loaded.")
    return _pipe


def predict_batch(texts: list[str], batch_size: int = 32) -> list[dict]:
    """Returns list of {"label": "positive|neutral|negative", "score": float}."""
    if not texts:
        return []

    pipe = _get_pipeline()
    results = []
    for i in range(0, len(texts), batch_size):
        chunk = texts[i : i + batch_size]
        for item in pipe(chunk, batch_size=batch_size):
            label = LABEL_MAP.get(item["label"], "neutral")
            results.append({"label": label, "score": round(item["score"], 4)})
    return results
