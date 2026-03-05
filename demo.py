#!/usr/bin/env python3
"""Demo script: exercises the full TrustSignal agent workflow.

Usage:
    python demo.py [--base-url http://localhost:8004]

This demonstrates:
1. Agent health check
2. Free signal generation (multiple assets)
3. Premium signal generation
4. Track record viewing
5. Agent registration on ERC-8004 (if configured)
6. Outcome recording with on-chain reputation
"""

import argparse
import json
import sys
import time

import httpx


def demo(base_url: str = "http://localhost:8004"):
    client = httpx.Client(base_url=base_url, timeout=30)

    print("=" * 60)
    print("  TrustSignal Agent Demo")
    print("=" * 60)

    # 1. Health check
    print("\n[1/6] Health Check")
    r = client.get("/health")
    print(f"  Status: {r.json()['status']}")

    # 2. Agent info
    print("\n[2/6] Agent Info")
    info = client.get("/").json()
    print(f"  Agent: {info['agent']} v{info['version']}")
    print(f"  Wallet: {info.get('wallet', 'Not configured')}")
    print(f"  x402 payments: {'Enabled' if info['x402_enabled'] else 'Disabled'}")
    print(f"  Endpoints: {len(info['endpoints'])}")

    # 3. Free signals for multiple assets
    print("\n[3/6] Free Trading Signals")
    for asset in ["bitcoin", "ethereum"]:
        r = client.get(f"/signal/free?asset={asset}")
        data = r.json()
        if "signal" in data:
            sig = data["signal"]
            print(f"  {asset.upper()}: {sig['direction']} @ {sig['confidence']:.0%} confidence")
        else:
            print(f"  {asset.upper()}: {data.get('error', 'No data')}")
        time.sleep(1)  # Rate limit

    # 4. Premium signal
    print("\n[4/6] Premium Signal (full detail)")
    r = client.get("/signal/premium?asset=bitcoin")
    if r.status_code == 402:
        print("  Payment required (x402 active)")
    else:
        data = r.json()
        if "signal" in data:
            sig = data["signal"]
            print(f"  Direction: {sig['direction']}")
            print(f"  Confidence: {sig['confidence']:.1%}")
            print(f"  Entry: ${sig['entry_price']:,.2f}")
            print(f"  Target: ${sig['target_price']:,.2f}")
            print(f"  Stop: ${sig['stop_loss']:,.2f}")
            print(f"  Reasoning: {sig['reasoning']}")

    # 5. Track record
    print("\n[5/6] Track Record")
    r = client.get("/track-record")
    stats = r.json()["stats"]
    print(f"  Total signals: {stats['total_signals']}")
    print(f"  Long: {stats['long']}, Short: {stats['short']}, Neutral: {stats['neutral']}")

    # 6. Identity
    print("\n[6/6] ERC-8004 Identity")
    r = client.get("/identity")
    data = r.json()
    if "error" in data:
        print(f"  {data['error']} (demo mode)")
    else:
        print(f"  Wallet: {data['wallet']}")
        print(f"  Agent ID: {data['agent_id']}")
        print(f"  Chain: {data['chain_id']}")

    print("\n" + "=" * 60)
    print("  Demo complete!")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TrustSignal Agent Demo")
    parser.add_argument("--base-url", default="http://localhost:8004")
    args = parser.parse_args()
    demo(args.base_url)
