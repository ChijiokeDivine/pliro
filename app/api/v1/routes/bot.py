from fastapi import APIRouter, Request
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
)
from app.bot.handlers import (
    handle_message,
    start_command,
    menu_command,
    button_callback,
    swap_command,
    swap_input_token,
    swap_output_token,
    swap_amount,
    swap_cancel,
    INPUT_TOKEN,
    OUTPUT_TOKEN,
    AMOUNT,
    CONFIRM_SWAP,
)
import logging
from app.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)

_telegram_app = None


def get_telegram_app():
    global _telegram_app
    if _telegram_app is None:
        _telegram_app = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()

        # ── Commands ──────────────────────────────────────────────────────
        _telegram_app.add_handler(CommandHandler("start", start_command))
        _telegram_app.add_handler(CommandHandler("menu", menu_command))

        # ── Swap conversation ─────────────────────────────────────────────
        swap_conv = ConversationHandler(
            entry_points=[CommandHandler("swap", swap_command)],
            states={
                INPUT_TOKEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, swap_input_token)],
                OUTPUT_TOKEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, swap_output_token)],
                AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, swap_amount)],
                CONFIRM_SWAP: [CallbackQueryHandler(button_callback, pattern="^(confirm_swap|cancel_swap)$")],
            },
            fallbacks=[CommandHandler("cancel", swap_cancel)],
        )
        _telegram_app.add_handler(swap_conv)

        # ── Inline button callbacks ───────────────────────────────────────
        _telegram_app.add_handler(CallbackQueryHandler(button_callback))

        # ── General text messages ─────────────────────────────────────────
        _telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    return _telegram_app


@router.post("/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    app = get_telegram_app()
    await app.initialize()
    update = Update.de_json(data, app.bot)
    await app.process_update(update)
    return {"status": "ok"}