import logging
from typing import Optional

import torch
from transformers import pipeline, Pipeline

from nlp.topics import MIN_TEXT_LENGTH, _is_meaningful

logger = logging.getLogger(__name__)

MODEL_NAME = "blanchefort/rubert-base-cased-sentiment"
LOW_CONFIDENCE_THRESHOLD = 0.55

LABEL_MAP = {
    "NEGATIVE": "negative",
    "NEUTRAL":  "neutral",
    "POSITIVE": "positive",
    "LABEL_0":  "negative",
    "LABEL_1":  "neutral",
    "LABEL_2":  "positive",
}

_FALLBACK = {"label": "neutral", "score": 0.0}

_pipe: Optional[Pipeline] = None


def _get_pipeline() -> Pipeline:
    global _pipe
    if _pipe is None:
        device = 0 if torch.cuda.is_available() else -1
        logger.info(f"Loading {MODEL_NAME} on {'GPU' if device == 0 else 'CPU'}")
        kwargs = dict(
            model=MODEL_NAME,
            tokenizer=MODEL_NAME,
            device=device,
            truncation=True,
            max_length=512,
        )
        try:
            _pipe = pipeline("text-classification", **kwargs, local_files_only=True)
        except OSError:
            logger.info("Model not cached — downloading from HuggingFace")
            _pipe = pipeline("text-classification", **kwargs)
        logger.info("Model loaded.")
    return _pipe


def predict_batch(texts: list[str], batch_size: int = 32) -> list[dict]:
    """Returns list of {"label": "positive|neutral|negative", "score": float}."""
    if not texts:
        return []

    results: list[dict] = [_FALLBACK.copy()] * len(texts)
    valid_indices = [i for i, t in enumerate(texts) if _is_meaningful(t)]

    if not valid_indices:
        return results

    pipe = _get_pipeline()
    valid_texts = [texts[i] for i in valid_indices]
    raw: list[dict] = []

    for i in range(0, len(valid_texts), batch_size):
        chunk = valid_texts[i : i + batch_size]
        raw.extend(pipe(chunk, batch_size=batch_size))

    for orig_idx, item in zip(valid_indices, raw):
        label = LABEL_MAP.get(item["label"], "neutral")
        score = round(item["score"], 4)
        if score < LOW_CONFIDENCE_THRESHOLD:
            logger.warning(f"Low confidence ({score:.3f}) → 'neutral' for '{texts[orig_idx][:60]}'")
            results[orig_idx] = {"label": "neutral", "score": score}
        else:
            results[orig_idx] = {"label": label, "score": score}

    return results
