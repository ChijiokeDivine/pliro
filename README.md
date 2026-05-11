# Pliro

> AI-powered self-custodial crypto wallet bot for Telegram — EVM + Solana, built with LangChain, Privy, and Zerion.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [How It Works](#how-it-works)
  - [Agent](#agent)
  - [Wallet Infrastructure](#wallet-infrastructure)
  - [On-Chain Data](#on-chain-data)
  - [Database](#database)
- [Features](#features)
- [Prerequisites](#prerequisites)
- [Environment Variables](#environment-variables)
- [Installation](#installation)
- [Running the Bot](#running-the-bot)
- [API Endpoints](#api-endpoints)
- [Database Schema](#database-schema)
- [Supported Chains](#supported-chains)
- [Roadmap](#roadmap)

---

## Overview
<img width="1369" height="813" alt="image" src="https://github.com/user-attachments/assets/696d4fd9-d262-4278-8adc-f6df1d4b43c7" />



Pliro is a Telegram-native crypto wallet assistant. Users interact entirely through natural language — no UI, no browser extension. The bot provisions self-custodial EVM and Solana wallets per user, and exposes wallet operations (balance, send, history, swap) through an LLM agent that interprets intent and calls the appropriate on-chain services.

Wallets are non-custodial from the user's perspective — keys are managed by Privy's server wallet infrastructure and never exposed to Pliro's backend. On-chain data (balances, positions, transactions, gas) is sourced from Zerion's unified API.

---

## Architecture

```
Telegram User
      │
      ▼
Telegram Bot (python-telegram-bot)
      │
      ├── Inline buttons → handlers.py (direct API calls, no agent)
      │
      └── Natural language → agent.py
                │
                ▼
          LangChain ReAct Agent (Groq / Llama 3.3 70B)
                │
                ├── get_or_create_wallet
                ├── get_wallet_addresses
                ├── get_portfolio_summary
                ├── get_token_positions
                ├── get_transaction_history
                ├── get_send_preview      ← gas estimation, no execution
                └── send_crypto          ← requires prior preview + user confirmation
                          │
                          ├── Privy API  (wallet creation, transaction signing & broadcast)
                          └── Zerion API (portfolio, positions, transactions, gas prices)
```

The bot operates on two distinct paths:

- **Button path** — inline keyboard actions (Portfolio, Tokens, Addresses, History, Gas) bypass the agent entirely and call Zerion/Privy directly for lower latency.
- **Chat path** — free-text messages are routed to the LangChain ReAct agent, which reasons over the input, selects tools, and returns a formatted response.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Bot framework | `python-telegram-bot` v21 |
| LLM | Groq API — `llama-3.3-70b-versatile` |
| Agent framework | LangChain `create_react_agent` + `AgentExecutor` |
| Wallet infra | Privy server wallets (EVM + Solana) |
| On-chain data | Zerion Unified API v1 |
| Database | PostgreSQL via SQLAlchemy (async) + Alembic |
| Runtime | Python 3.12, `asyncio`, `httpx` |
| Server | FastAPI + Uvicorn (webhook receiver) |

---

## Project Structure

```
pliro/
├── app/
│   ├── bot/
│   │   ├── agent.py          # LangChain ReAct agent, prompt, AgentExecutor
│   │   ├── handlers.py       # Telegram update handlers, button callbacks
│   │   └── ui_formatters.py  # HTML message formatters, keyboard builders
│   ├── tools/
│   │   └── wallet_tools.py   # LangChain @tool definitions
│   ├── wallet/
│   │   ├── privy.py          # Privy API client (wallet creation, tx broadcast)
│   │   ├── zerion.py         # Zerion API client (portfolio, positions, gas)
│   │   └── gas.py            # Gas estimation service
│   ├── db/
│   │   ├── models.py         # SQLAlchemy ORM models
│   │   ├── crud.py           # Async DB operations
│   │   └── database.py       # Async engine, session factory
│   ├── config.py             # Pydantic settings (env vars)
│   └── main.py               # FastAPI app, webhook registration
├── alembic/                  # DB migrations
├── .env
└── requirements.txt
```

---

## How It Works

### Agent

The agent is a standard LangChain **ReAct** (Reason + Act) agent backed by Llama 3.3 70B via Groq. Each user message is passed to the agent with the Telegram user ID appended. The agent:

1. Reasons about what tool to call based on the user's intent.
2. Calls the appropriate tool with a JSON payload including the `telegram_user_id`.
3. Observes the tool's return value.
4. Repeats until it has enough information to write a `Final Answer`.

The agent is stateless between invocations. Chat history (last 5 turns) is maintained in memory per user (`chat_histories` dict in `handlers.py`) and injected into the prompt on each call.

**Send flow specifically:**

The agent is instructed to never call `send_crypto` without first calling `get_send_preview` and presenting it to the user. After the preview is displayed, a confirmation keyboard is injected by `handlers.py`. The actual transaction is executed only on button confirmation (`confirm_send` callback), which calls Privy directly — bypassing the agent entirely to avoid re-reasoning overhead.

**Agent configuration:**
```
max_iterations     = 5
max_execution_time = 30s
handle_parsing_errors = True
```

### Wallet Infrastructure

Wallets are created and managed by **Privy** server wallets. On a user's first interaction, Pliro provisions:

- One EVM wallet (covers Ethereum, Base, Arbitrum, BNB Chain, Polygon, Optimism, Celo)
- One Solana wallet

Wallet IDs and public addresses are stored in PostgreSQL. Private keys never touch Pliro's backend — signing happens inside Privy's infrastructure.

**Transaction broadcast** uses Privy's `/v1/wallets/{wallet_id}/rpc` endpoint with `eth_sendTransaction`. The chain is specified via the `caip2` field (`eip155:{chain_id}`), not inside the transaction object.

```python
payload = {
    "method": "eth_sendTransaction",
    "caip2":  "eip155:1",
    "params": {
        "transaction": {
            "to":    "0x...",
            "value": "0x...",
            # chainId intentionally omitted — Privy rejects it
        }
    }
}
```

### On-Chain Data

All portfolio and market data is sourced from **Zerion's Unified API v1**:

| Zerion Endpoint | Used For |
|---|---|
| `/v1/wallets/{address}/portfolio` | Total value, 24h change |
| `/v1/wallets/{address}/positions/` | Token balances by chain |
| `/v1/wallets/{address}/transactions/` | Transaction history |
| `/v1/gas-prices/` | Gas estimation (cached 30s) |
| `/v1/swap/offers/` | Swap routing and quotes |
| `/v1/fungibles/{token_id}/` | Token price lookup |

Gas prices are cached in-memory with a 30-second TTL to avoid redundant API calls on every send preview.

### Database

PostgreSQL with SQLAlchemy async ORM. Two tables:

- `telegram_users` — maps Telegram user IDs to internal UUIDs.
- `user_wallets` — stores EVM and Solana addresses and their corresponding Privy wallet IDs.

Migrations are managed with **Alembic**.

---

## Features

- **Natural language wallet control** — send, check balance, view history via chat
- **Multi-chain EVM support** — Ethereum, Base, Arbitrum, BNB Chain, Polygon, Optimism, Celo
- **Solana support** — token balance viewing (send coming soon)
- **Self-custodial wallets** — provisioned per user via Privy, keys never exposed
- **Send preview before execution** — gas estimate shown, confirmation required
- **Inline keyboard UI** — quick access to Portfolio, Tokens, Addresses, History, Gas
- **Token swap** — guided swap flow via `/swap` command (Zerion routing)
- **Gas price display** — live standard/fast/instant fee estimates
- **Graceful error handling** — insufficient funds, broadcast failures surfaced cleanly

---

## Prerequisites

- Python 3.12+
- PostgreSQL 14+
- A publicly accessible HTTPS URL (for Telegram webhook) — use [ngrok](https://ngrok.com) locally
- API keys for: Telegram Bot API, Groq, Privy, Zerion

---

## Environment Variables

Create a `.env` file in the project root:

```env
# Telegram
TELEGRAM_BOT_TOKEN=

# Groq
GROQ_API_KEY=

# Privy
NEXT_PUBLIC_PRIVY_APP_ID=
PRIVY_APP_SECRET=

# Zerion
ZERION_API_KEY=

# Database
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/pliro

# Webhook
WEBHOOK_URL=https://your-domain.com/api/v1/bot/webhook
```

---

## Installation

```bash
# Clone the repository
git clone https://github.com/yourname/pliro.git
cd pliro

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run database migrations
alembic upgrade head
```

---

## Running the Bot

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

On startup, the FastAPI app registers the Telegram webhook at `WEBHOOK_URL`. Telegram will POST all updates to `/api/v1/bot/webhook`.

For local development with ngrok:

```bash
ngrok http 8000
# Copy the HTTPS forwarding URL → set as WEBHOOK_URL in .env
# Restart uvicorn
```

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/bot/webhook` | Telegram webhook receiver |
| `GET` | `/health` | Health check |

---

## Database Schema

```sql
-- Users
CREATE TABLE telegram_users (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_id BIGINT UNIQUE NOT NULL,
    username    TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Wallets (one per user)
CREATE TABLE user_wallets (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 UUID UNIQUE REFERENCES telegram_users(id) ON DELETE CASCADE,
    evm_address             TEXT NOT NULL,
    solana_address          TEXT NOT NULL,
    privy_evm_wallet_id     TEXT NOT NULL,
    privy_solana_wallet_id  TEXT NOT NULL,
    created_at              TIMESTAMPTZ DEFAULT NOW()
);
```

---

## Supported Chains

| Chain | CAIP-2 | Native Token |
|---|---|---|
| Ethereum | eip155:1 | ETH |
| Base | eip155:8453 | ETH |
| Arbitrum | eip155:42161 | ETH |
| BNB Chain | eip155:56 | BNB |
| Polygon | eip155:137 | POL |
| Optimism | eip155:10 | ETH |
| Celo | eip155:42220 | CELO |
| Solana | — | SOL |

---

## Roadmap

- [ ] Solana native token sends
- [ ] ERC-20 token sends
- [ ] Multi-chain send (auto chain detection from token)
- [ ] Push notifications for incoming transactions
- [ ] Persistent chat history (database-backed)
- [ ] Rate limiting per user
- [ ] WalletConnect integration
