# Репутационный монитор банка

MVP-система для мониторинга репутации банка на основе анализа отзывов из открытых источников.

## Источники данных
- [Банки.ру](https://www.banki.ru) — отзывы клиентов
- Telegram — публичные каналы и чаты
- VK — посты и комментарии по ключевым словам

## Стек
| Слой | Технология |
|------|-----------|
| Сбор данных | BeautifulSoup, Selenium, Telethon, VK API |
| NLP | ruBERT (HuggingFace), PyTorch |
| Хранилище | SQLite + SQLAlchemy |
| API | FastAPI |
| Дашборд | Streamlit + Plotly |
| Алерты | python-telegram-bot, APScheduler |

## Запуск

```bash
# 1. Установить зависимости
pip install -r requirements.txt

# 2. Создать .env из шаблона и заполнить ключи
cp .env.example .env

# 3. Инициализировать базу данных
python -c "from database import init_db; init_db()"

# 4. Запустить API
uvicorn api.main:app --reload

# 5. Запустить дашборд
streamlit run dashboard/app.py
```

## Структура проекта

```
├── collector/      # Парсеры источников данных
├── nlp/            # Модели тональности и тематики
├── scoring/        # Формула Reputation Score
├── api/            # FastAPI эндпоинты
├── dashboard/      # Streamlit дашборд
├── data/           # SQLite база данных (gitignored)
├── database.py     # Модели и подключение к БД
└── requirements.txt
```
