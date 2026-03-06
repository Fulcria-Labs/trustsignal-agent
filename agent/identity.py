"""
ERC-8004 Identity Management

Handles agent registration and identity updates on the ERC-8004 Identity Registry.
"""
import json
import logging
from dataclasses import dataclass, asdict
from typing import Optional
from datetime import datetime, timezone
from web3 import Web3
from eth_account import Account
from eth_account.messages import encode_defunct

logger = logging.getLogger(__name__)


@dataclass
class AgentRegistration:
    """Agent registration file schema per ERC-8004 spec"""
    name: str
    description: str
    version: str
    capabilities: list[str]
    created_at: str
    owner: str
    agent_address: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    @classmethod
    def from_json(cls, data: str) -> "AgentRegistration":
        return cls(**json.loads(data))


class IdentityManager:
    """
    Manages ERC-8004 Identity Registry interactions.

    The Identity Registry is an ERC-721 compatible contract that:
    - Mints unique agent identities as NFTs
    - Stores URI pointing to registration file
    - Enables on-chain metadata storage
    """

    # ERC-8004 Identity Registry ABI (minimal)
    IDENTITY_ABI = [
        {
            "name": "register",
            "type": "function",
            "inputs": [
                {"name": "uri", "type": "string"},
                {"name": "metadata", "type": "bytes"}
            ],
            "outputs": [{"name": "tokenId", "type": "uint256"}]
        },
        {
            "name": "setAgentURI",
            "type": "function",
            "inputs": [
                {"name": "tokenId", "type": "uint256"},
                {"name": "uri", "type": "string"}
            ],
            "outputs": []
        },
        {
            "name": "setMetadata",
            "type": "function",
            "inputs": [
                {"name": "tokenId", "type": "uint256"},
                {"name": "key", "type": "bytes32"},
                {"name": "value", "type": "bytes"}
            ],
            "outputs": []
        },
        {
            "name": "getRegistrationFile",
            "type": "function",
            "inputs": [{"name": "tokenId", "type": "uint256"}],
            "outputs": [{"name": "uri", "type": "string"}],
            "stateMutability": "view"
        },
        {
            "name": "ownerOf",
            "type": "function",
            "inputs": [{"name": "tokenId", "type": "uint256"}],
            "outputs": [{"name": "owner", "type": "address"}],
            "stateMutability": "view"
        }
    ]

    def __init__(
        self,
        w3: Web3,
        registry_address: str,
        private_key: str,
        agent_info: dict
    ):
        self.w3 = w3
        self.account = Account.from_key(private_key)
        self.registry = w3.eth.contract(
            address=Web3.to_checksum_address(registry_address),
            abi=self.IDENTITY_ABI
        )
        self.agent_info = agent_info
        self.token_id: Optional[int] = None

    def create_registration_file(self) -> AgentRegistration:
        """Create the agent registration file per ERC-8004 spec"""
        return AgentRegistration(
            name=self.agent_info.get("name", "Optimus Arbitrage Agent"),
            description=self.agent_info.get("description", "Autonomous arbitrage trading agent"),
            version=self.agent_info.get("version", "0.1.0"),
            capabilities=self.agent_info.get("capabilities", [
                "dex-arbitrage",
                "price-scanning",
                "trade-execution",
                "risk-management"
            ]),
            created_at=datetime.now(timezone.utc).isoformat(),
            owner=self.account.address,
            agent_address=self.account.address,
        )

    async def register(self, registration_uri: str, metadata: bytes = b"") -> int:
        """
        Register agent on the Identity Registry.

        Args:
            registration_uri: IPFS or HTTP URI to registration file
            metadata: Additional on-chain metadata (optional)

        Returns:
            Token ID of the registered agent
        """
        logger.info(f"Registering agent at {self.registry.address}")

        # Build transaction
        tx = self.registry.functions.register(
            registration_uri,
            metadata
        ).build_transaction({
            "from": self.account.address,
            "nonce": self.w3.eth.get_transaction_count(self.account.address),
            "gas": 300000,
            "gasPrice": self.w3.eth.gas_price,
        })

        # Sign and send
        signed = self.account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)

        # Extract token ID from events (simplified)
        # In production, parse Transfer event logs
        self.token_id = receipt.get("logs", [{}])[0].get("topics", [None, None, None])[3]

        logger.info(f"Agent registered with token ID: {self.token_id}")
        return self.token_id

    async def update_uri(self, new_uri: str) -> str:
        """Update the agent's registration URI"""
        if not self.token_id:
            raise ValueError("Agent not registered")

        tx = self.registry.functions.setAgentURI(
            self.token_id,
            new_uri
        ).build_transaction({
            "from": self.account.address,
            "nonce": self.w3.eth.get_transaction_count(self.account.address),
            "gas": 100000,
            "gasPrice": self.w3.eth.gas_price,
        })

        signed = self.account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        self.w3.eth.wait_for_transaction_receipt(tx_hash)

        return tx_hash.hex()

    async def set_metadata(self, key: str, value: bytes) -> str:
        """Set on-chain metadata for the agent"""
        if not self.token_id:
            raise ValueError("Agent not registered")

        # Convert key to bytes32
        key_bytes = Web3.to_bytes(text=key).ljust(32, b'\x00')[:32]

        tx = self.registry.functions.setMetadata(
            self.token_id,
            key_bytes,
            value
        ).build_transaction({
            "from": self.account.address,
            "nonce": self.w3.eth.get_transaction_count(self.account.address),
            "gas": 100000,
            "gasPrice": self.w3.eth.gas_price,
        })

        signed = self.account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        self.w3.eth.wait_for_transaction_receipt(tx_hash)

        return tx_hash.hex()

    def sign_message(self, message: str) -> str:
        """Sign a message with the agent's private key (EIP-191)"""
        msg = encode_defunct(text=message)
        signed = self.account.sign_message(msg)
        return signed.signature.hex()

    def sign_typed_data(self, domain: dict, types: dict, message: dict) -> str:
        """Sign typed data (EIP-712) for trade intents"""
        # Simplified - in production use full EIP-712 encoding
        from eth_account.messages import encode_typed_data

        full_message = {
            "domain": domain,
            "types": types,
            "primaryType": list(types.keys())[0],
            "message": message
        }

        signed = self.account.sign_message(encode_typed_data(full_message))
        return signed.signature.hex()
