"""
Tests for DEX Arbitrage Scanner
"""
import pytest
import asyncio
from decimal import Decimal
from unittest.mock import Mock, MagicMock, patch
from web3 import Web3

import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent))

from agent.scanner import ArbitrageScanner, PriceQuote, ArbitrageOpportunity


class TestPriceQuote:
    """Tests for PriceQuote dataclass"""

    def test_create_quote(self):
        """Test creating a price quote"""
        quote = PriceQuote(
            dex="uniswap_v3",
            token_in="USDC",
            token_out="WETH",
            amount_in=Decimal("1000"),
            amount_out=Decimal("0.3"),
            price=Decimal("0.0003"),
            gas_estimate=150000,
            timestamp=1700000000
        )

        assert quote.dex == "uniswap_v3"
        assert quote.amount_in == Decimal("1000")
        assert quote.price == Decimal("0.0003")


class TestArbitrageOpportunity:
    """Tests for ArbitrageOpportunity dataclass"""

    def test_create_opportunity(self):
        """Test creating an arbitrage opportunity"""
        opp = ArbitrageOpportunity(
            buy_dex="uniswap_v3",
            sell_dex="sushiswap",
            token="WETH",
            base_token="USDC",
            buy_price=Decimal("3330"),
            sell_price=Decimal("3350"),
            spread_bps=60,
            estimated_profit_usd=Decimal("20"),
            required_capital=Decimal("3330"),
            gas_cost_usd=Decimal("5"),
            net_profit_usd=Decimal("15"),
            confidence=0.6
        )

        assert opp.buy_dex == "uniswap_v3"
        assert opp.spread_bps == 60
        assert opp.net_profit_usd == Decimal("15")


class TestArbitrageScanner:
    """Tests for ArbitrageScanner"""

    @pytest.fixture
    def mock_w3(self):
        """Create a mock Web3 instance"""
        w3 = MagicMock(spec=Web3)
        w3.eth = MagicMock()
        w3.eth.gas_price = 20000000000  # 20 gwei
        return w3

    @pytest.fixture
    def scanner(self, mock_w3):
        """Create a scanner instance in testnet mode"""
        return ArbitrageScanner(
            w3=mock_w3,
            min_profit_bps=30,
            max_gas_gwei=50,
            is_testnet=True
        )

    def test_init(self, scanner):
        """Test scanner initialization"""
        assert scanner.min_profit_bps == 30
        assert scanner.max_gas_gwei == 50
        assert scanner.is_testnet is True

    @pytest.mark.asyncio
    async def test_get_quote_testnet(self, scanner):
        """Test getting a mock quote in testnet mode"""
        quote = await scanner.get_quote(
            dex="uniswap_v3",
            token_in="USDC",
            token_out="WETH",
            amount_in=Decimal("1000")
        )

        assert quote is not None
        assert quote.dex == "uniswap_v3"
        assert quote.token_in == "USDC"
        assert quote.token_out == "WETH"
        assert quote.amount_in == Decimal("1000")
        assert quote.price > 0

    @pytest.mark.asyncio
    async def test_scan_pair(self, scanner):
        """Test scanning a pair for arbitrage"""
        opportunities = await scanner.scan_pair(
            token_a="USDC",
            token_b="WETH",
            amount=Decimal("1000")
        )

        # May or may not find opportunities depending on mock randomness
        assert isinstance(opportunities, list)
        for opp in opportunities:
            assert isinstance(opp, ArbitrageOpportunity)
            assert opp.spread_bps >= scanner.min_profit_bps

    @pytest.mark.asyncio
    async def test_scan_all_pairs(self, scanner):
        """Test scanning all configured pairs"""
        opportunities = await scanner.scan_all_pairs()

        assert isinstance(opportunities, list)
        # Should be sorted by profit (descending)
        for i in range(len(opportunities) - 1):
            assert opportunities[i].net_profit_usd >= opportunities[i + 1].net_profit_usd

    @pytest.mark.asyncio
    async def test_close_session(self, scanner):
        """Test closing the HTTP session"""
        # Create a session
        await scanner._get_session()
        assert scanner._session is not None

        # Close it
        await scanner.close()
        assert scanner._session is None

    @pytest.mark.asyncio
    async def test_opportunity_has_positive_net_profit(self, scanner):
        """Test that returned opportunities have positive net profit"""
        opportunities = await scanner.scan_all_pairs()

        for opp in opportunities:
            assert opp.net_profit_usd > 0, "Opportunities should have positive net profit after gas"


class TestDEXConfiguration:
    """Test DEX configuration and addresses"""

    def test_token_addresses_are_checksummed(self):
        """Token addresses should be valid checksummed addresses"""
        for symbol, address in ArbitrageScanner.TOKENS.items():
            assert address.startswith("0x"), f"{symbol} address should start with 0x"
            assert len(address) == 42, f"{symbol} address should be 42 chars"
            # Check it's checksummed
            assert address == Web3.to_checksum_address(address), \
                f"{symbol} address should be checksummed"

    def test_router_addresses_are_checksummed(self):
        """Router addresses should be valid checksummed addresses"""
        for dex, address in ArbitrageScanner.ROUTERS.items():
            assert address.startswith("0x"), f"{dex} router should start with 0x"
            assert len(address) == 42, f"{dex} router should be 42 chars"


class TestMockQuotes:
    """Test mock quote generation for testnet"""

    @pytest.fixture
    def scanner(self):
        w3 = MagicMock(spec=Web3)
        w3.eth = MagicMock()
        w3.eth.gas_price = 20000000000
        return ArbitrageScanner(w3=w3, is_testnet=True)

    @pytest.mark.asyncio
    async def test_mock_usdc_to_weth_price_range(self, scanner):
        """USDC/WETH price should be in reasonable range"""
        quote = await scanner._mock_quote(
            dex="uniswap_v3",
            token_in="USDC",
            token_out="WETH",
            amount_in=Decimal("1000")
        )

        # Price should be around 0.0003 (1/3333)
        assert Decimal("0.00028") < quote.price < Decimal("0.00032")

    @pytest.mark.asyncio
    async def test_mock_weth_to_usdc_price_range(self, scanner):
        """WETH/USDC price should be in reasonable range"""
        quote = await scanner._mock_quote(
            dex="uniswap_v3",
            token_in="WETH",
            token_out="USDC",
            amount_in=Decimal("1")
        )

        # Price should be around 3333
        assert Decimal("3300") < quote.price < Decimal("3370")

    @pytest.mark.asyncio
    async def test_mock_quote_has_all_fields(self, scanner):
        """Mock quotes should have all required fields"""
        quote = await scanner._mock_quote(
            dex="sushiswap",
            token_in="USDC",
            token_out="DAI",
            amount_in=Decimal("100")
        )

        assert quote.dex == "sushiswap"
        assert quote.token_in == "USDC"
        assert quote.token_out == "DAI"
        assert quote.amount_in == Decimal("100")
        assert quote.amount_out > 0
        assert quote.gas_estimate > 0
        assert quote.timestamp > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
