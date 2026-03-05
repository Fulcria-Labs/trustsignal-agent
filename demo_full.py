#!/usr/bin/env python3
"""Full demo script for TrustSignal hackathon submission.

Exercises every endpoint and produces clean, formatted output
suitable for recording a demo video or live presentation.

Usage:
    python demo_full.py [--base-url http://localhost:8004]
"""

import argparse
import json
import sys
import time

import httpx

CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def header(text: str):
    print(f"\n{BOLD}{CYAN}{'=' * 60}{RESET}")
    print(f"{BOLD}{CYAN}  {text}{RESET}")
    print(f"{BOLD}{CYAN}{'=' * 60}{RESET}\n")


def step(num: int, total: int, text: str):
    print(f"{BOLD}[{num}/{total}] {text}{RESET}")


def kv(key: str, value, indent: int = 2):
    print(f"{' ' * indent}{DIM}{key}:{RESET} {value}")


def success(text: str):
    print(f"  {GREEN}{text}{RESET}")


def warn(text: str):
    print(f"  {YELLOW}{text}{RESET}")


def demo(base_url: str = "http://localhost:8004"):
    client = httpx.Client(base_url=base_url, timeout=30)
    total_steps = 8

    header("TrustSignal: AI Trading Agent with ERC-8004 Trust")

    # 1. Health check
    step(1, total_steps, "Health Check")
    r = client.get("/health")
    data = r.json()
    kv("Status", f"{GREEN}{data['status']}{RESET}")
    kv("Timestamp", data["timestamp"])

    # 2. Agent info
    step(2, total_steps, "Agent Identity & Configuration")
    info = client.get("/").json()
    kv("Agent", f"{info['agent']} v{info['version']}")
    kv("Status", f"{GREEN}{info['status']}{RESET}")
    kv("Wallet", info.get("wallet") or f"{YELLOW}Demo mode (no wallet){RESET}")
    kv("x402 Payments", f"{GREEN}Enabled{RESET}" if info["x402_enabled"] else f"{DIM}Disabled (demo){RESET}")
    kv("Endpoints", len(info["endpoints"]))

    # 3. Free signals
    step(3, total_steps, "Free Trading Signals (rate-limited)")
    assets = ["bitcoin", "ethereum", "solana"]
    for asset in assets:
        r = client.get(f"/signal/free?asset={asset}")
        data = r.json()
        if "signal" in data:
            sig = data["signal"]
            direction = sig["direction"]
            color = GREEN if direction == "long" else RED if direction == "short" else YELLOW
            conf = sig["confidence"]
            print(f"  {BOLD}{asset.upper():10s}{RESET} {color}{direction:7s}{RESET} "
                  f"confidence={conf:.0%}  id={DIM}{sig['signal_id']}{RESET}")
        else:
            warn(f"  {asset}: {data.get('error', 'No data')}")
        time.sleep(1.5)

    # 4. Premium signal (full detail)
    step(4, total_steps, "Premium Signal (full analysis - x402 gated in production)")
    r = client.get("/signal/premium?asset=bitcoin")
    if r.status_code == 402:
        warn("Payment Required - x402 active! ($0.01 USDC)")
    else:
        data = r.json()
        if "signal" in data:
            sig = data["signal"]
            direction = sig["direction"]
            color = GREEN if direction == "long" else RED if direction == "short" else YELLOW
            kv("Direction", f"{color}{BOLD}{direction.upper()}{RESET}")
            kv("Confidence", f"{sig['confidence']:.1%}")
            kv("Entry", f"${sig['entry_price']:,.2f}")
            kv("Target", f"${sig['target_price']:,.2f}")
            kv("Stop Loss", f"${sig['stop_loss']:,.2f}")
            kv("Reasoning", sig["reasoning"])
            kv("Signal ID", sig["signal_id"])

    # 5. Watchlist scan
    step(5, total_steps, "Multi-Asset Watchlist Scan")
    r = client.get("/watchlist?assets=bitcoin,ethereum,solana,dogecoin,cardano")
    data = r.json()
    if "watchlist" in data:
        print(f"  {'ASSET':12s} {'PRICE':>12s} {'24h':>8s} {'DIR':>7s} {'CONF':>6s} {'ENTRY':>12s} {'TARGET':>12s}")
        print(f"  {'-' * 75}")
        for item in data["watchlist"]:
            if "error" in item:
                print(f"  {item['asset']:12s} {RED}Error: {item['error']}{RESET}")
                continue
            color = GREEN if item["direction"] == "long" else RED if item["direction"] == "short" else YELLOW
            chg = item.get("change_24h") or 0
            chg_color = GREEN if chg > 0 else RED if chg < 0 else ""
            print(f"  {item['asset']:12s} ${item['price']:>11,.2f} "
                  f"{chg_color}{chg:>+7.1f}%{RESET} "
                  f"{color}{item['direction']:>7s}{RESET} "
                  f"{item['confidence']:>5.0%} "
                  f"${item['entry']:>11,.2f} ${item['target']:>11,.2f}")

    # 6. EIP-712 Trade Intent
    step(6, total_steps, "EIP-712 Signed Trade Intent")
    # Use the last bitcoin signal
    r = client.get("/track-record")
    track = r.json()
    signals = track.get("recent_signals", [])
    btc_signal = next((s for s in signals if s["asset"] == "bitcoin" and s["direction"] != "neutral"), None)
    if btc_signal:
        r = client.post(f"/trade-intent?signal_id={btc_signal['signal_id']}&amount_usd=100")
        if r.status_code == 200:
            intent = r.json()
            ti = intent.get("trade_intent", {})
            kv("Action", f"{BOLD}{intent.get('action', 'N/A').upper()}{RESET}")
            kv("Amount", f"${intent.get('amount_usd', 0):,.2f}")
            kv("Signer", ti.get("signer", "N/A"))
            sig_hex = ti.get("signature", "")
            kv("Signature", f"{sig_hex[:20]}...{sig_hex[-8:]}" if len(sig_hex) > 30 else sig_hex)
            kv("Chain ID", ti.get("domain", {}).get("chainId", "N/A"))
            kv("Deadline", intent.get("deadline_utc", "N/A"))
            success("Trade intent cryptographically signed with EIP-712!")
        elif r.status_code == 400:
            warn(f"Agent not registered on ERC-8004 (demo mode): {r.json().get('error')}")
    else:
        warn("No non-neutral signal available for trade intent demo")

    # 7. ERC-8004 Identity
    step(7, total_steps, "ERC-8004 On-Chain Identity")
    r = client.get("/identity")
    data = r.json()
    if "error" in data:
        warn(f"{data['error']}")
        kv("Note", "In production, agent registers as ERC-721 NFT on Base")
        kv("Registry", "0x8004A818BFB912233c491871b3d84c89A494BD9e")
        kv("Chain", "Base Sepolia (84532)")
    else:
        kv("Wallet", data["wallet"])
        kv("Agent ID", data["agent_id"])
        kv("Chain", data["chain_id"])
        kv("Identity Registry", data["identity_registry"])
        kv("Reputation Registry", data["reputation_registry"])
        success("Agent registered on ERC-8004!")

    # 8. Track record
    step(8, total_steps, "Signal Track Record")
    r = client.get("/track-record")
    stats = r.json()["stats"]
    kv("Total Signals", stats["total_signals"])
    kv("Long", f"{GREEN}{stats['long']}{RESET}")
    kv("Short", f"{RED}{stats['short']}{RESET}")
    kv("Neutral", f"{YELLOW}{stats['neutral']}{RESET}")
    kv("Note", "In production, outcomes are recorded on-chain as reputation feedback")

    header("Demo Complete!")
    print(f"  {BOLD}TrustSignal{RESET} demonstrates the full ERC-8004 agent lifecycle:")
    print(f"  1. {GREEN}Identity{RESET}    - Verifiable on-chain agent registration")
    print(f"  2. {GREEN}Signals{RESET}     - Real-time trading analysis from market data")
    print(f"  3. {GREEN}EIP-712{RESET}     - Cryptographically signed trade intents")
    print(f"  4. {GREEN}x402{RESET}        - Micropayment-gated premium access")
    print(f"  5. {GREEN}Reputation{RESET}  - On-chain outcome tracking builds trust")
    print()
    print(f"  {DIM}Built by an AI agent, for AI agents.{RESET}")
    print(f"  {DIM}github.com/Fulcria-Labs/trustsignal-agent{RESET}")
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TrustSignal Full Demo")
    parser.add_argument("--base-url", default="http://localhost:8004")
    args = parser.parse_args()
    demo(args.base_url)
