"""
ui_formatters.py — Beautiful HTML-formatted message cards for Pliro bot.
Uses Telegram HTML parse mode (more reliable than MarkdownV2).
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


# ─────────────────────────────────────────────
#  HELPER UTILITIES
# ─────────────────────────────────────────────

def short_addr(address: str, head: int = 6, tail: int = 4) -> str:
    """Shortens a wallet address: 0x1234...abcd"""
    if not address or len(address) < head + tail:
        return address or "N/A"
    return f"{address[:head]}...{address[-tail:]}"


def escape_html(text: str) -> str:
    """Escapes characters that would break Telegram HTML."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def chain_emoji(chain: str) -> str:
    """Returns an emoji for a given chain name."""
    return {
        "ethereum": "-",
        "base": "-",
        "arbitrum": "-",
        "bnb": "-",
        "polygon": "-",
        "optimism": "-",
        "celo": "-",
        "solana": "-",
        "bitcoin": "-",
    }.get(chain.lower(), "-")


# ─────────────────────────────────────────────
#  KEYBOARDS
# ─────────────────────────────────────────────

def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💼 Portfolio", callback_data="menu_portfolio"),
            InlineKeyboardButton("🪙 Tokens", callback_data="menu_tokens"),
        ],
        [
            InlineKeyboardButton("📬 My Addresses", callback_data="menu_addresses"),
            InlineKeyboardButton("📜 History", callback_data="menu_history"),
        ],
        [
            InlineKeyboardButton("📤 Send", callback_data="menu_send"),
            InlineKeyboardButton("📥 Receive", callback_data="menu_receive"),
        ],
        [
            InlineKeyboardButton("💱 Swap", callback_data="menu_swap"),
            InlineKeyboardButton("⛽ Gas Prices", callback_data="menu_gas"),
        ],
    ])


def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 Main Menu", callback_data="menu_home")]
    ])


def confirm_send_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Confirm", callback_data="confirm_send"),
            InlineKeyboardButton("❌ Cancel", callback_data="cancel_send"),
        ]
    ])


def confirm_swap_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Confirm Swap", callback_data="confirm_swap"),
            InlineKeyboardButton("❌ Cancel", callback_data="cancel_swap"),
        ]
    ])


def chain_select_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Ethereum", callback_data="chain_ethereum"),
            InlineKeyboardButton("Base", callback_data="chain_base"),
        ],
        [
            InlineKeyboardButton("Arbitrum", callback_data="chain_arbitrum"),
            InlineKeyboardButton("BNB", callback_data="chain_bnb"),
        ],
        [
            InlineKeyboardButton("Polygon", callback_data="chain_polygon"),
            InlineKeyboardButton("Optimism", callback_data="chain_optimism"),
        ],
        [
            InlineKeyboardButton("Celo", callback_data="chain_celo"),
            InlineKeyboardButton("Solana", callback_data="chain_solana"),
        ],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="menu_home")],
    ])


# ─────────────────────────────────────────────
#  WELCOME / START SCREEN
# ─────────────────────────────────────────────

def format_welcome(first_name: str) -> str:
    name = escape_html(first_name)
    return (
        f"👋 <b>Welcome to Pliro, {name}!</b>\n"
        f"{'─' * 28}"
        "Your <b>AI-powered crypto wallet</b> is ready.\n"
        "Manage EVM &amp; Solana assets — just by chatting.\n\n"
        "<b>What you can do:</b>\n"
        "  💼  Check portfolio &amp; balances\n"
        "  📬  View &amp; share wallet addresses\n"
        "  📤  Send crypto to any address\n"
        "  💱  Swap tokens instantly\n"
        "  📜  View transaction history\n\n"
        "🔐 <i>Your private keys are secured by Privy MPC.\n"
        "We never store or see them.</i>\n\n"
        "Tap a button below or just <b>type what you need</b>."
    )


# ─────────────────────────────────────────────
#  PORTFOLIO CARD
# ─────────────────────────────────────────────

def format_portfolio(total_value: float, change_abs: float, change_perc: float,
                     chain_breakdown: dict = None) -> str:
    sign = "+" if change_abs >= 0 else ""
    trend = "📈" if change_abs >= 0 else "📉"

    lines = [
        "💼 <b>Portfolio Overview</b>",
        "─" * 28,
        f"<b>Total Value</b>",
        f"  <code>${total_value:,.2f}</code>",
        "",
        f"<b>24h Change</b>",
        f"  {trend}  {sign}${change_abs:,.2f}  ({sign}{change_perc:.2f}%)",
    ]

    if chain_breakdown:
        lines += ["", "<b>By Chain</b>"]
        sorted_chains = sorted(chain_breakdown.items(), key=lambda x: x[1], reverse=True)
        for chain, value in sorted_chains:
            if value > 0:
                emoji = chain_emoji(chain)
                chain_label = chain.replace("-", " ").title()
                lines.append(f"  {emoji}  {escape_html(chain_label):<14}  <code>${value:,.2f}</code>")

    return "\n".join(lines)


# ─────────────────────────────────────────────
#  TOKEN POSITIONS CARD
# ─────────────────────────────────────────────

def format_token_positions(positions: list, chain: str = "all") -> str:
    chain_label = "All Chains" if chain == "all" else chain.title()

    if not positions:
        return (
            f"🪙 <b>Token Balances — {escape_html(chain_label)}</b>\n"
           
            "<i>No tokens found on this wallet yet.</i>\n\n"
            "Deposit funds to get started."
        )

    lines = [
        f"🪙 <b>Token Balances — {escape_html(chain_label)}</b>",
        "─" * 28,
    ]

    for p in positions[:15]:  # cap at 15 to avoid message too long
        symbol = escape_html(p.get("symbol") or "???")
        qty = p.get("quantity") or 0
        value = p.get("value_usd") or 0
        price = p.get("price") or 0

        lines.append(
            f"\n<b>{symbol}</b>\n"
            f"  Qty:    <code>{qty:.6f}</code>\n"
            f"  Value:  <code>${value:,.2f}</code>\n"
            f"  Price:  <code>${price:,.4f}</code>"
        )

    if len(positions) > 15:
        lines.append(f"\n<i>+ {len(positions) - 15} more tokens…</i>")

    return "\n".join(lines)


# ─────────────────────────────────────────────
#  WALLET ADDRESSES CARD
# ─────────────────────────────────────────────

def format_wallet_addresses(evm_address: str, solana_address: str) -> str:
    evm_short = short_addr(evm_address)
    sol_short = short_addr(solana_address)

    evm_chains = [
        ("-", "Ethereum"),
        ("-", "Base"),
        ("-", "Arbitrum"),
        ("-", "BNB Chain"),
        ("-", "Polygon"),
        ("-", "Optimism"),
        ("-", "Celo"),
    ]

    chain_lines = "\n".join(
        f"  {emoji}  {escape_html(name)}"
        for emoji, name in evm_chains
    )

    return (
        "📬 <b>Your Wallet Addresses</b>\n"
                
        "<b>EVM Address</b>  (Ethereum &amp; all EVM chains)\n"
        f"  <code>{escape_html(evm_address)}</code>\n"
        f"  <i>Tap address to copy</i>\n\n"
        f"<b>Works on:</b>\n"
        f"{chain_lines}\n\n"
      
        "<b>Solana Address</b>\n"
        f"  <code>{escape_html(solana_address)}</code>\n"
        f"  <i>Tap address to copy</i>\n\n"
        "🔐 <i>One address covers all EVM-compatible chains.\n"
        "Send only matching assets to each address.</i>"
    )


# ─────────────────────────────────────────────
#  RECEIVE CARD
# ─────────────────────────────────────────────

def format_receive_card(evm_address: str, solana_address: str, chain: str = "ethereum") -> str:
    is_solana = chain.lower() == "solana"
    address = solana_address if is_solana else evm_address
    emoji = chain_emoji(chain)
    chain_label = escape_html(chain.title())

    note = (
        "<i>This address works on Solana only.</i>"
        if is_solana else
        "<i>This address works on Ethereum, Base, Arbitrum,\n"
        "BNB Chain, Polygon, Optimism, and Celo.</i>"
    )

    return (
        f"📥 <b>Receive — {emoji} {chain_label}</b>\n"
      
        "Share this address to receive funds:\n\n"
        f"  <code>{escape_html(address)}</code>\n\n"
        f"{note}"
    )


# ─────────────────────────────────────────────
#  TRANSACTION HISTORY CARD
# ─────────────────────────────────────────────

def format_transaction_history(transactions: list) -> str:
    if not transactions:
        return (
            "📜 <b>Transaction History</b>\n"
            
            "<i>No transactions found yet.</i>"
        )

    type_emoji = {
        "send": "📤",
        "receive": "📥",
        "trade": "💱",
        "approve": "✅",
        "mint": "🪙",
        "burn": "🔥",
        "deposit": "⬇️",
        "withdraw": "⬆️",
    }

    lines = [
        "📜 <b>Transaction History</b>",
      
    ]

    for tx in transactions[:10]:
        op = tx.get("type") or "unknown"
        status = tx.get("status") or "unknown"
        mined_at = tx.get("mined_at") or ""
        emoji = type_emoji.get(op.lower(), "🔄")

        # Format date
        date_str = ""
        if mined_at:
            try:
                date_str = mined_at[:10]  # just YYYY-MM-DD
            except Exception:
                date_str = mined_at[:10] if len(mined_at) >= 10 else mined_at

        status_icon = "✅" if status == "confirmed" else "⏳" if status == "pending" else "❌"

        lines.append(
            f"\n{emoji}  <b>{escape_html(op.title())}</b>  {status_icon}\n"
            f"  <i>{escape_html(date_str)}</i>"
        )

    return "\n".join(lines)


# ─────────────────────────────────────────────
#  SEND PREVIEW CARD
# ─────────────────────────────────────────────

def format_send_preview(data: dict) -> str:
    # Handle both "to" and "to_address" key variants
    to_addr = data.get("to_address") or data.get("to", "")
    amount  = data.get("amount", "")
    token   = data.get("token", "").upper()
    chain   = data.get("chain", "ethereum")

    # fee_usd might arrive as a dict e.g. {"standard": 0.12, "fast": 0.18}
    raw_fee = data.get("fee_usd") or 0.0
    if isinstance(raw_fee, dict):
        fee_usd = float(raw_fee.get("standard") or raw_fee.get("low") or 0.0)
    else:
        fee_usd = float(raw_fee or 0.0)

    short_to    = short_addr(to_addr)
    emoji       = chain_emoji(chain)
    chain_label = escape_html(chain.title())

    warning = ""
    if fee_usd > 10:
        warning = f"⚠️ <b>High Network Fees (~${fee_usd:,.2f})</b>\n\n"

    return (
        f"{warning}"
        f"📤 <b>Send Preview</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>To:</b>      <code>{escape_html(short_to)}</code>\n"
        f"<b>Amount:</b>  <code>{escape_html(str(amount))} {escape_html(token)}</code>\n"
        f"<b>Chain:</b>   {emoji} {chain_label}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⛽ <b>Network Fee:</b>  ~<code>${fee_usd:,.2f}</code> (Standard)\n"
        f"⏱ <b>Speed:</b>        ~Instant\n\n"
        f"Reply <b>YES</b> to confirm or <b>CANCEL</b> to abort."
    )

# ─────────────────────────────────────────────
#  SWAP QUOTE CARD
# ─────────────────────────────────────────────

def format_swap_quote(offer: dict, input_token: str, output_token: str, amount: str) -> str:
    est = offer.get("estimation", {})
    output_amount = est.get("output_quantity", {}).get("numeric", "0")
    provider = offer.get("liquidity_source", {}).get("name", "Unknown")
    seconds = est.get("seconds", 0)
    fee_percent = offer.get("fee", {}).get("integrator", {}).get("percent", 0)
    fee_usd = offer.get("gas_usd", 0)

    warning = ""
    if fee_usd > 10:
        warning = (
            f"⚠️ <b>High Network Fees</b>\n"
            f"Gas is currently high (~${fee_usd:,.2f})\n\n"
        )

    pre = offer.get("preconditions", {})
    alerts = ""
    if not pre.get("enough_balance", True):
        alerts += "⚠️ <b>Warning:</b> Insufficient balance\n"
    if not pre.get("enough_allowance", True):
        alerts += "⚠️ <b>Warning:</b> Token approval required before swap\n"

    return (
        f"{warning}"
        "💱 <b>Swap Preview</b>\n"
        
        f"<b>From:</b>     <code>{escape_html(amount)} {escape_html(input_token.upper())}</code>\n"
        f"<b>To:</b>       <code>≈ {escape_html(output_amount)} {escape_html(output_token.upper())}</code>\n\n"
        
        f"🏦 <b>Route:</b>         {escape_html(provider)}\n"
        f"⛽ <b>Gas:</b>           ~<code>${fee_usd:,.2f}</code>  (Standard)\n"
        f"⏱ <b>Time:</b>          ~{escape_html(str(seconds))}s\n"
        f"💸 <b>Protocol Fee:</b>  {escape_html(str(fee_percent))}%\n\n"
        f"{alerts}"
        "Confirm or cancel below."
    )


# ─────────────────────────────────────────────
#  GAS PRICES CARD
# ─────────────────────────────────────────────

def format_gas_prices(gas_info: dict, chain: str = "ethereum") -> str:
    emoji = chain_emoji(chain)
    chain_label = escape_html(chain.title())

    if not gas_info:
        return (
            f"⛽ <b>Gas Prices — {emoji} {chain_label}</b>\n"
                
            "<i>Unable to fetch gas prices right now.</i>"
        )

    slow = gas_info.get("slow", {})
    standard = gas_info.get("standard", {})
    fast = gas_info.get("fast", {})

    def format_price(info):
        usd = info.get("usd", 0.0)
        gwei = info.get("gwei", 0.0)
        return f"<code>${usd:,.2f}</code>  ({gwei:.1f} Gwei)"

    return (
        f"⛽ <b>Gas Prices — {emoji} {chain_label}</b>\n"
     
        f"🐢  <b>Slow</b>       {format_price(slow)}\n"
        f"🚗  <b>Standard</b>   {format_price(standard)}\n"
        f"🚀  <b>Fast</b>       {format_price(fast)}\n\n"
        "<i>Prices are for a standard ETH transfer.</i>"
    )


# ─────────────────────────────────────────────
#  SUCCESS / ERROR CARDS
# ─────────────────────────────────────────────

def format_tx_success(tx_hash: str, chain: str, amount: str, token: str, to_address: str) -> str:
    emoji = chain_emoji(chain)
    chain_label = escape_html(chain.title())
    short_to = short_addr(to_address)
    explorer_urls = {
        "ethereum": f"https://etherscan.io/tx/{tx_hash}",
        "base": f"https://basescan.org/tx/{tx_hash}",
        "arbitrum": f"https://arbiscan.io/tx/{tx_hash}",
        "bnb": f"https://bscscan.com/tx/{tx_hash}",
        "polygon": f"https://polygonscan.com/tx/{tx_hash}",
        "optimism": f"https://optimistic.etherscan.io/tx/{tx_hash}",
        "celo": f"https://celoscan.io/tx/{tx_hash}",
    }
    explorer = explorer_urls.get(chain.lower(), "")
    explorer_line = f'\n\n🔗 <a href="{escape_html(explorer)}">View on Explorer</a>' if explorer else ""

    return (
        "✅ <b>Transaction Sent!</b>\n"

        f"<b>Amount:</b>   <code>{escape_html(amount)} {escape_html(token.upper())}</code>\n"
        f"<b>To:</b>       <code>{escape_html(short_to)}</code>\n"
        f"<b>Chain:</b>    {emoji} {chain_label}\n\n"
        f"<b>TX Hash:</b>\n"
        f"<code>{escape_html(tx_hash)}</code>"
        f"{explorer_line}"
    )


def format_error(message: str) -> str:
    return (
        "❌ <b>Something went wrong</b>\n"
 
        f"<i>{escape_html(message)}</i>\n\n"
        "Please try again or type your request differently."
    )


def format_status(message: str, emoji: str = "⏳") -> str:
    return f"{emoji}  <i>{escape_html(message)}</i>"


# ─────────────────────────────────────────────
#  SWAP CONVERSATION HELPER (used by handlers)
# ─────────────────────────────────────────────

def format_swap_step_input() -> str:
    return (
        "💱 <b>Token Swap</b>\n"

        "What token do you want to swap <b>FROM</b>?\n\n"
        "<i>Example: ETH, USDC, LINK</i>"
    )


def format_swap_step_output(input_token: str) -> str:
    return (
        f"💱 <b>Token Swap</b>\n"
 
        f"Swapping from: <code>{escape_html(input_token.upper())}</code>\n\n"
        "What token do you want to swap <b>TO</b>?\n\n"
        "<i>Example: USDT, DAI, WBTC</i>"
    )


def format_swap_step_amount(input_token: str, output_token: str) -> str:
    return (
        f"💱 <b>Token Swap</b>\n"
    
        f"<b>From:</b> <code>{escape_html(input_token.upper())}</code>\n"
        f"<b>To:</b>   <code>{escape_html(output_token.upper())}</code>\n\n"
        f"How much <b>{escape_html(input_token.upper())}</b> do you want to swap?\n\n"
        "<i>Example: 0.1</i>"
    )