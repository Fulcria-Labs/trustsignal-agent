"""
ERC-8004 Reputation Management

Handles reputation tracking and feedback on the ERC-8004 Reputation Registry.
"""
import logging
from dataclasses import dataclass
from typing import Optional, List
from web3 import Web3
from eth_account import Account

logger = logging.getLogger(__name__)


@dataclass
class FeedbackEntry:
    """Feedback entry structure"""
    from_agent: str
    to_agent: int  # token ID
    score: int  # 0-100
    tags: List[str]
    comment: str
    timestamp: int


@dataclass
class ReputationSummary:
    """Aggregated reputation summary"""
    token_id: int
    total_feedback: int
    average_score: float
    tag_scores: dict  # tag -> average score
    recent_feedback: List[FeedbackEntry]


class ReputationManager:
    """
    Manages ERC-8004 Reputation Registry interactions.

    The Reputation Registry allows:
    - Giving feedback to other agents
    - Aggregated scoring with tag filters
    - Reading historical feedback
    """

    # ERC-8004 Reputation Registry ABI (minimal)
    REPUTATION_ABI = [
        {
            "name": "giveFeedback",
            "type": "function",
            "inputs": [
                {"name": "to", "type": "uint256"},
                {"name": "score", "type": "uint8"},
                {"name": "tags", "type": "bytes32[]"},
                {"name": "comment", "type": "string"}
            ],
            "outputs": []
        },
        {
            "name": "getSummary",
            "type": "function",
            "inputs": [
                {"name": "tokenId", "type": "uint256"},
                {"name": "tagFilter", "type": "bytes32"}
            ],
            "outputs": [
                {"name": "totalFeedback", "type": "uint256"},
                {"name": "averageScore", "type": "uint256"},
                {"name": "lastUpdated", "type": "uint256"}
            ],
            "stateMutability": "view"
        },
        {
            "name": "readFeedback",
            "type": "function",
            "inputs": [
                {"name": "tokenId", "type": "uint256"},
                {"name": "offset", "type": "uint256"},
                {"name": "limit", "type": "uint256"}
            ],
            "outputs": [
                {
                    "name": "feedback",
                    "type": "tuple[]",
                    "components": [
                        {"name": "from", "type": "address"},
                        {"name": "score", "type": "uint8"},
                        {"name": "tags", "type": "bytes32[]"},
                        {"name": "comment", "type": "string"},
                        {"name": "timestamp", "type": "uint256"}
                    ]
                }
            ],
            "stateMutability": "view"
        }
    ]

    # Standard tags for trading agents
    TAGS = {
        "execution": Web3.keccak(text="execution")[:32],
        "profitability": Web3.keccak(text="profitability")[:32],
        "reliability": Web3.keccak(text="reliability")[:32],
        "speed": Web3.keccak(text="speed")[:32],
        "risk_management": Web3.keccak(text="risk_management")[:32],
    }

    def __init__(
        self,
        w3: Web3,
        registry_address: str,
        private_key: str,
        agent_token_id: Optional[int] = None
    ):
        self.w3 = w3
        self.account = Account.from_key(private_key)
        self.registry = w3.eth.contract(
            address=Web3.to_checksum_address(registry_address),
            abi=self.REPUTATION_ABI
        )
        self.agent_token_id = agent_token_id

    async def give_feedback(
        self,
        to_agent: int,
        score: int,
        tags: List[str],
        comment: str
    ) -> str:
        """
        Give feedback to another agent.

        Args:
            to_agent: Token ID of the agent to rate
            score: Score 0-100
            tags: List of tag names (will be converted to bytes32)
            comment: Human-readable comment

        Returns:
            Transaction hash
        """
        if score < 0 or score > 100:
            raise ValueError("Score must be 0-100")

        # Convert tag names to bytes32
        tag_bytes = [self.TAGS.get(t, Web3.keccak(text=t)[:32]) for t in tags]

        tx = self.registry.functions.giveFeedback(
            to_agent,
            score,
            tag_bytes,
            comment
        ).build_transaction({
            "from": self.account.address,
            "nonce": self.w3.eth.get_transaction_count(self.account.address),
            "gas": 200000,
            "gasPrice": self.w3.eth.gas_price,
        })

        signed = self.account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        self.w3.eth.wait_for_transaction_receipt(tx_hash)

        logger.info(f"Gave feedback to agent {to_agent}: {score}/100")
        return tx_hash.hex()

    async def get_summary(
        self,
        token_id: Optional[int] = None,
        tag_filter: Optional[str] = None
    ) -> ReputationSummary:
        """
        Get aggregated reputation summary.

        Args:
            token_id: Agent token ID (defaults to self)
            tag_filter: Optional tag to filter by

        Returns:
            ReputationSummary with aggregated scores
        """
        tid = token_id or self.agent_token_id
        if not tid:
            raise ValueError("No token ID specified")

        tag_bytes = self.TAGS.get(tag_filter, b'\x00' * 32) if tag_filter else b'\x00' * 32

        total, avg, updated = self.registry.functions.getSummary(
            tid,
            tag_bytes
        ).call()

        return ReputationSummary(
            token_id=tid,
            total_feedback=total,
            average_score=avg / 100.0 if avg > 0 else 0.0,  # Stored as fixed point
            tag_scores={},
            recent_feedback=[]
        )

    async def get_feedback_history(
        self,
        token_id: Optional[int] = None,
        offset: int = 0,
        limit: int = 10
    ) -> List[FeedbackEntry]:
        """
        Read historical feedback for an agent.

        Args:
            token_id: Agent token ID (defaults to self)
            offset: Pagination offset
            limit: Number of entries to return

        Returns:
            List of FeedbackEntry
        """
        tid = token_id or self.agent_token_id
        if not tid:
            raise ValueError("No token ID specified")

        raw_feedback = self.registry.functions.readFeedback(
            tid,
            offset,
            limit
        ).call()

        entries = []
        for f in raw_feedback:
            entries.append(FeedbackEntry(
                from_agent=f[0],
                to_agent=tid,
                score=f[1],
                tags=[],  # Would need to decode bytes32 tags
                comment=f[3],
                timestamp=f[4]
            ))

        return entries

    def calculate_trust_score(self, summary: ReputationSummary) -> float:
        """
        Calculate a composite trust score from reputation data.

        Uses weighted factors:
        - Average score (40%)
        - Total feedback count (30%)
        - Recency of feedback (30%)

        Returns:
            Trust score 0.0 - 1.0
        """
        if summary.total_feedback == 0:
            return 0.0

        # Score component (0-1)
        score_factor = summary.average_score / 100.0

        # Volume component (logarithmic, caps at 100 feedback)
        import math
        volume_factor = min(1.0, math.log10(summary.total_feedback + 1) / 2.0)

        # Recency component would need timestamp analysis
        recency_factor = 1.0  # Placeholder

        trust = (
            0.4 * score_factor +
            0.3 * volume_factor +
            0.3 * recency_factor
        )

        return round(trust, 4)
