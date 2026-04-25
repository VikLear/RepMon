import logging
import re
import time
from datetime import datetime, timezone

import requests
from sqlalchemy import func
from sqlalchemy.orm import Session

from collector.base import BaseCollector, save_review
from database import Review

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


def _strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()


def _parse_date(raw: str) -> datetime:
    if not raw:
        logger.warning("_parse_date: empty dateCreate — falling back to now()")
        return datetime.now(timezone.utc).replace(tzinfo=None)
    s = raw.strip()
    # fromisoformat handles "2026-04-24", "2026-04-24T15:23:50", "2026-04-24 15:23:50"
    # and timezone-aware variants; strip trailing Z first
    try:
        dt = datetime.fromisoformat(s.rstrip("Z"))
        return dt.replace(tzinfo=None)
    except ValueError:
        pass
    for fmt in ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%d.%m.%Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    try:
        return datetime.utcfromtimestamp(int(s))
    except (ValueError, TypeError):
        pass
    logger.warning("_parse_date: unrecognised format %r — falling back to now()", s)
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _fetch_page(bank: str, page: int) -> tuple[list[dict], bool]:
    params = {"page": page, "is_countable": "on", "bank": bank}
    resp = requests.get(API_URL, params=params, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    payload = resp.json()
    return payload.get("data", []), payload.get("hasMorePages", False)


def _extract(raw: dict) -> dict | None:
    text = _strip_html(raw.get("text") or "")
    if len(text) < 20:
        return None
    return {
        "text": text,
        "rating": float(raw.get("grade") or 0),
        "date": _parse_date(raw.get("dateCreate") or ""),
        "source": "banki_ru",
    }


class BankiCollector(BaseCollector):
    source = "banki_ru"

    def __init__(self, bank: str = "tcs", page_delay: float = 1.0):
        self.bank = bank
        self.page_delay = page_delay

    def collect(self, db: Session, max_reviews: int = 500) -> int:
        saved = 0
        page = 1
        cutoff = db.query(func.max(Review.date)).filter(Review.source == self.source).scalar()
        logger.info(f"Banki.ru: bank={self.bank}, max={max_reviews}, cutoff={cutoff}")

        while saved < max_reviews:
            try:
                items, has_more = _fetch_page(self.bank, page)
            except Exception as e:
                logger.error(f"Request failed on page {page}: {e}")
                break

            if not items:
                break

            all_old = True
            new_on_page = 0
            for raw in items:
                r = _extract(raw)
                if not r:
                    continue
                if cutoff is None or r["date"] > cutoff:
                    all_old = False
                    if save_review(db, r):
                        saved += 1
                        new_on_page += 1

            logger.info(f"Page {page}: +{new_on_page} new, {saved} total")

            if all_old and cutoff:
                logger.info(f"All reviews on page {page} predate DB cutoff ({cutoff.date()}) — stopping")
                break

            if not has_more or saved >= max_reviews:
                break

            page += 1
            time.sleep(self.page_delay)

        logger.info(f"Banki.ru done: {saved} saved.")
        return saved
