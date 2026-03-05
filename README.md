# TrustSignal: AI Trading Agent with ERC-8004 Trust

An autonomous AI trading signal agent that earns verifiable on-chain trust through ERC-8004 registries and monetizes premium signals via x402 micropayments.

Built for the [ERC-8004 AI Trading Agents Hackathon](https://lablab.ai/ai-hackathons/ai-trading-agents-erc-8004) (March 9-22, 2026).

## Architecture

```
                    ┌──────────────────────────────────┐
                    │        TrustSignal Agent          │
                    ├──────────┬───────────┬────────────┤
                    │ Signal   │ EIP-712   │ x402       │
                    │ Engine   │ Intents   │ Payments   │
                    └────┬─────┴─────┬─────┴──────┬─────┘
                         │           │            │
      CoinGecko ─────────┘           │            │
      Market Data                    │            │
                         ┌───────────┴────────────┘
                         ▼
              ERC-8004 Registries (Base Sepolia)
              ├── Identity Registry (ERC-721)
              ├── Reputation Registry
              └── Validation Registry
```

## Key Features

1. **Technical Analysis Engine** - SMA crossover, RSI, momentum, volatility scoring with composite signal generation
2. **ERC-8004 Agent Identity** - On-chain registration with verifiable identity NFT
3. **EIP-712 Signed Trade Intents** - Cryptographically signed, typed trade decisions for auditability and on-chain execution
4. **On-Chain Reputation** - Trading outcomes recorded as reputation feedback (PnL in basis points)
5. **x402 Payment Gating** - Premium signals require USDC micropayment ($0.01/request)
6. **Multi-Asset Watchlist** - Scan multiple assets simultaneously for trading opportunities
7. **Transparent Track Record** - All predictions, outcomes, and reputation verifiable on-chain

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Agent info and status |
| `/health` | GET | Health check |
| `/signal/free` | GET | Free signal (limited detail) |
| `/signal/premium` | GET | Premium signal with full analysis (x402 gated) |
| `/watchlist` | GET | Multi-asset signal scan |
| `/trade-intent` | POST | Create EIP-712 signed trade intent from signal |
| `/identity` | GET | ERC-8004 identity info |
| `/reputation` | GET | On-chain reputation summary |
| `/track-record` | GET | Signal generation statistics |
| `/backtest` | GET | Historical backtest with win rate and Sharpe ratio |
| `/register` | POST | Register agent on ERC-8004 |
| `/record-outcome` | POST | Record signal outcome as reputation |

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run in demo mode (no on-chain features)
python main.py

# Run with ERC-8004 (needs Base Sepolia ETH)
cp .env.example .env
# Edit .env with your private key
python main.py
```

## Demo

```bash
# Start the server
python main.py &

# Run the demo script
python demo.py
```

## EIP-712 Trade Intents

TrustSignal creates cryptographically signed trade intents per ERC-8004 requirements:

```json
{
  "domain": {
    "name": "TrustSignal",
    "version": "1",
    "chainId": 84532,
    "verifyingContract": "0x8004A818BFB912233c491871b3d84c89A494BD9e"
  },
  "types": {
    "TradeIntent": [
      {"name": "agentId", "type": "uint256"},
      {"name": "action", "type": "string"},
      {"name": "asset", "type": "string"},
      {"name": "amountUsd", "type": "uint256"},
      {"name": "price", "type": "uint256"},
      {"name": "signalId", "type": "string"},
      {"name": "deadline", "type": "uint256"},
      {"name": "nonce", "type": "uint256"}
    ]
  }
}
```

Each intent is signed with the agent's private key, binding trade decisions to the registered on-chain identity. Intents can be verified by any party and submitted to a Risk Router for execution.

## Signal Engine

The technical analysis engine uses:
- **SMA Crossover** (5/10 period) - Trend direction
- **RSI** - Overbought/oversold detection with reversal signals
- **Momentum** - Price change relative to recent range
- **Volatility** - Normalized standard deviation for dynamic risk sizing
- **Composite Score** - Weighted combination (40% trend + 30% momentum + 30% RSI)

## Tech Stack

- **Python 3.12** + FastAPI
- **web3.py** + eth-account (EIP-712 signing)
- **chaoschain-sdk** (ERC-8004 contract interaction)
- **x402** (payment middleware)
- **httpx** (async HTTP for market data)
- **Base Sepolia** testnet

## Configuration

See `.env.example` for all configuration options.

## License

MIT
