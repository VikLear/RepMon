import hashlib
import logging
import time
import random
import sys
import os
import re
from datetime import datetime

from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import Review, init_db, SessionLocal

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

BASE_URL = "https://otzovik.com"

MONTH_MAP = {
    "янв": 1, "фев": 2, "мар": 3, "апр": 4, "май": 5, "июн": 6,
    "июл": 7, "авг": 8, "сен": 9, "окт": 10, "ноя": 11, "дек": 12,
}


def make_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_ru_date(raw: str) -> datetime:
    raw = raw.strip()
    m = re.match(r"(\d{1,2})\s+([а-яё]+)\s+(\d{4})", raw, re.IGNORECASE)
    if m:
        day, mon_str, year = int(m.group(1)), m.group(2)[:3].lower(), int(m.group(3))
        month = MONTH_MAP.get(mon_str, 1)
        return datetime(year, month, day)
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(raw[:10], fmt)
        except ValueError:
            continue
    return datetime.utcnow()


def build_driver(headless: bool = False):
    import undetected_chromedriver as uc

    options = uc.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--lang=ru-RU,ru")

    driver = uc.Chrome(options=options, version_main=147)
    driver.set_page_load_timeout(30)
    return driver


def human_scroll(driver):
    total = random.randint(600, 1400)
    steps = random.randint(4, 8)
    for _ in range(steps):
        driver.execute_script(f"window.scrollBy(0, {total // steps})")
        time.sleep(random.uniform(0.2, 0.6))


def wait_for_reviews(driver, timeout: int = 20) -> bool:
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.common.by import By
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "[itemtype='http://schema.org/Review'], .review-list-item, [itemprop='review']"))
        )
        return True
    except Exception:
        return False


def get_page_source(driver, url: str) -> str | None:
    try:
        driver.get(url)
        time.sleep(random.uniform(2.0, 3.0))

        if "captcha" in driver.page_source.lower():
            logger.warning("Captcha detected! Waiting 30s — solve it manually in the browser window.")
            time.sleep(30)

        found = wait_for_reviews(driver)
        if not found:
            logger.warning(f"Review elements not found after wait on {url}")

        human_scroll(driver)
        time.sleep(random.uniform(1.0, 2.0))
        return driver.page_source
    except Exception as e:
        logger.error(f"Selenium failed to load {url}: {e}")
        return None


def parse_reviews(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    reviews = []

    items = soup.select("div[itemtype='http://schema.org/Review']")
    if not items:
        items = soup.select("[itemprop='review']")
    if not items:
        logger.warning("No review items found — check selectors or run with --debug")
        return reviews

    for item in items:
        body_el = item.select_one("[itemprop='reviewBody']")
        text = body_el.get_text(" ", strip=True) if body_el else ""
        if not text:
            text = item.get_text(" ", strip=True)
        if len(text) < 20:
            continue

        rating_el = item.select_one("meta[itemprop='ratingValue']")
        if rating_el:
            try:
                rating = float(rating_el.get("content", 0))
            except (ValueError, TypeError):
                rating = None
        else:
            grade_el = item.select_one(".product-grade, .rating, [class*='grade']")
            try:
                rating = float(grade_el.get_text(strip=True)) if grade_el else None
            except (ValueError, TypeError):
                rating = None

        date_el = item.select_one("meta[itemprop='datePublished']")
        if date_el:
            raw_date = date_el.get("content", "")
        else:
            date_el = item.select_one(".review-postdate, [class*='date'], time")
            raw_date = (date_el.get("datetime") or date_el.get_text(strip=True)) if date_el else ""
        date = parse_ru_date(raw_date) if raw_date else datetime.utcnow()

        reviews.append({"text": text, "rating": rating, "date": date, "source": "otzovik"})

    return reviews


def get_next_page_url(html: str, current_url: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    next_el = soup.select_one("a.next, a[rel='next'], .pager a.next")
    if next_el and next_el.get("href"):
        href = next_el["href"]
        return href if href.startswith("http") else BASE_URL + href

    m = re.search(r"/reviews/([^/]+)/(\d+)/", current_url)
    if m:
        slug, page = m.group(1), int(m.group(2))
        qs = re.search(r"\?.*", current_url)
        return f"{BASE_URL}/reviews/{slug}/{page + 1}/{qs.group(0) if qs else ''}"

    m = re.search(r"/reviews/([^/?]+)/?(\?.*)?$", current_url)
    if m:
        slug = m.group(1)
        qs = m.group(2) or ""
        return f"{BASE_URL}/reviews/{slug}/2/{qs}"

    return None


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
    start_url: str = "https://otzovik.com/reviews/t-bank/?order=date_desc",
    max_reviews: int = 500,
    page_delay: float = 3.0,
    headless: bool = False,
    debug: bool = False,
) -> int:
    init_db()
    db = SessionLocal()
    driver = build_driver(headless=headless)
    saved = 0
    url = start_url

    logger.info(f"Starting otzovik collect (Selenium): max={max_reviews}, url={url}")

    try:
        while saved < max_reviews and url:
            html = get_page_source(driver, url)
            if html is None:
                break

            if debug:
                debug_path = os.path.join(os.path.dirname(__file__), "..", "debug_otzovik.html")
                with open(debug_path, "w", encoding="utf-8") as f:
                    f.write(html)
                logger.info(f"Debug HTML saved to {debug_path}")
                debug = False

            reviews = parse_reviews(html)
            if not reviews:
                logger.warning(f"No reviews on {url} — stopping.")
                break

            new_on_page = 0
            for r in reviews:
                if save_review(db, r):
                    saved += 1
                    new_on_page += 1
                if saved >= max_reviews:
                    break

            logger.info(f"Page {url}: +{new_on_page} new, {saved} total")

            url = get_next_page_url(html, url)
            sleep_time = page_delay * random.uniform(0.7, 1.4)
            logger.info(f"Sleeping {sleep_time:.1f}s")
            time.sleep(sleep_time)

    finally:
        db.close()
        try:
            driver.quit()
        except Exception:
            pass

    logger.info(f"Done. Saved {saved} otzovik reviews.")
    return saved


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Otzovik.com review collector (Selenium)")
    ap.add_argument("--url", default="https://otzovik.com/reviews/t-bank/?order=date_desc")
    ap.add_argument("--max", type=int, default=500)
    ap.add_argument("--delay", type=float, default=3.0)
    ap.add_argument("--headless", action="store_true", help="Run browser in headless mode (not recommended)")
    ap.add_argument("--debug", action="store_true", help="Save first page HTML")
    args = ap.parse_args()

    collect(
        start_url=args.url,
        max_reviews=args.max,
        page_delay=args.delay,
        headless=args.headless,
        debug=args.debug,
    )
