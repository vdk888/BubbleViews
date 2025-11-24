"""
Moderation service implementation.

Provides content evaluation, moderation queue management,
and auto-posting configuration management.
"""

import logging
from typing import Dict, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.interfaces.moderation import IModerationService
from app.models.pending_post import PendingPost
from app.models.agent_config import AgentConfig
from app.services.event_publisher import event_publisher

logger = logging.getLogger(__name__)


class ModerationService(IModerationService):
    """
    Implementation of moderation service.

    Evaluates content against basic rules, manages moderation queue,
    and checks auto-posting configuration.
    """

    # Hardcoded list of banned keywords (can be moved to config)
    BANNED_KEYWORDS = [
        "spam",
        "viagra",
        "casino",
        "lottery",
        # Add more as needed
    ]

    # Content length limits
    MIN_CONTENT_LENGTH = 10
    MAX_CONTENT_LENGTH = 10000

    def __init__(self, db: AsyncSession):
        """
        Initialize moderation service.

        Args:
            db: Database session for queries
        """
        self.db = db

    async def evaluate_content(
        self,
        persona_id: str,
        content: str,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Evaluate content against moderation rules.

        Performs basic checks:
        1. Length validation (min/max)
        2. Banned keyword detection
        3. Placeholder for future LLM-based toxicity check

        Args:
            persona_id: ID of the persona creating content
            content: The content to evaluate
            context: Additional context (subreddit, post_type, etc.)

        Returns:
            Dictionary with evaluation result:
            {
                "approved": bool,
                "flagged": bool,
                "flags": List[str],
                "action": str  # "allow", "review", or "block"
            }

        Raises:
            ValueError: If persona_id or content is invalid
        """
        if not persona_id:
            raise ValueError("persona_id is required")
        if content is None:
            raise ValueError("content is required")

        flags = []
        approved = True

        # Check length
        content_length = len(content)
        if content_length < self.MIN_CONTENT_LENGTH:
            flags.append(f"content_too_short (min {self.MIN_CONTENT_LENGTH} chars)")
            approved = False
        elif content_length > self.MAX_CONTENT_LENGTH:
            flags.append(f"content_too_long (max {self.MAX_CONTENT_LENGTH} chars)")
            approved = False

        # Check for banned keywords
        content_lower = content.lower()
        for keyword in self.BANNED_KEYWORDS:
            if keyword in content_lower:
                flags.append(f"banned_keyword: {keyword}")
                approved = False

        # Placeholder for future LLM-based toxicity check
        # This would call an LLM client to analyze sentiment/toxicity
        # For now, we just note it as a TODO
        # if self.llm_client:
        #     toxicity_result = await self.llm_client.check_toxicity(content)
        #     if toxicity_result["toxic"]:
        #         flags.append("potential_toxicity")
        #         approved = False

        # Determine action
        if not approved:
            action = "block" if len(flags) > 0 else "review"
        else:
            action = "allow"

        result = {
            "approved": approved,
            "flagged": len(flags) > 0,
            "flags": flags,
            "action": action
        }

        logger.info(
            f"Content evaluation for persona {persona_id}: "
            f"approved={approved}, flags={flags}"
        )

        return result

    async def enqueue_for_review(
        self,
        persona_id: str,
        content: str,
        metadata: Dict[str, Any]
    ) -> str:
        """
        Add content to moderation queue for human review.

        Args:
            persona_id: ID of the persona
            content: Draft content to be reviewed
            metadata: Context metadata (post_type, target_subreddit, etc.)

        Returns:
            ID of the queued item

        Raises:
            ValueError: If required metadata is missing
        """
        if not persona_id:
            raise ValueError("persona_id is required")
        if not content:
            raise ValueError("content is required")

        # Extract metadata fields
        post_type = metadata.get("post_type", "comment")
        target_subreddit = metadata.get("target_subreddit")
        parent_id = metadata.get("parent_id")

        # Create pending post
        pending_post = PendingPost(
            persona_id=persona_id,
            content=content,
            post_type=post_type,
            target_subreddit=target_subreddit,
            parent_id=parent_id,
            status="pending"
        )

        # Store additional metadata
        pending_post.set_draft_metadata(metadata)

        self.db.add(pending_post)
        await self.db.commit()
        await self.db.refresh(pending_post)

        logger.info(
            f"Enqueued content for review: "
            f"item_id={pending_post.id}, persona_id={persona_id}"
        )

        # Publish event for real-time dashboard updates
        await event_publisher.publish_pending_post_added(
            persona_id=persona_id,
            pending_post_data={
                "id": pending_post.id,
                "content": content,
                "post_type": post_type,
                "target_subreddit": target_subreddit,
                "parent_id": parent_id,
                "status": "pending"
            }
        )

        return pending_post.id

    async def is_auto_posting_enabled(
        self,
        persona_id: str
    ) -> bool:
        """
        Check if auto-posting is enabled for a persona.

        Queries the agent_config table for the auto_posting_enabled flag.
        Returns False by default if not configured.

        Args:
            persona_id: ID of the persona

        Returns:
            True if auto-posting is enabled, False otherwise

        Raises:
            ValueError: If persona_id is invalid
        """
        if not persona_id:
            raise ValueError("persona_id is required")

        # Query agent_config for auto_posting_enabled
        stmt = select(AgentConfig).where(
            AgentConfig.persona_id == persona_id,
            AgentConfig.config_key == "auto_posting_enabled"
        )

        result = await self.db.execute(stmt)
        config = result.scalar_one_or_none()

        if config is None:
            # Default to False if not set
            logger.debug(
                f"Auto-posting config not found for persona {persona_id}, "
                f"defaulting to False"
            )
            return False

        # Parse the value
        value = config.get_value()
        is_enabled = bool(value) if value is not None else False

        logger.debug(
            f"Auto-posting for persona {persona_id}: {is_enabled}"
        )

        return is_enabled

    async def should_post_immediately(
        self,
        persona_id: str,
        evaluation: Dict[str, Any]
    ) -> bool:
        """
        Determine if content should be posted immediately.

        Decision logic:
        1. Check if auto-posting is enabled
        2. Check if content evaluation is approved
        3. Post immediately only if both conditions are true

        Args:
            persona_id: ID of the persona
            evaluation: Result from evaluate_content()

        Returns:
            True if content should post immediately, False if requires review

        Raises:
            ValueError: If evaluation dict is malformed
        """
        if not persona_id:
            raise ValueError("persona_id is required")
        if not evaluation or "approved" not in evaluation:
            raise ValueError("evaluation dict must contain 'approved' key")

        # Check auto-posting flag
        auto_enabled = await self.is_auto_posting_enabled(persona_id)
        if not auto_enabled:
            logger.info(
                f"Auto-posting disabled for persona {persona_id}, "
                f"requiring manual review"
            )
            return False

        # Check content evaluation
        if evaluation.get("flagged", False):
            logger.info(
                f"Content flagged for persona {persona_id}, "
                f"requiring manual review despite auto-posting enabled"
            )
            return False

        approved = evaluation.get("approved", False)
        logger.info(
            f"Content decision for persona {persona_id}: "
            f"post_immediately={approved}"
        )

        return approved
