import logging
from app.wallet.zerion import ZerionClient

logger = logging.getLogger(__name__)

# Default gas limits
DEFAULT_GAS_LIMITS = {
    "send": 21000,
    "swap": 150000, # Conservative estimate for complex swaps
}

# Native token mapping for price fetching
CHAIN_NATIVE_TOKENS = {
    "ethereum": "eth",
    "base": "eth",
    "arbitrum": "eth",
    "optimism": "eth",
    "polygon": "matic",
    "bnb": "bnb",
    "celo": "celo",
}

class GasService:
    def __init__(self, zerion_client: ZerionClient):
        self.zerion = zerion_client

    async def estimate_fee_usd(self, chain_id: str, action: str = "send", gas_limit: int = None) -> dict:
        """
        Estimates the network fee in USD for a given chain and action.
        Returns a dict with 'slow', 'standard', 'fast' USD estimates.
        """
        if gas_limit is None:
            gas_limit = DEFAULT_GAS_LIMITS.get(action, 21000)

        # 1. Get gas prices in wei
        gas_prices = await self.zerion.get_gas_prices(chain_id)
        if not gas_prices:
            return {"standard": 0.0, "slow": 0.0, "fast": 0.0}

        # 2. Get native token price
        token_id = CHAIN_NATIVE_TOKENS.get(chain_id, "eth")
        token_price = await self.zerion.get_token_price(token_id)

        estimates = {}
        for speed in ["slow", "standard", "fast"]:
            wei_price = gas_prices.get(speed)
            if wei_price is None:
                # Fallback to standard if others are null
                wei_price = gas_prices.get("standard", 0)
            
            # fee = gas_limit * gas_price (in wei) / 1e18 (to get eth) * token_price
            fee_eth = (gas_limit * wei_price) / 1e18
            fee_usd = fee_eth * token_price
            estimates[speed] = fee_usd

        return estimates

    def get_speed_label(self, speed: str) -> str:
        return speed.capitalize()

    async def get_gas_info(self, chain_id: str) -> dict:
        """
        Returns a dictionary of gas prices in USD for slow, standard, and fast speeds.
        Used for the /gas menu.
        """
        # We'll use a standard gas limit of 21000 for simple display
        estimates = await self.estimate_fee_usd(chain_id, action="send", gas_limit=21000)
        
        # We also want the Gwei values for the UI formatter if we keep it
        raw_gas_prices = await self.zerion.get_gas_prices(chain_id)
        
        return {
            "slow": {
                "usd": estimates.get("slow", 0.0),
                "gwei": (raw_gas_prices.get("slow", 0) / 1e9) if raw_gas_prices.get("slow") else 0
            },
            "standard": {
                "usd": estimates.get("standard", 0.0),
                "gwei": (raw_gas_prices.get("standard", 0) / 1e9) if raw_gas_prices.get("standard") else 0
            },
            "fast": {
                "usd": estimates.get("fast", 0.0),
                "gwei": (raw_gas_prices.get("fast", 0) / 1e9) if raw_gas_prices.get("fast") else 0
            }
        }
