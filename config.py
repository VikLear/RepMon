from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "sqlite:///data/reviews.db"

    vk_access_token: str = ""
    vk_api_version: str = "5.131"

    telegram_api_id: int = 0
    telegram_api_hash: str = ""
    telegram_phone: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    score_alert_threshold: int = 30


settings = Settings()
