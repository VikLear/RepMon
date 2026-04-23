import logging
import os
import sys
from typing import Optional

import torch
from transformers import pipeline, Pipeline

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import Review, SessionLocal, init_db

logger = logging.getLogger(__name__)

MODEL_NAME = "blanchefort/rubert-base-cased-sentiment"

# NEGATIVE → negative, NEUTRAL → neutral, POSITIVE → positive
LABEL_MAP = {
    "NEGATIVE": "negative",
    "NEUTRAL":  "neutral",
    "POSITIVE": "positive",
    # некоторые чекпоинты используют LABEL_0/1/2
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
    """
    Returns list of {"label": "positive|neutral|negative", "score": float}
    для каждого текста в том же порядке.
    """
    if not texts:
        return []

    pipe = _get_pipeline()
    results = []

    for i in range(0, len(texts), batch_size):
        chunk = texts[i : i + batch_size]
        raw = pipe(chunk, batch_size=batch_size)
        for item in raw:
            label = LABEL_MAP.get(item["label"], "neutral")
            results.append({"label": label, "score": round(item["score"], 4)})

    return results


def classify_db_reviews(batch_size: int = 32, source_filter: Optional[str] = None) -> int:
    """
    Проходит по всем записям без sentiment в БД и проставляет тональность.
    Возвращает кол-во обработанных записей.
    """
    init_db()
    db = SessionLocal()
    processed = 0

    try:
        query = db.query(Review).filter(Review.sentiment.is_(None))
        if source_filter:
            query = query.filter(Review.source == source_filter)

        reviews = query.all()
        total = len(reviews)
        logger.info(f"Found {total} unclassified reviews, starting inference...")

        for i in range(0, total, batch_size):
            batch = reviews[i : i + batch_size]
            texts = [r.text for r in batch]
            preds = predict_batch(texts, batch_size=batch_size)

            for review, pred in zip(batch, preds):
                review.sentiment = pred["label"]
                review.sentiment_score = pred["score"]

            db.commit()
            processed += len(batch)
            logger.info(f"  {processed}/{total} classified")

    finally:
        db.close()

    logger.info(f"Done. Classified {processed} reviews.")
    return processed


def evaluate_sample(n: int = 100) -> None:
    """
    Выводит n случайных отзывов с предсказанной тональностью для ручной проверки.
    """
    import random

    init_db()
    db = SessionLocal()
    try:
        reviews = db.query(Review).filter(Review.sentiment.isnot(None)).all()
        sample = random.sample(reviews, min(n, len(reviews)))
    finally:
        db.close()

    if not sample:
        print("No classified reviews in DB yet.")
        return

    correct = 0
    total_checked = 0

    print(f"\n{'='*70}")
    print(f"Manual evaluation on {len(sample)} samples")
    print("Enter: p=positive  n=negative  u=neutral  s=skip  q=quit")
    print("="*70)

    for rev in sample:
        print(f"\n[{rev.source}] predicted: {rev.sentiment} (score={rev.sentiment_score:.2f})")
        print(f"Text: {rev.text[:300]}")
        ans = input("Your label (p/n/u/s/q): ").strip().lower()

        if ans == "q":
            break
        if ans == "s":
            continue

        label_map_input = {"p": "positive", "n": "negative", "u": "neutral"}
        true_label = label_map_input.get(ans)
        if true_label:
            total_checked += 1
            if true_label == rev.sentiment:
                correct += 1

    if total_checked:
        acc = correct / total_checked * 100
        print(f"\nAccuracy on {total_checked} checked: {acc:.1f}% ({correct}/{total_checked})")
    else:
        print("\nNo samples were evaluated.")


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    ap = argparse.ArgumentParser(description="ruBERT sentiment classifier")
    sub = ap.add_subparsers(dest="cmd")

    run_p = sub.add_parser("run", help="Classify all unclassified reviews in DB")
    run_p.add_argument("--batch", type=int, default=32, help="Batch size (default: 32)")
    run_p.add_argument("--source", default=None, help="Filter by source (banki_ru / vk / telegram)")

    eval_p = sub.add_parser("eval", help="Manual evaluation on sample")
    eval_p.add_argument("--n", type=int, default=100, help="Sample size (default: 100)")

    args = ap.parse_args()

    if args.cmd == "run":
        classify_db_reviews(batch_size=args.batch, source_filter=args.source)
    elif args.cmd == "eval":
        evaluate_sample(n=args.n)
    else:
        ap.print_help()
