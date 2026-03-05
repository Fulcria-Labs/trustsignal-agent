"""TrustSignal: AI Trading Agent with ERC-8004 Trust & x402 Payments.

An autonomous trading signal agent that:
1. Registers on-chain via ERC-8004 Identity Registry
2. Generates trading signals from crypto market data
3. Gates premium signals behind x402 micropayments
4. Records prediction outcomes as on-chain reputation
"""

import json
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

from erc8004_client import ERC8004Client
from signal_engine import SignalEngine

load_dotenv()

# === Configuration ===
PRIVATE_KEY = os.getenv("PRIVATE_KEY", "")
WALLET_ADDRESS = os.getenv("WALLET_ADDRESS", "")
RPC_URL = os.getenv("RPC_URL", "https://sepolia.base.org")
CHAIN_ID = int(os.getenv("CHAIN_ID", "84532"))
IDENTITY_REGISTRY = os.getenv("IDENTITY_REGISTRY", "0x8004A818BFB912233c491871b3d84c89A494BD9e")
REPUTATION_REGISTRY = os.getenv("REPUTATION_REGISTRY", "0x8004B663056A597Dffe9eCcC1965A193B7388713")
PAY_TO = os.getenv("PAY_TO", WALLET_ADDRESS)
FACILITATOR_URL = os.getenv("FACILITATOR_URL", "https://www.x402.org/facilitator")
USDC_ADDRESS = os.getenv("USDC_ADDRESS", "0x036CbD53842c5426634e7929541eC2318f3dCF7e")
NETWORK = os.getenv("NETWORK", "eip155:84532")

# === State ===
agent_id: int | None = None
erc8004: ERC8004Client | None = None
engine = SignalEngine()


def setup_x402_middleware(app: FastAPI):
    """Set up x402 payment middleware for premium endpoints."""
    if not PAY_TO:
        print("No PAY_TO address - x402 payment gating disabled")
        return False
    try:
        from x402 import x402ResourceServer
        from x402.http.middleware.fastapi import payment_middleware

        facilitator_url = FACILITATOR_URL
        # Create facilitator client
        try:
            from x402.http import HTTPFacilitatorClient
            facilitator = HTTPFacilitatorClient(facilitator_url)
        except ImportError:
            from x402 import FacilitatorClient
            facilitator = FacilitatorClient(facilitator_url)

        server = x402ResourceServer(facilitator)

        routes = {
            "GET /signal/premium": {
                "accepts": {
                    "scheme": "exact",
                    "payTo": PAY_TO,
                    "price": "$0.01",
                    "network": NETWORK,
                },
                "description": "Premium real-time trading signal with AI analysis",
            },
        }

        mw = payment_middleware(routes, server, sync_facilitator_on_start=True)

        @app.middleware("http")
        async def x402_mw(request, call_next):
            return await mw(request, call_next)

        return True
    except Exception as e:
        print(f"x402 middleware setup failed (running without payments): {e}")
        return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize ERC-8004 client and register agent on startup."""
    global agent_id, erc8004

    if PRIVATE_KEY:
        try:
            erc8004 = ERC8004Client(
                rpc_url=RPC_URL,
                private_key=PRIVATE_KEY,
                identity_registry=IDENTITY_REGISTRY,
                reputation_registry=REPUTATION_REGISTRY,
                chain_id=CHAIN_ID,
            )
            print(f"ERC-8004 client initialized. Wallet: {erc8004.address}")
        except Exception as e:
            print(f"ERC-8004 init failed: {e}")
    else:
        print("No PRIVATE_KEY set - running in demo mode (no on-chain features)")

    yield


app = FastAPI(
    title="TrustSignal Agent",
    description="AI trading signal agent with ERC-8004 trust and x402 payments",
    version="0.1.0",
    lifespan=lifespan,
)

# Try to set up x402 payment gating
x402_enabled = setup_x402_middleware(app)


# === Registration File ===
REGISTRATION_FILE = {
    "type": "AgentRegistration",
    "name": "TrustSignal Agent",
    "description": "Autonomous AI trading signal agent. Generates crypto trading signals "
    "with verifiable on-chain track record via ERC-8004 reputation.",
    "image": "https://raw.githubusercontent.com/Fulcria-Labs/trustsignal-agent/main/logo.png",
    "services": [
        {
            "type": "api",
            "url": "https://trustsignal.fulcria.com",
            "description": "Trading signal API with x402 payment gating",
        }
    ],
    "supportedTrust": ["reputation"],
}


# === API Endpoints ===


@app.get("/")
async def root():
    """Agent info and status."""
    return {
        "agent": "TrustSignal",
        "version": "0.1.0",
        "status": "active",
        "agent_id": agent_id,
        "wallet": erc8004.address if erc8004 else None,
        "x402_enabled": x402_enabled,
        "endpoints": {
            "/signal/free": "Free delayed trading signal",
            "/signal/premium": "Premium real-time signal (x402 payment required)",
            "/identity": "ERC-8004 agent identity info",
            "/reputation": "On-chain reputation summary",
            "/track-record": "Signal generation statistics",
            "/register": "Register agent on ERC-8004 (POST)",
        },
    }


@app.get("/health")
async def health():
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/signal/free")
async def free_signal(asset: str = Query(default="bitcoin", description="CoinGecko coin ID")):
    """Free trading signal (delayed, less detail)."""
    try:
        market_data = await engine.get_market_data(asset)
        signal = engine.analyze_technicals(market_data)
        # Free tier: redact some fields
        return {
            "tier": "free",
            "signal": {
                "asset": signal.asset,
                "direction": signal.direction.value,
                "confidence": round(signal.confidence, 1),  # rounded
                "timeframe": signal.timeframe,
                "timestamp": signal.timestamp,
                "signal_id": signal.signal_id,
            },
            "note": "Upgrade to premium for entry/target/stop prices and full reasoning",
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/signal/premium")
async def premium_signal(asset: str = Query(default="bitcoin", description="CoinGecko coin ID")):
    """Premium real-time trading signal (x402 payment required)."""
    try:
        market_data = await engine.get_market_data(asset)
        signal = engine.analyze_technicals(market_data)
        return {
            "tier": "premium",
            "signal": signal.to_dict(),
            "market_data": {
                "current_price": market_data["current_price"],
                "change_24h": market_data.get("change_24h"),
            },
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/identity")
async def identity():
    """Get agent's ERC-8004 identity information."""
    if not erc8004:
        return {"error": "ERC-8004 not configured"}
    info = {
        "wallet": erc8004.address,
        "agent_id": agent_id,
        "chain_id": CHAIN_ID,
        "identity_registry": IDENTITY_REGISTRY,
        "reputation_registry": REPUTATION_REGISTRY,
        "registration_file": REGISTRATION_FILE,
    }
    if agent_id is not None:
        try:
            uri = erc8004.get_agent_uri(agent_id)
            info["agent_uri"] = uri
        except Exception:
            pass
    return info


@app.get("/reputation")
async def reputation(
    client_addresses: str = Query(
        default="",
        description="Comma-separated client addresses for reputation query",
    ),
):
    """Get agent's on-chain reputation summary."""
    if not erc8004 or agent_id is None:
        return {"error": "Agent not registered on ERC-8004"}
    if not client_addresses:
        return {"error": "Provide client_addresses parameter"}
    try:
        addresses = [a.strip() for a in client_addresses.split(",")]
        summary = erc8004.get_summary(agent_id, addresses)
        return {"agent_id": agent_id, "reputation": summary}
    except Exception as e:
        return {"error": str(e)}


@app.get("/track-record")
async def track_record():
    """Get signal generation track record."""
    return {
        "agent_id": agent_id,
        "stats": engine.get_track_record(),
        "recent_signals": [s.to_dict() for s in engine.signals_history[-10:]],
    }


@app.post("/register")
async def register_agent():
    """Register agent on ERC-8004 Identity Registry."""
    global agent_id
    if not erc8004:
        return JSONResponse(status_code=400, content={"error": "ERC-8004 not configured"})
    if agent_id is not None:
        return {"message": "Already registered", "agent_id": agent_id}
    try:
        # For hackathon demo, use inline JSON URI
        uri = "data:application/json;base64," + __import__("base64").b64encode(
            json.dumps(REGISTRATION_FILE).encode()
        ).decode()
        agent_id = erc8004.register_agent(uri)
        return {
            "message": "Agent registered successfully",
            "agent_id": agent_id,
            "tx": "confirmed",
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/record-outcome")
async def record_outcome(
    signal_id: str = Query(..., description="Signal ID to record outcome for"),
    outcome_price: float = Query(..., description="Actual price at prediction window end"),
):
    """Record a signal outcome and post reputation feedback on-chain."""
    if not erc8004 or agent_id is None:
        return JSONResponse(status_code=400, content={"error": "Agent not registered"})

    # Find the signal
    signal = next((s for s in engine.signals_history if s.signal_id == signal_id), None)
    if not signal:
        return JSONResponse(status_code=404, content={"error": "Signal not found"})

    # Calculate accuracy
    if signal.direction.value == "long":
        correct = outcome_price > signal.entry_price
        pnl_pct = ((outcome_price - signal.entry_price) / signal.entry_price) * 100
    elif signal.direction.value == "short":
        correct = outcome_price < signal.entry_price
        pnl_pct = ((signal.entry_price - outcome_price) / signal.entry_price) * 100
    else:
        correct = True
        pnl_pct = 0

    # Post as reputation feedback (value = PnL basis points, 2 decimals)
    value = int(pnl_pct * 100)  # basis points
    try:
        erc8004.give_feedback(
            agent_id=agent_id,
            value=value,
            value_decimals=2,
            tag1="trading_signal",
            tag2=signal.asset,
        )
        return {
            "signal_id": signal_id,
            "correct": correct,
            "pnl_pct": round(pnl_pct, 2),
            "reputation_posted": True,
            "on_chain_value": value,
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8004)
