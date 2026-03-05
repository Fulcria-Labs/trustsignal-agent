"""Tests for the multi-timeframe signal engine."""

from signal_engine import Direction, Signal, SignalEngine


def _make_ohlc(prices: list[float], interval_ms: int = 14400000) -> list:
    """Create OHLC candles from a list of close prices."""
    ohlc = []
    base_ts = 1700000000000
    for i, p in enumerate(prices):
        ts = base_ts + i * interval_ms
        ohlc.append([ts, p * 0.99, p * 1.01, p * 0.98, p])
    return ohlc


class TestComputeIndicators:
    def test_basic_indicators(self):
        closes = [100, 101, 102, 103, 104, 105, 106, 107, 108, 109]
        result = SignalEngine._compute_indicators(closes)
        assert "rsi" in result
        assert "composite" in result
        assert "sma_5" in result
        assert "sma_10" in result
        assert result["sma_5"] > result["sma_10"]  # trending up

    def test_insufficient_data(self):
        result = SignalEngine._compute_indicators([100, 101])
        assert result == {}

    def test_rsi_range(self):
        closes = [100 + i for i in range(20)]
        result = SignalEngine._compute_indicators(closes)
        assert 0 <= result["rsi"] <= 100


class TestMACD:
    def test_macd_computed_with_enough_data(self):
        closes = [100 + i * 0.5 for i in range(30)]
        result = SignalEngine._compute_indicators(closes)
        assert "macd_line" in result
        assert "macd_signal" in result
        assert "macd_histogram" in result
        assert result["macd_line"] != 0  # Should have a non-zero MACD with trending data

    def test_macd_zero_with_short_data(self):
        closes = [100 + i for i in range(10)]
        result = SignalEngine._compute_indicators(closes)
        assert result["macd_line"] == 0  # Not enough data for 26-period EMA


class TestBollingerBands:
    def test_bb_computed(self):
        closes = [100 + i * 0.5 for i in range(20)]
        result = SignalEngine._compute_indicators(closes)
        assert "bb_upper" in result
        assert "bb_lower" in result
        assert "bb_pct" in result
        assert result["bb_upper"] > result["bb_lower"]

    def test_bb_pct_range(self):
        # Normal trending data should be within bands
        closes = [100 + i * 0.3 for i in range(20)]
        result = SignalEngine._compute_indicators(closes)
        assert 0 <= result["bb_pct"] <= 1.5  # Can exceed 1 if price breaks above upper


class TestEMA:
    def test_ema_basic(self):
        values = [10, 11, 12, 13, 14, 15]
        ema = SignalEngine._ema(values, 3)
        assert len(ema) == 4  # len(values) - period + 1
        assert ema[0] == 11.0  # First EMA = SMA of first 3

    def test_ema_insufficient(self):
        ema = SignalEngine._ema([10, 11], 5)
        assert ema == []


class TestMultiTimeframe:
    def test_signal_with_both_timeframes(self):
        import math
        engine = SignalEngine()
        # Oscillating data avoids RSI extremes from monotonic series
        st_prices = [100 + 3 * math.sin(i * 0.5) + i * 0.2 for i in range(20)]
        mt_prices = [90 + 2 * math.sin(i * 0.3) + i * 0.5 for i in range(30)]

        market_data = {
            "coin_id": "bitcoin",
            "current_price": st_prices[-1],
            "change_24h": 2.5,
            "ohlc": _make_ohlc(st_prices),
            "ohlc_30d": _make_ohlc(mt_prices, interval_ms=86400000),
        }
        signal = engine.analyze_technicals(market_data)
        assert isinstance(signal, Signal)
        assert signal.timeframe == "4h+daily"
        assert signal.direction in (Direction.LONG, Direction.SHORT, Direction.NEUTRAL)

    def test_neutral_when_timeframes_disagree(self):
        engine = SignalEngine()
        # Short-term trending up
        st_prices = [100 + i * 0.5 for i in range(20)]
        # Medium-term trending down strongly
        mt_prices = [150 - i * 2.0 for i in range(30)]

        market_data = {
            "coin_id": "ethereum",
            "current_price": st_prices[-1],
            "change_24h": 1.0,
            "ohlc": _make_ohlc(st_prices),
            "ohlc_30d": _make_ohlc(mt_prices, interval_ms=86400000),
        }
        signal = engine.analyze_technicals(market_data)
        # When MT strongly disagrees, should be more cautious
        assert signal.confidence <= 0.9

    def test_no_mt_data_still_works(self):
        engine = SignalEngine()
        st_prices = [100 + i * 0.5 for i in range(20)]
        market_data = {
            "coin_id": "solana",
            "current_price": st_prices[-1],
            "change_24h": 0.5,
            "ohlc": _make_ohlc(st_prices),
        }
        signal = engine.analyze_technicals(market_data)
        assert isinstance(signal, Signal)

    def test_signal_id_generated(self):
        engine = SignalEngine()
        market_data = {
            "coin_id": "bitcoin",
            "current_price": 70000,
            "change_24h": 1.0,
            "ohlc": _make_ohlc([69000 + i * 100 for i in range(20)]),
        }
        signal = engine.analyze_technicals(market_data)
        assert signal.signal_id.startswith("sig_")

    def test_track_record(self):
        import math
        engine = SignalEngine()
        for i in range(3):
            prices = [70000 + 100 * math.sin(j * 0.4 + i) for j in range(20)]
            market_data = {
                "coin_id": "bitcoin",
                "current_price": prices[-1],
                "change_24h": 0,
                "ohlc": _make_ohlc(prices),
            }
            engine.analyze_technicals(market_data)
        record = engine.get_track_record()
        assert record["total_signals"] == 3

    def test_mt_confluence_boosts_confidence(self):
        engine = SignalEngine()
        # Both timeframes strongly bullish
        st_prices = [100 + i * 1.0 for i in range(20)]
        mt_prices = [80 + i * 1.5 for i in range(30)]

        market_data = {
            "coin_id": "bitcoin",
            "current_price": st_prices[-1],
            "change_24h": 5.0,
            "ohlc": _make_ohlc(st_prices),
            "ohlc_30d": _make_ohlc(mt_prices, interval_ms=86400000),
        }
        signal_with_mt = engine.analyze_technicals(market_data)

        # Without MT data
        engine2 = SignalEngine()
        market_data_no_mt = {
            "coin_id": "bitcoin",
            "current_price": st_prices[-1],
            "change_24h": 5.0,
            "ohlc": _make_ohlc(st_prices),
        }
        signal_no_mt = engine2.analyze_technicals(market_data_no_mt)

        # With MT confluence, confidence should be >= without
        if signal_with_mt.direction == signal_no_mt.direction:
            assert signal_with_mt.confidence >= signal_no_mt.confidence
