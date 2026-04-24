# Репутационный монитор банка

MVP-система для мониторинга репутации банка на основе анализа отзывов из открытых источников.

## Источники данных

| Источник | Статус |
|----------|--------|
| [Банки.ру](https://www.banki.ru) | реализован |
| [Отзовик](https://otzovik.com) | реализован |
| Telegram | запланирован |
| VK | запланирован |

## Стек

| Слой | Технология |
|------|-----------|
| Сбор данных | BeautifulSoup, Selenium, undetected-chromedriver |
| Тональность | ruBERT (`blanchefort/rubert-base-cased-sentiment`) |
| Топики | SBERT (`ai-forever/sbert_large_nlu_ru`) — zero-shot cosine similarity |
| Хранилище | SQLite + SQLAlchemy |
| API | FastAPI (запланирован) |
| Дашборд | Streamlit + Plotly (запланирован) |
| Алерты | python-telegram-bot, APScheduler (запланированы) |

## Установка

```bash
# 1. Установить зависимости
pip install -r requirements.txt

# 2. Для GPU (рекомендуется) — переустановить torch с CUDA
pip uninstall torch -y
pip install torch --index-url https://download.pytorch.org/whl/cu121

# 3. Создать .env из шаблона
cp .env.example .env
```

## Основные команды

```bash
# Полный цикл: сбор → классификация → скоринг
python main.py

# Только сбор данных (banki + otzovik, 500 отзывов каждый)
python main.py --stage collect

# Только классификация (sentiment + topic)
python main.py --stage classify

# Только пересчитать reputation score
python main.py --stage score

# Статистика по тональности и топикам
python main.py --stage stats

# Ручная оценка качества предсказаний
python main.py --stage evaluate
```

## Флаги

```bash
# Сбор только с одного источника
python main.py --stage collect --sources banki
python main.py --stage collect --sources otzovik

# Классифицировать только один источник
python main.py --stage classify --nlp-source banki_ru

# Скоринг за последние N дней
python main.py --stage score --score-days 7
```

### Все параметры CLI

| Параметр | По умолчанию | Описание |
|----------|-------------|----------|
| `--stage` | `all` | Этап: `collect`, `classify`, `score`, `all`, `stats`, `evaluate` |
| `--sources` | все | Источники: `banki`, `otzovik` |
| `--max` | `500` | Максимум отзывов на источник |
| `--bank` | `tcs` | Слаг банка на Банки.ру |
| `--nlp-batch` | `32` | Размер батча для NLP |
| `--nlp-source` | все | Классифицировать только этот источник |
| `--score-days` | `30` | Глубина истории для скоринга (дней) |
| `--otzovik-headless` | `False` | Запуск Selenium в headless-режиме |

## Тесты

```bash
# Тесты скоринга (без модели, быстро)
python -m scoring.test_engine

# Тесты топик-классификатора — только unit (без модели)
python -m nlp.test_topics --unit

# Тесты топик-классификатора с реальной моделью
python -m nlp.test_topics
```

## Миграции

```bash
# Почистить мусор в текстах Otzovik + сбросить NLP-метки у всех записей
python -m scripts.clean_otzovik_texts
```

Запускается один раз при переезде на новую версию модели или после изменения логики парсера.

## Структура проекта

```
├── collector/
│   ├── base.py             # Базовый класс коллектора
│   ├── banki_parser.py     # Парсер Банки.ру (API)
│   └── otzovik_parser.py   # Парсер Отзовика (Selenium)
├── nlp/
│   ├── sentiment.py        # ruBERT: классификация тональности
│   ├── topics.py           # SBERT: zero-shot классификация тем
│   ├── pipeline.py         # Оркестратор NLP
│   └── test_topics.py      # Unit + integration тесты топиков
├── scoring/
│   ├── engine.py           # Формула Reputation Score
│   └── test_engine.py      # Unit-тесты (8/8)
├── scripts/
│   └── clean_otzovik_texts.py  # Миграция: чистка БД
├── api/                    # FastAPI (в разработке)
├── dashboard/              # Streamlit дашборд (в разработке)
├── data/                   # SQLite база данных (gitignored)
├── config.py               # Настройки из .env
├── database.py             # Модели SQLAlchemy и подключение
├── pipeline.py             # Оркестратор этапов
├── main.py                 # CLI точка входа
└── requirements.txt
```

## Темы отзывов

`приложение` / `кредиты` / `поддержка` / `карты` / `переводы` / `общее`

Классификация через cosine similarity между embedding текста и anchor-фразами каждой темы. Если уверенность ниже порога — тема `общее`.

## Переменные окружения

```env
# База данных
DATABASE_URL=sqlite:///data/reviews.db

# Telegram Bot (алерты — запланированы)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# Telegram (Telethon, источник — запланирован)
TELEGRAM_API_ID=
TELEGRAM_API_HASH=
TELEGRAM_PHONE=

# VK API (источник — запланирован)
VK_ACCESS_TOKEN=
VK_API_VERSION=5.131

# Скоринг
SCORE_ALERT_THRESHOLD=30
```
