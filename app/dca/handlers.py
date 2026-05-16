"""
dca_handlers.py - Telegram command handlers for DCA management.
Handles /dca create, list, pause, resume, cancel commands.
"""

import logging
from typing import Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from app.db.database import async_session_factory
from app.dca.parser import parse_dca_command, DCAParseError, DCAParser
from app.dca.crud import DCAOperations
from app.dca.scheduler import get_dca_scheduler
from app.bot.ui_formatters import format_error, format_status

logger = logging.getLogger(__name__)


async def dca_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /dca command with subcommands."""
    user_id = str(update.effective_user.id)
    
    if not context.args:
        # Show help
        await _show_dca_help(update, context)
        return
    
    subcommand = context.args[0].lower()
    
    if subcommand == "create":
        # /dca create <command>
        full_command = " ".join(context.args[1:]) if len(context.args) > 1 else ""
        await _handle_dca_create(update, context, full_command)
    
    elif subcommand == "list":
        await _handle_dca_list(update, context, user_id)
    
    elif subcommand == "pause":
        payment_id = int(context.args[1]) if len(context.args) > 1 else None
        await _handle_dca_pause(update, context, user_id, payment_id)
    
    elif subcommand == "resume":
        payment_id = int(context.args[1]) if len(context.args) > 1 else None
        await _handle_dca_resume(update, context, user_id, payment_id)
    
    elif subcommand == "cancel":
        payment_id = int(context.args[1]) if len(context.args) > 1 else None
        await _handle_dca_cancel(update, context, user_id, payment_id)
    
    else:
        await update.message.reply_text(
            f"Unknown subcommand: {subcommand}\n\n"
            "Use /dca help for available commands.",
            parse_mode=ParseMode.HTML
        )


async def _show_dca_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show DCA help menu."""
    help_text = (
        "<b>💰 DCA (Dollar Cost Averaging) Commands</b>\n\n"
        "<b>Create a recurring payment:</b>\n"
        "/dca create Send 10 dollars to 0x50C5b2284D7fc3E7DE4c132D0CD5ABFD7aa11247 every monday\n\n"
        "<b>Supported intervals:</b>\n"
        "• hourly\n"
        "• daily / everyday\n"
        "• weekly / every week\n"
        "• monthly / every month\n"
        "• monday-sunday (specific weekdays)\n\n"
        "<b>Manage payments:</b>\n"
        "/dca list - View all recurring payments\n"
        "/dca pause [ID] - Pause a payment\n"
        "/dca resume [ID] - Resume a payment\n"
        "/dca cancel [ID] - Cancel a payment\n\n"
        "<b>Examples:</b>\n"
        "• Send 10 dollars to 0x50C5b228... every monday\n"
        "• Send 5 USDC to 0x50C5b228... every day\n"
        "• Send 100 dollars to 0x50C5b228... every hour"
    )
    
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)


async def _handle_dca_create(update: Update, context: ContextTypes.DEFAULT_TYPE, command: str):
    """Handle /dca create <command>."""
    user_id = str(update.effective_user.id)
    
    if not command:
        await update.message.reply_text(
            "Usage: /dca create Send 10 dollars to 0x... every monday",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Try to parse the command
    try:
        parsed = parse_dca_command(command)
    except DCAParseError as e:
        await update.message.reply_text(
            f"❌ <b>Failed to parse command:</b>\n{str(e)}",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Validate recipient address
    if not await DCAParser.validate_address(parsed["recipient"]):
        await update.message.reply_text(
            f"❌ <b>Invalid recipient address:</b>\n{parsed['recipient']}",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Show confirmation
    confirmation_text = (
        f"<b>📋 DCA Confirmation</b>\n\n"
        f"<b>Amount:</b> ${parsed['amount']} {parsed['token']}\n"
        f"<b>Recipient:</b> <code>{parsed['recipient']}</code>\n"
        f"<b>Schedule:</b> Every {parsed['interval']}\n"
        f"<b>Next execution:</b> {DCAParser.calculate_next_execution(parsed['interval']).strftime('%Y-%m-%d %H:%M UTC')}\n\n"
        f"Confirm to activate this recurring payment."
    )
    
    # Create confirmation buttons
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Confirm", callback_data=f"dca_confirm:{command}"),
            InlineKeyboardButton("❌ Cancel", callback_data="dca_cancel_creation"),
        ]
    ])
    
    context.user_data["dca_creation"] = {
        "parsed": parsed,
        "original_command": command,
    }
    
    await update.message.reply_text(
        confirmation_text,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )


async def dca_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle DCA callback queries."""
    query = update.callback_query
    user_id = str(update.effective_user.id)
    
    await query.answer()
    
    if query.data.startswith("dca_confirm:"):
        command = query.data.replace("dca_confirm:", "")
        await _confirm_dca_creation(update, context, user_id, command)
    
    elif query.data == "dca_cancel_creation":
        await query.edit_message_text("❌ <b>Creation cancelled.</b>", parse_mode=ParseMode.HTML)

    elif query.data == "dca_list":
        await _show_dca_list_callback(query, user_id)

    elif query.data.startswith("dca_details:"):
        payment_id = _parse_callback_payment_id(query.data, "dca_details:")
        if payment_id is None:
            await query.edit_message_text("❌ <b>Invalid payment ID.</b>", parse_mode=ParseMode.HTML)
            return
        await _show_dca_details(query, user_id, payment_id)

    elif query.data.startswith("dca_manage:"):
        payment_id = _parse_callback_payment_id(query.data, "dca_manage:")
        if payment_id is None:
            await query.edit_message_text("❌ <b>Invalid payment ID.</b>", parse_mode=ParseMode.HTML)
            return
        await _show_dca_manage(query, user_id, payment_id)

    elif query.data.startswith("dca_pause:"):
        payment_id = _parse_callback_payment_id(query.data, "dca_pause:")
        if payment_id is None:
            await query.edit_message_text("❌ <b>Invalid payment ID.</b>", parse_mode=ParseMode.HTML)
            return
        await _handle_dca_pause_callback(query, user_id, payment_id)

    elif query.data.startswith("dca_resume:"):
        payment_id = _parse_callback_payment_id(query.data, "dca_resume:")
        if payment_id is None:
            await query.edit_message_text("❌ <b>Invalid payment ID.</b>", parse_mode=ParseMode.HTML)
            return
        await _handle_dca_resume_callback(query, user_id, payment_id)

    elif query.data.startswith("dca_cancel:"):
        payment_id = _parse_callback_payment_id(query.data, "dca_cancel:")
        if payment_id is None:
            await query.edit_message_text("❌ <b>Invalid payment ID.</b>", parse_mode=ParseMode.HTML)
            return
        await _handle_dca_cancel_callback(query, user_id, payment_id)

    else:
        await query.answer("Unsupported DCA action.", show_alert=False)


async def _confirm_dca_creation(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: str, command: str):
    """Confirm and create DCA."""
    query = update.callback_query
    
    try:
        parsed = parse_dca_command(command)
        next_exec = DCAParser.calculate_next_execution(parsed["interval"])
        
        async with async_session_factory() as session:
            # Create recurring payment
            payment = await DCAOperations.create_recurring_payment(
                session,
                user_id=user_id,
                recipient_address=parsed["recipient"],
                amount=parsed["amount"],
                token_symbol=parsed["token"],
                chain="ethereum",  # Default to ethereum
                recurrence_type=parsed["interval"],
                cron_expression=parsed["cron_expression"],
                next_execution_at=next_exec,
                description=f"DCA: ${parsed['amount']} {parsed['token']} every {parsed['interval']}",
            )
            
            await session.commit()
            
            # Schedule the job
            scheduler = await get_dca_scheduler()
            await scheduler.schedule_job(payment)
        
        success_text = (
            f"✅ <b>DCA Created!</b>\n\n"
            f"<b>Payment ID:</b> #{payment.id}\n"
            f"<b>Amount:</b> ${payment.amount} {payment.token_symbol}\n"
            f"<b>Recipient:</b> <code>{payment.recipient_address[:20]}...</code>\n"
            f"<b>Schedule:</b> Every {payment.recurrence_type}\n"
            f"<b>First execution:</b> {payment.next_execution_at.strftime('%Y-%m-%d %H:%M UTC')}\n\n"
            f"You can pause, resume, or cancel this payment at any time."
        )
        
        await query.edit_message_text(
            success_text,
            parse_mode=ParseMode.HTML
        )
    
    except Exception as e:
        logger.error(f"Failed to create DCA for user {user_id}: {e}", exc_info=True)
        await query.edit_message_text(
            f"❌ <b>Failed to create DCA:</b>\n{str(e)}",
            parse_mode=ParseMode.HTML
        )


async def _handle_dca_list(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: str):
    """List user's recurring payments."""
    try:
        async with async_session_factory() as session:
            payments = await DCAOperations.list_user_recurring_payments(session, user_id)
        
        if not payments:
            await update.message.reply_text(
                "📭 <b>No recurring payments.</b>\n\n"
                "Create your first DCA with:\n"
                "/dca create Send 10 dollars to 0x... every monday",
                parse_mode=ParseMode.HTML
            )
            return
        
        text = _build_dca_list_text(payments)
        keyboard = _build_dca_list_keyboard(payments)
        
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )
    
    except Exception as e:
        logger.error(f"Failed to list DCAs: {e}", exc_info=True)
        await update.message.reply_text(
            format_error(str(e)),
            parse_mode=ParseMode.HTML
        )


async def _handle_dca_pause(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: str, payment_id: Optional[int]):
    """Pause a recurring payment."""
    if not payment_id:
        await update.message.reply_text(
            "Usage: /dca pause [PAYMENT_ID]",
            parse_mode=ParseMode.HTML
        )
        return
    
    try:
        async with async_session_factory() as session:
            payment = await DCAOperations.get_recurring_payment(session, payment_id)
            
            if not payment:
                await update.message.reply_text("❌ Payment not found.", parse_mode=ParseMode.HTML)
                return
            
            if payment.user_id != user_id:
                await update.message.reply_text("❌ You don't have permission.", parse_mode=ParseMode.HTML)
                return
            
            await DCAOperations.pause_recurring_payment(session, payment_id)
            await session.commit()
            
            # Pause scheduler job
            scheduler = await get_dca_scheduler()
            await scheduler.pause_job(payment_id)
        
        await update.message.reply_text(
            f"⏸ <b>Payment #{payment_id} paused.</b>\n\n"
            f"Use /dca resume {payment_id} to resume.",
            parse_mode=ParseMode.HTML
        )
    
    except Exception as e:
        logger.error(f"Failed to pause DCA: {e}", exc_info=True)
        await update.message.reply_text(
            format_error(str(e)),
            parse_mode=ParseMode.HTML
        )


async def _handle_dca_resume(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: str, payment_id: Optional[int]):
    """Resume a paused recurring payment."""
    if not payment_id:
        await update.message.reply_text(
            "Usage: /dca resume [PAYMENT_ID]",
            parse_mode=ParseMode.HTML
        )
        return
    
    try:
        async with async_session_factory() as session:
            payment = await DCAOperations.get_recurring_payment(session, payment_id)
            
            if not payment:
                await update.message.reply_text("❌ Payment not found.", parse_mode=ParseMode.HTML)
                return
            
            if payment.user_id != user_id:
                await update.message.reply_text("❌ You don't have permission.", parse_mode=ParseMode.HTML)
                return
            
            await DCAOperations.resume_recurring_payment(session, payment_id)
            await session.commit()
            
            # Resume scheduler job
            scheduler = await get_dca_scheduler()
            await scheduler.resume_job(payment_id)
        
        await update.message.reply_text(
            f"▶️ <b>Payment #{payment_id} resumed.</b>\n\n"
            f"Next execution: {payment.next_execution_at.strftime('%Y-%m-%d %H:%M UTC')}",
            parse_mode=ParseMode.HTML
        )
    
    except Exception as e:
        logger.error(f"Failed to resume DCA: {e}", exc_info=True)
        await update.message.reply_text(
            format_error(str(e)),
            parse_mode=ParseMode.HTML
        )


async def _handle_dca_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: str, payment_id: Optional[int]):
    """Cancel a recurring payment."""
    if not payment_id:
        await update.message.reply_text(
            "Usage: /dca cancel [PAYMENT_ID]",
            parse_mode=ParseMode.HTML
        )
        return
    
    try:
        async with async_session_factory() as session:
            payment = await DCAOperations.get_recurring_payment(session, payment_id)
            
            if not payment:
                await update.message.reply_text("❌ Payment not found.", parse_mode=ParseMode.HTML)
                return
            
            if payment.user_id != user_id:
                await update.message.reply_text("❌ You don't have permission.", parse_mode=ParseMode.HTML)
                return
            
            await DCAOperations.cancel_recurring_payment(session, payment_id)
            await session.commit()
            
            # Unschedule job
            scheduler = await get_dca_scheduler()
            await scheduler.unschedule_job(payment_id)
        
        await update.message.reply_text(
            f"✅ <b>Payment #{payment_id} cancelled.</b>",
            parse_mode=ParseMode.HTML
        )
    
    except Exception as e:
        logger.error(f"Failed to cancel DCA: {e}", exc_info=True)
        await update.message.reply_text(
            format_error(str(e)),
            parse_mode=ParseMode.HTML
        )


def _parse_callback_payment_id(callback_data: str, prefix: str) -> Optional[int]:
    """Extract payment ID from callback data."""
    try:
        return int(callback_data.replace(prefix, "", 1))
    except (TypeError, ValueError):
        return None


def _format_next_execution(payment) -> str:
    """Format the next execution timestamp for display."""
    if not payment.next_execution_at:
        return "N/A"
    return payment.next_execution_at.strftime("%Y-%m-%d %H:%M UTC")


def _build_dca_list_text(payments) -> str:
    """Build the recurring payments list text."""
    text = "<b>💰 Your Recurring Payments</b>\n\n"
    for payment in payments:
        status_emoji = "✅" if payment.status == "active" else "⏸"
        text += (
            f"{status_emoji} <b>#{payment.id}</b> - ${payment.amount} {payment.token_symbol}\n"
            f"   → {payment.recipient_address[:20]}...\n"
            f"   ⏰ Every {payment.recurrence_type}\n"
            f"   Next: {_format_next_execution(payment)}\n"
            f"   Status: {payment.status}\n\n"
        )
    return text


def _build_dca_list_keyboard(payments) -> InlineKeyboardMarkup:
    """Build per-payment action buttons for the DCA list."""
    rows = []
    for payment in payments:
        rows.append([
            InlineKeyboardButton(f"📋 #{payment.id}", callback_data=f"dca_details:{payment.id}"),
            InlineKeyboardButton(f"⚙️ #{payment.id}", callback_data=f"dca_manage:{payment.id}"),
        ])
    return InlineKeyboardMarkup(rows)


async def _get_user_payment(user_id: str, payment_id: int):
    """Fetch a payment and verify it belongs to the user."""
    async with async_session_factory() as session:
        payment = await DCAOperations.get_recurring_payment(session, payment_id)
        if not payment or payment.user_id != user_id:
            return None
        return payment


async def _show_dca_list_callback(query, user_id: str):
    """Show the DCA list in response to an inline callback."""
    try:
        async with async_session_factory() as session:
            payments = await DCAOperations.list_user_recurring_payments(session, user_id)

        if not payments:
            await query.edit_message_text(
                "📭 <b>No recurring payments.</b>\n\nCreate your first DCA with /dca create",
                parse_mode=ParseMode.HTML,
            )
            return

        await query.edit_message_text(
            _build_dca_list_text(payments),
            parse_mode=ParseMode.HTML,
            reply_markup=_build_dca_list_keyboard(payments),
        )
    except Exception as e:
        logger.error(f"Failed to show DCA list callback: {e}", exc_info=True)
        await query.edit_message_text(format_error(str(e)), parse_mode=ParseMode.HTML)


async def _show_dca_details(query, user_id: str, payment_id: int):
    """Show details for a single recurring payment."""
    try:
        payment = await _get_user_payment(user_id, payment_id)
        if not payment:
            await query.edit_message_text("❌ <b>Payment not found.</b>", parse_mode=ParseMode.HTML)
            return

        text = (
            f"<b>📋 Payment #{payment.id}</b>\n\n"
            f"<b>Amount:</b> ${payment.amount} {payment.token_symbol}\n"
            f"<b>Recipient:</b> <code>{payment.recipient_address}</code>\n"
            f"<b>Chain:</b> {payment.chain}\n"
            f"<b>Schedule:</b> Every {payment.recurrence_type}\n"
            f"<b>Cron:</b> <code>{payment.cron_expression}</code>\n"
            f"<b>Next execution:</b> {_format_next_execution(payment)}\n"
            f"<b>Status:</b> {payment.status}\n"
            f"<b>Executions:</b> {payment.execution_count or 0}"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⚙️ Manage", callback_data=f"dca_manage:{payment.id}")],
            [InlineKeyboardButton("⬅️ Back", callback_data="dca_list")],
        ])
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    except Exception as e:
        logger.error(f"Failed to show DCA details: {e}", exc_info=True)
        await query.edit_message_text(format_error(str(e)), parse_mode=ParseMode.HTML)


async def _show_dca_manage(query, user_id: str, payment_id: int):
    """Show management actions for a recurring payment."""
    try:
        payment = await _get_user_payment(user_id, payment_id)
        if not payment:
            await query.edit_message_text("❌ <b>Payment not found.</b>", parse_mode=ParseMode.HTML)
            return

        action_button = (
            InlineKeyboardButton("⏸ Pause", callback_data=f"dca_pause:{payment.id}")
            if payment.status == "active"
            else InlineKeyboardButton("▶️ Resume", callback_data=f"dca_resume:{payment.id}")
        )
        keyboard = InlineKeyboardMarkup([
            [action_button, InlineKeyboardButton("🗑 Cancel", callback_data=f"dca_cancel:{payment.id}")],
            [InlineKeyboardButton("📋 Details", callback_data=f"dca_details:{payment.id}")],
            [InlineKeyboardButton("⬅️ Back", callback_data="dca_list")],
        ])
        text = (
            f"<b>⚙️ Manage Payment #{payment.id}</b>\n\n"
            f"<b>Amount:</b> ${payment.amount} {payment.token_symbol}\n"
            f"<b>Status:</b> {payment.status}\n"
            f"<b>Next execution:</b> {_format_next_execution(payment)}"
        )
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    except Exception as e:
        logger.error(f"Failed to show DCA manage actions: {e}", exc_info=True)
        await query.edit_message_text(format_error(str(e)), parse_mode=ParseMode.HTML)


async def _handle_dca_pause_callback(query, user_id: str, payment_id: int):
    """Pause a recurring payment from an inline button."""
    try:
        async with async_session_factory() as session:
            payment = await DCAOperations.get_recurring_payment(session, payment_id)
            if not payment or payment.user_id != user_id:
                await query.edit_message_text("❌ <b>Payment not found.</b>", parse_mode=ParseMode.HTML)
                return

            await DCAOperations.pause_recurring_payment(session, payment_id)
            await session.commit()

        scheduler = await get_dca_scheduler()
        await scheduler.pause_job(payment_id)

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Back To Manage", callback_data=f"dca_manage:{payment_id}")],
            [InlineKeyboardButton("📋 Back To List", callback_data="dca_list")],
        ])
        await query.edit_message_text(
            f"⏸ <b>Payment #{payment_id} paused.</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
        )
    except Exception as e:
        logger.error(f"Failed to pause DCA from callback: {e}", exc_info=True)
        await query.edit_message_text(format_error(str(e)), parse_mode=ParseMode.HTML)


async def _handle_dca_resume_callback(query, user_id: str, payment_id: int):
    """Resume a recurring payment from an inline button."""
    try:
        async with async_session_factory() as session:
            payment = await DCAOperations.get_recurring_payment(session, payment_id)
            if not payment or payment.user_id != user_id:
                await query.edit_message_text("❌ <b>Payment not found.</b>", parse_mode=ParseMode.HTML)
                return

            await DCAOperations.resume_recurring_payment(session, payment_id)
            await session.commit()

        scheduler = await get_dca_scheduler()
        await scheduler.resume_job(payment_id)

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Back To Manage", callback_data=f"dca_manage:{payment_id}")],
            [InlineKeyboardButton("📋 Back To List", callback_data="dca_list")],
        ])
        await query.edit_message_text(
            f"▶️ <b>Payment #{payment_id} resumed.</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
        )
    except Exception as e:
        logger.error(f"Failed to resume DCA from callback: {e}", exc_info=True)
        await query.edit_message_text(format_error(str(e)), parse_mode=ParseMode.HTML)


async def _handle_dca_cancel_callback(query, user_id: str, payment_id: int):
    """Cancel a recurring payment from an inline button."""
    try:
        async with async_session_factory() as session:
            payment = await DCAOperations.get_recurring_payment(session, payment_id)
            if not payment or payment.user_id != user_id:
                await query.edit_message_text("❌ <b>Payment not found.</b>", parse_mode=ParseMode.HTML)
                return

            await DCAOperations.cancel_recurring_payment(session, payment_id)
            await session.commit()

        scheduler = await get_dca_scheduler()
        await scheduler.unschedule_job(payment_id)

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 Back To List", callback_data="dca_list")],
        ])
        await query.edit_message_text(
            f"✅ <b>Payment #{payment_id} cancelled.</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
        )
    except Exception as e:
        logger.error(f"Failed to cancel DCA from callback: {e}", exc_info=True)
        await query.edit_message_text(format_error(str(e)), parse_mode=ParseMode.HTML)
