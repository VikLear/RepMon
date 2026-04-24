import logging
import random
from typing import Optional

from database import Review, db_session
from nlp.sentiment import predict_batch
from nlp.topics import classify_batch

logger = logging.getLogger(__name__)


def run(batch_size: int = 32, source_filter: Optional[str] = None) -> int:
    """Single DB pass: assigns sentiment + topic to all unprocessed reviews."""
    with db_session() as db:
        query = db.query(Review).filter(
            Review.sentiment.is_(None) | Review.topic.is_(None)
        )
        if source_filter:
            query = query.filter(Review.source == source_filter)

        reviews = query.all()
        total = len(reviews)
        logger.info(f"Found {total} reviews to process (sentiment + topic)")

        for i in range(0, total, batch_size):
            batch = reviews[i : i + batch_size]
            texts = [r.text for r in batch]

            preds = predict_batch(texts, batch_size=batch_size)
            topics = classify_batch(texts, batch_size=batch_size)

            for review, pred, topic in zip(batch, preds, topics):
                review.sentiment = pred["label"]
                review.sentiment_score = pred["score"]
                review.topic = topic

            db.commit()
            logger.info(f"  {i + len(batch)}/{total} processed")

    logger.info(f"Done. Processed {total} reviews.")
    return total


def stats() -> dict:
    """Returns sentiment and topic distribution from DB."""
    from sqlalchemy import func

    with db_session() as db:
        sentiment_rows = (
            db.query(Review.sentiment, func.count(Review.id))
            .filter(Review.sentiment.isnot(None))
            .group_by(Review.sentiment)
            .all()
        )
        topic_rows = (
            db.query(Review.topic, func.count(Review.id))
            .filter(Review.topic.isnot(None))
            .group_by(Review.topic)
            .all()
        )

    return {
        "sentiment": {s: c for s, c in sentiment_rows},
        "topics":    {t: c for t, c in topic_rows},
    }


def evaluate(n: int = 100) -> None:
    """Interactive manual evaluation of sentiment predictions."""
    with db_session() as db:
        reviews = db.query(Review).filter(Review.sentiment.isnot(None)).all()
        sample = random.sample(reviews, min(n, len(reviews)))

    if not sample:
        print("No classified reviews in DB yet.")
        return

    correct = total_checked = 0
    label_map = {"p": "positive", "n": "negative", "u": "neutral"}

    print(f"\n{'='*70}")
    print(f"Manual evaluation — {len(sample)} samples")
    print("p=positive  n=negative  u=neutral  s=skip  q=quit")
    print("=" * 70)

    for rev in sample:
        print(f"\n[{rev.source}] predicted: {rev.sentiment} ({rev.sentiment_score:.2f})")
        print(f"Text: {rev.text[:300]}")
        ans = input("Your label: ").strip().lower()
        if ans == "q":
            break
        if ans == "s":
            continue
        true_label = label_map.get(ans)
        if true_label:
            total_checked += 1
            if true_label == rev.sentiment:
                correct += 1

    if total_checked:
        print(f"\nAccuracy: {correct/total_checked*100:.1f}% ({correct}/{total_checked})")
    else:
        print("\nNo samples checked.")
