import os
from contextlib import contextmanager
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text, Index, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from datetime import datetime

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data/reviews.db")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False, "timeout": 30})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


class Review(Base):
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, index=True)
    text = Column(Text, nullable=False)
    text_hash = Column(String(64), unique=True, index=True)
    source = Column(String(50), nullable=False, index=True)  # banki_ru / telegram / vk
    rating = Column(Float, nullable=True)
    date = Column(DateTime, nullable=False, index=True)
    sentiment = Column(String(20), nullable=True, index=True)  # positive / neutral / negative
    sentiment_score = Column(Float, nullable=True)
    topic = Column(String(50), nullable=True, index=True)   # primary topic (первая из списка)
    topics = Column(Text, nullable=True)                     # JSON-список тем, напр. '["карты","переводы"]'
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_reviews_date_source", "date", "source"),
    )


class DailyScore(Base):
    __tablename__ = "daily_scores"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(DateTime, nullable=False, unique=True)
    score = Column(Float, nullable=False)
    total_reviews = Column(Integer, nullable=False)
    positive_count = Column(Integer, nullable=False)
    neutral_count = Column(Integer, nullable=False)
    negative_count = Column(Integer, nullable=False)


_MIGRATIONS = [
    "CREATE INDEX IF NOT EXISTS ix_reviews_date        ON reviews (date)",
    "CREATE INDEX IF NOT EXISTS ix_reviews_source      ON reviews (source)",
    "CREATE INDEX IF NOT EXISTS ix_reviews_sentiment   ON reviews (sentiment)",
    "CREATE INDEX IF NOT EXISTS ix_reviews_topic       ON reviews (topic)",
    "CREATE INDEX IF NOT EXISTS ix_reviews_date_source ON reviews (date, source)",
    "ALTER TABLE reviews ADD COLUMN topics TEXT",
]


def init_db():
    os.makedirs("data", exist_ok=True)
    Base.metadata.create_all(bind=engine)
    with engine.connect() as conn:
        for stmt in _MIGRATIONS:
            try:
                conn.execute(text(stmt))
            except Exception:
                pass  # index/column already exists
        conn.commit()


@contextmanager
def db_session():
    """Context manager for regular (non-FastAPI) use."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db():
    """FastAPI dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
