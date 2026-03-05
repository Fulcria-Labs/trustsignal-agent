"""ERC-8004 client for agent identity and reputation management."""

import json
import os
from pathlib import Path

from web3 import Web3
from eth_account import Account
from eth_account.messages import encode_typed_data


ABI_DIR = Path(__file__).parent.parent / "erc8004-contracts" / "abis"


def load_abi(name: str) -> list:
    with open(ABI_DIR / f"{name}.json") as f:
        return json.load(f)


class ERC8004Client:
    """Client for interacting with ERC-8004 Identity and Reputation registries."""

    def __init__(
        self,
        rpc_url: str,
        private_key: str,
        identity_registry: str,
        reputation_registry: str,
        chain_id: int = 84532,
    ):
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        self.account = Account.from_key(private_key)
        self.chain_id = chain_id

        identity_abi = load_abi("IdentityRegistry")
        reputation_abi = load_abi("ReputationRegistry")

        self.identity = self.w3.eth.contract(
            address=Web3.to_checksum_address(identity_registry),
            abi=identity_abi,
        )
        self.reputation = self.w3.eth.contract(
            address=Web3.to_checksum_address(reputation_registry),
            abi=reputation_abi,
        )

    def _send_tx(self, tx_func):
        """Build, sign, and send a transaction."""
        tx = tx_func.build_transaction({
            "from": self.account.address,
            "nonce": self.w3.eth.get_transaction_count(self.account.address),
            "gas": 500_000,
            "gasPrice": self.w3.eth.gas_price,
            "chainId": self.chain_id,
        })
        signed = self.account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
        return receipt

    def register_agent(self, agent_uri: str) -> int:
        """Register a new agent identity. Returns agentId."""
        receipt = self._send_tx(
            self.identity.functions.register(agent_uri)
        )
        # Parse Transfer event to get tokenId (agentId)
        logs = self.identity.events.Transfer().process_receipt(receipt)
        if logs:
            return logs[0]["args"]["tokenId"]
        raise RuntimeError("Registration failed - no Transfer event")

    def set_agent_uri(self, agent_id: int, uri: str):
        """Update the agent's registration URI."""
        return self._send_tx(
            self.identity.functions.setAgentURI(agent_id, uri)
        )

    def get_agent_uri(self, agent_id: int) -> str:
        """Get the agent's registration URI."""
        return self.identity.functions.tokenURI(agent_id).call()

    def give_feedback(
        self,
        agent_id: int,
        value: int,
        value_decimals: int,
        tag1: str = "",
        tag2: str = "",
        feedback_uri: str = "",
        feedback_hash: bytes = b"\x00" * 32,
    ):
        """Give reputation feedback for an agent."""
        return self._send_tx(
            self.reputation.functions.giveFeedback(
                agent_id,
                value,
                value_decimals,
                tag1,
                tag2,
                feedback_uri,
                feedback_hash,
            )
        )

    def get_summary(
        self,
        agent_id: int,
        client_addresses: list[str],
        tag1: str = "",
        tag2: str = "",
    ) -> dict:
        """Get aggregated reputation summary."""
        result = self.reputation.functions.getSummary(
            agent_id,
            [Web3.to_checksum_address(a) for a in client_addresses],
            tag1,
            tag2,
        ).call()
        return {
            "count": result[0],
            "summary_value": result[1],
            "summary_value_decimals": result[2],
        }

    def get_agent_owner(self, agent_id: int) -> str:
        """Get the owner of an agent NFT."""
        return self.identity.functions.ownerOf(agent_id).call()

    @property
    def address(self) -> str:
        return self.account.address
