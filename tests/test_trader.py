"""
Tests for Trade Executor
"""
import pytest
import asyncio
from decimal import Decimal
from unittest.mock import Mock, MagicMock, patch
from web3 import Web3

import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent))

from agent.trader import TradeExecutor, TradeIntent, TradeResult
from agent.scanner import ArbitrageOpportunity


class TestTradeIntent:
    """Tests for TradeIntent dataclass"""

    def test_create_intent(self):
        """Test creating a trade intent"""
        intent = TradeIntent(
            agent_id=1,
            from_token="0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",  # USDC
            to_token="0x4200000000000000000000000000000000000006",    # WETH
            amount_in=1000 * 10**18,
            min_amount_out=int(0.3 * 10**18),
            deadline=1700000000,
            nonce=1,
            chain_id=84532
        )

        assert intent.agent_id == 1
        assert intent.amount_in == 1000 * 10**18
        assert intent.chain_id == 84532


class TestTradeResult:
    """Tests for TradeResult dataclass"""

    def test_create_success_result(self):
        """Test creating a successful trade result"""
        result = TradeResult(
            success=True,
            tx_hash="0x123...",
            amount_received=Decimal("15.50"),
            gas_used=300000,
            error=None
        )

        assert result.success is True
        assert result.tx_hash == "0x123..."
        assert result.error is None

    def test_create_failure_result(self):
        """Test creating a failed trade result"""
        result = TradeResult(
            success=False,
            tx_hash=None,
            amount_received=None,
            gas_used=None,
            error="Slippage too high"
        )

        assert result.success is False
        assert result.error == "Slippage too high"


class TestTradeExecutor:
    """Tests for TradeExecutor"""

    @pytest.fixture
    def mock_w3(self):
        """Create a mock Web3 instance"""
        w3 = MagicMock(spec=Web3)
        w3.eth = MagicMock()
        w3.eth.chain_id = 84532  # Base Sepolia
        w3.eth.gas_price = 20000000000
        w3.eth.get_transaction_count.return_value = 0
        return w3

    @pytest.fixture
    def test_private_key(self):
        """Generate a test private key"""
        return "0x" + "1" * 64

    @pytest.fixture
    def executor(self, mock_w3, test_private_key):
        """Create a TradeExecutor instance"""
        return TradeExecutor(
            w3=mock_w3,
            private_key=test_private_key,
            agent_token_id=1,
            risk_router_address="0x0000000000000000000000000000000000000001",
            slippage_bps=50,
            max_position_usd=100.0
        )

    def test_init(self, executor):
        """Test executor initialization"""
        assert executor.agent_token_id == 1
        assert executor.slippage_bps == 50
        assert executor.max_position_usd == 100.0

    def test_create_trade_intent(self, executor):
        """Test creating a trade intent"""
        intent = executor.create_trade_intent(
            from_token="0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
            to_token="0x4200000000000000000000000000000000000006",
            amount_in=Decimal("100"),
            expected_out=Decimal("0.03"),
            deadline_seconds=300
        )

        assert intent.agent_id == 1
        assert intent.amount_in == int(Decimal("100") * Decimal("1e18"))
        # min_amount_out should be reduced by slippage
        expected_min = int(Decimal("0.03") * Decimal("0.995") * Decimal("1e18"))
        assert intent.min_amount_out == expected_min

    def test_sign_trade_intent(self, executor):
        """Test signing a trade intent"""
        intent = executor.create_trade_intent(
            from_token="0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
            to_token="0x4200000000000000000000000000000000000006",
            amount_in=Decimal("100"),
            expected_out=Decimal("0.03"),
        )

        signature = executor.sign_trade_intent(intent)

        # Signature should be a hex string
        assert isinstance(signature, str)
        # EIP-712 signatures are 65 bytes = 130 hex chars (without 0x)
        assert len(signature) >= 128

    @pytest.mark.asyncio
    async def test_execute_arbitrage_position_too_large(self, executor):
        """Test rejection of positions exceeding max size"""
        opportunity = ArbitrageOpportunity(
            buy_dex="uniswap_v3",
            sell_dex="sushiswap",
            token="WETH",
            base_token="USDC",
            buy_price=Decimal("3330"),
            sell_price=Decimal("3350"),
            spread_bps=60,
            estimated_profit_usd=Decimal("20"),
            required_capital=Decimal("5000"),  # > max_position_usd
            gas_cost_usd=Decimal("5"),
            net_profit_usd=Decimal("15"),
            confidence=0.6
        )

        result = await executor.execute_arbitrage(opportunity)

        assert result.success is False
        assert "exceeds max" in result.error

    @pytest.mark.asyncio
    async def test_execute_arbitrage_success(self, executor):
        """Test successful arbitrage execution"""
        # Use actual addresses instead of symbols for EIP-712 encoding
        opportunity = ArbitrageOpportunity(
            buy_dex="uniswap_v3",
            sell_dex="sushiswap",
            token="0x4200000000000000000000000000000000000006",    # WETH
            base_token="0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",  # USDC
            buy_price=Decimal("3330"),
            sell_price=Decimal("3350"),
            spread_bps=60,
            estimated_profit_usd=Decimal("5"),
            required_capital=Decimal("50"),  # < max_position_usd
            gas_cost_usd=Decimal("2"),
            net_profit_usd=Decimal("3"),
            confidence=0.6
        )

        result = await executor.execute_arbitrage(opportunity)

        assert result.success is True
        assert result.tx_hash is not None

    @pytest.mark.asyncio
    async def test_validate_execution(self, executor):
        """Test execution validation"""
        validation = await executor.validate_execution(
            tx_hash="0x123...",
            expected_profit=Decimal("15.00")
        )

        assert validation["success"] is True
        assert "score" in validation
        assert validation["score"] >= 0 and validation["score"] <= 100


class TestEIP712Signing:
    """Test EIP-712 typed data signing"""

    @pytest.fixture
    def executor(self):
        w3 = MagicMock(spec=Web3)
        w3.eth = MagicMock()
        w3.eth.chain_id = 84532
        return TradeExecutor(
            w3=w3,
            private_key="0x" + "1" * 64,
            agent_token_id=1,
            risk_router_address="0x0000000000000000000000000000000000000001"
        )

    def test_eip712_domain_structure(self):
        """Test EIP-712 domain has required fields"""
        domain = TradeExecutor.EIP712_DOMAIN

        assert "name" in domain
        assert "version" in domain
        assert "chainId" in domain
        assert "verifyingContract" in domain

    def test_eip712_types_structure(self):
        """Test EIP-712 types define TradeIntent correctly"""
        types = TradeExecutor.EIP712_TYPES

        assert "TradeIntent" in types
        intent_fields = {f["name"] for f in types["TradeIntent"]}

        required_fields = {
            "agentId", "fromToken", "toToken", "amountIn",
            "minAmountOut", "deadline", "nonce"
        }
        assert required_fields.issubset(intent_fields)


class TestSlippageCalculation:
    """Test slippage protection"""

    @pytest.fixture
    def executor(self):
        w3 = MagicMock(spec=Web3)
        w3.eth = MagicMock()
        w3.eth.chain_id = 84532
        return TradeExecutor(
            w3=w3,
            private_key="0x" + "1" * 64,
            agent_token_id=1,
            risk_router_address="0x0000000000000000000000000000000000000001",
            slippage_bps=100  # 1%
        )

    def test_slippage_applied_correctly(self, executor):
        """Test that slippage is applied to min_amount_out"""
        intent = executor.create_trade_intent(
            from_token="0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
            to_token="0x4200000000000000000000000000000000000006",
            amount_in=Decimal("100"),
            expected_out=Decimal("100"),  # 1:1 for easy math
        )

        # With 1% slippage, min should be 99
        expected_min = int(Decimal("99") * Decimal("1e18"))
        assert intent.min_amount_out == expected_min


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
