import httpx
import base64
import logging
from app.config import settings
import time

logger = logging.getLogger(__name__)

class ZerionClient:
    def __init__(self):
        self.api_key = settings.ZERION_API_KEY
        self.base_url = "https://api.zerion.io"
        
        auth_str = f"{self.api_key}:"
        encoded_auth = base64.b64encode(auth_str.encode()).decode()
        
        self.headers = {
            "Authorization": f"Basic {encoded_auth}",
            "Accept": "application/json"
        }
        
        # Simple cache for gas prices: {chain_id: (timestamp, data)}
        self._gas_cache = {}
        self._cache_ttl = 30  # 30 seconds

    def _normalize_gas_info(self, gas_type: str, info: dict) -> dict:
        """Normalize Zerion gas formats into a stable shape for app consumers."""
        gas_type = (gas_type or "").lower()

        if gas_type == "eip1559":
            return {
                "gas_type": gas_type,
                "base_fee": int(info.get("base_fee") or 0),
                "slow": int((info.get("slow") or {}).get("max_fee") or 0),
                "standard": int((info.get("standard") or {}).get("max_fee") or 0),
                "fast": int((info.get("fast") or {}).get("max_fee") or 0),
                "rapid": int((info.get("rapid") or {}).get("max_fee") or 0),
            }

        if gas_type == "optimistic":
            l2_gas_price = int(info.get("l2") or 0)
            return {
                "gas_type": gas_type,
                "l1": int(info.get("l1") or 0),
                "l2": l2_gas_price,
                "fixed_overhead": int(info.get("fixed_overhead") or 0),
                "dynamic_overhead": int(info.get("dynamic_overhead") or 0),
                # Keep the same speed keys so existing callers can still read values.
                "slow": l2_gas_price,
                "standard": l2_gas_price,
                "fast": l2_gas_price,
                "rapid": l2_gas_price,
            }

        return {
            "gas_type": "classic",
            "slow": int(info.get("slow") or 0),
            "standard": int(info.get("standard") or 0),
            "fast": int(info.get("fast") or 0),
            "rapid": int(info.get("rapid") or 0),
        }

    def _select_preferred_gas_info(self, chain_id: str, gas_options: list[dict]) -> dict:
        """Pick the most useful gas payload when Zerion returns multiple gas types."""
        if not gas_options:
            return {}

        if chain_id == "optimism":
            priority = {"optimistic": 0, "eip1559": 1, "classic": 2}
        else:
            priority = {"eip1559": 0, "classic": 1, "optimistic": 2}

        return sorted(
            gas_options,
            key=lambda item: priority.get(item.get("gas_type", "classic"), 99),
        )[0]

    async def get_portfolio(self, address: str) -> dict:
        url = f"{self.base_url}/v1/wallets/{address}/portfolio"

        async with httpx.AsyncClient(follow_redirects=True) as client:
            logger.info(f"Fetching portfolio for {address}")
            response = await client.get(url, headers=self.headers)

            if response.status_code != 200:
                logger.error(f"Zerion get_portfolio error: {response.status_code} - {response.text}")
                response.raise_for_status()

            data = response.json()
            attributes = data.get("data", {}).get("attributes", {})

            return {
                "total_value": attributes.get("total", {}).get("positions"),
                "change_1d_abs": attributes.get("changes", {}).get("absolute_1d"),
                "change_1d_perc": attributes.get("changes", {}).get("percent_1d")
            }

    async def get_positions(self, address: str, chain: str = None) -> list:
        url = f"{self.base_url}/v1/wallets/{address}/positions/"
        params = {
            "filter[position_types]": "wallet",
            "currency": "usd",
            "sort": "value"
        }
        if chain:
            params["filter[chain_ids]"] = chain

        async with httpx.AsyncClient(follow_redirects=True) as client:
            logger.info(f"Fetching positions for {address} (chain: {chain})")
            response = await client.get(url, params=params, headers=self.headers)

            if response.status_code != 200:
                logger.error(f"Zerion get_positions error: {response.status_code} - {response.text}")
                response.raise_for_status()

            data = response.json()
            positions = []

            for item in data.get("data", []):
                attr = item.get("attributes", {})
                fungible_info = attr.get("fungible_info", {})
                quantity = attr.get("quantity", {})
                positions.append({
                    "name": fungible_info.get("name"),
                    "symbol": fungible_info.get("symbol"),
                    "quantity": quantity.get("float"),
                    "value_usd": attr.get("value"),
                    "price": attr.get("price")
                })

            return positions

    async def get_transactions(self, address: str, limit: int = 20) -> list:
        url = f"{self.base_url}/v1/wallets/{address}/transactions/"
        params = {
            "currency": "usd",
            "page[size]": limit,
            "filter[trash]": "no_filter"
        }

        async with httpx.AsyncClient(follow_redirects=True) as client:
            logger.info(f"Fetching transactions for {address}")
            response = await client.get(url, params=params, headers=self.headers)

            if response.status_code != 200:
                logger.error(f"Zerion get_transactions error: {response.status_code} - {response.text}")
                response.raise_for_status()

            data = response.json()
            transactions = []

            for item in data.get("data", []):
                attr = item.get("attributes", {})
                transactions.append({
                    "type": attr.get("operation_type"),
                    "status": attr.get("status"),
                    "mined_at": attr.get("mined_at"),
                    "transfers": attr.get("transfers", [])
                })

            return transactions

    async def get_swap_offers(
        self, 
        wallet_address: str, 
        input_token: str, 
        output_token: str, 
        amount: str,
        chain_id: str = "ethereum"
    ) -> list:
        """
        Fetches swap offers from Zerion.
        input_token/output_token: symbol (e.g., 'eth') or address
        amount: human readable amount (e.g., '0.1')
        """
        url = f"{self.base_url}/v1/swap/offers/"
        params = {
            "wallet_address": wallet_address,
            "input[fungible_id]": input_token,
            "output[fungible_id]": output_token,
            "input[quantity]": amount,
            "input[chain_id]": chain_id,
            "output[chain_id]": chain_id
        }
        
        async with httpx.AsyncClient(follow_redirects=True) as client:
            logger.info(f"Fetching swap offers for {wallet_address}: {amount} {input_token} -> {output_token}")
            # Zerion docs say GET for offers
            response = await client.get(url, params=params, headers=self.headers, timeout=20.0)
            
            if response.status_code != 200:
                logger.error(f"Zerion get_swap_offers error: {response.status_code} - {response.text}")
                response.raise_for_status()
                
            data = response.json()
            offers = []
            
            for item in data.get("data", []):
                attr = item.get("attributes", {})
                offers.append({
                    "id": item.get("id"),
                    "preconditions": attr.get("preconditions_met", {}),
                    "estimation": attr.get("estimation", {}),
                    "liquidity_source": attr.get("liquidity_source", {}),
                    "transaction": attr.get("transaction", {}),
                    "fee": attr.get("fee", {}),
                    "input_quantity_max": attr.get("input_quantity_max", {}),
                    "output_quantity_min": attr.get("output_quantity_min", {})
                })
                
            return offers

    async def get_swap_quotes(
        self,
        from_address: str,
        to_address: str,
        input_fungible_id: str,
        output_fungible_id: str,
        amount: str,
        input_chain_id: str = "ethereum",
        output_chain_id: str | None = None,
        currency: str = "usd",
    ) -> list:
        """
        Fetch swap quotes from Zerion's quotes endpoint.
        Amount must be a human-readable decimal string, not wei.
        """
        url = f"{self.base_url}/v1/swap/quotes/"
        params = {
            "currency": currency,
            "from": from_address,
            "to": to_address,
            "input[chain_id]": input_chain_id,
            "input[fungible_id]": input_fungible_id,
            "input[amount]": amount,
            "output[fungible_id]": output_fungible_id,
        }
        if output_chain_id:
            params["output[chain_id]"] = output_chain_id

        async with httpx.AsyncClient(follow_redirects=True) as client:
            logger.info(
                "Fetching swap quotes: %s %s on %s -> %s on %s",
                amount,
                input_fungible_id,
                input_chain_id,
                output_fungible_id,
                output_chain_id or input_chain_id,
            )
            response = await client.get(url, params=params, headers=self.headers, timeout=20.0)

            if response.status_code != 200:
                logger.error(f"Zerion get_swap_quotes error: {response.status_code} - {response.text}")
                response.raise_for_status()

            data = response.json()
            quotes = []

            for item in data.get("data", []):
                attr = item.get("attributes", {})
                relationships = item.get("relationships", {})
                quotes.append({
                    "id": item.get("id"),
                    "liquidity_source": attr.get("liquidity_source", {}),
                    "input_amount": attr.get("input_amount", {}),
                    "output_amount": attr.get("output_amount", {}),
                    "minimum_output_amount": attr.get("minimum_output_amount", {}),
                    "output_amount_after_fees": attr.get("output_amount_after_fees", {}),
                    "slippage_percent": attr.get("slippage_percent"),
                    "rate": attr.get("rate", []),
                    "protocol_fee": attr.get("protocol_fee"),
                    "bridge_fee": attr.get("bridge_fee"),
                    "network_fee": attr.get("network_fee"),
                    "transaction_approve": attr.get("transaction_approve"),
                    "transaction_swap": attr.get("transaction_swap"),
                    "error": attr.get("error"),
                    "estimated_time_seconds": attr.get("estimated_time_seconds"),
                    "input_chain": relationships.get("input_chain", {}).get("data", {}),
                    "output_chain": relationships.get("output_chain", {}).get("data", {}),
                    "input_fungible": relationships.get("input_fungible", {}).get("data", {}),
                    "output_fungible": relationships.get("output_fungible", {}).get("data", {}),
                })

            return quotes

    async def get_gas_prices(self, chain_id: str = "ethereum") -> dict:
        """
        Fetches gas prices from Zerion with caching.
        """
        chain_id = (chain_id or "ethereum").strip().lower()
        now = time.time()
        if chain_id in self._gas_cache:
            ts, data = self._gas_cache[chain_id]
            if now - ts < self._cache_ttl:
                return data

        url = f"{self.base_url}/v1/gas-prices/"
        params = {
            "filter[chain_ids]": chain_id,
            "filter[gas_types]": "classic,eip1559,optimistic"
        }
        
        async with httpx.AsyncClient(follow_redirects=True) as client:
            logger.info(f"Fetching gas prices for {chain_id}")
            response = await client.get(url, params=params, headers=self.headers)
            
            if response.status_code != 200:
                logger.error(f"Zerion get_gas_prices error: {response.status_code} - {response.text}")
                # Return empty if fails to not crash
                return {}
                
            data = response.json()
            gas_options = []
            for item in data.get("data", []):
                attr = item.get("attributes", {})
                relationships = item.get("relationships", {})
                item_chain_id = relationships.get("chain", {}).get("data", {}).get("id")
                if item_chain_id and item_chain_id != chain_id:
                    continue

                info = attr.get("info") or {}
                gas_type = attr.get("gas_type")
                if info:
                    gas_options.append(self._normalize_gas_info(gas_type, info))
            
            gas_info = self._select_preferred_gas_info(chain_id, gas_options)
            self._gas_cache[chain_id] = (now, gas_info)
            return gas_info

    async def get_token_price(self, token_id: str = "eth") -> float:
        """
        Fetches the current price of a token in USD.
        token_id: 'eth', 'sol', etc.
        """
        url = f"{self.base_url}/v1/fungibles/{token_id}/"
        
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(url, headers=self.headers)
            if response.status_code != 200:
                return 0.0
            
            data = response.json()
            return data.get("data", {}).get("attributes", {}).get("price", 0.0)
