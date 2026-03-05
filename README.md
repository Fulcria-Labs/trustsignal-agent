# TrustSignal: AI Trading Signal Agent with ERC-8004 Trust

An autonomous AI trading signal agent that earns verifiable trust through ERC-8004 registries and monetizes signals via x402 micropayments.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  TrustSignal Agent                    │
├──────────┬──────────┬──────────┬────────────────────┤
│ Strategy │ Signal   │ Trust    │ Payment            │
│ Engine   │ Publisher│ Manager  │ Gateway (x402)     │
└──────────┴──────────┴──────────┴────────────────────┘
                         │
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
   ERC-8004 Identity  Reputation    Validation
   Registry           Registry      Registry
         Base Sepolia / Base Mainnet
```

## Features

1. **AI-Powered Trading Signals**: Analyzes crypto market data
2. **ERC-8004 Identity**: Agent registers on-chain with verifiable identity NFT
3. **Reputation Building**: Trading performance recorded as on-chain reputation signals
4. **x402 Payment Gate**: Premium signals require USDC micropayment
5. **Transparent Track Record**: All predictions and outcomes verifiable on-chain

## Tech Stack

- Python (FastAPI), chaoschain-sdk / web3.py, x402, Claude API, Base Sepolia
