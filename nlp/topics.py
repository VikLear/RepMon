import logging
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import Review, SessionLocal, init_db

logger = logging.getLogger(__name__)

# Ключевые слова для каждой темы (подстроки, case-insensitive)
TOPIC_KEYWORDS: dict[str, list[str]] = {
    "приложение": [
        "приложени", "апп", " app", "мобильн", "смартфон", "iphone", "android",
        "ios", "телефон", "скачал", "установил", "обновлен", "интерфейс",
        "авторизац", "пуш", "уведомлен", "вход в", "не открывает", "вылетает",
        "лагает", "тормоз", "кнопк", "экран", "виджет", "версия приложен",
    ],
    "кредиты": [
        "кредит", "займ", "заём", "ипотек", "рассрочк", "долг", "выплат",
        "процентн", "процент по", "ставк", "одобри", "отказ в", "заявк",
        "погашен", "задолженн", "рефинансир", "досрочн", "кредитн истори",
        "скоринг", "платеж по кредит",
    ],
    "поддержка": [
        "поддержк", "оператор", "звони", "позвони", "дозвони", "чат",
        "консультант", "менеджер", "сотрудник", "служба", "колл-центр",
        "колл центр", "кол-центр", "горяч лини", "техподдержк", "обратил",
        "жалоб", "претензи", "ответ не", "не отвеч", "не помог", "грубо",
        "хамит", "вежлив", "помоgli", "решил проблем", "не решил",
    ],
    "карты": [
        "карт", "дебетов", "visa", "виза", "mastercard", "мастеркард",
        " мир ", "пин-код", "пин код", "банкомат", "бесконтактн", "чип",
        "cashback", "кэшбек", "кэш бек", "перевыпуск", "заблокир карт",
        "карту заблок", "новая карт", "выпуск карт",
    ],
    "переводы": [
        "перевод", "перевест", "перевёл", "переслал", "отправил деньг",
        "получил деньг", "сбп", "система быстрых", "swift", "межбанк",
        "реквизит", "на счет", "на карту", "платёж", "платеж",
        "пополнени", "снятие", "вывод средств", "зачислен",
    ],
}

TOPICS = list(TOPIC_KEYWORDS.keys()) + ["общее"]


def _normalize(text: str) -> str:
    return " " + text.lower() + " "


def classify_text(text: str) -> str:
    norm = _normalize(text)
    scores: dict[str, int] = {}

    for topic, keywords in TOPIC_KEYWORDS.items():
        count = sum(1 for kw in keywords if kw in norm)
        if count > 0:
            scores[topic] = count

    if not scores:
        return "общее"

    return max(scores, key=lambda t: scores[t])


def classify_batch(texts: list[str]) -> list[str]:
    return [classify_text(t) for t in texts]


def classify_db_topics(batch_size: int = 500, source_filter: str | None = None) -> int:
    """Проставляет тему всем записям без topic в БД."""
    init_db()
    db = SessionLocal()
    processed = 0

    try:
        query = db.query(Review).filter(Review.topic.is_(None))
        if source_filter:
            query = query.filter(Review.source == source_filter)

        reviews = query.all()
        total = len(reviews)
        logger.info(f"Found {total} reviews without topic")

        for i in range(0, total, batch_size):
            batch = reviews[i : i + batch_size]
            for review in batch:
                review.topic = classify_text(review.text)
            db.commit()
            processed += len(batch)
            logger.info(f"  {processed}/{total} tagged")

    finally:
        db.close()

    logger.info(f"Done. Tagged {processed} reviews.")
    return processed


def topic_stats() -> dict[str, int]:
    """Статистика по темам из БД."""
    from sqlalchemy import func
    db = SessionLocal()
    try:
        rows = (
            db.query(Review.topic, func.count(Review.id))
            .filter(Review.topic.isnot(None))
            .group_by(Review.topic)
            .all()
        )
        return {topic: cnt for topic, cnt in rows}
    finally:
        db.close()


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    ap = argparse.ArgumentParser(description="Keyword-based topic classifier")
    sub = ap.add_subparsers(dest="cmd")

    run_p = sub.add_parser("run", help="Tag all untagged reviews in DB")
    run_p.add_argument("--source", default=None, help="Filter by source")

    sub.add_parser("stats", help="Print topic distribution")

    test_p = sub.add_parser("test", help="Classify a single text")
    test_p.add_argument("text", help="Text to classify")

    args = ap.parse_args()

    if args.cmd == "run":
        classify_db_topics(source_filter=args.source)
    elif args.cmd == "stats":
        stats = topic_stats()
        total = sum(stats.values())
        print(f"\nTopic distribution ({total} total):")
        for topic, cnt in sorted(stats.items(), key=lambda x: -x[1]):
            bar = "#" * (cnt * 40 // max(stats.values()))
            print(f"  {topic:12} {cnt:5}  ({cnt/total*100:.1f}%)  {bar}")
    elif args.cmd == "test":
        print(classify_text(args.text))
    else:
        ap.print_help()
