"""
Moderation service interface.

Defines contract for content evaluation and moderation queue management.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any


class IModerationService(ABC):
    """
    Abstract interface for moderation operations.

    Provides methods for content evaluation, queue management,
    and auto-posting configuration checks. All implementations
    must enforce persona isolation.
    """

    @abstractmethod
    async def evaluate_content(
        self,
        persona_id: str,
        content: str,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Evaluate content against moderation rules.

        Checks content for policy violations, banned keywords, length limits,
        and other quality criteria. Returns evaluation result with flags
        and recommended action.

        Args:
            persona_id: ID of the persona creating content
            content: The content to evaluate
            context: Additional context (subreddit, post_type, etc.)

        Returns:
            Dictionary with evaluation result:
            {
                "approved": bool,      # Content passes all checks
                "flagged": bool,       # Content has warnings/concerns
                "flags": List[str],    # List of specific issues found
                "action": str          # "allow", "review", or "block"
            }

        Raises:
            ValueError: If persona_id or content is invalid
        """
        pass

    @abstractmethod
    async def enqueue_for_review(
        self,
        persona_id: str,
        content: str,
        metadata: Dict[str, Any]
    ) -> str:
        """
        Add content to moderation queue for human review.

        Creates a pending post entry that requires approval before
        publication to Reddit.

        Args:
            persona_id: ID of the persona
            content: Draft content to be reviewed
            metadata: Context metadata (post_type, target_subreddit, etc.)

        Returns:
            ID of the queued item

        Raises:
            ValueError: If required metadata is missing
        """
        pass

    @abstractmethod
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
        pass

    @abstractmethod
    async def should_post_immediately(
        self,
        persona_id: str,
        evaluation: Dict[str, Any]
    ) -> bool:
        """
        Determine if content should be posted immediately.

        Decision logic combining auto-posting flag and content evaluation.
        Content is posted immediately only if:
        - Auto-posting is enabled for the persona
        - Content evaluation is approved (no flags)

        Args:
            persona_id: ID of the persona
            evaluation: Result from evaluate_content()

        Returns:
            True if content should post immediately, False if requires review

        Raises:
            ValueError: If evaluation dict is malformed
        """
        pass
