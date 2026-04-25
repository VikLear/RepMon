import hashlib
import logging
from abc import ABC, abstractmethod

from sqlalchemy.orm import Session

from database import Review

logger = logging.getLogger(__name__)

MAX_TEXT_LEN = 1500


def _make_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def save_review(db: Session, data: dict) -> bool:
    """Save a review to DB. Returns True if newly inserted, False if duplicate."""
    if len(data["text"]) > MAX_TEXT_LEN:
        logger.debug("Skipping review >%d chars (len=%d)", MAX_TEXT_LEN, len(data["text"]))
        return False
    text_hash = _make_hash(data["text"])
    if db.query(Review).filter(Review.text_hash == text_hash).first():
        return False
    db.add(Review(
        text=data["text"],
        text_hash=text_hash,
        source=data["source"],
        rating=data["rating"],
        date=data["date"],
    ))
    db.commit()
    return True


class BaseCollector(ABC):
    source: str

    @abstractmethod
    def collect(self, db: Session, max_reviews: int) -> int:
        """Collect reviews, save to DB, return count of newly saved records."""
        ...
