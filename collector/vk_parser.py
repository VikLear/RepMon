import hashlib
import logging
import time
import random
import sys
import os
from datetime import datetime

import requests
from sqlalchemy.orm import Session
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import Review, init_db, SessionLocal

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

VK_API_URL = "https://api.vk.com/method/"
VK_TOKEN = os.getenv("VK_ACCESS_TOKEN")
VK_VERSION = os.getenv("VK_API_VERSION", "5.131")

# Ключевые слова для поиска отзывов
DEFAULT_QUERIES = [
    "Т-Банк отзыв",
    "Тинькофф отзыв",
    "Tinkoff банк проблема",
    "Т-Банк не работает",
    "Тинькофф плохой",
    "Тинькофф хороший",
]


def make_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def vk_request(method: str, params: dict, retries: int = 3) -> dict | None:
    params.update({"access_token": VK_TOKEN, "v": VK_VERSION})
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(VK_API_URL + method, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            if "error" in data:
                code = data["error"].get("error_code")
                msg = data["error"].get("error_msg", "")

                # Rate limit — ждём и повторяем
                if code == 6:
                    wait = 2 * attempt
                    logger.warning(f"VK rate limit, waiting {wait}s")
                    time.sleep(wait)
                    continue

                # Токен протух или нет доступа
                if code in (5, 15, 17):
                    logger.error(f"VK auth error: {msg}")
                    return None

                logger.error(f"VK API error {code}: {msg}")
                return None

            return data.get("response")

        except Exception as e:
            logger.error(f"Request failed attempt {attempt}/{retries}: {e}")
            if attempt < retries:
                time.sleep(3 * attempt)

    return None


def search_posts(query: str, count: int = 200, start_from: str = "") -> tuple[list[dict], str]:
    params = {"q": query, "count": count, "extended": 0}
    if start_from:
        params["start_from"] = start_from

    response = vk_request("newsfeed.search", params)
    if not response:
        return [], ""

    items = response.get("items", [])
    next_from = response.get("next_from", "")
    return items, next_from


def extract_review(post: dict) -> dict | None:
    text = (post.get("text") or "").strip()
    if len(text) < 20:
        return None

    date_ts = post.get("date", 0)
    date = datetime.utcfromtimestamp(date_ts) if date_ts else datetime.utcnow()

    # Лайки как косвенный показатель "рейтинга" — нормализуем в 1-5
    likes = post.get("likes", {}).get("count", 0)
    rating = None  # у постов ВК нет явного рейтинга

    return {"text": text, "rating": rating, "date": date, "source": "vk"}


def save_review(db: Session, data: dict) -> bool:
    text_hash = make_hash(data["text"])
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


def collect(
    queries: list[str] | None = None,
    max_reviews: int = 500,
    posts_per_query: int = 200,
    request_delay: float = 0.5,
) -> int:
    if not VK_TOKEN:
        logger.error("VK_ACCESS_TOKEN not set in .env")
        return 0

    init_db()
    db = SessionLocal()
    saved = 0

    if queries is None:
        queries = DEFAULT_QUERIES

    logger.info(f"Starting VK collect: {len(queries)} queries, max={max_reviews}")

    try:
        for query in queries:
            if saved >= max_reviews:
                break

            logger.info(f"Query: '{query}'")
            start_from = ""
            query_saved = 0

            while saved < max_reviews:
                posts, next_from = search_posts(query, count=200, start_from=start_from)

                if not posts:
                    logger.info(f"No more posts for '{query}'")
                    break

                for post in posts:
                    review = extract_review(post)
                    if review and save_review(db, review):
                        saved += 1
                        query_saved += 1
                    if saved >= max_reviews:
                        break

                logger.info(f"  '{query}': +{query_saved} new so far, total={saved}")

                if not next_from or query_saved >= posts_per_query:
                    break

                start_from = next_from
                time.sleep(request_delay + random.uniform(0, 0.3))

    finally:
        db.close()

    logger.info(f"Done. Saved {saved} VK posts.")
    return saved


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="VK posts collector via newsfeed.search")
    ap.add_argument("--max", type=int, default=500, help="Max posts to collect (default: 500)")
    ap.add_argument("--delay", type=float, default=0.5, help="Delay between requests (default: 0.5)")
    ap.add_argument(
        "--queries",
        nargs="+",
        default=None,
        help="Search queries (default: built-in list)",
    )
    args = ap.parse_args()

    collect(queries=args.queries, max_reviews=args.max, request_delay=args.delay)
