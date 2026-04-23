import hashlib
import logging
import re
import time
import sys
import os
from datetime import datetime, timezone

import requests
from sqlalchemy.orm import Session

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import Review, init_db, SessionLocal

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

API_URL = "https://www.banki.ru/services/responses/list/ajax/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "ru-RU,ru;q=0.9",
    "Referer": "https://www.banki.ru/services/responses/bank/tcs/",
    "X-Requested-With": "XMLHttpRequest",
}


def make_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_date(raw: str) -> datetime:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw.strip()[:len(fmt)], fmt)
        except (ValueError, TypeError):
            continue
    return datetime.now(timezone.utc).replace(tzinfo=None)


def fetch_page(bank: str, page: int) -> tuple[list[dict], bool]:
    params = {"page": page, "is_countable": "on", "bank": bank}
    resp = requests.get(API_URL, params=params, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    payload = resp.json()
    return payload.get("data", []), payload.get("hasMorePages", False)


def extract_review(raw: dict) -> dict | None:
    html_text = raw.get("text") or ""
    text = strip_html(html_text)
    if len(text) < 20:
        return None
    return {
        "text": text,
        "rating": float(raw.get("grade") or 0),
        "date": parse_date(raw.get("dateCreate") or ""),
        "source": "banki_ru",
    }


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


def collect(bank: str = "tcs", max_reviews: int = 200, page_delay: float = 1.0) -> int:
    init_db()
    db = SessionLocal()
    saved = 0
    page = 1

    logger.info(f"Starting: bank={bank}, max={max_reviews}")

    try:
        while saved < max_reviews:
            try:
                items, has_more = fetch_page(bank, page)
            except Exception as e:
                logger.error(f"Request failed on page {page}: {e}")
                break

            if not items:
                logger.info("No items returned — stopping.")
                break

            new_on_page = 0
            for raw in items:
                review = extract_review(raw)
                if review and save_review(db, review):
                    saved += 1
                    new_on_page += 1
                if saved >= max_reviews:
                    break

            logger.info(f"Page {page}: +{new_on_page} new, {saved} total")

            if not has_more:
                logger.info("No more pages.")
                break

            page += 1
            time.sleep(page_delay)

    finally:
        db.close()

    logger.info(f"Done. Saved {saved} reviews.")
    return saved


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Banki.ru collector via AJAX API")
    ap.add_argument("--bank", default="tcs",
                    help="Bank slug, e.g. tcs, sberbank, vtb, alfabank")
    ap.add_argument("--max", type=int, default=200,
                    help="Max reviews to collect (default: 200)")
    ap.add_argument("--delay", type=float, default=1.0,
                    help="Delay between pages in seconds (default: 1.0)")
    args = ap.parse_args()

    collect(bank=args.bank, max_reviews=args.max, page_delay=args.delay)
