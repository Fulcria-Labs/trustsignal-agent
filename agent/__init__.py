"""
ERC-8004 Trading Agent Package
"""
from .identity import IdentityManager, AgentRegistration
from .reputation import ReputationManager
from .scanner import ArbitrageScanner
from .trader import TradeExecutor
from .ipfs_uploader import upload_registration, upload_to_ipfs, pin_cid

__all__ = [
    "IdentityManager",
    "AgentRegistration",
    "ReputationManager",
    "ArbitrageScanner",
    "TradeExecutor",
    "upload_registration",
    "upload_to_ipfs",
    "pin_cid",
]
