from langchain.tools import tool
from app.db.database import async_session_factory
from app.db import crud
from app.wallet.privy import PrivyClient
from app.wallet.zerion import ZerionClient
from app.wallet.gas import GasService
from app.config import settings
import logging
import json
import aiohttp
import asyncio

logger = logging.getLogger(__name__)

privy_client = PrivyClient()
zerion_client = ZerionClient()
gas_service = GasService(zerion_client)

def extract_user_id(val: str) -> int:
    """Helper to extract and validate telegram_user_id from agent input."""
    if not val or str(val).lower() == "none":
        raise ValueError("Missing telegram_user_id. Please provide the numeric user ID.")
    
    # In case agent passes "User ID: 123456"
    val_str = str(val).strip()
    if " " in val_str:
        val_str = val_str.split()[-1]
    
    return int(val_str)

@tool
async def get_or_create_wallet(telegram_user_id: str) -> str:
    """
    Checks if the user has a wallet. If not, creates an EVM and a Solana wallet for them.
    Required: telegram_user_id (the numeric ID from context).
    Returns the public addresses of both wallets.
    """
    try:
        user_id_int = extract_user_id(telegram_user_id)
    except Exception as e:
        return f"Error: {str(e)}"

    async with async_session_factory() as session:
        async with session.begin():
            user = await crud.get_or_create_user(session, user_id_int)
            wallet = await crud.get_user_wallet(session, user.id)
            
            if not wallet:
                # Create EVM wallet
                evm_data = await privy_client.create_wallet("ethereum")
                # Create Solana wallet
                sol_data = await privy_client.create_wallet("solana")
                
                wallet = await crud.create_user_wallet(
                    session,
                    user_id=user.id,
                    evm_address=evm_data["address"],
                    solana_address=sol_data["address"],
                    privy_evm_wallet_id=evm_data["id"],
                    privy_solana_wallet_id=sol_data["id"]
                )
            
            return f"EVM: {wallet.evm_address}\nSolana: {wallet.solana_address}"

@tool
async def get_wallet_addresses(telegram_user_id: str) -> str:
    """
    Fetches the user's EVM and Solana wallet addresses from the database.
    Required: telegram_user_id (the numeric ID from context).
    """
    try:
        user_id_int = extract_user_id(telegram_user_id)
    except Exception as e:
        return f"Error: {str(e)}"

    async with async_session_factory() as session:
        user = await crud.get_or_create_user(session, user_id_int)
        wallet = await crud.get_user_wallet(session, user.id)
        
        if not wallet:
            return "No wallet found. Please create one first."
            
        return f"EVM: {wallet.evm_address}\nSolana: {wallet.solana_address}"

@tool
async def get_portfolio_summary(telegram_user_id: str) -> str:
    """
    Gets the user's total portfolio value and 24h change from Zerion.
    Required: telegram_user_id (the numeric ID from context).
    Note: For Solana, only wallet token holdings are returned (protocol positions are not supported).
    """
    try:
        user_id_int = extract_user_id(telegram_user_id)
    except Exception as e:
        return f"Error: {str(e)}"

    async with async_session_factory() as session:
        user = await crud.get_or_create_user(session, user_id_int)
        wallet = await crud.get_user_wallet(session, user.id)
        
        if not wallet:
            return "No wallet found."
            
        # Zerion portfolio (currently only for EVM address as summary)
        portfolio = await zerion_client.get_portfolio(wallet.evm_address)
        
        # Fetch positions for both EVM and Solana to populate the UI format
        positions = await zerion_client.get_positions(wallet.evm_address)
        sol_positions = await zerion_client.get_positions(wallet.solana_address, chain="solana")
        
        all_positions = positions + sol_positions
        
        return json.dumps({
            "total_value": portfolio.get("total_value", 0),
            "change_1d_abs": portfolio.get("change_1d_abs", 0),
            "change_1d_perc": portfolio.get("change_1d_perc", 0),
            "positions": all_positions
        })


@tool
async def get_token_positions(input_json: str) -> str:
    """
    Gets a list of the user's token positions.
    Input MUST be a JSON string with keys: telegram_user_id (required), chain (optional, default 'all').
    Example: {"telegram_user_id": "6034765096", "chain": "ethereum"}
    """
    try:
        data = json.loads(input_json)
        telegram_user_id = data["telegram_user_id"]
        user_id_int = extract_user_id(telegram_user_id)
        chain = data.get("chain", "all")
    except Exception as e:
        return f"Error parsing input: {str(e)}. Ensure you pass a valid JSON string."

    async with async_session_factory() as session:
        user = await crud.get_or_create_user(session, user_id_int)
        wallet = await crud.get_user_wallet(session, user.id)

        if not wallet:
            return "No wallet found."

        address = wallet.evm_address if chain != "solana" else wallet.solana_address
        chain_id = chain if chain != "all" else None

        positions = await zerion_client.get_positions(address, chain=chain_id)

        if not positions:
            return "No tokens found."

        lines = []
        for p in positions:
            lines.append(f"{p['quantity']:.4f} {p['symbol']} (${p['value_usd']:,.2f})")

        return "\n".join(lines)


@tool
async def get_transaction_history(telegram_user_id: str) -> str:
    """
    Fetches the user's recent transaction history.
    Required: telegram_user_id (the numeric ID from context).
    """
    try:
        user_id_int = extract_user_id(telegram_user_id)
    except Exception as e:
        return f"Error: {str(e)}"

    async with async_session_factory() as session:
        user = await crud.get_or_create_user(session, user_id_int)
        wallet = await crud.get_user_wallet(session, user.id)
        
        if not wallet:
            return "No wallet found."
            
        txs = await zerion_client.get_transactions(wallet.evm_address, limit=10)
        
        if not txs:
            return "No transactions found."
            
        lines = []
        for tx in txs:
            date = tx["mined_at"]
            type_ = tx["type"]
            lines.append(f"{date} | {type_.capitalize()} | Status: {tx['status']}")
            
        return "\n".join(lines)

@tool
async def get_send_preview(input_json: str) -> str:
    """
    Generates a send preview with gas estimates.
    Input MUST be a JSON string with keys: telegram_user_id, to_address, amount, token, chain.
    Example: {"telegram_user_id": "6034765096", "to_address": "0x...", "amount": "0.1", "token": "ETH", "chain": "ethereum"}
    """
    try:
        data = json.loads(input_json)
        telegram_user_id = data["telegram_user_id"]
        user_id_int = extract_user_id(telegram_user_id)
        to_address = data["to_address"]
        amount = data["amount"]
        token = data["token"]
        chain = data.get("chain", "ethereum")
    except Exception as e:
        return f"Error parsing input: {str(e)}"

    gas_estimates = await gas_service.estimate_fee_usd(chain_id=chain, action="send")
    # Unwrap if it returned a dict
    if isinstance(gas_estimates, dict):
        fee_usd = float(gas_estimates.get("standard") or gas_estimates.get("low") or 0.0)
    else:
        fee_usd = float(gas_estimates or 0.0)
    # We return a structured string that the agent can present to the user.
    # The actual buttons will be handled by the agent's response being processed in handlers.py if we want,
    # OR the agent can just ask for confirmation.
    
    preview_data = {
        "to": to_address,
        "amount": amount,
        "token": token,
        "fee_usd": fee_usd,
        "chain": chain,
        "high_gas": fee_usd > 10
    }
    
    return json.dumps(preview_data)

@tool
async def send_crypto(input_json: str) -> str:
    """
    Sends crypto to another address.
    Input MUST be a JSON string with keys: telegram_user_id, to_address, amount, chain, gas_speed (optional, default 'standard').
    Example: {"telegram_user_id": "6034765096", "to_address": "0x...", "amount": "0.01", "chain": "ethereum"}
    """
    try:
        data = json.loads(input_json)
        telegram_user_id = data["telegram_user_id"]
        user_id_int = extract_user_id(telegram_user_id)
        to_address = data["to_address"]
        amount = data["amount"]
        chain = data.get("chain", "ethereum")
        gas_speed = data.get("gas_speed", "standard")
    except Exception as e:
        return f"Error parsing input: {str(e)}"

    async with async_session_factory() as session:
        user = await crud.get_or_create_user(session, user_id_int)
        wallet = await crud.get_user_wallet(session, user.id)

        if not wallet:
            return "No wallet found."

        if chain.lower() in ("ethereum", "evm", "base", "polygon", "bnb", "arbitrum", "optimism"):
            # Get gas price for selected speed
            gas_prices = await zerion_client.get_gas_prices(chain.lower() if chain.lower() != "evm" else "ethereum")
            gas_price = gas_prices.get(gas_speed, gas_prices.get("standard", 0))
            
            wei = int(float(amount) * 10**18)
            value_hex = hex(wei)
            gas_price_hex = hex(gas_price) if gas_price else None
            
            tx_hash = await privy_client.send_evm_transaction(
                wallet_id=wallet.privy_evm_wallet_id,
                to_address=to_address,
                value_hex=value_hex,
                chain=chain,
                gas_hex=hex(21000), # Standard send gas limit
                # Note: We can add gasPrice to Privy payload if needed, 
                # but standard EIP-1559 might be handled by Privy internally.
            )
            return f"Transaction sent! Hash: {tx_hash}"
        elif chain.lower() == "solana":
            return "Solana sending is not fully implemented yet."
        else:
            return f"Unsupported chain: {chain}"


# ─── PRICE CONVERSION TOOLS ────────────────────────────────────────────────

async def _get_cryptocompare_price(token_symbol: str) -> str | None:
    """Get price from CryptoCompare's free API as fallback."""
    try:
        url = f"https://min-api.cryptocompare.com/data/price?fsym={token_symbol.upper()}&tsyms=USD"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                logger.debug(f"CryptoCompare response status for {token_symbol}: {response.status}")
                if response.status == 200:
                    data = await response.json()
                    if "USD" in data:
                        return str(data["USD"])
                    elif "Response" in data and data["Response"] == "Error":
                        logger.warning(f"CryptoCompare error for {token_symbol}: {data.get('Message')}")
        return None
    except Exception as e:
        logger.warning(f"Failed to get CryptoCompare price for {token_symbol}: {e}", exc_info=True)
        return None


async def _get_binance_price(token_symbol: str) -> str | None:
    """Get price from Binance's free API as fallback."""
    try:
        binance_symbols = {
            "ETH": "ETHUSDT",
            "BTC": "BTCUSDT",
            "SOL": "SOLUSDT",
            "MATIC": "POLUSDT",
            "POL": "POLUSDT",
            "ARB": "ARBUSDT",
            "OP": "OPUSDT",
            "CELO": "CELOUSDT",
            "USDC": "USDCUSDT",
            "USDT": "USDTUSDT"
        }

        symbol_upper = token_symbol.upper()
        binance_pair = binance_symbols.get(symbol_upper)

        if not binance_pair:
            return None

        url = f"https://api.binance.com/api/v3/ticker/price?symbol={binance_pair}"

        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                logger.debug(f"Binance response status for {token_symbol}: {response.status}")
                if response.status == 200:
                    data = await response.json()
                    if "price" in data:
                        return str(float(data["price"]))
                else:
                    logger.warning(f"Binance returned {response.status} for {token_symbol}: {await response.text()}")
        return None
    except Exception as e:
        logger.warning(f"Failed to get Binance price for {token_symbol}: {e}", exc_info=True)
        return None



async def _get_token_price(token_symbol: str) -> str:
    """
    Gets the current USD price of a cryptocurrency.
    Tries CryptoCompare → CoinGecko, returning the first success.
    """
    symbol_to_id = {
        "ETH": "ethereum",
        "ETHEREUM": "ethereum",
        "BTC": "bitcoin",
        "BITCOIN": "bitcoin",
        "USDC": "usd-coin",
        "USDT": "tether",
        "DAI": "dai",
        "WBTC": "wrapped-bitcoin",
        "LINK": "chainlink",
        "AAVE": "aave",
        "UNI": "uniswap",
        "MATIC": "polygon",
        "SOL": "solana",
        "SOLANA": "solana",
        "ARB": "arbitrum",
        "OP": "optimism",
    }

    # 1. Try CryptoCompare
    try:
        cc_price = await _get_cryptocompare_price(token_symbol)
        if cc_price:
            return cc_price
        logger.warning(f"CryptoCompare returned no price for {token_symbol}")
    except Exception as e:
        logger.error(f"CryptoCompare exception for {token_symbol}: {e}", exc_info=True)

    # 2. Try CoinGecko
    logger.info(f"CryptoCompare failed, trying CoinGecko for {token_symbol}")
    try:
        coin_id = symbol_to_id.get(token_symbol.upper(), token_symbol.lower())
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd"
        if settings.COINGECKO_DEMO_API_KEY:
            url += f"&x_cg_demo_token={settings.COINGECKO_DEMO_API_KEY}"

        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                logger.debug(f"CoinGecko response status for {token_symbol}: {response.status}")
                if response.status == 200:
                    data = await response.json()
                    if coin_id in data and "usd" in data[coin_id]:
                        return str(data[coin_id]["usd"])
                else:
                    logger.warning(f"CoinGecko returned {response.status} for {token_symbol}")
    except asyncio.TimeoutError:
        logger.warning(f"CoinGecko timed out for {token_symbol}")
    except Exception as e:
        logger.error(f"CoinGecko exception for {token_symbol}: {e}", exc_info=True)

    logger.error(f"All price sources failed for {token_symbol}")
    return f"Price data not found for {token_symbol}"



@tool
async def get_token_price(token_symbol: str) -> str:
    """
    Gets the current USD price of a cryptocurrency using CoinGecko.
    Required: token_symbol (e.g., "ETH", "USDC", "BTC").
    Returns the current price in USD as a string.
    Example: "get_token_price("ETH")" returns "2500.50"
    """
    return await _get_token_price(token_symbol)


async def _convert_usd_to_token(input_json: str) -> str:
    """
    Converts a USD amount to token quantity using current CoinGecko prices.
    Input MUST be a JSON string with keys: usd_amount (required), token_symbol (required).
    Example: {"usd_amount": 20, "token_symbol": "ETH"}
    Returns the token quantity as a string, rounded to 6 decimals.
    """
    try:
        data = json.loads(input_json)
        usd_amount = float(data["usd_amount"])
        token_symbol = data["token_symbol"]
        
        if usd_amount <= 0:
            return "Error: USD amount must be greater than 0"
        
        # Get the current token price
        price_str = await _get_token_price(token_symbol)
        
        try:
            price = float(price_str)
        except ValueError:
            return f"Error: Could not retrieve price for {token_symbol}: {price_str}"
        
        if price <= 0:
            return f"Error: Invalid price {price} for {token_symbol}"
        
        # Calculate token quantity
        token_quantity = usd_amount / price
        
        # Round to 6 decimals for display
        return str(round(token_quantity, 6))
    
    except json.JSONDecodeError:
        return "Error parsing input: Ensure you pass a valid JSON string"
    except KeyError as e:
        return f"Error: Missing required field {e}"
    except Exception as e:
        logger.error(f"Failed to convert USD to token: {e}", exc_info=True)
        return f"Error: {str(e)}"


@tool
async def convert_usd_to_token(input_json: str) -> str:
    """
    Converts a USD amount to token quantity using current CoinGecko prices.
    Input MUST be a JSON string with keys: usd_amount (required), token_symbol (required).
    Example: {"usd_amount": 20, "token_symbol": "ETH"}
    Returns the token quantity as a string, rounded to 6 decimals.
    """
    return await _convert_usd_to_token(input_json)


# ─── DCA TOOLS ─────────────────────────────────────────────────────────────

@tool
async def list_dca_payments(telegram_user_id: str) -> str:
    """
    Lists all recurring payments (DCA) for the user.
    Required: telegram_user_id (the numeric ID from context).
    Returns a summary of all active and paused payments.
    """
    try:
        user_id_int = extract_user_id(telegram_user_id)
        user_id = str(user_id_int)
    except Exception as e:
        return f"Error: {str(e)}"

    try:
        from app.dca.crud import DCAOperations
        
        async with async_session_factory() as session:
            payments = await DCAOperations.list_user_recurring_payments(session, user_id)
        
        if not payments:
            return "No recurring payments found. Create one with /dca create"
        
        lines = ["💰 Your Recurring Payments:\n"]
        for payment in payments:
            status_icon = "✅" if payment.status == "active" else "⏸"
            next_exec = payment.next_execution_at.strftime("%Y-%m-%d %H:%M UTC") if payment.next_execution_at else "N/A"
            
            lines.append(
                f"{status_icon} Payment #{payment.id}\n"
                f"  Amount: ${payment.amount} {payment.token_symbol}\n"
                f"  To: {payment.recipient_address[:20]}...\n"
                f"  Schedule: Every {payment.recurrence_type}\n"
                f"  Next: {next_exec}\n"
                f"  Status: {payment.status}\n"
            )
        
        return "\n".join(lines)
    
    except Exception as e:
        logger.error(f"Failed to list DCA payments: {e}", exc_info=True)
        return f"Error fetching payments: {str(e)}"


@tool
async def create_dca_payment(input_json: str) -> str:
    """
    Creates a new recurring payment (DCA).
    Input MUST be a JSON string with keys: telegram_user_id, recipient_address, amount, token_symbol, interval.
    Optional: chain (default 'ethereum'), description.
    Example: {"telegram_user_id": "6034765096", "recipient_address": "0x...", "amount": 10, "token_symbol": "USDC", "interval": "daily"}
    Supported intervals: hourly, daily, weekly, monthly, or specific weekdays (monday-sunday).
    """
    try:
        data = json.loads(input_json)
        telegram_user_id = data["telegram_user_id"]
        user_id_int = extract_user_id(telegram_user_id)
        user_id = str(user_id_int)
        recipient = data["recipient_address"]
        amount = float(data["amount"])
        token_symbol = data["token_symbol"]
        interval = data["interval"]
        chain = data.get("chain", "ethereum")
        description = data.get("description", f"DCA: ${amount} {token_symbol} every {interval}")
    except Exception as e:
        return f"Error parsing input: {str(e)}"

    try:
        from app.dca.parser import DCAParser
        from app.dca.crud import DCAOperations
        from app.dca.scheduler import get_dca_scheduler
        
        # Validate recipient address (not async)
        if not DCAParser.validate_address(recipient):
            return f"Invalid recipient address: {recipient}"
        
        # Calculate next execution time and cron expression
        next_exec = DCAParser.calculate_next_execution(interval)
        cron_expr = DCAParser.get_cron_expression(interval)
        
        async with async_session_factory() as session:
            payment = await DCAOperations.create_recurring_payment(
                session,
                user_id=user_id,
                recipient_address=recipient,
                amount=amount,
                token_symbol=token_symbol,
                chain=chain,
                recurrence_type=interval,
                cron_expression=cron_expr,
                next_execution_at=next_exec,
                description=description,
            )
            await session.commit()
            
            # Schedule the job
            scheduler = await get_dca_scheduler()
            await scheduler.schedule_job(payment)
        
        return (
            f"✅ DCA Created!\n"
            f"Payment ID: #{payment.id}\n"
            f"Amount: ${payment.amount} {payment.token_symbol}\n"
            f"Schedule: Every {payment.recurrence_type}\n"
            f"First execution: {payment.next_execution_at.strftime('%Y-%m-%d %H:%M UTC')}"
        )
    
    except Exception as e:
        logger.error(f"Failed to create DCA: {e}", exc_info=True)
        return f"Error creating DCA: {str(e)}"


@tool
async def pause_dca_payment(input_json: str) -> str:
    """
    Pauses a recurring payment (DCA).
    Input MUST be a JSON string with keys: telegram_user_id, payment_id.
    Example: {"telegram_user_id": "6034765096", "payment_id": 1}
    """
    try:
        data = json.loads(input_json)
        telegram_user_id = data["telegram_user_id"]
        user_id_int = extract_user_id(telegram_user_id)
        user_id = str(user_id_int)
        payment_id = int(data["payment_id"])
    except Exception as e:
        return f"Error parsing input: {str(e)}"

    try:
        from app.dca.crud import DCAOperations
        from app.dca.scheduler import get_dca_scheduler
        
        async with async_session_factory() as session:
            payment = await DCAOperations.get_recurring_payment(session, payment_id)
            
            if not payment:
                return f"Payment #{payment_id} not found."
            
            if payment.user_id != user_id:
                return "You don't have permission to pause this payment."
            
            await DCAOperations.pause_recurring_payment(session, payment_id)
            await session.commit()
            
            # Pause scheduler job
            scheduler = await get_dca_scheduler()
            await scheduler.pause_job(payment_id)
        
        return f"⏸ Payment #{payment_id} paused successfully."
    
    except Exception as e:
        logger.error(f"Failed to pause DCA: {e}", exc_info=True)
        return f"Error pausing DCA: {str(e)}"


@tool
async def resume_dca_payment(input_json: str) -> str:
    """
    Resumes a paused recurring payment (DCA).
    Input MUST be a JSON string with keys: telegram_user_id, payment_id.
    Example: {"telegram_user_id": "6034765096", "payment_id": 1}
    """
    try:
        data = json.loads(input_json)
        telegram_user_id = data["telegram_user_id"]
        user_id_int = extract_user_id(telegram_user_id)
        user_id = str(user_id_int)
        payment_id = int(data["payment_id"])
    except Exception as e:
        return f"Error parsing input: {str(e)}"

    try:
        from app.dca.crud import DCAOperations
        from app.dca.scheduler import get_dca_scheduler
        
        async with async_session_factory() as session:
            payment = await DCAOperations.get_recurring_payment(session, payment_id)
            
            if not payment:
                return f"Payment #{payment_id} not found."
            
            if payment.user_id != user_id:
                return "You don't have permission to resume this payment."
            
            await DCAOperations.resume_recurring_payment(session, payment_id)
            await session.commit()
            
            # Resume scheduler job
            scheduler = await get_dca_scheduler()
            await scheduler.resume_job(payment_id)
        
        return f"✅ Payment #{payment_id} resumed successfully."
    
    except Exception as e:
        logger.error(f"Failed to resume DCA: {e}", exc_info=True)
        return f"Error resuming DCA: {str(e)}"


@tool
async def cancel_dca_payment(input_json: str) -> str:
    """
    Cancels and removes a recurring payment (DCA) permanently.
    Input MUST be a JSON string with keys: telegram_user_id, payment_id.
    Example: {"telegram_user_id": "6034765096", "payment_id": 1}
    """
    try:
        data = json.loads(input_json)
        telegram_user_id = data["telegram_user_id"]
        user_id_int = extract_user_id(telegram_user_id)
        user_id = str(user_id_int)
        payment_id = int(data["payment_id"])
    except Exception as e:
        return f"Error parsing input: {str(e)}"

    try:
        from app.dca.crud import DCAOperations
        from app.dca.scheduler import get_dca_scheduler
        
        async with async_session_factory() as session:
            payment = await DCAOperations.get_recurring_payment(session, payment_id)
            
            if not payment:
                return f"Payment #{payment_id} not found."
            
            if payment.user_id != user_id:
                return "You don't have permission to cancel this payment."
            
            await DCAOperations.cancel_recurring_payment(session, payment_id)
            await session.commit()
            
            # Cancel scheduler job
            scheduler = await get_dca_scheduler()
            await scheduler.cancel_job(payment_id)
        
        return f"❌ Payment #{payment_id} cancelled permanently."
    
    except Exception as e:
        logger.error(f"Failed to cancel DCA: {e}", exc_info=True)
        return f"Error cancelling DCA: {str(e)}"
