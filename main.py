import argparse
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def run_banki(max_reviews: int, bank: str, delay: float):
    from collector.banki_parser import collect
    logger.info("=== Banki.ru collector ===")
    saved = collect(bank=bank, max_reviews=max_reviews, page_delay=delay)
    logger.info(f"Banki.ru: saved {saved} reviews")


def run_otzovik(max_reviews: int, url: str, delay: float, debug: bool):
    from collector.otzovik_parser import collect
    logger.info("=== Otzovik.com collector ===")
    saved = collect(start_url=url, max_reviews=max_reviews, page_delay=delay, debug=debug)
    logger.info(f"Otzovik: saved {saved} reviews")


def run_vk(max_reviews: int, delay: float, queries: list[str] | None):
    from collector.vk_parser import collect
    logger.info("=== VK collector ===")
    saved = collect(queries=queries, max_reviews=max_reviews, request_delay=delay)
    logger.info(f"VK: saved {saved} posts")


def run_nlp(batch_size: int, source_filter: str | None):
    from nlp.sentiment import classify_db_reviews
    logger.info("=== NLP sentiment classifier ===")
    classified = classify_db_reviews(batch_size=batch_size, source_filter=source_filter)
    logger.info(f"NLP: classified {classified} reviews")


def run_topics(source_filter: str | None):
    from nlp.topics import classify_db_topics
    logger.info("=== Topic classifier ===")
    tagged = classify_db_topics(source_filter=source_filter)
    logger.info(f"Topics: tagged {tagged} reviews")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Reputation monitor — data collector & NLP")

    ap.add_argument(
        "--source",
        choices=["banki", "otzovik", "vk", "nlp", "topics", "all"],
        default="all",
        help="Which step to run (default: all)",
    )
    ap.add_argument("--max", type=int, default=500, help="Max reviews per source (default: 500)")
    ap.add_argument("--delay", type=float, default=2.0, help="Delay between requests (default: 2.0)")
    ap.add_argument("--bank", default="tcs", help="Bank slug for Banki.ru (default: tcs)")
    ap.add_argument(
        "--otzovik-url",
        default="https://otzovik.com/reviews/t-bank/?order=date_desc",
        help="Start URL for Otzovik",
    )
    ap.add_argument("--vk-queries", nargs="+", default=None, help="Search queries for VK")
    ap.add_argument("--debug", action="store_true", help="Save debug HTML (Otzovik only)")
    ap.add_argument("--nlp-batch", type=int, default=32, help="NLP batch size (default: 32)")
    ap.add_argument("--nlp-source", default=None, help="Filter NLP by source (banki_ru / vk / telegram)")

    args = ap.parse_args()

    if args.source in ("banki", "all"):
        run_banki(max_reviews=args.max, bank=args.bank, delay=args.delay)

    if args.source in ("otzovik", "all"):
        run_otzovik(max_reviews=args.max, url=args.otzovik_url, delay=args.delay, debug=args.debug)

    if args.source in ("vk", "all"):
        run_vk(max_reviews=args.max, delay=args.delay, queries=args.vk_queries)

    if args.source in ("nlp", "all"):
        run_nlp(batch_size=args.nlp_batch, source_filter=args.nlp_source)

    if args.source in ("topics", "all"):
        run_topics(source_filter=args.nlp_source)
