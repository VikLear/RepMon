import os
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text
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
    source = Column(String(50), nullable=False)  # banki_ru / telegram / vk
    rating = Column(Float, nullable=True)
    date = Column(DateTime, nullable=False)
    sentiment = Column(String(20), nullable=True)  # positive / neutral / negative
    sentiment_score = Column(Float, nullable=True)
    topic = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class DailyScore(Base):
    __tablename__ = "daily_scores"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(DateTime, nullable=False, unique=True)
    score = Column(Float, nullable=False)
    total_reviews = Column(Integer, nullable=False)
    positive_count = Column(Integer, nullable=False)
    neutral_count = Column(Integer, nullable=False)
    negative_count = Column(Integer, nullable=False)


def init_db():
    os.makedirs("data", exist_ok=True)
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
