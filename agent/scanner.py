"""
DEX Arbitrage Scanner

Scans decentralized exchanges for price discrepancies and arbitrage opportunities.
"""
import asyncio
import logging
from dataclasses import dataclass
from typing import List, Optional, Dict
from decimal import Decimal
import aiohttp
from web3 import Web3

logger = logging.getLogger(__name__)


@dataclass
class PriceQuote:
    """Price quote from a DEX"""
    dex: str
    token_in: str
    token_out: str
    amount_in: Decimal
    amount_out: Decimal
    price: Decimal  # token_out per token_in
    gas_estimate: int
    timestamp: int


@dataclass
class ArbitrageOpportunity:
    """Detected arbitrage opportunity"""
    buy_dex: str
    sell_dex: str
    token: str
    base_token: str
    buy_price: Decimal
    sell_price: Decimal
    spread_bps: int
    estimated_profit_usd: Decimal
    required_capital: Decimal
    gas_cost_usd: Decimal
    net_profit_usd: Decimal
    confidence: float  # 0.0 - 1.0


class ArbitrageScanner:
    """
    Scans multiple DEXs for arbitrage opportunities.

    Supports:
    - Uniswap V2/V3
    - SushiSwap
    - Curve
    - Balancer

    On testnets, uses mock data for development.
    """

    # Common token addresses (Base mainnet)
    TOKENS = {
        "WETH": "0x4200000000000000000000000000000000000006",
        "USDC": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
        "DAI": "0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb",
        "USDT": "0xfde4C96c8593536E31F229EA8f37b2ADa2699bb2",
    }

    # DEX router addresses (Base mainnet)
    ROUTERS = {
        "uniswap_v3": "0x2626664c2603336E57B271c5C0b26F421741e481",
        "sushiswap": "0x6BDED42c6DA8FBf0d2bA55B2fa120C5e0c8D7891",
        "aerodrome": "0xcF77a3Ba9A5CA399B7c97c74d54e5b1Beb874E43",
    }

    def __init__(
        self,
        w3: Web3,
        min_profit_bps: int = 50,
        max_gas_gwei: int = 50,
        is_testnet: bool = True
    ):
        self.w3 = w3
        self.min_profit_bps = min_profit_bps
        self.max_gas_gwei = max_gas_gwei
        self.is_testnet = is_testnet
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if not self._session:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        if self._session:
            await self._session.close()
            self._session = None

    async def get_quote(
        self,
        dex: str,
        token_in: str,
        token_out: str,
        amount_in: Decimal
    ) -> Optional[PriceQuote]:
        """
        Get a price quote from a specific DEX.

        In testnet mode, returns simulated data.
        """
        if self.is_testnet:
            return await self._mock_quote(dex, token_in, token_out, amount_in)

        # Production would call DEX quoter contracts
        # Example for Uniswap V3:
        # quoter = self.w3.eth.contract(address=QUOTER_ADDRESS, abi=QUOTER_ABI)
        # amount_out = quoter.functions.quoteExactInputSingle(...).call()
        raise NotImplementedError("Production quotes not yet implemented")

    async def _mock_quote(
        self,
        dex: str,
        token_in: str,
        token_out: str,
        amount_in: Decimal
    ) -> PriceQuote:
        """Generate mock quote for testing"""
        import random
        import time

        # Base price with small random variation per DEX
        base_price = Decimal("1.0")
        if token_in == "USDC" and token_out == "WETH":
            base_price = Decimal("0.0003")  # ~$3333/ETH
        elif token_in == "WETH" and token_out == "USDC":
            base_price = Decimal("3333")

        # Add DEX-specific variation (creates arb opportunities)
        variation = Decimal(str(1.0 + random.uniform(-0.003, 0.003)))
        price = base_price * variation

        return PriceQuote(
            dex=dex,
            token_in=token_in,
            token_out=token_out,
            amount_in=amount_in,
            amount_out=amount_in * price,
            price=price,
            gas_estimate=150000,
            timestamp=int(time.time())
        )

    async def scan_pair(
        self,
        token_a: str,
        token_b: str,
        amount: Decimal
    ) -> List[ArbitrageOpportunity]:
        """
        Scan all DEXs for arbitrage on a specific pair.

        Args:
            token_a: First token symbol
            token_b: Second token symbol
            amount: Amount of token_a to check

        Returns:
            List of profitable arbitrage opportunities
        """
        opportunities = []
        quotes: Dict[str, PriceQuote] = {}

        # Get quotes from all DEXs
        dex_list = list(self.ROUTERS.keys())
        tasks = [
            self.get_quote(dex, token_a, token_b, amount)
            for dex in dex_list
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for dex, result in zip(dex_list, results):
            if isinstance(result, PriceQuote):
                quotes[dex] = result
            else:
                logger.warning(f"Failed to get quote from {dex}: {result}")

        if len(quotes) < 2:
            return opportunities

        # Find arbitrage by comparing all pairs
        dexes = list(quotes.keys())
        for i, buy_dex in enumerate(dexes):
            for sell_dex in dexes[i+1:]:
                buy_quote = quotes[buy_dex]
                sell_quote = quotes[sell_dex]

                # Calculate spread
                spread_bps = int(
                    (sell_quote.price - buy_quote.price) / buy_quote.price * 10000
                )

                if abs(spread_bps) >= self.min_profit_bps:
                    # Determine direction
                    if spread_bps > 0:
                        actual_buy, actual_sell = buy_dex, sell_dex
                        actual_spread = spread_bps
                    else:
                        actual_buy, actual_sell = sell_dex, buy_dex
                        actual_spread = -spread_bps

                    # Estimate costs
                    gas_price = self.w3.eth.gas_price if not self.is_testnet else 1e9
                    total_gas = buy_quote.gas_estimate + sell_quote.gas_estimate
                    gas_cost_usd = Decimal(str(gas_price * total_gas / 1e18 * 3333))  # ETH price estimate

                    gross_profit = amount * Decimal(str(actual_spread / 10000))
                    net_profit = gross_profit - gas_cost_usd

                    if net_profit > 0:
                        opportunities.append(ArbitrageOpportunity(
                            buy_dex=actual_buy,
                            sell_dex=actual_sell,
                            token=token_a,
                            base_token=token_b,
                            buy_price=quotes[actual_buy].price,
                            sell_price=quotes[actual_sell].price,
                            spread_bps=actual_spread,
                            estimated_profit_usd=gross_profit,
                            required_capital=amount,
                            gas_cost_usd=gas_cost_usd,
                            net_profit_usd=net_profit,
                            confidence=min(1.0, actual_spread / 100)  # Higher spread = more confidence
                        ))

        return sorted(opportunities, key=lambda x: x.net_profit_usd, reverse=True)

    async def scan_all_pairs(self) -> List[ArbitrageOpportunity]:
        """
        Scan all configured token pairs for arbitrage opportunities.
        """
        all_opportunities = []
        pairs = [
            ("WETH", "USDC"),
            ("USDC", "DAI"),
            ("WETH", "DAI"),
        ]
        amounts = [Decimal("1000"), Decimal("5000"), Decimal("10000")]

        for token_a, token_b in pairs:
            for amount in amounts:
                opps = await self.scan_pair(token_a, token_b, amount)
                all_opportunities.extend(opps)

        # Deduplicate and sort by profit
        unique = {}
        for opp in all_opportunities:
            key = (opp.buy_dex, opp.sell_dex, opp.token)
            if key not in unique or opp.net_profit_usd > unique[key].net_profit_usd:
                unique[key] = opp

        return sorted(unique.values(), key=lambda x: x.net_profit_usd, reverse=True)
