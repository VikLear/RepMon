import json
import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from database import DailyScore, Review, db_session

logger = logging.getLogger(__name__)

SOURCE_WEIGHTS: dict[str, float] = {
    "banki_ru":  1.5,
    "otzovik":   1.2,
    "telegram":  1.0,
    "vk":        0.8,
}
DEFAULT_WEIGHT = 1.0

SENTIMENT_WEIGHTS: dict[str, float] = {
    "positive": 1.0,
    "neutral":  0.5,
    "negative": 0.0,
}


def compute_score(reviews: list[Review]) -> float:
    """
    Score = weighted_sum / max_weighted_sum * 100
    Учитывает веса источника и тональности.
    """
    if not reviews:
        return 0.0

    weighted_sum = 0.0
    max_sum = 0.0

    for r in reviews:
        if r.sentiment not in SENTIMENT_WEIGHTS:
            continue
        w = SOURCE_WEIGHTS.get(r.source, DEFAULT_WEIGHT)
        weighted_sum += SENTIMENT_WEIGHTS[r.sentiment] * w
        max_sum += w

    return round(weighted_sum / max_sum * 100, 2) if max_sum > 0 else 0.0


def _date_range(date: datetime) -> tuple[datetime, datetime]:
    start = date.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start, end


def save_daily_snapshot(db: Session, date: Optional[datetime] = None) -> DailyScore:
    """Вычисляет и сохраняет дневной снимок скора (или обновляет существующий)."""
    date = (date or datetime.now(timezone.utc).replace(tzinfo=None)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    start, end = _date_range(date)

    reviews = (
        db.query(Review)
        .filter(Review.date >= start, Review.date < end, Review.sentiment.isnot(None))
        .all()
    )

    score = compute_score(reviews)
    pos = sum(1 for r in reviews if r.sentiment == "positive")
    neu = sum(1 for r in reviews if r.sentiment == "neutral")
    neg = sum(1 for r in reviews if r.sentiment == "negative")

    existing = db.query(DailyScore).filter(DailyScore.date == date).first()
    if existing:
        existing.score = score
        existing.total_reviews = len(reviews)
        existing.positive_count = pos
        existing.neutral_count = neu
        existing.negative_count = neg
        db.commit()
        return existing

    snapshot = DailyScore(
        date=date,
        score=score,
        total_reviews=len(reviews),
        positive_count=pos,
        neutral_count=neu,
        negative_count=neg,
    )
    db.add(snapshot)
    db.commit()
    logger.info(f"Snapshot {date.date()}: score={score}, total={len(reviews)} (pos={pos} neu={neu} neg={neg})")
    return snapshot


def backfill_history(days: int = 30) -> int:
    """Пересчитывает исторические снимки за последние N дней из имеющихся данных."""
    today = datetime.now(timezone.utc).replace(tzinfo=None, hour=0, minute=0, second=0, microsecond=0)
    saved = 0

    with db_session() as db:
        for i in range(days):
            date = today - timedelta(days=i)
            snapshot = save_daily_snapshot(db, date)
            if snapshot.total_reviews > 0:
                saved += 1

    logger.info(f"Backfill done: {saved}/{days} days had data.")
    return saved


def get_history(days: int = 30) -> list[DailyScore]:
    """Возвращает снимки за последние N дней, отсортированные по дате."""
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    with db_session() as db:
        return (
            db.query(DailyScore)
            .filter(DailyScore.date >= since)
            .order_by(DailyScore.date)
            .all()
        )


def current_score() -> float:
    """Скор за сегодня (по накопленным данным без привязки к дате отзыва)."""
    with db_session() as db:
        reviews = db.query(Review).filter(Review.sentiment.isnot(None)).all()
    return compute_score(reviews)


def topic_breakdown(days: int = 30, source: Optional[str] = None) -> dict[str, int]:
    """
    Подсчёт упоминаний по темам за последние N дней.
    Один отзыв может попасть в несколько тем (мультитопик).
    """
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    counts: Counter = Counter()

    with db_session() as db:
        query = db.query(Review.topics).filter(
            Review.date >= since,
            Review.topics.isnot(None),
        )
        if source:
            query = query.filter(Review.source == source)
        rows = query.all()

    for (topics_json,) in rows:
        for t in json.loads(topics_json):
            counts[t] += 1

    return dict(counts.most_common())
