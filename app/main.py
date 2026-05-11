from fastapi import FastAPI
import logging
from app.api.v1.routes import bot, health
from app.config import settings
import httpx
from contextlib import asynccontextmanager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Register Telegram webhook
    # In production, this should be the public URL of your FastAPI app
    webhook_url = settings.WEBHOOK_URL + "/api/v1/bot/webhook" # Should probably be an env var
    
    logger.info(f"`Setting Telegram webhook` to {webhook_url}")
    
    telegram_url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/setWebhook"
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(telegram_url, data={"url": webhook_url})
            response.raise_for_status()
            logger.info(f"Telegram webhook set successfully: {response.json()}")
        except Exception as e:
            logger.error(f"Failed to set Telegram webhook: {e}")
            
    yield
    # Shutdown: could unregister webhook if desired
    logger.info("Shutting down...")

app = FastAPI(
    title="Pliro Crypto Wallet Bot",
    lifespan=lifespan
)

# Include routers
app.include_router(bot.router, prefix="/api/v1/bot", tags=["bot"])
app.include_router(health.router, prefix="/api/v1", tags=["health"])

@app.get("/")
async def root():
    return {"message": "Pliro Crypto Wallet Bot API is running"}
