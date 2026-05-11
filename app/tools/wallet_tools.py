from langchain.tools import tool
from app.db.database import async_session_factory
from app.db import crud
from app.wallet.privy import PrivyClient
from app.wallet.zerion import ZerionClient
from app.wallet.gas import GasService
import logging
import json

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
