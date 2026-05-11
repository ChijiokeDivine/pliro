import httpx
import base64
import logging
from app.config import settings

logger = logging.getLogger(__name__)

EVM_CHAINS = {
    "ethereum": 1,
    "base":     8453,
    "arbitrum": 42161,
    "bnb":      56,
    "polygon":  137,
    "optimism": 10,
    "celo":     42220,
}

class PrivyClient:
    def __init__(self):
        self.app_id     = settings.NEXT_PUBLIC_PRIVY_APP_ID
        self.app_secret = settings.PRIVY_APP_SECRET
        self.base_url   = "https://api.privy.io/v1"

        auth_str     = f"{self.app_id}:{self.app_secret}"
        encoded_auth = base64.b64encode(auth_str.encode()).decode()

        self.headers = {
            "Authorization": f"Basic {encoded_auth}",
            "privy-app-id":  self.app_id,
            "Content-Type":  "application/json",
            "Accept":        "application/json",
        }

    async def create_wallet(self, chain_type: str) -> dict:
        """chain_type: 'ethereum' or 'solana'"""
        url     = f"{self.base_url}/wallets"
        payload = {"chain_type": chain_type}

        async with httpx.AsyncClient() as client:
            logger.info(f"Creating {chain_type} wallet via Privy")
            response = await client.post(url, json=payload, headers=self.headers)

            if response.status_code != 201:
                logger.error(f"Privy create_wallet error: {response.status_code} - {response.text}")
                response.raise_for_status()

            data = response.json()
            logger.info(f"Successfully created {chain_type} wallet: {data.get('address')}")
            return data

    async def send_evm_transaction(
        self,
        wallet_id:  str,
        to_address: str,
        value_hex:  str,
        chain:      str = "ethereum",
        chain_id:   int = None,       # kept for swap compat, derived from chain if None
        data_hex:   str = None,
        gas_hex:    str = None,
    ) -> str:
        # Resolve chain_id from name if not provided directly
        if chain_id is None:
            chain_id = EVM_CHAINS.get(chain.lower())
            if not chain_id:
                raise ValueError(f"Unsupported chain: {chain}")

        # ✅ chainId must NOT be inside transaction — Privy rejects it
        transaction: dict = {
            "to":    to_address,
            "value": value_hex,
        }
        if data_hex:
            transaction["data"] = data_hex
        if gas_hex:
            transaction["gas"] = gas_hex

        payload = {
            "method": "eth_sendTransaction",
            "caip2":  f"eip155:{chain_id}",   # ✅ chain specified here only
            "params": {
                "transaction": transaction
            },
        }

        async with httpx.AsyncClient() as client:
            logger.info(f"Sending transaction on eip155:{chain_id} from wallet {wallet_id}")
            response = await client.post(
                f"{self.base_url}/wallets/{wallet_id}/rpc",
                json=payload,
                headers=self.headers,
            )

            if response.status_code != 200:
                logger.error(f"Privy send_evm_transaction error: {response.status_code} - {response.text}")
                
                # Parse Privy error and raise clean exceptions
                try:
                    error_body = response.json()
                    error_msg  = error_body.get("error", "")
                    error_code = error_body.get("code", "")

                    if error_code == "transaction_broadcast_failure":
                        if "insufficient funds" in error_msg:
                            raise ValueError("insufficient_funds")
                        raise ValueError(f"broadcast_failed: {error_msg}")

                except (ValueError, KeyError):
                    raise  # re-raise our clean ValueError
                except Exception:
                    pass   # fall through to raise_for_status

                response.raise_for_status()

            data     = response.json()
            tx_hash  = data.get("result")
            logger.info(f"Transaction sent: {tx_hash}")
            return tx_hash

    async def send_solana_transaction(self, wallet_id: str, serialized_tx_base64: str) -> str:
        payload = {
            "method": "solana_signAndSendTransaction",
            "params": {
                "transaction": serialized_tx_base64
            },
        }

        async with httpx.AsyncClient() as client:
            logger.info(f"Sending Solana transaction from {wallet_id}")
            response = await client.post(
                f"{self.base_url}/wallets/{wallet_id}/rpc",
                json=payload,
                headers=self.headers,
            )

            if response.status_code != 200:
                logger.error(f"Privy send_solana_transaction error: {response.status_code} - {response.text}")
                response.raise_for_status()

            data         = response.json()
            tx_signature = data.get("result")
            logger.info(f"Solana transaction sent: {tx_signature}")
            return tx_signature