import logging
from typing import Optional

import numpy as np
import torch
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

MODEL_NAME = "ai-forever/sbert_large_nlu_ru"
LOW_CONFIDENCE_THRESHOLD = 0.35
MIN_TEXT_LENGTH = 3

TOPIC_ANCHORS: dict[str, list[str]] = {
    "приложение": [
        "мобильное приложение банка не работает",
        "приложение вылетает, тормозит, не открывается",
        "обновление приложения сломало авторизацию",
        "не могу войти в личный кабинет на телефоне",
    ],
    "кредиты": [
        "оформление кредита и одобрение заявки",
        "высокая процентная ставка по кредиту",
        "ипотека, рассрочка, досрочное погашение долга",
        "отказали в кредите, плохая кредитная история",
    ],
    "поддержка": [
        "служба поддержки не отвечает на звонки",
        "оператор колл-центра нагрубил и не помог",
        "долго ждал ответа в чате поддержки",
        "сотрудник банка решил мою проблему",
    ],
    "карты": [
        "банковская карта заблокирована без причины",
        "кэшбек по дебетовой карте не начислился",
        "банкомат не выдал деньги, проблема с картой",
        "перевыпуск карты Visa или Mastercard",
    ],
    "переводы": [
        "перевод денег не дошёл до получателя",
        "пополнение счёта и снятие наличных",
        "перевод через СБП завис или не прошёл",
        "межбанковский перевод по реквизитам",
    ],
    "общее": [
        "отличный банк, рекомендую всем",
        "общее впечатление от банковского обслуживания",
        "условия вклада и процентная ставка по депозиту",
        "открыл счёт, доволен работой банка",
    ],
}

TOPICS = list(TOPIC_ANCHORS.keys())

_model: Optional[SentenceTransformer] = None
_topic_embeddings: Optional[np.ndarray] = None  # shape: (n_topics, hidden), unit-normalized


def _load_model() -> SentenceTransformer:
    global _model
    if _model is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"Loading {MODEL_NAME} on {device.upper()}")
        try:
            _model = SentenceTransformer(MODEL_NAME, device=device, local_files_only=True)
        except OSError:
            logger.info("Model not cached — downloading from HuggingFace")
            _model = SentenceTransformer(MODEL_NAME, device=device)
        logger.info("Topic model loaded.")
    return _model


def _encode(texts: list[str]) -> np.ndarray:
    """Returns unit-normalized embeddings, shape (n, hidden)."""
    return _load_model().encode(texts, normalize_embeddings=True, show_progress_bar=False)


def _get_topic_embeddings() -> np.ndarray:
    global _topic_embeddings
    if _topic_embeddings is None:
        logger.info("Precomputing topic anchor embeddings...")
        all_anchors: list[str] = []
        counts: list[int] = []
        for topic in TOPICS:
            anchors = TOPIC_ANCHORS[topic]
            all_anchors.extend(anchors)
            counts.append(len(anchors))

        raw = _encode(all_anchors)

        topic_vecs = []
        idx = 0
        for count in counts:
            vecs = raw[idx : idx + count]
            mean_vec = vecs.mean(axis=0)
            topic_vecs.append(mean_vec / (np.linalg.norm(mean_vec) + 1e-9))
            idx += count

        _topic_embeddings = np.stack(topic_vecs)
        logger.info("Topic embeddings ready.")
    return _topic_embeddings


def _cosine_scores(embeddings: np.ndarray) -> np.ndarray:
    """Cosine similarity matrix (n_texts, n_topics). Embeddings must be unit-normalized."""
    return embeddings @ _get_topic_embeddings().T


def _is_meaningful(text: str) -> bool:
    return bool(text) and len(text.strip()) >= MIN_TEXT_LENGTH


def classify_batch(texts: list[str], batch_size: int = 32, threshold: float = LOW_CONFIDENCE_THRESHOLD) -> list[str]:
    if not texts:
        return []

    results = ["общее"] * len(texts)
    valid_indices = [i for i, t in enumerate(texts) if _is_meaningful(t)]

    if not valid_indices:
        return results

    valid_texts = [texts[i] for i in valid_indices]
    all_scores: list[np.ndarray] = []

    for i in range(0, len(valid_texts), batch_size):
        chunk = valid_texts[i : i + batch_size]
        all_scores.append(_cosine_scores(_encode(chunk)))

    scores_matrix = np.concatenate(all_scores, axis=0)

    for orig_idx, scores in zip(valid_indices, scores_matrix):
        best_idx = int(scores.argmax())
        best_score = float(scores[best_idx])
        if best_score < threshold:
            logger.warning(f"Low confidence ({best_score:.3f}) for '{texts[orig_idx][:60]}' → 'общее'")
        else:
            results[orig_idx] = TOPICS[best_idx]

    return results


def classify_batch_multi(
    texts: list[str],
    batch_size: int = 32,
    threshold: float = LOW_CONFIDENCE_THRESHOLD,
    max_topics: int = 3,
) -> list[list[str]]:
    """Returns up to max_topics topics per text, ordered by score. Falls back to ['общее']."""
    if not texts:
        return []

    results: list[list[str]] = [["общее"]] * len(texts)
    valid_indices = [i for i, t in enumerate(texts) if _is_meaningful(t)]

    if not valid_indices:
        return results

    valid_texts = [texts[i] for i in valid_indices]
    all_scores: list[np.ndarray] = []

    for i in range(0, len(valid_texts), batch_size):
        chunk = valid_texts[i : i + batch_size]
        all_scores.append(_cosine_scores(_encode(chunk)))

    scores_matrix = np.concatenate(all_scores, axis=0)

    for orig_idx, scores in zip(valid_indices, scores_matrix):
        above = [(TOPICS[j], float(scores[j])) for j in range(len(TOPICS)) if float(scores[j]) >= threshold]
        if not above:
            logger.warning(f"No topics above threshold for '{texts[orig_idx][:60]}' → ['общее']")
        else:
            above.sort(key=lambda x: x[1], reverse=True)
            results[orig_idx] = [t for t, _ in above[:max_topics]]

    return results


def classify_text(text: str) -> str:
    return classify_batch([text])[0]


def classify_text_multi(text: str, threshold: float = LOW_CONFIDENCE_THRESHOLD) -> list[str]:
    return classify_batch_multi([text], threshold=threshold)[0]
