"""Trading signal engine - generates signals from market data."""

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum

import httpx


class Direction(str, Enum):
    LONG = "long"
    SHORT = "short"
    NEUTRAL = "neutral"


@dataclass
class Signal:
    asset: str
    direction: Direction
    confidence: float  # 0-1
    entry_price: float
    target_price: float
    stop_loss: float
    timeframe: str  # e.g. "4h", "1d"
    reasoning: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    signal_id: str = ""

    def __post_init__(self):
        if not self.signal_id:
            h = hashlib.sha256(
                f"{self.asset}{self.direction}{self.timestamp}{self.entry_price}".encode()
            ).hexdigest()[:16]
            self.signal_id = f"sig_{h}"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["direction"] = self.direction.value
        return d


class SignalEngine:
    """Generates trading signals from market data using technical analysis."""

    COINGECKO_URL = "https://api.coingecko.com/api/v3"

    def __init__(self):
        self.signals_history: list[Signal] = []

    async def get_market_data(self, coin_id: str = "bitcoin") -> dict:
        """Fetch current market data from CoinGecko."""
        async with httpx.AsyncClient() as client:
            # Current price
            price_resp = await client.get(
                f"{self.COINGECKO_URL}/simple/price",
                params={"ids": coin_id, "vs_currencies": "usd", "include_24hr_change": "true"},
                timeout=10,
            )
            price_data = price_resp.json()

            # OHLC data (last 7 days)
            ohlc_resp = await client.get(
                f"{self.COINGECKO_URL}/coins/{coin_id}/ohlc",
                params={"vs_currency": "usd", "days": "7"},
                timeout=10,
            )
            ohlc_data = ohlc_resp.json()

        return {
            "coin_id": coin_id,
            "current_price": price_data.get(coin_id, {}).get("usd", 0),
            "change_24h": price_data.get(coin_id, {}).get("usd_24h_change", 0),
            "ohlc": ohlc_data[-20:] if isinstance(ohlc_data, list) else [],
        }

    def analyze_technicals(self, market_data: dict) -> Signal:
        """Generate a trading signal from market data using simple technicals."""
        ohlc = market_data.get("ohlc", [])
        price = market_data["current_price"]
        change_24h = market_data.get("change_24h", 0)

        if len(ohlc) < 5:
            return Signal(
                asset=market_data["coin_id"],
                direction=Direction.NEUTRAL,
                confidence=0.1,
                entry_price=price,
                target_price=price,
                stop_loss=price * 0.95,
                timeframe="4h",
                reasoning="Insufficient data for analysis",
            )

        # Simple moving averages from OHLC close prices
        closes = [candle[4] for candle in ohlc]
        sma_5 = sum(closes[-5:]) / 5
        sma_10 = sum(closes[-10:]) / min(10, len(closes))

        # RSI approximation (simplified)
        gains, losses = [], []
        for i in range(1, len(closes)):
            diff = closes[i] - closes[i - 1]
            if diff > 0:
                gains.append(diff)
            else:
                losses.append(abs(diff))
        avg_gain = sum(gains) / len(gains) if gains else 0.001
        avg_loss = sum(losses) / len(losses) if losses else 0.001
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        # Momentum: recent price change relative to range
        price_range = max(closes) - min(closes) if max(closes) != min(closes) else 1
        momentum = (price - closes[0]) / price_range  # -1 to 1

        # Volatility (normalized standard deviation)
        mean_price = sum(closes) / len(closes)
        variance = sum((c - mean_price) ** 2 for c in closes) / len(closes)
        volatility = (variance ** 0.5) / mean_price

        # Composite scoring: trend + momentum + RSI
        trend_score = (sma_5 - sma_10) / sma_10 * 100  # % above/below
        rsi_score = (rsi - 50) / 50  # -1 to 1, positive = bullish
        composite = trend_score * 0.4 + momentum * 0.3 + rsi_score * 0.3

        # Adjust risk based on volatility
        risk_mult = max(1.0, min(3.0, volatility * 50))

        # Signal logic with RSI extremes
        reasons = []
        if rsi > 75:
            reasons.append(f"RSI overbought ({rsi:.0f})")
        elif rsi < 25:
            reasons.append(f"RSI oversold ({rsi:.0f})")

        if sma_5 > sma_10:
            reasons.append(f"SMA5 ({sma_5:.0f}) > SMA10 ({sma_10:.0f})")
        else:
            reasons.append(f"SMA5 ({sma_5:.0f}) < SMA10 ({sma_10:.0f})")

        if abs(change_24h) > 3:
            reasons.append(f"24h change {change_24h:+.1f}%")

        if composite > 0.5 and rsi < 75:
            direction = Direction.LONG
            confidence = min(0.9, 0.5 + composite * 0.1)
            target = price * (1 + 0.02 * risk_mult)
            stop = price * (1 - 0.015 * risk_mult)
            reasons.insert(0, "Bullish")
        elif composite < -0.5 and rsi > 25:
            direction = Direction.SHORT
            confidence = min(0.9, 0.5 + abs(composite) * 0.1)
            target = price * (1 - 0.02 * risk_mult)
            stop = price * (1 + 0.015 * risk_mult)
            reasons.insert(0, "Bearish")
        elif rsi > 80:
            direction = Direction.SHORT
            confidence = min(0.75, 0.4 + (rsi - 80) * 0.02)
            target = price * 0.97
            stop = price * 1.02
            reasons.insert(0, "Overbought reversal")
        elif rsi < 20:
            direction = Direction.LONG
            confidence = min(0.75, 0.4 + (20 - rsi) * 0.02)
            target = price * 1.03
            stop = price * 0.98
            reasons.insert(0, "Oversold reversal")
        else:
            direction = Direction.NEUTRAL
            confidence = 0.3
            target = price
            stop = price * (1 - 0.02 * risk_mult)
            reasons.insert(0, "Neutral")

        reasoning = ". ".join(reasons)

        signal = Signal(
            asset=market_data["coin_id"],
            direction=direction,
            confidence=round(confidence, 3),
            entry_price=round(price, 2),
            target_price=round(target, 2),
            stop_loss=round(stop, 2),
            timeframe="4h",
            reasoning=reasoning,
        )
        self.signals_history.append(signal)
        return signal

    def get_track_record(self) -> dict:
        """Return signal generation statistics."""
        total = len(self.signals_history)
        if total == 0:
            return {"total_signals": 0, "long": 0, "short": 0, "neutral": 0}
        return {
            "total_signals": total,
            "long": sum(1 for s in self.signals_history if s.direction == Direction.LONG),
            "short": sum(1 for s in self.signals_history if s.direction == Direction.SHORT),
            "neutral": sum(1 for s in self.signals_history if s.direction == Direction.NEUTRAL),
        }
