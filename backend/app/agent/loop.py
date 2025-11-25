"""
Agent Decision Loop Core

Implements the main agent loop with phases:
1. Perception: Monitor Reddit for new posts
2. Decision: Decide whether to respond
3. Retrieval: Assemble context (beliefs, past comments, evidence)
4. Generation: Draft response via LLM
5. Consistency: Check draft against beliefs
6. Moderation: Evaluate content and decide action
7. Action: Post immediately or enqueue for review

Follows Week 4 Day 2 specifications with graceful shutdown,
error handling, exponential backoff, and structured logging.
"""

import asyncio
import logging
import random
import uuid
from typing import Dict, List, Optional, Any
from datetime import datetime

from app.services.interfaces.reddit_client import IRedditClient
from app.services.interfaces.llm_client import ILLMClient
from app.services.interfaces.memory_store import IMemoryStore
from app.services.retrieval import RetrievalCoordinator
from app.services.moderation import ModerationService
from app.services.belief_analyzer import analyze_interaction_for_beliefs

logger = logging.getLogger(__name__)


class AgentLoop:
    """
    Main agent decision loop with dependency injection.

    Orchestrates the complete agent workflow:
    - Monitors Reddit for relevant posts
    - Retrieves context from memory and belief graph
    - Generates draft responses using LLM
    - Checks consistency with beliefs
    - Applies moderation rules
    - Posts or enqueues content

    Implements graceful shutdown, error handling with exponential backoff,
    and structured logging with correlation IDs.
    """

    def __init__(
        self,
        reddit_client: IRedditClient,
        llm_client: ILLMClient,
        memory_store: IMemoryStore,
        retrieval: RetrievalCoordinator,
        moderation: ModerationService,
        interval_seconds: int = 14400,
        max_posts_per_cycle: int = 5,
        response_probability: float = 0.3,
    ):
        """
        Initialize agent loop with injected dependencies.

        Args:
            reddit_client: Reddit API client
            llm_client: LLM client for generation and consistency checking
            memory_store: Memory store for interactions and beliefs
            retrieval: Retrieval coordinator for context assembly
            moderation: Moderation service for content evaluation
            interval_seconds: Seconds between perception cycles (default: 14400 = 4 hours)
            max_posts_per_cycle: Max posts to process per cycle (default: 5)
            response_probability: Probability of responding to eligible posts (default: 0.3)
        """
        self.reddit_client = reddit_client
        self.llm_client = llm_client
        self.memory_store = memory_store
        self.retrieval = retrieval
        self.moderation = moderation

        self.interval_seconds = interval_seconds
        self.max_posts_per_cycle = max_posts_per_cycle
        self.response_probability = response_probability

        # Internal state
        self._stop_event = asyncio.Event()
        self._consecutive_errors = 0
        self._max_consecutive_errors = 5

    async def run(self, persona_id: str, stop_event: Optional[asyncio.Event] = None) -> None:
        """
        Run the main agent loop for a specific persona.

        Continuously monitors Reddit, processes posts, and executes actions
        until stop event is set or max consecutive errors reached.

        Args:
            persona_id: UUID of persona to run loop for
            stop_event: Optional external stop event (default: use internal)

        Raises:
            ValueError: If persona_id is invalid or persona not found
        """
        if not persona_id:
            raise ValueError("persona_id is required")

        # Validate persona exists
        try:
            persona = await self.memory_store.get_persona(persona_id)
            if not persona:
                raise ValueError(f"Persona not found: {persona_id}")
        except Exception as e:
            logger.error(f"Failed to load persona {persona_id}: {e}")
            raise

        # Use provided stop event or internal
        stop_signal = stop_event or self._stop_event

        logger.info(
            f"Agent loop starting for persona {persona['reddit_username']}",
            extra={
                "persona_id": persona_id,
                "interval_seconds": self.interval_seconds,
                "max_posts_per_cycle": self.max_posts_per_cycle,
            }
        )

        cycle_count = 0

        while not stop_signal.is_set():
            correlation_id = str(uuid.uuid4())
            cycle_count += 1

            logger.info(
                f"Agent loop cycle {cycle_count} starting",
                extra={"persona_id": persona_id, "correlation_id": correlation_id}
            )

            try:
                # Execute one cycle
                await self._execute_cycle(persona_id, correlation_id)

                # Reset error counter on success
                self._consecutive_errors = 0

                # Wait before next cycle
                await asyncio.sleep(self.interval_seconds)

            except Exception as e:
                self._consecutive_errors += 1
                logger.error(
                    f"Agent loop cycle {cycle_count} failed (consecutive errors: {self._consecutive_errors}): {e}",
                    extra={"persona_id": persona_id, "correlation_id": correlation_id},
                    exc_info=True
                )

                # Check if max errors reached
                if self._consecutive_errors >= self._max_consecutive_errors:
                    logger.critical(
                        f"Max consecutive errors ({self._max_consecutive_errors}) reached, stopping agent loop",
                        extra={"persona_id": persona_id}
                    )
                    break

                # Exponential backoff with jitter
                backoff_delay = self._calculate_backoff(self._consecutive_errors)
                logger.info(
                    f"Backing off for {backoff_delay:.2f}s before retry",
                    extra={"persona_id": persona_id, "consecutive_errors": self._consecutive_errors}
                )
                await asyncio.sleep(backoff_delay)

        logger.info(
            f"Agent loop stopped for persona {persona['reddit_username']}",
            extra={"persona_id": persona_id, "cycle_count": cycle_count}
        )

    async def stop(self) -> None:
        """
        Signal agent loop to stop gracefully.

        Sets internal stop event. Loop will complete current cycle
        and then exit.
        """
        logger.info("Agent loop stop requested")
        self._stop_event.set()

    async def _execute_cycle(self, persona_id: str, correlation_id: str) -> None:
        """
        Execute one complete agent loop cycle.

        Steps:
        1. Perceive new posts
        2. Filter and decide which to respond to
        3. For each eligible post:
           a. Retrieve context
           b. Generate draft
           c. Check consistency
           d. Moderate draft
           e. Execute action (post or enqueue)

        Args:
            persona_id: UUID of persona
            correlation_id: Request correlation ID for logging

        Raises:
            Exception: Propagates any errors for cycle-level handling
        """
        # Phase 1: Perception
        posts = await self.perceive(persona_id)

        if not posts:
            logger.debug(
                f"No new posts found in cycle",
                extra={"persona_id": persona_id, "correlation_id": correlation_id}
            )
            return

        logger.info(
            f"Perceived {len(posts)} new posts",
            extra={"persona_id": persona_id, "correlation_id": correlation_id}
        )

        # Phase 2: Decision - filter posts
        eligible_posts = []
        for post in posts:
            if await self.should_respond(persona_id, post):
                eligible_posts.append(post)

        if not eligible_posts:
            logger.debug(
                f"No eligible posts after filtering",
                extra={"persona_id": persona_id, "correlation_id": correlation_id}
            )
            return

        logger.info(
            f"{len(eligible_posts)} posts eligible for response",
            extra={"persona_id": persona_id, "correlation_id": correlation_id}
        )

        # Limit to max posts per cycle
        posts_to_process = eligible_posts[:self.max_posts_per_cycle]

        # Process each post
        for post in posts_to_process:
            post_correlation_id = f"{correlation_id}-{post['id']}"
            try:
                await self._process_post(persona_id, post, post_correlation_id)
            except Exception as e:
                logger.error(
                    f"Failed to process post {post['id']}: {e}",
                    extra={"persona_id": persona_id, "correlation_id": post_correlation_id},
                    exc_info=True
                )
                # Continue with next post

    async def perceive(self, persona_id: str) -> List[Dict[str, Any]]:
        """
        Perception phase: Monitor Reddit for new posts.

        Fetches new posts from configured subreddits and filters
        out already-seen posts.

        Args:
            persona_id: UUID of persona

        Returns:
            List of unseen post dictionaries

        Raises:
            ValueError: If persona config invalid or target_subreddits missing
            ConnectionError: If Reddit API unreachable
        """
        # Load persona config
        persona = await self.memory_store.get_persona(persona_id)
        config = persona.get("config", {})
        target_subreddits = config.get("target_subreddits", [])

        if not target_subreddits:
            logger.warning(
                f"No target_subreddits configured for persona {persona_id}, skipping perception"
            )
            return []

        # Fetch new posts
        all_posts = await self.reddit_client.get_new_posts(
            subreddits=target_subreddits,
            limit=10
        )

        # Filter already-seen posts
        unseen_posts = []
        for post in all_posts:
            reddit_id = post["id"]

            # Check if we've already interacted with this post
            interactions = await self.memory_store.search_interactions(
                persona_id=persona_id,
                reddit_id=reddit_id
            )

            if not interactions:
                unseen_posts.append(post)

        logger.debug(
            f"Perceived {len(all_posts)} posts, {len(unseen_posts)} unseen",
            extra={"persona_id": persona_id, "subreddits": target_subreddits}
        )

        return unseen_posts

    async def should_respond(self, persona_id: str, post: Dict[str, Any]) -> bool:
        """
        Decision phase: Decide if agent should respond to post.

        Checks:
        1. Post is not by this persona (avoid self-replies)
        2. Post matches interest keywords (if configured)
        3. Random sampling (to limit volume)

        Args:
            persona_id: UUID of persona
            post: Post dictionary from Reddit

        Returns:
            True if agent should respond, False otherwise

        Raises:
            ValueError: If post dict missing required fields
        """
        if "author" not in post or "id" not in post:
            raise ValueError("Post dict must contain 'author' and 'id'")

        # Load persona
        persona = await self.memory_store.get_persona(persona_id)
        reddit_username = persona["reddit_username"]
        config = persona.get("config", {})

        # Check 1: Not own post
        if post["author"].lower() == reddit_username.lower():
            logger.debug(
                f"Skipping own post {post['id']}",
                extra={"persona_id": persona_id, "post_id": post["id"], "reason": "own_post"}
            )
            return False

        # Check 2: Interest keywords (optional)
        interest_keywords = config.get("interest_keywords", [])
        if interest_keywords:
            # Check if post title or body contains any keyword
            title = post.get("title", "").lower()
            body = post.get("selftext", "").lower()
            content = f"{title} {body}"

            has_match = any(keyword.lower() in content for keyword in interest_keywords)
            if not has_match:
                logger.debug(
                    f"Skipping post {post['id']} (no keyword match)",
                    extra={"persona_id": persona_id, "post_id": post["id"], "reason": "no_keyword_match"}
                )
                return False

        # Check 3: Random sampling
        if random.random() > self.response_probability:
            logger.debug(
                f"Skipping post {post['id']} (random sampling)",
                extra={"persona_id": persona_id, "post_id": post["id"], "reason": "random_sampling"}
            )
            return False

        logger.info(
            f"Post {post['id']} eligible for response",
            extra={"persona_id": persona_id, "post_id": post["id"]}
        )
        return True

    async def _process_post(
        self,
        persona_id: str,
        post: Dict[str, Any],
        correlation_id: str
    ) -> None:
        """
        Process a single post through the full pipeline.

        Steps:
        1. Assemble context
        2. Generate draft
        3. Check consistency
        4. Moderate
        5. Execute action

        Args:
            persona_id: UUID of persona
            post: Post dictionary
            correlation_id: Request correlation ID

        Raises:
            Exception: Propagates any processing errors
        """
        # Phase 3: Retrieval - assemble context
        thread_context = {
            "title": post.get("title", ""),
            "body": post.get("selftext", ""),
            "subreddit": post["subreddit"],
            "reddit_id": post["id"],
            "url": post.get("url", ""),
        }

        context = await self.retrieval.assemble_context(
            persona_id=persona_id,
            thread_context=thread_context
        )

        logger.debug(
            f"Assembled context for post {post['id']}: {context['token_count']} tokens",
            extra={"persona_id": persona_id, "correlation_id": correlation_id}
        )

        # Phase 4: Generation - draft response
        draft = await self.generate_draft(persona_id, context, correlation_id)

        logger.info(
            f"Generated draft for post {post['id']}: {len(draft['text'])} chars",
            extra={
                "persona_id": persona_id,
                "correlation_id": correlation_id,
                "tokens_in": draft["tokens_in"],
                "tokens_out": draft["tokens_out"],
                "cost": draft["cost"],
            }
        )

        # Phase 5: Consistency - check against beliefs
        consistency_result = await self.check_draft_consistency(
            draft["text"],
            context["beliefs"],
            correlation_id
        )

        if not consistency_result["is_consistent"]:
            logger.warning(
                f"Draft for post {post['id']} conflicts with beliefs: {consistency_result['explanation']}",
                extra={"persona_id": persona_id, "correlation_id": correlation_id, "conflicts": consistency_result["conflicts"]}
            )

        # Phase 6: Moderation - evaluate and decide
        decision = await self.moderate_draft(persona_id, draft["text"], post, correlation_id)

        logger.info(
            f"Moderation decision for post {post['id']}: {decision['action']}",
            extra={"persona_id": persona_id, "correlation_id": correlation_id, "decision": decision}
        )

        # Phase 7: Action - execute
        result = await self.execute_action(persona_id, draft["text"], post, decision, correlation_id)

        logger.info(
            f"Action executed for post {post['id']}: {result}",
            extra={"persona_id": persona_id, "correlation_id": correlation_id}
        )

    async def generate_draft(
        self,
        persona_id: str,
        context: Dict[str, Any],
        correlation_id: str
    ) -> Dict[str, Any]:
        """
        Generate draft response using LLM.

        Builds system prompt from persona config and calls LLM client
        to generate a response based on assembled context.

        Args:
            persona_id: UUID of persona
            context: Assembled context from retrieval
            correlation_id: Request correlation ID

        Returns:
            Draft response dict:
            {
                "text": "Generated response",
                "model": "model-name",
                "tokens_in": 1234,
                "tokens_out": 567,
                "total_tokens": 1801,
                "cost": 0.0234
            }

        Raises:
            Exception: LLM API errors or context assembly errors
        """
        # Load persona
        persona = await self.memory_store.get_persona(persona_id)

        # Build system prompt
        config = persona.get("config", {})
        system_prompt = self._build_system_prompt(config)

        # Assemble prompt from context
        prompt = await self.retrieval.assemble_prompt(persona, context)

        # User message
        thread = context.get("thread", {})
        user_message = f"Draft a comment in response to this Reddit post in r/{thread.get('subreddit')}."

        # Call LLM
        response = await self.llm_client.generate_response(
            system_prompt=system_prompt,
            context=context,
            user_message=user_message,
            temperature=0.7,
            max_tokens=500,
            correlation_id=correlation_id
        )

        return response

    async def check_draft_consistency(
        self,
        draft: str,
        beliefs: List[Dict[str, Any]],
        correlation_id: str
    ) -> Dict[str, Any]:
        """
        Check if draft is consistent with agent's beliefs.

        Uses LLM to analyze whether the draft contradicts any
        held beliefs.

        Args:
            draft: Generated draft text
            beliefs: List of belief dictionaries
            correlation_id: Request correlation ID

        Returns:
            Consistency check result:
            {
                "is_consistent": bool,
                "conflicts": List[str],  # Belief IDs
                "explanation": str,
                "model": str,
                "tokens_in": int,
                "tokens_out": int,
                "cost": float
            }

        Raises:
            Exception: LLM API errors
        """
        if not beliefs:
            # No beliefs to check against, automatically consistent
            return {
                "is_consistent": True,
                "conflicts": [],
                "explanation": "No beliefs to check against",
                "model": "none",
                "tokens_in": 0,
                "tokens_out": 0,
                "cost": 0.0
            }

        result = await self.llm_client.check_consistency(
            draft_response=draft,
            beliefs=beliefs,
            correlation_id=correlation_id
        )

        return result

    async def moderate_draft(
        self,
        persona_id: str,
        draft: str,
        post: Dict[str, Any],
        correlation_id: str
    ) -> Dict[str, Any]:
        """
        Moderate draft and decide action.

        Evaluates content against moderation rules and checks
        auto-posting configuration.

        Args:
            persona_id: UUID of persona
            draft: Draft text to moderate
            post: Original Reddit post dict
            correlation_id: Request correlation ID

        Returns:
            Decision dict:
            {
                "action": "post_now" | "queue" | "drop",
                "evaluation": {...},  # From moderation service
                "auto_posting_enabled": bool
            }

        Raises:
            ValueError: If evaluation fails
        """
        # Evaluate content
        context = {
            "subreddit": post["subreddit"],
            "post_type": "comment",
            "parent_id": f"t3_{post['id']}",
        }

        evaluation = await self.moderation.evaluate_content(
            persona_id=persona_id,
            content=draft,
            context=context
        )

        # Check auto-posting
        auto_enabled = await self.moderation.is_auto_posting_enabled(persona_id)

        # Decide action
        if evaluation["action"] == "block":
            action = "drop"
            logger.warning(
                f"Draft blocked by moderation: {evaluation['flags']}",
                extra={"persona_id": persona_id, "correlation_id": correlation_id}
            )
        elif not auto_enabled or evaluation.get("flagged", False):
            action = "queue"
        else:
            action = "post_now"

        return {
            "action": action,
            "evaluation": evaluation,
            "auto_posting_enabled": auto_enabled
        }

    async def execute_action(
        self,
        persona_id: str,
        draft: str,
        post: Dict[str, Any],
        decision: Dict[str, Any],
        correlation_id: str
    ) -> str:
        """
        Execute action based on moderation decision.

        Posts immediately, enqueues for review, or drops based on decision.

        Args:
            persona_id: UUID of persona
            draft: Draft text
            post: Original Reddit post
            decision: Decision dict from moderate_draft
            correlation_id: Request correlation ID

        Returns:
            Result string describing action taken:
            - "posted:{reddit_id}" if posted immediately
            - "queued:{queue_id}" if enqueued for review
            - "dropped:{reason}" if dropped

        Raises:
            Exception: Reddit API errors or database errors
        """
        action = decision["action"]
        parent_id = f"t3_{post['id']}"

        if action == "post_now":
            try:
                # Post to Reddit
                reddit_id = await self.reddit_client.reply(
                    parent_id=parent_id,
                    content=draft
                )

                # Log interaction
                await self.memory_store.log_interaction(
                    persona_id=persona_id,
                    content=draft,
                    interaction_type="comment",
                    metadata={
                        "reddit_id": reddit_id,
                        "parent_id": parent_id,
                        "subreddit": post["subreddit"],
                        "correlation_id": correlation_id,
                        "auto_posted": True
                    }
                )

                logger.info(
                    f"Posted comment {reddit_id} to Reddit",
                    extra={"persona_id": persona_id, "correlation_id": correlation_id}
                )

                return f"posted:{reddit_id}"

            except Exception as e:
                logger.error(
                    f"Failed to post to Reddit: {e}",
                    extra={"persona_id": persona_id, "correlation_id": correlation_id},
                    exc_info=True
                )
                # Fall back to queueing
                action = "queue"

        if action == "queue":
            # Analyze interaction for belief evolution proposals
            thread_context = {
                "subreddit": post.get("subreddit", ""),
                "title": post.get("title", ""),
                "body": post.get("selftext", post.get("body", "")),
                "parent_comment": None  # Direct reply to post, no parent comment
            }

            belief_proposals = await analyze_interaction_for_beliefs(
                persona_id=persona_id,
                draft_content=draft,
                thread_context=thread_context,
                llm_client=self.llm_client,
                memory_store=self.memory_store,
                correlation_id=correlation_id
            )

            # Enqueue for review with belief proposals
            metadata = {
                "post_type": "comment",
                "target_subreddit": post["subreddit"],
                "parent_id": parent_id,
                "correlation_id": correlation_id,
                "evaluation": decision["evaluation"],
                "belief_proposals": belief_proposals.to_dict()
            }

            queue_id = await self.moderation.enqueue_for_review(
                persona_id=persona_id,
                content=draft,
                metadata=metadata
            )

            logger.info(
                f"Enqueued draft for review: {queue_id}",
                extra={
                    "persona_id": persona_id,
                    "correlation_id": correlation_id,
                    "belief_update_count": len(belief_proposals.updates),
                    "has_new_belief": belief_proposals.new_belief is not None
                }
            )

            return f"queued:{queue_id}"

        # action == "drop"
        reason = ", ".join(decision["evaluation"].get("flags", ["blocked"]))
        logger.info(
            f"Dropped draft: {reason}",
            extra={"persona_id": persona_id, "correlation_id": correlation_id}
        )
        return f"dropped:{reason}"

    def _build_system_prompt(self, config: Dict[str, Any]) -> str:
        """
        Build system prompt from persona config.

        Args:
            config: Persona config dict

        Returns:
            System prompt string
        """
        tone = config.get("tone", "neutral")
        style = config.get("style", "casual")
        values = config.get("values", [])

        prompt = f"""You are a Reddit user with the following characteristics:

Tone: {tone}
Style: {style}
Core Values: {", ".join(values) if values else "None specified"}

Instructions:
- Stay true to your beliefs and persona
- Be respectful and follow Reddit etiquette
- Cite evidence when making factual claims
- Avoid contradicting your core beliefs without good reason
- Keep responses concise and on-topic
- Use markdown formatting when appropriate

Never:
- Share personal information
- Engage in harassment or hate speech
- Spread misinformation
- Violate Reddit's content policy
"""
        return prompt

    def _calculate_backoff(self, consecutive_errors: int) -> float:
        """
        Calculate exponential backoff delay with jitter.

        Formula: (2^consecutive_errors) + random(0, 1)
        Max: 60 seconds

        Args:
            consecutive_errors: Number of consecutive errors

        Returns:
            Delay in seconds
        """
        base_delay = min(2 ** consecutive_errors, 60)
        jitter = random.random()
        return base_delay + jitter


async def run_agent(
    persona_id: str,
    reddit_client: IRedditClient,
    llm_client: ILLMClient,
    memory_store: IMemoryStore,
    retrieval: RetrievalCoordinator,
    moderation: ModerationService,
    stop_event: Optional[asyncio.Event] = None,
    interval_seconds: int = 14400
) -> None:
    """
    Convenience function to run agent loop.

    Args:
        persona_id: UUID of persona to run
        reddit_client: Reddit client instance
        llm_client: LLM client instance
        memory_store: Memory store instance
        retrieval: Retrieval coordinator instance
        moderation: Moderation service instance
        stop_event: Optional stop event
        interval_seconds: Seconds between cycles (default: 14400 = 4 hours)

    Raises:
        ValueError: If persona not found or dependencies invalid
    """
    loop = AgentLoop(
        reddit_client=reddit_client,
        llm_client=llm_client,
        memory_store=memory_store,
        retrieval=retrieval,
        moderation=moderation,
        interval_seconds=interval_seconds
    )

    await loop.run(persona_id, stop_event)
