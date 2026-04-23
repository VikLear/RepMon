import argparse
import logging

import pipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def main() -> None:
    ap = argparse.ArgumentParser(description="Reputation monitor")

    ap.add_argument(
        "--stage",
        choices=["collect", "classify", "score", "all", "stats", "evaluate"],
        default="all",
        help="Pipeline stage to run (default: all)",
    )

    # collect
    ap.add_argument("--sources", nargs="+", default=None,
                    choices=["banki", "otzovik"],
                    help="Data sources (default: all)")
    ap.add_argument("--max", type=int, default=500, help="Max reviews per source")
    ap.add_argument("--bank", default="tcs", help="Banki.ru bank slug")
    ap.add_argument("--banki-delay", type=float, default=1.0)
    ap.add_argument("--otzovik-url",
                    default="https://otzovik.com/reviews/t-bank/?order=date_desc")
    ap.add_argument("--otzovik-delay", type=float, default=3.0)
    ap.add_argument("--otzovik-headless", action="store_true")
    ap.add_argument("--otzovik-debug", action="store_true")

    # classify
    ap.add_argument("--nlp-batch", type=int, default=32)
    ap.add_argument("--nlp-source", default=None,
                    help="Classify only reviews from this source")

    # score
    ap.add_argument("--score-days", type=int, default=30,
                    help="Days of history to backfill")

    # evaluate
    ap.add_argument("--eval-n", type=int, default=100,
                    help="Number of samples for manual evaluation")

    args = ap.parse_args()

    from database import init_db
    init_db()

    collect_kwargs = dict(
        banki_bank=args.bank,
        banki_delay=args.banki_delay,
        otzovik_url=args.otzovik_url,
        otzovik_delay=args.otzovik_delay,
        otzovik_headless=args.otzovik_headless,
        otzovik_debug=args.otzovik_debug,
    )

    if args.stage == "collect":
        pipeline.collect(sources=args.sources, max_reviews=args.max, **collect_kwargs)

    elif args.stage == "classify":
        pipeline.classify(batch_size=args.nlp_batch, source_filter=args.nlp_source)

    elif args.stage == "score":
        pipeline.score(days=args.score_days)

    elif args.stage == "stats":
        pipeline.stats()

    elif args.stage == "evaluate":
        pipeline.evaluate(n=args.eval_n)

    else:  # all
        result = pipeline.run_all(
            sources=args.sources,
            max_reviews=args.max,
            nlp_batch=args.nlp_batch,
            score_days=args.score_days,
            **collect_kwargs,
        )
        print(f"\nReputation score: {result['score']:.1f} / 100")


if __name__ == "__main__":
    main()
