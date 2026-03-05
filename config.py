"""
Configuration for ERC-8004 Trading Agent
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Agent identity
AGENT_NAME = "optimus-arbitrage-agent"
AGENT_DESCRIPTION = "Autonomous arbitrage agent with on-chain reputation"
AGENT_VERSION = "0.1.0"

# Network configuration
# Base Sepolia for development, can switch to mainnet later
NETWORK = os.getenv("NETWORK", "base-sepolia")

NETWORKS = {
    "base-sepolia": {
        "chain_id": 84532,
        "rpc_url": os.getenv("BASE_SEPOLIA_RPC", "https://sepolia.base.org"),
        "explorer": "https://sepolia.basescan.org",
        # ERC-8004 Registry contracts on Base Sepolia (discovered 2026-02-16)
        # https://github.com/erc-8004/erc-8004-contracts
        "identity_registry": os.getenv("IDENTITY_REGISTRY", "0x8004A818BFB912233c491871b3d84c89A494BD9e"),
        "reputation_registry": os.getenv("REPUTATION_REGISTRY", "0x8004B663056A597Dffe9eCcC1965A193B7388713"),
        "validation_registry": os.getenv("VALIDATION_REGISTRY", ""),  # TBD
    },
    "arbitrum-sepolia": {
        "chain_id": 421614,
        "rpc_url": os.getenv("ARB_SEPOLIA_RPC", "https://sepolia-rollup.arbitrum.io/rpc"),
        "explorer": "https://sepolia.arbiscan.io",
        "identity_registry": os.getenv("ARB_IDENTITY_REGISTRY", ""),
        "reputation_registry": os.getenv("ARB_REPUTATION_REGISTRY", ""),
        "validation_registry": os.getenv("ARB_VALIDATION_REGISTRY", ""),
    },
}

# Get current network config
def get_network_config():
    return NETWORKS.get(NETWORK, NETWORKS["base-sepolia"])

# Wallet configuration
WALLET_PATH = Path(os.getenv("WALLET_PATH", "~/.agent/wallets/trading_wallet.txt")).expanduser()
PRIVATE_KEY = os.getenv("PRIVATE_KEY", "")

# Trading parameters
MAX_GAS_GWEI = int(os.getenv("MAX_GAS_GWEI", "50"))
MIN_PROFIT_BPS = int(os.getenv("MIN_PROFIT_BPS", "50"))  # 0.5% minimum profit
MAX_POSITION_USD = float(os.getenv("MAX_POSITION_USD", "100"))
SLIPPAGE_BPS = int(os.getenv("SLIPPAGE_BPS", "50"))  # 0.5% slippage tolerance

# DEX endpoints for price checking
DEXES = {
    "uniswap_v3": {
        "router": "0x...",  # Uniswap V3 Router on testnet
        "quoter": "0x...",
    },
    "sushiswap": {
        "router": "0x...",
    },
}

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = Path("logs/agent.log")
