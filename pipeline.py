"""
Top-level orchestrator.

Flow: collect → nlp → score
Each stage is independent and can be run separately.
"""
import logging

from database import init_db, db_session

logger = logging.getLogger(__name__)


def collect(
    sources: list[str] | None = None,
    max_reviews: int = 500,
    banki_bank: str = "tcs",
    banki_delay: float = 1.0,
    otzovik_url: str = "https://otzovik.com/reviews/t-bank/?order=date_desc",
    otzovik_delay: float = 3.0,
    otzovik_headless: bool = False,
    otzovik_debug: bool = False,
) -> dict[str, int]:
    """Run data collection for the specified sources. Returns {source: saved_count}."""
    from collector.banki_parser import BankiCollector
    from collector.otzovik_parser import OtzovikCollector

    active = set(sources or ["banki", "otzovik"])
    results: dict[str, int] = {}

    collectors = []
    if "banki" in active:
        collectors.append(BankiCollector(bank=banki_bank, page_delay=banki_delay))
    if "otzovik" in active:
        collectors.append(OtzovikCollector(
            start_url=otzovik_url,
            page_delay=otzovik_delay,
            headless=otzovik_headless,
            debug=otzovik_debug,
        ))

    with db_session() as db:
        for c in collectors:
            logger.info(f"=== Collecting: {c.source} ===")
            saved = c.collect(db, max_reviews=max_reviews)
            results[c.source] = saved

    return results


def classify(batch_size: int = 32, source_filter: str | None = None) -> int:
    """Run NLP pipeline (sentiment + topic) on unprocessed reviews."""
    from nlp.pipeline import run as nlp_run
    logger.info("=== NLP pipeline (sentiment + topic) ===")
    return nlp_run(batch_size=batch_size, source_filter=source_filter)


def score(days: int = 30) -> float:
    """Backfill daily score history and return current overall score."""
    from scoring.engine import backfill_history, current_score
    logger.info("=== Scoring ===")
    backfill_history(days=days)
    result = current_score()
    logger.info(f"Current reputation score: {result:.1f}")
    return result


def stats() -> dict:
    """Print and return sentiment/topic distribution."""
    from nlp.pipeline import stats as nlp_stats
    result = nlp_stats()
    print("\nSentiment distribution:")
    for label, count in result.get("sentiment", {}).items():
        print(f"  {label}: {count}")
    print("\nTopic distribution:")
    for topic, count in result.get("topics", {}).items():
        print(f"  {topic}: {count}")
    return result


def evaluate(n: int = 100) -> None:
    """Interactive manual evaluation of NLP predictions."""
    from nlp.pipeline import evaluate as nlp_evaluate
    nlp_evaluate(n=n)


def run_all(
    sources: list[str] | None = None,
    max_reviews: int = 500,
    nlp_batch: int = 32,
    score_days: int = 30,
    **collect_kwargs,
) -> dict:
    """Full pipeline: collect → classify → score."""
    collect_results = collect(sources=sources, max_reviews=max_reviews, **collect_kwargs)
    classified = classify(batch_size=nlp_batch)
    reputation_score = score(days=score_days)

    return {
        "collected": collect_results,
        "classified": classified,
        "score": reputation_score,
    }
