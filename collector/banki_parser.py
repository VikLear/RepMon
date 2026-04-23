import logging
import re
import time
from datetime import datetime, timezone

import requests
from sqlalchemy.orm import Session

from collector.base import BaseCollector, save_review

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
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw.strip()[:len(fmt)], fmt)
        except (ValueError, TypeError):
            continue
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
        logger.info(f"Banki.ru: bank={self.bank}, max={max_reviews}")

        while saved < max_reviews:
            try:
                items, has_more = _fetch_page(self.bank, page)
            except Exception as e:
                logger.error(f"Request failed on page {page}: {e}")
                break

            if not items:
                break

            new_on_page = sum(save_review(db, r) for raw in items if (r := _extract(raw)))
            saved += new_on_page
            logger.info(f"Page {page}: +{new_on_page} new, {saved} total")

            if not has_more or saved >= max_reviews:
                break

            page += 1
            time.sleep(self.page_delay)

        logger.info(f"Banki.ru done: {saved} saved.")
        return saved
