"""
handlers.py — Telegram bot handlers with rich HTML UI.
Uses InlineKeyboardMarkup for navigation and HTML parse_mode for formatting.
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode, ChatAction

from app.bot.agent import run_agent
from app.wallet.zerion import ZerionClient
from app.wallet.privy import PrivyClient
from app.db.database import async_session_factory
from app.db import crud
from app.bot.ui_formatters import (
    format_welcome,
    format_portfolio,
    format_token_positions,
    format_wallet_addresses,
    format_receive_card,
    format_transaction_history,
    format_send_preview,
    format_swap_quote,
    format_gas_prices,
    format_tx_success,
    format_error,
    format_status,
    format_swap_step_input,
    format_swap_step_output,
    format_swap_step_amount,
    main_menu_keyboard,
    back_to_menu_keyboard,
    confirm_send_keyboard,
    confirm_swap_keyboard,
    chain_select_keyboard,
    quick_actions_keyboard,
    back_to_menu_quick_keyboard,
    confirm_keyboard,
)
from app.wallet.gas import GasService

import asyncio
import logging
from langchain_core.messages import HumanMessage, AIMessage

logger = logging.getLogger(__name__)

# ─── Swap conversation states ───────────────────────────────────────────────
INPUT_TOKEN, OUTPUT_TOKEN, AMOUNT, CONFIRM_SWAP = range(4)

zerion_client = ZerionClient()
privy_client = PrivyClient()
gas_service = GasService(zerion_client)

# In-memory chat + session storage
chat_histories: dict = {}
send_sessions: dict = {}     # user_id → pending send details

import re

SEND_PATTERN = re.compile(
    r"send\s+([\d.]+)\s+(\w+)(?:\s+on\s+(\w+))?\s+to\s+(0x[a-fA-F0-9]{40})",
    re.IGNORECASE
)

# ─── Safe send helper ───────────────────────────────────────────────────────

async def safe_send(update_or_query, text: str, keyboard=None, edit: bool = False):
    """Sends or edits a message safely with HTML parse mode and fallback."""
    kwargs = {
        "text": text,
        "parse_mode": ParseMode.HTML,
        "disable_web_page_preview": True,
    }
    if keyboard:
        kwargs["reply_markup"] = keyboard

    try:
        if edit and hasattr(update_or_query, "edit_message_text"):
            return await update_or_query.edit_message_text(**kwargs)
        elif hasattr(update_or_query, "message") and update_or_query.message:
            return await update_or_query.message.reply_text(**kwargs)
        elif hasattr(update_or_query, "reply_text"):
            return await update_or_query.reply_text(**kwargs)
    except Exception as e:
        # Strip HTML and retry plain text on failure
        logger.warning(f"HTML send failed ({e}), retrying plain text")
        plain = text.replace("<b>", "").replace("</b>", "").replace(
            "<i>", "").replace("</i>", "").replace(
            "<code>", "").replace("</code>", "").replace(
            "<a href>", "").replace("</a>", "")
        try:
            plain_kwargs = {"text": plain}
            if keyboard:
                plain_kwargs["reply_markup"] = keyboard
            if edit and hasattr(update_or_query, "edit_message_text"):
                return await update_or_query.edit_message_text(**plain_kwargs)
            elif hasattr(update_or_query, "message") and update_or_query.message:
                return await update_or_query.message.reply_text(**plain_kwargs)
        except Exception as e2:
            logger.error(f"Plain text fallback also failed: {e2}")


# ─── /start command ─────────────────────────────────────────────────────────

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action=ChatAction.TYPING
    )

    # Silently create wallet on first message
    user_id = str(user.id)
    try:
        async with async_session_factory() as session:
            db_user = await crud.get_or_create_user(session, int(user_id), user.username)
            await session.commit()
    except Exception as e:
        logger.error(f"Failed to create user on start: {e}")

    text = format_welcome(user.first_name or "there")
    await safe_send(update, text, keyboard=quick_actions_keyboard())


# ─── /menu command ──────────────────────────────────────────────────────────

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🏠 <b>Main Menu</b>\n"
        
        "What would you like to do?"
    )
    await safe_send(update, text, keyboard=quick_actions_keyboard())


# ─── Command handlers for quick actions ──────────────────────────────────────

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /balance command."""
    user_id = str(update.effective_user.id)
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action=ChatAction.TYPING
    )
    await safe_send(update, format_status("Calculating portfolio value…"), keyboard=quick_actions_keyboard())
    try:
        async with async_session_factory() as session:
            user = await crud.get_or_create_user(session, int(user_id))
            wallet = await crud.get_user_wallet(session, user.id)

        if not wallet:
            await safe_send(update, format_error("No wallet found. Send any message to set one up."),
                             keyboard=quick_actions_keyboard())
            return

        portfolio = await zerion_client.get_portfolio(wallet.evm_address)
        total = portfolio.get("total_value") or 0
        change_abs = portfolio.get("change_1d_abs") or 0
        change_perc = portfolio.get("change_1d_perc") or 0

        # Get chain breakdown from full portfolio response
        chain_breakdown = portfolio.get("chain_breakdown", {})

        text = format_portfolio(total, change_abs, change_perc, chain_breakdown or None)
        await safe_send(update, text, keyboard=quick_actions_keyboard())

    except Exception as e:
        logger.error(f"Balance command error: {e}", exc_info=True)
        await safe_send(update, format_error(str(e)), keyboard=quick_actions_keyboard())


async def addresses_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /addresses command."""
    user_id = str(update.effective_user.id)
    try:
        async with async_session_factory() as session:
            user = await crud.get_or_create_user(session, int(user_id))
            wallet = await crud.get_user_wallet(session, user.id)

        if not wallet:
            await safe_send(update, format_error("No wallet found."),
                             keyboard=quick_actions_keyboard())
            return

        text = format_wallet_addresses(wallet.evm_address, wallet.solana_address)
        await safe_send(update, text, keyboard=quick_actions_keyboard())

    except Exception as e:
        logger.error(f"Addresses command error: {e}", exc_info=True)
        await safe_send(update, format_error(str(e)), keyboard=quick_actions_keyboard())


async def get_tokens_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /get_tokens command."""
    user_id = str(update.effective_user.id)
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action=ChatAction.TYPING
    )
    await safe_send(update, format_status("Fetching token balances…"), keyboard=quick_actions_keyboard())
    try:
        async with async_session_factory() as session:
            user = await crud.get_or_create_user(session, int(user_id))
            wallet = await crud.get_user_wallet(session, user.id)

        if not wallet:
            await safe_send(update, format_error("No wallet found."),
                             keyboard=quick_actions_keyboard())
            return

        positions = await zerion_client.get_positions(wallet.evm_address)
        text = format_token_positions(positions)
        await safe_send(update, text, keyboard=quick_actions_keyboard())

    except Exception as e:
        logger.error(f"Get tokens command error: {e}", exc_info=True)
        await safe_send(update, format_error(str(e)), keyboard=quick_actions_keyboard())


async def transactions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /transactions command."""
    user_id = str(update.effective_user.id)
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action=ChatAction.TYPING
    )
    await safe_send(update, format_status("Retrieving transaction history…"), keyboard=quick_actions_keyboard())
    try:
        async with async_session_factory() as session:
            user = await crud.get_or_create_user(session, int(user_id))
            wallet = await crud.get_user_wallet(session, user.id)

        if not wallet:
            await safe_send(update, format_error("No wallet found."),
                             keyboard=quick_actions_keyboard())
            return

        txs = await zerion_client.get_transactions(wallet.evm_address, limit=10)
        text = format_transaction_history(txs)
        await safe_send(update, text, keyboard=quick_actions_keyboard())

    except Exception as e:
        logger.error(f"Transactions command error: {e}", exc_info=True)
        await safe_send(update, format_error(str(e)), keyboard=quick_actions_keyboard())


async def send_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /send command - prompts for send details."""
    text = (
        "📤 <b>Send Crypto</b>\n"
        
        "Just tell me what to send:\n\n"
        "<i>Example:\n"
        "  Send 0.01 ETH to 0xABC...123\n"
        "  Send 5 USDC on Base to 0xABC...123</i>"
    )
    await safe_send(update, text, keyboard=quick_actions_keyboard())


# ─── Inline button callbacks ────────────────────────────────────────────────

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = str(update.effective_user.id)
    data = query.data

    # ── Home ──────────────────────────────────────────────────────────────
    if data == "menu_home":
        text = (
            "🏠 <b>Main Menu</b>\n"
            
            "What would you like to do?"
        )
        await safe_send(query, text, keyboard=main_menu_keyboard(), edit=True)

    # ── Portfolio ─────────────────────────────────────────────────────────
    elif data == "menu_portfolio":
        await safe_send(query, format_status("Calculating portfolio value…"), edit=True)
        try:
            async with async_session_factory() as session:
                user = await crud.get_or_create_user(session, int(user_id))
                wallet = await crud.get_user_wallet(session, user.id)

            if not wallet:
                await safe_send(query, format_error("No wallet found. Send any message to set one up."),
                                 keyboard=back_to_menu_keyboard(), edit=True)
                return

            portfolio = await zerion_client.get_portfolio(wallet.evm_address)
            total = portfolio.get("total_value") or 0
            change_abs = portfolio.get("change_1d_abs") or 0
            change_perc = portfolio.get("change_1d_perc") or 0

            # Get chain breakdown from full portfolio response
            chain_breakdown = portfolio.get("chain_breakdown", {})

            text = format_portfolio(total, change_abs, change_perc, chain_breakdown or None)
            await safe_send(query, text, keyboard=back_to_menu_keyboard(), edit=True)

        except Exception as e:
            logger.error(f"Portfolio callback error: {e}", exc_info=True)
            await safe_send(query, format_error(str(e)), keyboard=back_to_menu_keyboard(), edit=True)

    # ── Tokens ────────────────────────────────────────────────────────────
    elif data == "menu_tokens":
        await safe_send(query, format_status("Fetching token balances…"), edit=True)
        try:
            async with async_session_factory() as session:
                user = await crud.get_or_create_user(session, int(user_id))
                wallet = await crud.get_user_wallet(session, user.id)

            if not wallet:
                await safe_send(query, format_error("No wallet found."),
                                 keyboard=back_to_menu_keyboard(), edit=True)
                return

            positions = await zerion_client.get_positions(wallet.evm_address)
            text = format_token_positions(positions)
            await safe_send(query, text, keyboard=back_to_menu_keyboard(), edit=True)

        except Exception as e:
            logger.error(f"Tokens callback error: {e}", exc_info=True)
            await safe_send(query, format_error(str(e)), keyboard=back_to_menu_keyboard(), edit=True)

    # ── Addresses ─────────────────────────────────────────────────────────
    elif data == "menu_addresses":
        try:
            async with async_session_factory() as session:
                user = await crud.get_or_create_user(session, int(user_id))
                wallet = await crud.get_user_wallet(session, user.id)

            if not wallet:
                await safe_send(query, format_error("No wallet found."),
                                 keyboard=back_to_menu_keyboard(), edit=True)
                return

            text = format_wallet_addresses(wallet.evm_address, wallet.solana_address)
            await safe_send(query, text, keyboard=back_to_menu_keyboard(), edit=True)

        except Exception as e:
            logger.error(f"Addresses callback error: {e}", exc_info=True)
            await safe_send(query, format_error(str(e)), keyboard=back_to_menu_keyboard(), edit=True)

    # ── History ───────────────────────────────────────────────────────────
    elif data == "menu_history":
        await safe_send(query, format_status("Retrieving transaction history…"), edit=True)
        try:
            async with async_session_factory() as session:
                user = await crud.get_or_create_user(session, int(user_id))
                wallet = await crud.get_user_wallet(session, user.id)

            if not wallet:
                await safe_send(query, format_error("No wallet found."),
                                 keyboard=back_to_menu_keyboard(), edit=True)
                return

            txs = await zerion_client.get_transactions(wallet.evm_address, limit=10)
            text = format_transaction_history(txs)
            await safe_send(query, text, keyboard=back_to_menu_keyboard(), edit=True)

        except Exception as e:
            logger.error(f"History callback error: {e}", exc_info=True)
            await safe_send(query, format_error(str(e)), keyboard=back_to_menu_keyboard(), edit=True)

    # ── Receive ───────────────────────────────────────────────────────────
    elif data == "menu_receive":
        text = (
            "📥 <b>Receive Funds</b>\n"
            
            "Select the chain you want to receive on:"
        )
        await safe_send(query, text, keyboard=chain_select_keyboard(), edit=True)

    elif data.startswith("chain_"):
        chain = data.replace("chain_", "")
        try:
            async with async_session_factory() as session:
                user = await crud.get_or_create_user(session, int(user_id))
                wallet = await crud.get_user_wallet(session, user.id)

            if not wallet:
                await safe_send(query, format_error("No wallet found."),
                                 keyboard=back_to_menu_keyboard(), edit=True)
                return

            text = format_receive_card(wallet.evm_address, wallet.solana_address, chain)
            await safe_send(query, text, keyboard=back_to_menu_keyboard(), edit=True)

        except Exception as e:
            logger.error(f"Receive chain callback error: {e}", exc_info=True)
            await safe_send(query, format_error(str(e)), keyboard=back_to_menu_keyboard(), edit=True)

    # ── Send (prompt via chat) ─────────────────────────────────────────────
    elif data == "menu_send":
        text = (
            "📤 <b>Send Crypto</b>\n"
            
            "Just tell me what to send in the chat:\n\n"
            "<i>Example:\n"
            "  Send 0.01 ETH to 0xABC...123\n"
            "  Send 5 USDC on Base to 0xABC...123</i>"
        )
        await safe_send(query, text, keyboard=back_to_menu_keyboard(), edit=True)

    # ── Swap (prompt via chat) ─────────────────────────────────────────────
    elif data == "menu_swap":
        text = (
            "💱 <b>Swap Tokens</b>\n"
            
            "Use the /swap command to exchange tokens,\n"
            "or just tell me what to swap:\n\n"
            "<i>Example:\n"
            "  Swap 0.1 ETH to USDC</i>"
        )
        await safe_send(query, text, keyboard=back_to_menu_keyboard(), edit=True)

    # ── Gas ───────────────────────────────────────────────────────────────
    elif data == "menu_gas":
        await safe_send(query, format_status("Fetching gas prices…"), edit=True)
        try:
            gas_info = await gas_service.get_gas_info("ethereum")
            text = format_gas_prices(gas_info, "ethereum")
            await safe_send(query, text, keyboard=back_to_menu_keyboard(), edit=True)
        except Exception as e:
            logger.error(f"Gas callback error: {e}", exc_info=True)
            await safe_send(query, format_error(str(e)), keyboard=back_to_menu_keyboard(), edit=True)

    # ── Confirm Send ──────────────────────────────────────────────────────
    elif data == "confirm_send":
        session_data = send_sessions.get(user_id)
        if not session_data:
            await safe_send(query, format_error("Session expired. Please try again."),
                            keyboard=back_to_menu_keyboard(), edit=True)
            return

        await safe_send(query, format_status("Signing and broadcasting transaction…", "⏳"), edit=True)
        try:
            async with async_session_factory() as session:
                user   = await crud.get_or_create_user(session, int(user_id))
                wallet = await crud.get_user_wallet(session, user.id)

            chain      = session_data["chain"]
            amount     = session_data["amount"]
            to_address = session_data["to_address"]
            token      = session_data.get("token", "ETH")

            wei     = int(float(amount) * 10 ** 18)
            tx_hash = await privy_client.send_evm_transaction(
                wallet_id=wallet.privy_evm_wallet_id,
                to_address=to_address,
                value_hex=hex(wei),
                chain=chain,
            )

            send_sessions.pop(user_id, None)
            text = format_tx_success(tx_hash, chain, amount, token, to_address)
            await safe_send(query, text, keyboard=back_to_menu_keyboard(), edit=True)

        except ValueError as e:
            # Handle clean errors raised from privy.py
            if "insufficient_funds" in str(e):
                await safe_send(
                    query,
                    (
                        "⚠️ <b>Insufficient Funds</b>\n\n"
                        f"Your wallet doesn't have enough ETH to cover\n"
                        f"the amount + network fees.\n\n"
                        f"<b>Tried to send:</b> {session_data.get('amount')} {session_data.get('token', 'ETH')}\n\n"
                        f"Deposit funds to your wallet and try again."
                    ),
                    keyboard=back_to_menu_keyboard(),
                    edit=True,
                )
            else:
                await safe_send(query, format_error(str(e)), keyboard=back_to_menu_keyboard(), edit=True)

        except Exception as e:
            logger.error(f"Confirm send error: {e}", exc_info=True)
            await safe_send(query, format_error("Transaction failed. Please try again."),
                            keyboard=back_to_menu_keyboard(), edit=True)

    elif data == "cancel_send":
        send_sessions.pop(user_id, None)
        await safe_send(query, "❌ <b>Send cancelled.</b>", keyboard=back_to_menu_keyboard(), edit=True)

    # ── Confirm Swap ──────────────────────────────────────────────────────
    elif data == "confirm_swap":
        best_offer = context.user_data.get("best_offer")
        if not best_offer:
            await safe_send(query, format_error("Offer expired. Please start over with /swap."),
                             keyboard=back_to_menu_keyboard(), edit=True)
            return

        await safe_send(query, format_status("Signing and broadcasting swap…", "⏳"), edit=True)
        try:
            tx_data = best_offer["transaction"]
            chain_id_int = int(tx_data["chain_id"], 16)

            async with async_session_factory() as session:
                user = await crud.get_or_create_user(session, int(user_id))
                wallet = await crud.get_user_wallet(session, user.id)

            tx_hash = await privy_client.send_evm_transaction(
                wallet_id=wallet.privy_evm_wallet_id,
                to_address=tx_data["to"],
                value_hex=tx_data["value"],
                chain_id=chain_id_int,
                data_hex=tx_data.get("data"),
                gas_hex=tx_data.get("gas"),
            )

            text = (
                "✅ <b>Swap Sent!</b>\n"
                
                f"<b>TX Hash:</b>\n<code>{tx_hash}</code>\n\n"
                "<i>Check your balance in a few moments.</i>"
            )
            await safe_send(query, text, keyboard=back_to_menu_keyboard(), edit=True)

        except Exception as e:
            logger.error(f"Confirm swap error: {e}", exc_info=True)
            await safe_send(query, format_error(str(e)), keyboard=back_to_menu_keyboard(), edit=True)

    elif data == "cancel_swap":
        await safe_send(query, "❌ <b>Swap cancelled.</b>", keyboard=back_to_menu_keyboard(), edit=True)


# ─── General chat message handler ───────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = update.message.text
    
    # ── Quick action buttons ───────────────────────────────────────────────
    quick_actions_map = {
        "💼 Balance": balance_command,
        "🪙 Tokens": get_tokens_command,
        "📬 Addresses": addresses_command,
        "📜 History": transactions_command,
        "📤 Send": send_command,
        "📥 Receive": lambda u, c: button_callback_helper(u, c, "menu_receive"),
        "💱 Swap": swap_command,
        "⛽ Gas": lambda u, c: button_callback_helper(u, c, "menu_gas"),
        "🏠 Main Menu": menu_command,
    }
    
    if text in quick_actions_map:
        await quick_actions_map[text](update, context)
        return
    
    # Check for yes/cancel confirmations
    if text.upper() in ("YES", "✅ YES"):
        user_id = str(update.effective_user.id)
        session_data = send_sessions.get(user_id)
        if session_data:
            # Handle send confirmation
            await safe_send(update, format_status("Signing and broadcasting transaction…", "⏳"), keyboard=quick_actions_keyboard())
            try:
                async with async_session_factory() as session:
                    user   = await crud.get_or_create_user(session, int(user_id))
                    wallet = await crud.get_user_wallet(session, user.id)

                chain      = session_data["chain"]
                amount     = session_data["amount"]
                to_address = session_data["to_address"]
                token      = session_data.get("token", "ETH")

                wei     = int(float(amount) * 10 ** 18)
                tx_hash = await privy_client.send_evm_transaction(
                    wallet_id=wallet.privy_evm_wallet_id,
                    to_address=to_address,
                    value_hex=hex(wei),
                    chain=chain,
                )

                send_sessions.pop(user_id, None)
                text = format_tx_success(tx_hash, chain, amount, token, to_address)
                await safe_send(update, text, keyboard=quick_actions_keyboard())
            except Exception as e:
                logger.error(f"Confirm send error: {e}", exc_info=True)
                await safe_send(update, format_error(str(e)), keyboard=quick_actions_keyboard())
            return
    
    if text.upper() in ("CANCEL", "❌ CANCEL"):
        user_id = str(update.effective_user.id)
        send_sessions.pop(user_id, None)
        await safe_send(update, "❌ <b>Cancelled.</b>", keyboard=quick_actions_keyboard())
        return

    match = SEND_PATTERN.search(text)
    if match:
        amount, token, chain, to_address = match.groups()
        chain = chain or "ethereum"
        await _handle_send_preview(update, context, amount, token, chain, to_address)
        return

        
    if not update.message or not update.message.text:
        return

    user = update.effective_user
    user_id = str(user.id)
    text = update.message.text
    chat_id = update.effective_chat.id

    logger.info(f"Received message from {user_id}: {text}")

    if user_id not in chat_histories:
        chat_histories[user_id] = []

    status_msg_ctx = {"message": None}

    async def update_status(new_status: str):
        try:
            styled = format_status(new_status)
            if status_msg_ctx["message"] is None:
                status_msg_ctx["message"] = await update.message.reply_text(
                    styled, parse_mode=ParseMode.HTML, reply_markup=quick_actions_keyboard()
                )
            else:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=status_msg_ctx["message"].message_id,
                    text=styled,
                    parse_mode=ParseMode.HTML,
                    reply_markup=quick_actions_keyboard(),
                )
            await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        except Exception as e:
            logger.warning(f"Failed to update status: {e}")

    try:
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

        response = await run_agent(
            text, user_id, chat_histories[user_id], update_status_func=update_status
        )

        chat_histories[user_id].append(HumanMessage(content=text))
        chat_histories[user_id].append(AIMessage(content=response))
        if len(chat_histories[user_id]) > 10:
            chat_histories[user_id] = chat_histories[user_id][-10:]

        # Check if agent response contains send confirmation to show inline button
        response_lower = response.lower()
        keyboard = quick_actions_keyboard()
        if any(kw in response_lower for kw in ["reply yes to confirm", "confirm or cancel", "send preview"]):
            keyboard = confirm_keyboard()
        elif "main menu" in response_lower or response.startswith("✅"):
            keyboard = quick_actions_keyboard()

        if status_msg_ctx["message"]:
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=status_msg_ctx["message"].message_id,
                    text=response,
                    parse_mode=ParseMode.HTML,
                    reply_markup=keyboard,
                    disable_web_page_preview=True,
                )
            except Exception:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=status_msg_ctx["message"].message_id,
                    text=response,
                    reply_markup=keyboard,
                )
        else:
            try:
                await update.message.reply_text(
                    response,
                    parse_mode=ParseMode.HTML,
                    reply_markup=keyboard,
                    disable_web_page_preview=True,
                )
            except Exception:
                await update.message.reply_text(response, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Error handling message: {e}", exc_info=True)
        error_text = format_error("Something went wrong. Please try again.")
        if status_msg_ctx["message"]:
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=status_msg_ctx["message"].message_id,
                    text=error_text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=quick_actions_keyboard(),
                )
            except Exception:
                pass
        else:
            await update.message.reply_text(
                error_text,
                parse_mode=ParseMode.HTML,
                reply_markup=quick_actions_keyboard(),
            )


# ─── Helper for button callbacks via message text ─────────────────────────────

async def button_callback_helper(update: Update, context: ContextTypes.DEFAULT_TYPE, button_data: str):
    """Simulates button callback behavior for quick action buttons."""
    user_id = str(update.effective_user.id)
    
    if button_data == "menu_receive":
        text = (
            "📥 <b>Receive Funds</b>\n"
            
            "Select the chain you want to receive on:"
        )
        await safe_send(update, text, keyboard=chain_select_keyboard())
    
    elif button_data == "menu_gas":
        await safe_send(update, format_status("Fetching gas prices…"), keyboard=quick_actions_keyboard())
        try:
            gas_info = await gas_service.get_gas_info("ethereum")
            text = format_gas_prices(gas_info, "ethereum")
            await safe_send(update, text, keyboard=quick_actions_keyboard())
        except Exception as e:
            logger.error(f"Gas command error: {e}", exc_info=True)
            await safe_send(update, format_error(str(e)), keyboard=quick_actions_keyboard())


# ─── /swap conversation ──────────────────────────────────────────────────────

async def swap_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await safe_send(update, format_swap_step_input())
    return INPUT_TOKEN


async def swap_input_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["input_token"] = update.message.text.strip()
    await safe_send(update, format_swap_step_output(context.user_data["input_token"]))
    return OUTPUT_TOKEN


async def swap_output_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["output_token"] = update.message.text.strip()
    await safe_send(
        update,
        format_swap_step_amount(
            context.user_data["input_token"], context.user_data["output_token"]
        ),
    )
    return AMOUNT


async def swap_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    amount = update.message.text.strip()
    context.user_data["amount"] = amount
    user_id = str(update.effective_user.id)
    chat_id = update.effective_chat.id

    status_msg = await update.message.reply_text(
        format_status("Finding best route…"), parse_mode=ParseMode.HTML
    )
    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    await asyncio.sleep(1.2)

    try:
        async with async_session_factory() as session:
            user = await crud.get_or_create_user(session, int(user_id))
            wallet = await crud.get_user_wallet(session, user.id)

        if not wallet:
            await status_msg.edit_text(
                format_error("No wallet found. Send any message first."),
                parse_mode=ParseMode.HTML,
            )
            return ConversationHandler.END

        offers_task = zerion_client.get_swap_offers(
            wallet_address=wallet.evm_address,
            input_token=context.user_data["input_token"].lower(),
            output_token=context.user_data["output_token"].lower(),
            amount=amount,
        )
        gas_task = gas_service.estimate_fee_usd(chain_id="ethereum", action="swap")
        offers, gas_estimates = await asyncio.gather(offers_task, gas_task)

        if not offers:
            await status_msg.edit_text(
                format_error("No swap route found. Try different tokens or amount."),
                parse_mode=ParseMode.HTML,
            )
            return ConversationHandler.END

        best_offer = offers[0]
        best_offer["gas_usd"] = gas_estimates.get("standard", 0.0)
        context.user_data["best_offer"] = best_offer

        quote_text = format_swap_quote(
            best_offer,
            context.user_data["input_token"],
            context.user_data["output_token"],
            amount,
        )

        await status_msg.delete()
        await update.message.reply_text(
            quote_text,
            parse_mode=ParseMode.HTML,
            reply_markup=confirm_swap_keyboard(),
            disable_web_page_preview=True,
        )
        return CONFIRM_SWAP

    except Exception as e:
        logger.error(f"Swap amount error: {e}", exc_info=True)
        await status_msg.edit_text(
            format_error(str(e)), parse_mode=ParseMode.HTML
        )
        return ConversationHandler.END


async def swap_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❌ <b>Swap cancelled.</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=back_to_menu_keyboard(),
    )
    return ConversationHandler.END


async def _handle_send_preview(update, context, amount, token, chain, to_address):
    user_id = str(update.effective_user.id)
    
    status = await update.message.reply_text(
        format_status("⏳ Estimating network fees..."), parse_mode=ParseMode.HTML
    )
    
    try:
        # Call directly — no agent, no LLM
        from app.wallet.gas import GasService
        fee_usd = await gas_service.estimate_fee_usd(chain_id=chain, action="send")
        
        # Store in session for confirm button
        send_sessions[user_id] = {
            "to_address": to_address,
            "amount": amount,
            "token": token,
            "chain": chain,
        }
        
        preview_text = format_send_preview({
            "to": to_address,
            "amount": amount,
            "token": token,
            "chain": chain,
            "fee_usd": fee_usd,
        })
        
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id,
            message_id=status.message_id,
            text=preview_text,
            parse_mode=ParseMode.HTML,
            reply_markup=confirm_send_keyboard(),
        )
    except Exception as e:
        await status.edit_text(format_error(str(e)), parse_mode=ParseMode.HTML)