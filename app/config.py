from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    TELEGRAM_BOT_TOKEN: str
    GROQ_API_KEY: str
    NEXT_PUBLIC_PRIVY_APP_ID: str
    PRIVY_APP_SECRET: str
    ZERION_API_KEY: str
    DATABASE_URL: str
    
    # Optional: ALEMBIC_DATABASE_URL for migrations (psycopg2)
    # If not provided, we might need to derive it from DATABASE_URL
    ALEMBIC_DATABASE_URL: str | None = None
    WEBHOOK_URL: str = Field(..., description="Public URL for Telegram webhook, e.g. https://myapp.com")
    REDIS_URL: str = Field(..., description="Redis connection URL, e.g. rediss://user:pass@host:port")
    COINGECKO_DEMO_API_KEY: str = Field(default="", description="Optional CoinGecko API key for price queries")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
