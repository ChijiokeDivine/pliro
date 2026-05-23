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

CHAIN_ALIASES = {
    "evm": "ethereum",
    "mainnet": "ethereum",
    "eth": "ethereum",
    "bnb chain": "bnb",
    "binance": "bnb",
    "binance smart chain": "bnb",
    "matic": "polygon",
}

class GasService:
    def __init__(self, zerion_client: ZerionClient):
        self.zerion = zerion_client

    def _normalize_chain_id(self, chain_id: str) -> str:
        normalized = (chain_id or "ethereum").strip().lower()
        return CHAIN_ALIASES.get(normalized, normalized)

    def _estimate_fee_wei(self, gas_data: dict, speed: str, gas_limit: int) -> int:
        gas_type = gas_data.get("gas_type", "classic")

        if gas_type == "optimistic":
            l1_cost = int(gas_data.get("l1") or 0)
            l2_gas_price = int(gas_data.get("l2") or gas_data.get("standard") or 0)
            return l1_cost + (gas_limit * l2_gas_price)

        gas_price_wei = int(gas_data.get(speed) or gas_data.get("standard") or 0)
        return gas_limit * gas_price_wei

    async def estimate_fee_usd(self, chain_id: str, action: str = "send", gas_limit: int = None) -> dict:
        """
        Estimates the network fee in USD for a given chain and action.
        Returns a dict with 'slow', 'standard', 'fast' USD estimates.
        """
        chain_id = self._normalize_chain_id(chain_id)
        if gas_limit is None:
            gas_limit = DEFAULT_GAS_LIMITS.get(action, 21000)

        # 1. Get normalized gas data from Zerion
        gas_prices = await self.zerion.get_gas_prices(chain_id)
        if not gas_prices:
            return {"standard": 0.0, "slow": 0.0, "fast": 0.0}

        # 2. Get native token price
        token_id = CHAIN_NATIVE_TOKENS.get(chain_id, "eth")
        token_price = float(await self.zerion.get_token_price(token_id) or 0.0)
        if token_price <= 0:
            logger.warning("Missing token price for chain %s (token %s)", chain_id, token_id)
            return {"standard": 0.0, "slow": 0.0, "fast": 0.0}

        estimates = {}
        for speed in ["slow", "standard", "fast"]:
            fee_wei = self._estimate_fee_wei(gas_prices, speed, gas_limit)
            fee_eth = fee_wei / 1e18
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
        chain_id = self._normalize_chain_id(chain_id)
        # We'll use a standard gas limit of 21000 for simple display
        estimates = await self.estimate_fee_usd(chain_id, action="send", gas_limit=21000)
        
        # We also want the Gwei values for the UI formatter if we keep it
        raw_gas_prices = await self.zerion.get_gas_prices(chain_id)
        gas_type = raw_gas_prices.get("gas_type", "classic")

        def _display_gwei(speed: str) -> float:
            if gas_type == "optimistic":
                return (raw_gas_prices.get("l2", 0) / 1e9) if raw_gas_prices.get("l2") else 0
            return (raw_gas_prices.get(speed, 0) / 1e9) if raw_gas_prices.get(speed) else 0
        
        return {
            "slow": {
                "usd": estimates.get("slow", 0.0),
                "gwei": _display_gwei("slow")
            },
            "standard": {
                "usd": estimates.get("standard", 0.0),
                "gwei": _display_gwei("standard")
            },
            "fast": {
                "usd": estimates.get("fast", 0.0),
                "gwei": _display_gwei("fast")
            }
        }
