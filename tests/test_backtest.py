"""Tests for the backtesting engine."""

from backtest import run_backtest, BacktestResult


def _make_ohlc(prices: list[float], interval_ms: int = 14400000) -> list:
    """Create OHLC candles from a list of close prices."""
    ohlc = []
    base_ts = 1700000000000
    for i, p in enumerate(prices):
        ts = base_ts + i * interval_ms
        ohlc.append([ts, p * 0.99, p * 1.01, p * 0.98, p])
    return ohlc


class TestBacktest:
    def test_insufficient_data(self):
        ohlc = _make_ohlc([100] * 10)
        result = run_backtest(ohlc, "test", lookahead=6)
        assert result.total_signals == 0

    def test_basic_backtest(self):
        # Create trending-up data to generate some long signals
        prices = [100 + i * 0.5 for i in range(40)]
        ohlc = _make_ohlc(prices)
        result = run_backtest(ohlc, "test-coin", lookahead=3)
        assert isinstance(result, BacktestResult)
        assert result.asset == "test-coin"
        assert result.total_signals > 0

    def test_result_fields(self):
        prices = list(range(100, 140))
        ohlc = _make_ohlc(prices)
        result = run_backtest(ohlc, "test", lookahead=3)
        assert hasattr(result, "win_rate")
        assert hasattr(result, "sharpe_ratio")
        assert hasattr(result, "signals")
        assert 0 <= result.win_rate <= 1

    def test_signals_have_required_fields(self):
        prices = [100 + i * 0.3 for i in range(40)]
        ohlc = _make_ohlc(prices)
        result = run_backtest(ohlc, "test", lookahead=3)
        for sig in result.signals:
            assert "direction" in sig
            assert "confidence" in sig
            assert "entry" in sig
            assert "pnl_pct" in sig
