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
| NLP | ruBERT (HuggingFace), PyTorch |
| Хранилище | SQLite + SQLAlchemy |
| API | FastAPI (запланирован) |
| Дашборд | Streamlit + Plotly (запланирован) |
| Алерты | python-telegram-bot, APScheduler (запланированы) |

## Запуск

```bash
# 1. Установить зависимости
pip install -r requirements.txt

# 2. Создать .env из шаблона и заполнить ключи
cp .env.example .env

# 3. Запустить полный пайплайн (сбор → NLP → скоринг)
python main.py

# Только сбор данных
python main.py --stage collect --sources banki otzovik --max 500

# Только NLP-классификация
python main.py --stage classify

# Только скоринг
python main.py --stage score

# Статистика по тональности и темам
python main.py --stage stats

# Интерактивная оценка NLP-предсказаний
python main.py --stage evaluate --eval-n 100
```

### Параметры CLI

| Параметр | По умолчанию | Описание |
|----------|-------------|----------|
| `--stage` | `all` | Этап: `collect`, `classify`, `score`, `all`, `stats`, `evaluate` |
| `--sources` | все | Источники: `banki`, `otzovik` |
| `--max` | `500` | Максимум отзывов на источник |
| `--bank` | `tcs` | Слаг банка на Банки.ру |
| `--nlp-batch` | `32` | Размер батча для NLP |
| `--score-days` | `30` | Глубина истории для скоринга (дней) |
| `--otzovik-headless` | `False` | Запуск Selenium в headless-режиме |

## Структура проекта

```
├── collector/
│   ├── base.py             # Базовый класс коллектора
│   ├── banki_parser.py     # Парсер Банки.ру
│   └── otzovik_parser.py   # Парсер Отзовика (Selenium)
├── nlp/
│   ├── sentiment.py        # ruBERT: классификация тональности
│   ├── topics.py           # Keyword-based классификатор тем
│   └── pipeline.py         # Оркестратор NLP
├── scoring/
│   ├── engine.py           # Формула Reputation Score
│   └── test_engine.py      # Unit-тесты (8/8)
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
