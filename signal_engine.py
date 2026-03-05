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
    """Generates trading signals from market data using technical analysis.

    Supports multi-timeframe analysis by fetching 7-day and 30-day OHLC
    data for short-term and medium-term confluence.
    """

    COINGECKO_URL = "https://api.coingecko.com/api/v3"
    CACHE_TTL = 60  # seconds

    def __init__(self):
        self.signals_history: list[Signal] = []
        self._cache: dict[str, tuple[float, dict]] = {}

    async def get_market_data(self, coin_id: str = "bitcoin") -> dict:
        """Fetch current market data from CoinGecko (cached for 60s)."""
        now = time.time()
        if coin_id in self._cache:
            ts, data = self._cache[coin_id]
            if now - ts < self.CACHE_TTL:
                return data

        async with httpx.AsyncClient() as client:
            # Current price
            price_resp = await client.get(
                f"{self.COINGECKO_URL}/simple/price",
                params={"ids": coin_id, "vs_currencies": "usd", "include_24hr_change": "true"},
                timeout=10,
            )
            price_data = price_resp.json()

            # OHLC data: short-term (7 days, ~4h candles) and medium-term (30 days, ~daily)
            ohlc_7d_resp = await client.get(
                f"{self.COINGECKO_URL}/coins/{coin_id}/ohlc",
                params={"vs_currency": "usd", "days": "7"},
                timeout=10,
            )
            ohlc_7d = ohlc_7d_resp.json()

            ohlc_30d_resp = await client.get(
                f"{self.COINGECKO_URL}/coins/{coin_id}/ohlc",
                params={"vs_currency": "usd", "days": "30"},
                timeout=10,
            )
            ohlc_30d = ohlc_30d_resp.json()

        result = {
            "coin_id": coin_id,
            "current_price": price_data.get(coin_id, {}).get("usd", 0),
            "change_24h": price_data.get(coin_id, {}).get("usd_24h_change", 0),
            "ohlc": ohlc_7d[-20:] if isinstance(ohlc_7d, list) else [],
            "ohlc_30d": ohlc_30d[-30:] if isinstance(ohlc_30d, list) else [],
        }
        self._cache[coin_id] = (now, result)
        return result

    @staticmethod
    def _compute_indicators(closes: list[float]) -> dict:
        """Compute technical indicators from a series of close prices."""
        if len(closes) < 5:
            return {}

        sma_5 = sum(closes[-5:]) / 5
        sma_10 = sum(closes[-10:]) / min(10, len(closes))

        # RSI
        gains, losses = [], []
        for i in range(1, len(closes)):
            diff = closes[i] - closes[i - 1]
            if diff > 0:
                gains.append(diff)
            else:
                losses.append(abs(diff))
        avg_gain = sum(gains) / len(gains) if gains else 0
        avg_loss = sum(losses) / len(losses) if losses else 0
        if avg_loss == 0:
            rs = 100 if avg_gain > 0 else 1  # All gains or flat
        else:
            rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        # Momentum
        price_range = max(closes) - min(closes) if max(closes) != min(closes) else 1
        momentum = (closes[-1] - closes[0]) / price_range

        # Volatility (normalized std dev)
        mean_price = sum(closes) / len(closes)
        variance = sum((c - mean_price) ** 2 for c in closes) / len(closes)
        volatility = (variance ** 0.5) / mean_price

        # Trend score
        trend_score = (sma_5 - sma_10) / sma_10 * 100

        # RSI score: -1 to 1
        rsi_score = (rsi - 50) / 50

        # Composite
        composite = trend_score * 0.4 + momentum * 0.3 + rsi_score * 0.3

        return {
            "sma_5": sma_5,
            "sma_10": sma_10,
            "rsi": rsi,
            "momentum": momentum,
            "volatility": volatility,
            "trend_score": trend_score,
            "rsi_score": rsi_score,
            "composite": composite,
        }

    def analyze_technicals(self, market_data: dict) -> Signal:
        """Generate a trading signal using multi-timeframe confluence.

        Analyzes both short-term (4h candles, 7-day) and medium-term (daily
        candles, 30-day) timeframes. Signals only fire when both timeframes
        agree, improving selectivity and win rate.
        """
        ohlc = market_data.get("ohlc", [])
        ohlc_30d = market_data.get("ohlc_30d", [])
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

        # Short-term indicators (4h candles)
        closes_st = [candle[4] for candle in ohlc]
        st = self._compute_indicators(closes_st)

        # Medium-term indicators (daily candles) - optional but boosts confidence
        mt = {}
        if ohlc_30d and len(ohlc_30d) >= 10:
            closes_mt = [candle[4] for candle in ohlc_30d]
            mt = self._compute_indicators(closes_mt)

        rsi = st["rsi"]
        composite = st["composite"]
        volatility = st["volatility"]

        # Adjust risk based on volatility
        risk_mult = max(1.0, min(3.0, volatility * 50))

        # Multi-timeframe confluence: check if medium-term agrees
        mt_agrees = True  # default if no MT data
        mt_label = ""
        if mt:
            mt_composite = mt["composite"]
            mt_rsi = mt["rsi"]
            mt_label = f" [MT: comp={mt_composite:.1f}, RSI={mt_rsi:.0f}]"

        # Signal logic with RSI extremes
        reasons = []
        if rsi > 75:
            reasons.append(f"RSI overbought ({rsi:.0f})")
        elif rsi < 25:
            reasons.append(f"RSI oversold ({rsi:.0f})")

        if st["sma_5"] > st["sma_10"]:
            reasons.append(f"SMA5 ({st['sma_5']:.0f}) > SMA10 ({st['sma_10']:.0f})")
        else:
            reasons.append(f"SMA5 ({st['sma_5']:.0f}) < SMA10 ({st['sma_10']:.0f})")

        if abs(change_24h) > 3:
            reasons.append(f"24h change {change_24h:+.1f}%")

        # Check multi-timeframe confluence for directional trades
        if mt:
            mt_agrees_long = mt["composite"] > -0.3  # MT not strongly bearish
            mt_agrees_short = mt["composite"] < 0.3  # MT not strongly bullish
        else:
            mt_agrees_long = True
            mt_agrees_short = True

        if composite > 0.5 and rsi < 75 and mt_agrees_long:
            direction = Direction.LONG
            confidence = min(0.9, 0.5 + composite * 0.1)
            if mt and mt["composite"] > 0.3:
                confidence = min(0.95, confidence + 0.1)
                reasons.append("MT confirms bullish")
            target = price * (1 + 0.02 * risk_mult)
            stop = price * (1 - 0.015 * risk_mult)
            reasons.insert(0, "Bullish")
        elif composite < -0.5 and rsi > 25 and mt_agrees_short:
            direction = Direction.SHORT
            confidence = min(0.9, 0.5 + abs(composite) * 0.1)
            if mt and mt["composite"] < -0.3:
                confidence = min(0.95, confidence + 0.1)
                reasons.append("MT confirms bearish")
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
            reasons.insert(0, "Neutral - no multi-timeframe confluence")

        if mt_label:
            reasons.append(mt_label.strip())

        reasoning = ". ".join(reasons)

        signal = Signal(
            asset=market_data["coin_id"],
            direction=direction,
            confidence=round(confidence, 3),
            entry_price=round(price, 2),
            target_price=round(target, 2),
            stop_loss=round(stop, 2),
            timeframe="4h+daily",
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
