"""Backtesting engine for TrustSignal signal validation.

Fetches historical OHLC data and replays the signal engine to compute
win rate, average PnL, and Sharpe ratio. Results demonstrate that the
agent's on-chain reputation reflects real predictive ability.

Usage:
    python backtest.py [--asset bitcoin] [--days 30]
"""

import argparse
import asyncio
import time
from dataclasses import dataclass

import httpx

from signal_engine import Direction, SignalEngine


@dataclass
class BacktestResult:
    asset: str
    total_signals: int
    long_signals: int
    short_signals: int
    neutral_signals: int
    wins: int
    losses: int
    win_rate: float
    avg_pnl_pct: float
    total_pnl_pct: float
    max_win_pct: float
    max_loss_pct: float
    sharpe_ratio: float
    signals: list


COINGECKO_URL = "https://api.coingecko.com/api/v3"


async def fetch_historical_ohlc(asset: str, days: int) -> list:
    """Fetch historical OHLC data from CoinGecko."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{COINGECKO_URL}/coins/{asset}/ohlc",
            params={"vs_currency": "usd", "days": str(days)},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()


def run_backtest(ohlc_data: list, asset: str, lookahead: int = 6) -> BacktestResult:
    """Run backtest over historical OHLC candles.

    For each window of 20 candles, generate a signal, then check
    the next `lookahead` candles for outcome.
    """
    engine = SignalEngine()
    signals = []
    pnls = []
    wins = 0
    losses = 0

    window = 20
    if len(ohlc_data) < window + lookahead:
        return BacktestResult(
            asset=asset, total_signals=0, long_signals=0, short_signals=0,
            neutral_signals=0, wins=0, losses=0, win_rate=0, avg_pnl_pct=0,
            total_pnl_pct=0, max_win_pct=0, max_loss_pct=0, sharpe_ratio=0,
            signals=[],
        )

    for i in range(window, len(ohlc_data) - lookahead, lookahead):
        candles = ohlc_data[i - window:i]
        future_candles = ohlc_data[i:i + lookahead]

        current_price = candles[-1][4]  # close of last candle
        future_price = future_candles[-1][4]  # close of lookahead candle

        market_data = {
            "coin_id": asset,
            "current_price": current_price,
            "change_24h": ((current_price - candles[-2][4]) / candles[-2][4]) * 100 if candles[-2][4] else 0,
            "ohlc": candles,
        }

        signal = engine.analyze_technicals(market_data)

        if signal.direction == Direction.NEUTRAL:
            signals.append({
                "timestamp": candles[-1][0],
                "direction": "neutral",
                "confidence": signal.confidence,
                "entry": current_price,
                "outcome": future_price,
                "pnl_pct": 0,
                "correct": None,
            })
            continue

        if signal.direction == Direction.LONG:
            pnl_pct = ((future_price - current_price) / current_price) * 100
            correct = future_price > current_price
        else:  # SHORT
            pnl_pct = ((current_price - future_price) / current_price) * 100
            correct = future_price < current_price

        pnls.append(pnl_pct)
        if correct:
            wins += 1
        else:
            losses += 1

        signals.append({
            "timestamp": candles[-1][0],
            "direction": signal.direction.value,
            "confidence": signal.confidence,
            "entry": round(current_price, 2),
            "outcome": round(future_price, 2),
            "pnl_pct": round(pnl_pct, 3),
            "correct": correct,
        })

    total_trades = wins + losses
    win_rate = wins / total_trades if total_trades > 0 else 0
    avg_pnl = sum(pnls) / len(pnls) if pnls else 0
    total_pnl = sum(pnls)

    # Sharpe ratio (simplified: mean / std of returns)
    if len(pnls) > 1:
        mean_r = sum(pnls) / len(pnls)
        var_r = sum((r - mean_r) ** 2 for r in pnls) / (len(pnls) - 1)
        std_r = var_r ** 0.5
        sharpe = mean_r / std_r if std_r > 0 else 0
    else:
        sharpe = 0

    return BacktestResult(
        asset=asset,
        total_signals=len(signals),
        long_signals=sum(1 for s in signals if s["direction"] == "long"),
        short_signals=sum(1 for s in signals if s["direction"] == "short"),
        neutral_signals=sum(1 for s in signals if s["direction"] == "neutral"),
        wins=wins,
        losses=losses,
        win_rate=round(win_rate, 3),
        avg_pnl_pct=round(avg_pnl, 3),
        total_pnl_pct=round(total_pnl, 3),
        max_win_pct=round(max(pnls), 3) if pnls else 0,
        max_loss_pct=round(min(pnls), 3) if pnls else 0,
        sharpe_ratio=round(sharpe, 3),
        signals=signals,
    )


def print_report(result: BacktestResult):
    """Print formatted backtest report."""
    print(f"\n{'=' * 60}")
    print(f"  TrustSignal Backtest: {result.asset.upper()}")
    print(f"{'=' * 60}\n")

    print(f"  Total Signals:   {result.total_signals}")
    print(f"  Long:            {result.long_signals}")
    print(f"  Short:           {result.short_signals}")
    print(f"  Neutral (skip):  {result.neutral_signals}")
    print()

    total_trades = result.wins + result.losses
    print(f"  Trades Taken:    {total_trades}")
    print(f"  Wins:            {result.wins}")
    print(f"  Losses:          {result.losses}")
    print(f"  Win Rate:        {result.win_rate:.1%}")
    print()

    print(f"  Avg PnL/Trade:   {result.avg_pnl_pct:+.3f}%")
    print(f"  Total PnL:       {result.total_pnl_pct:+.3f}%")
    print(f"  Max Win:         {result.max_win_pct:+.3f}%")
    print(f"  Max Loss:        {result.max_loss_pct:+.3f}%")
    print(f"  Sharpe Ratio:    {result.sharpe_ratio:.3f}")
    print()

    # Show last 10 signals
    recent = [s for s in result.signals if s["direction"] != "neutral"][-10:]
    if recent:
        print(f"  {'DIR':>5s} {'CONF':>5s} {'ENTRY':>10s} {'OUTCOME':>10s} {'PnL':>8s} {'OK':>3s}")
        print(f"  {'-' * 47}")
        for s in recent:
            ok = "Y" if s["correct"] else "N"
            print(f"  {s['direction']:>5s} {s['confidence']:>5.0%} "
                  f"${s['entry']:>9,.2f} ${s['outcome']:>9,.2f} "
                  f"{s['pnl_pct']:>+7.3f}% {ok:>3s}")

    print(f"\n{'=' * 60}\n")


async def main():
    parser = argparse.ArgumentParser(description="TrustSignal Backtest")
    parser.add_argument("--asset", default="bitcoin", help="CoinGecko coin ID")
    parser.add_argument("--days", type=int, default=30, help="Days of history")
    parser.add_argument("--lookahead", type=int, default=6, help="Candles to look ahead for outcome")
    args = parser.parse_args()

    print(f"Fetching {args.days}-day OHLC for {args.asset}...")
    ohlc = await fetch_historical_ohlc(args.asset, args.days)
    print(f"Got {len(ohlc)} candles. Running backtest...")

    result = run_backtest(ohlc, args.asset, args.lookahead)
    print_report(result)

    return result


if __name__ == "__main__":
    asyncio.run(main())
