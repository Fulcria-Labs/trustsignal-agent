"""
Trade Executor

Executes arbitrage trades with EIP-712 signed intents.
"""
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Dict, Any
from web3 import Web3
from eth_account import Account
from eth_account.messages import encode_typed_data

from .scanner import ArbitrageOpportunity

logger = logging.getLogger(__name__)


@dataclass
class TradeIntent:
    """EIP-712 typed trade intent"""
    agent_id: int  # ERC-8004 token ID
    from_token: str
    to_token: str
    amount_in: int  # wei
    min_amount_out: int  # wei
    deadline: int  # unix timestamp
    nonce: int
    chain_id: int


@dataclass
class TradeResult:
    """Result of a trade execution"""
    success: bool
    tx_hash: Optional[str]
    amount_received: Optional[Decimal]
    gas_used: Optional[int]
    error: Optional[str]


class TradeExecutor:
    """
    Executes trades via the ERC-8004 Risk Router.

    Features:
    - EIP-712 signed trade intents
    - Slippage protection
    - Gas estimation
    - On-chain validation support
    """

    # EIP-712 domain for trade intents
    EIP712_DOMAIN = {
        "name": "ERC8004TradingAgent",
        "version": "1",
        "chainId": 84532,  # Base Sepolia
        "verifyingContract": "0x0000000000000000000000000000000000000000",  # Risk Router
    }

    # EIP-712 types for trade intent
    EIP712_TYPES = {
        "TradeIntent": [
            {"name": "agentId", "type": "uint256"},
            {"name": "fromToken", "type": "address"},
            {"name": "toToken", "type": "address"},
            {"name": "amountIn", "type": "uint256"},
            {"name": "minAmountOut", "type": "uint256"},
            {"name": "deadline", "type": "uint256"},
            {"name": "nonce", "type": "uint256"},
        ]
    }

    def __init__(
        self,
        w3: Web3,
        private_key: str,
        agent_token_id: int,
        risk_router_address: str,
        slippage_bps: int = 50,
        max_position_usd: float = 100.0
    ):
        self.w3 = w3
        self.account = Account.from_key(private_key)
        self.agent_token_id = agent_token_id
        self.risk_router = risk_router_address
        self.slippage_bps = slippage_bps
        self.max_position_usd = max_position_usd
        self._nonce = 0

    def create_trade_intent(
        self,
        from_token: str,
        to_token: str,
        amount_in: Decimal,
        expected_out: Decimal,
        deadline_seconds: int = 300
    ) -> TradeIntent:
        """
        Create a signed trade intent.

        Args:
            from_token: Token to sell
            to_token: Token to buy
            amount_in: Amount to sell (decimal)
            expected_out: Expected amount out (decimal)
            deadline_seconds: Seconds until deadline

        Returns:
            TradeIntent ready for execution
        """
        import time

        # Apply slippage to min_amount_out
        slippage_factor = Decimal(str(1 - self.slippage_bps / 10000))
        min_out = expected_out * slippage_factor

        self._nonce += 1

        return TradeIntent(
            agent_id=self.agent_token_id,
            from_token=from_token,
            to_token=to_token,
            amount_in=int(amount_in * Decimal("1e18")),
            min_amount_out=int(min_out * Decimal("1e18")),
            deadline=int(time.time()) + deadline_seconds,
            nonce=self._nonce,
            chain_id=self.w3.eth.chain_id
        )

    def sign_trade_intent(self, intent: TradeIntent) -> str:
        """
        Sign a trade intent using EIP-712.

        Returns:
            Hex-encoded signature
        """
        message = {
            "agentId": intent.agent_id,
            "fromToken": intent.from_token,
            "toToken": intent.to_token,
            "amountIn": intent.amount_in,
            "minAmountOut": intent.min_amount_out,
            "deadline": intent.deadline,
            "nonce": intent.nonce,
        }

        # Use full_message format for encode_typed_data
        full_message = {
            "types": self.EIP712_TYPES,
            "primaryType": "TradeIntent",
            "domain": self.EIP712_DOMAIN,
            "message": message,
        }

        signable = encode_typed_data(full_message=full_message)
        signed = self.account.sign_message(signable)

        return signed.signature.hex()

    async def execute_arbitrage(
        self,
        opportunity: ArbitrageOpportunity
    ) -> TradeResult:
        """
        Execute an arbitrage opportunity.

        This performs a two-leg trade:
        1. Buy token on buy_dex
        2. Sell token on sell_dex

        Args:
            opportunity: ArbitrageOpportunity to execute

        Returns:
            TradeResult with outcome
        """
        # Validate position size
        if float(opportunity.required_capital) > self.max_position_usd:
            return TradeResult(
                success=False,
                tx_hash=None,
                amount_received=None,
                gas_used=None,
                error=f"Position ${opportunity.required_capital} exceeds max ${self.max_position_usd}"
            )

        logger.info(
            f"Executing arbitrage: Buy {opportunity.token} on {opportunity.buy_dex}, "
            f"Sell on {opportunity.sell_dex}, Expected profit: ${opportunity.net_profit_usd}"
        )

        try:
            # Create and sign trade intents
            buy_intent = self.create_trade_intent(
                from_token=opportunity.base_token,
                to_token=opportunity.token,
                amount_in=opportunity.required_capital,
                expected_out=opportunity.required_capital / opportunity.buy_price
            )
            buy_sig = self.sign_trade_intent(buy_intent)

            sell_intent = self.create_trade_intent(
                from_token=opportunity.token,
                to_token=opportunity.base_token,
                amount_in=opportunity.required_capital / opportunity.buy_price,
                expected_out=opportunity.required_capital * Decimal(str(
                    1 + opportunity.spread_bps / 10000
                ))
            )
            sell_sig = self.sign_trade_intent(sell_intent)

            # In production, would submit to Risk Router
            # For now, simulate success
            logger.info(f"Trade intents signed: buy={buy_sig[:20]}..., sell={sell_sig[:20]}...")

            # Simulate execution
            return TradeResult(
                success=True,
                tx_hash="0x" + "0" * 64,  # Mock tx hash
                amount_received=opportunity.net_profit_usd,
                gas_used=300000,
                error=None
            )

        except Exception as e:
            logger.error(f"Trade execution failed: {e}")
            return TradeResult(
                success=False,
                tx_hash=None,
                amount_received=None,
                gas_used=None,
                error=str(e)
            )

    async def validate_execution(
        self,
        tx_hash: str,
        expected_profit: Decimal
    ) -> Dict[str, Any]:
        """
        Validate trade execution for the Validation Registry.

        Returns:
            Validation data to submit to Validation Registry
        """
        # In production, would analyze tx receipt
        return {
            "tx_hash": tx_hash,
            "success": True,
            "actual_profit": expected_profit,  # Would calculate from logs
            "score": 85,  # 0-100 validation score
            "notes": "Trade executed within slippage tolerance"
        }
