from datetime import datetime
from scoring.engine import compute_score, SOURCE_WEIGHTS
from database import Review


def _review(sentiment: str, source: str = "banki_ru") -> Review:
    r = Review()
    r.sentiment = sentiment
    r.source = source
    r.text = "test"
    r.text_hash = f"{sentiment}_{source}"
    r.date = datetime.utcnow()
    return r


def test_all_positive():
    reviews = [_review("positive")] * 10
    assert compute_score(reviews) == 100.0


def test_all_negative():
    reviews = [_review("negative")] * 10
    assert compute_score(reviews) == 0.0


def test_all_neutral():
    reviews = [_review("neutral")] * 10
    assert compute_score(reviews) == 50.0


def test_empty():
    assert compute_score([]) == 0.0


def test_mixed_equal():
    reviews = [_review("positive"), _review("negative")]
    assert compute_score(reviews) == 50.0


def test_source_weights():
    # banki_ru (1.5) positive vs vk (0.8) negative
    # weighted_sum = 1.5*1.0 + 0.8*0.0 = 1.5
    # max_sum = 1.5 + 0.8 = 2.3
    # score = 1.5 / 2.3 * 100 ≈ 65.22
    reviews = [_review("positive", "banki_ru"), _review("negative", "vk")]
    score = compute_score(reviews)
    assert abs(score - 65.22) < 0.1


def test_unknown_source_uses_default_weight():
    reviews = [_review("positive", "unknown_source")]
    assert compute_score(reviews) == 100.0


def test_no_valid_sentiment_skipped():
    r = _review("positive")
    r.sentiment = None
    assert compute_score([r]) == 0.0


if __name__ == "__main__":
    tests = [
        test_all_positive,
        test_all_negative,
        test_all_neutral,
        test_empty,
        test_mixed_equal,
        test_source_weights,
        test_unknown_source_uses_default_weight,
        test_no_valid_sentiment_skipped,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {t.__name__}: {e}")
    print(f"\n{passed}/{len(tests)} passed")
