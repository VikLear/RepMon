import logging
import time
import random
import re
from datetime import datetime

from bs4 import BeautifulSoup
from sqlalchemy import func
from sqlalchemy.orm import Session

from collector.base import BaseCollector, save_review
from database import Review

logger = logging.getLogger(__name__)

BASE_URL = "https://otzovik.com"

MONTH_MAP = {
    "янв": 1, "фев": 2, "мар": 3, "апр": 4, "май": 5, "июн": 6,
    "июл": 7, "авг": 8, "сен": 9, "окт": 10, "ноя": 11, "дек": 12,
}

# Matches "28 янв 2026", "28 января 2026" etc.
_RU_DATE_RE = re.compile(
    r"\d{1,2}\s+(?:янв|фев|мар|апр|май|июн|июл|авг|сен|окт|ноя|дек)\w*\s+\d{4}",
    re.IGNORECASE,
)


def _clean_text(text: str) -> str:
    """Strip Otzovik author metadata header: 'Ник Репутация N Страна R DD Mon YYYY ...'"""
    if "Репутация" not in text[:150]:
        return text
    m = _RU_DATE_RE.search(text)
    if m:
        return text[m.end():].strip()
    # Date not found but Репутация present — strip up to the reputation block
    idx = text.index("Репутация")
    cut = text[idx:].split(None, 2)  # ['Репутация', 'N', 'остаток']
    return cut[2].strip() if len(cut) >= 3 else text


def _parse_ru_date(raw: str) -> datetime:
    raw = raw.strip()
    m = re.match(r"(\d{1,2})\s+([а-яё]+)\s+(\d{4})", raw, re.IGNORECASE)
    if m:
        day, mon_str, year = int(m.group(1)), m.group(2)[:3].lower(), int(m.group(3))
        return datetime(year, MONTH_MAP.get(mon_str, 1), day)
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(raw[:10], fmt)
        except ValueError:
            continue
    return datetime.utcnow()


def _build_driver(headless: bool = False):
    import undetected_chromedriver as uc
    options = uc.ChromeOptions()
    options.page_load_strategy = "eager"  # ждём только DOM, не все ресурсы
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--lang=ru-RU,ru")
    driver = uc.Chrome(options=options, version_main=147)
    driver.set_page_load_timeout(90)
    driver.set_script_timeout(30)
    driver.implicitly_wait(10)
    return driver


def _human_scroll(driver) -> None:
    total = random.randint(600, 1400)
    steps = random.randint(4, 8)
    for _ in range(steps):
        driver.execute_script(f"window.scrollBy(0, {total // steps})")
        time.sleep(random.uniform(0.2, 0.6))


def _wait_for_reviews(driver, timeout: int = 20) -> bool:
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.common.by import By
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR,
                 "[itemtype='http://schema.org/Review'], .review-list-item, [itemprop='review']")
            )
        )
        return True
    except Exception:
        return False


def _get_page_source(driver, url: str, retries: int = 3) -> str | None:
    for attempt in range(1, retries + 1):
        try:
            driver.get(url)
            time.sleep(random.uniform(3.0, 5.0))
            if "captcha" in driver.page_source.lower():
                logger.warning("Captcha detected — solve it manually (30s window)")
                time.sleep(30)
            if _wait_for_reviews(driver, timeout=30):
                _human_scroll(driver)
                time.sleep(random.uniform(1.5, 2.5))
                return driver.page_source
            logger.warning(f"Attempt {attempt}/{retries}: reviews not found on {url}")
        except Exception as e:
            logger.warning(f"Attempt {attempt}/{retries} failed on {url}: {e}")
            time.sleep(5 * attempt)
    logger.error(f"All {retries} attempts failed for {url}")
    return None


def _parse_reviews(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    items = soup.select("div[itemtype='http://schema.org/Review']") or soup.select("[itemprop='review']")
    if not items:
        logger.warning("No review items found — check selectors")
        return []

    results = []
    for item in items:
        body_el = item.select_one("[itemprop='reviewBody']")
        text = _clean_text(body_el.get_text(" ", strip=True) if body_el else item.get_text(" ", strip=True))
        if len(text) < 20:
            continue

        rating_el = item.select_one("meta[itemprop='ratingValue']")
        try:
            rating = float(rating_el["content"]) if rating_el else None
        except (ValueError, TypeError):
            rating = None

        date_el = item.select_one("meta[itemprop='datePublished']")
        if date_el:
            raw_date = date_el.get("content", "")
        else:
            date_el = item.select_one(".review-postdate, [class*='date'], time")
            raw_date = (date_el.get("datetime") or date_el.get_text(strip=True)) if date_el else ""
        date = _parse_ru_date(raw_date) if raw_date else datetime.utcnow()

        results.append({"text": text, "rating": rating, "date": date, "source": "otzovik"})
    return results


def _get_next_url(html: str, current_url: str) -> str | None:
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
        return f"{BASE_URL}/reviews/{m.group(1)}/2/{m.group(2) or ''}"

    return None


class OtzovikCollector(BaseCollector):
    source = "otzovik"
    def __init__(
        self,
        start_url: str = "https://otzovik.com/reviews/t-bank/?order=date_desc",
        page_delay: float = 3.0,
        headless: bool = False,
        debug: bool = False,
    ):
        self.start_url = start_url
        self.page_delay = page_delay
        self.headless = headless
        self.debug = debug

    def collect(self, db: Session, max_reviews: int = 500) -> int:
        driver = _build_driver(headless=self.headless)
        saved = 0
        cutoff = db.query(func.max(Review.date)).filter(Review.source == self.source).scalar()
        url = self.start_url
        debug = self.debug
        logger.info(f"Otzovik: max={max_reviews}, cutoff={cutoff}, url={url}")

        try:
            while saved < max_reviews and url:
                html = _get_page_source(driver, url)
                if html is None:
                    break

                if debug:
                    with open("debug_otzovik.html", "w", encoding="utf-8") as f:
                        f.write(html)
                    logger.info("Debug HTML saved to debug_otzovik.html")
                    debug = False

                reviews = _parse_reviews(html)
                if not reviews:
                    logger.warning(f"No reviews on {url} — stopping.")
                    break

                all_old = True
                new_on_page = 0
                for r in reviews:
                    if cutoff is None or r["date"] > cutoff:
                        all_old = False
                        if save_review(db, r):
                            saved += 1
                            new_on_page += 1
                    if saved >= max_reviews:
                        break

                logger.info(f"Page {url}: +{new_on_page} new, {saved} total")

                if all_old and cutoff:
                    logger.info(f"All reviews on page predate DB cutoff ({cutoff.date()}) — stopping")
                    break

                url = _get_next_url(html, url)
                time.sleep(self.page_delay * random.uniform(0.7, 1.4))

        finally:
            try:
                driver.quit()
            except Exception:
                pass

        logger.info(f"Otzovik done: {saved} saved.")
        return saved
