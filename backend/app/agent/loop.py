"""
Agent Decision Loop Core

Implements the main agent loop with phases:
1. Perception: Monitor Reddit for new posts
2. Decision: Decide whether to respond
3. Retrieval: Assemble context (beliefs, past comments, evidence)
4. Generation: Draft response via LLM (with tool calling support)
5. Consistency: Check draft against beliefs
6. Moderation: Evaluate content and decide action
7. Action: Post immediately or enqueue for review

Follows Week 4 Day 2 specifications with graceful shutdown,
error handling, exponential backoff, and structured logging.

Tool Calling:
The agent can use tools during response generation, such as:
- fetch_url: Fetch and read content from web URLs

Tool calls are executed in a loop until the LLM returns a final response
without tool calls, or max iterations is reached.
"""

import asyncio
import json
import logging
import math
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
from app.agent.tools import AGENT_TOOLS
from app.agent.tool_executor import ToolExecutor, create_tool_executor

logger = logging.getLogger(__name__)

# Maximum tool calling iterations to prevent infinite loops
MAX_TOOL_ITERATIONS = 3


class AgentLoop:
    """
    Main agent decision loop with dependency injection.

    Orchestrates the complete agent workflow:
    - Monitors Reddit for relevant posts
    - Detects and responds to replies to agent's comments
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
        tool_executor: Optional[ToolExecutor] = None,
        interval_seconds: int = 14400,
        max_posts_per_cycle: int = 10,
        response_probability: float = 0.3,
        max_conversation_depth: int = 5,
        engagement_config: Optional[Dict[str, float]] = None,
        max_post_age_hours: int = 24,
        # Natural timing config
        active_hours_start: int = 8,
        active_hours_end: int = 23,
        burst_probability: float = 0.2,
    ):
        """
        Initialize agent loop with injected dependencies.

        Args:
            reddit_client: Reddit API client
            llm_client: LLM client for generation and consistency checking
            memory_store: Memory store for interactions and beliefs
            retrieval: Retrieval coordinator for context assembly
            moderation: Moderation service for content evaluation
            tool_executor: Optional tool executor for LLM tool calls (auto-created if None)
            interval_seconds: Seconds between perception cycles (default: 14400 = 4 hours).
                Note: This is now used as a fallback; natural timing is preferred.
            max_posts_per_cycle: Max posts to process per cycle (default: 10)
            response_probability: Probability of responding to eligible posts (default: 0.3)
            max_conversation_depth: Maximum depth of reply chain to engage in (default: 5)
            engagement_config: Configuration for engagement-based post selection (optional).
                Keys: score_weight, comment_weight, min_probability, max_probability, probability_midpoint
            max_post_age_hours: Maximum age of posts to consider in hours (default: 24).
                Posts older than this are skipped even if they appear in the "new" feed.
            active_hours_start: Hour when active period starts (default: 8 = 8am)
            active_hours_end: Hour when active period ends (default: 23 = 11pm)
            burst_probability: Probability of quick follow-up after activity (default: 0.2)
        """
        self.reddit_client = reddit_client
        self.llm_client = llm_client
        self.memory_store = memory_store
        self.retrieval = retrieval
        self.moderation = moderation
        self.tool_executor = tool_executor or create_tool_executor()

        self.interval_seconds = interval_seconds
        self.max_posts_per_cycle = max_posts_per_cycle
        self.response_probability = response_probability
        self.max_conversation_depth = max_conversation_depth
        self.engagement_config = engagement_config or {
            "score_weight": 1.0,
            "comment_weight": 2.0,
            "min_probability": 0.1,
            "max_probability": 0.8,
            "probability_midpoint": 20.0,
        }
        self.max_post_age_hours = max_post_age_hours

        # Natural timing config
        self.active_hours_start = active_hours_start
        self.active_hours_end = active_hours_end
        self.burst_probability = burst_probability

        # Internal state
        self._stop_event = asyncio.Event()
        self._consecutive_errors = 0
        self._max_consecutive_errors = 5
        self._last_was_burst = False

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

        # Log persona config summary for verification
        config = persona.get("config", {})
        self._log_persona_config_summary(persona, config)

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
                had_activity = await self._execute_cycle(persona_id, correlation_id)

                # Reset error counter on success
                self._consecutive_errors = 0

                # Calculate natural delay based on activity and time of day
                delay, self._last_was_burst = self._calculate_next_delay(
                    had_activity, self._last_was_burst
                )
                delay_hours = delay / 3600

                logger.info(
                    f"Next cycle in {delay_hours:.1f} hours" + (" (burst)" if self._last_was_burst else ""),
                    extra={
                        "persona_id": persona_id,
                        "delay_seconds": delay,
                        "delay_hours": round(delay_hours, 2),
                        "is_burst": self._last_was_burst,
                        "had_activity": had_activity
                    }
                )

                # Wait before next cycle
                await asyncio.sleep(delay)

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

    async def _execute_cycle(self, persona_id: str, correlation_id: str) -> bool:
        """
        Execute one complete agent loop cycle.

        Steps:
        1. Perceive replies to agent's comments (inbox)
        2. Process eligible replies
        3. Perceive new posts
        4. Filter and decide which to respond to
        5. For each eligible post:
           a. Retrieve context
           b. Generate draft
           c. Check consistency
           d. Moderate draft
           e. Execute action (post or enqueue)

        Args:
            persona_id: UUID of persona
            correlation_id: Request correlation ID for logging

        Returns:
            True if any posts or replies were processed, False otherwise

        Raises:
            Exception: Propagates any errors for cycle-level handling
        """
        had_activity = False
        # Phase 1a: Perceive replies to our comments
        replies = await self.perceive_replies(persona_id)

        if replies:
            logger.info(
                f"Perceived {len(replies)} new replies to process",
                extra={"persona_id": persona_id, "correlation_id": correlation_id}
            )

            # Process each reply
            for reply in replies:
                reply_correlation_id = f"{correlation_id}-reply-{reply['id']}"
                try:
                    await self.process_reply(persona_id, reply, reply_correlation_id)
                    had_activity = True  # Mark that we processed a reply
                except Exception as e:
                    logger.error(
                        f"Failed to process reply {reply['id']}: {e}",
                        extra={"persona_id": persona_id, "correlation_id": reply_correlation_id},
                        exc_info=True
                    )
                    # Continue with next reply
        else:
            logger.debug(
                f"No new replies found in cycle",
                extra={"persona_id": persona_id, "correlation_id": correlation_id}
            )

        # Phase 1b: Perception - new posts
        posts = await self.perceive(persona_id)

        if not posts:
            logger.debug(
                f"No new posts found in cycle",
                extra={"persona_id": persona_id, "correlation_id": correlation_id}
            )
            return had_activity

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
            return had_activity

        logger.info(
            f"{len(eligible_posts)} posts eligible for response",
            extra={"persona_id": persona_id, "correlation_id": correlation_id}
        )

        # Sort by engagement score (descending) to prioritize high-engagement posts
        eligible_posts.sort(
            key=lambda p: self._calculate_engagement_score(p),
            reverse=True
        )

        # Randomize number of posts (1 to max) for more natural behavior
        num_posts = random.randint(1, min(len(eligible_posts), self.max_posts_per_cycle))
        posts_to_process = eligible_posts[:num_posts]

        logger.info(
            f"Processing {num_posts} posts this cycle (max: {self.max_posts_per_cycle})",
            extra={"persona_id": persona_id, "correlation_id": correlation_id, "num_posts": num_posts}
        )

        # Process each post
        for post in posts_to_process:
            post_correlation_id = f"{correlation_id}-{post['id']}"
            try:
                await self._process_post(persona_id, post, post_correlation_id)
                had_activity = True  # Mark that we processed a post
            except Exception as e:
                logger.error(
                    f"Failed to process post {post['id']}: {e}",
                    extra={"persona_id": persona_id, "correlation_id": post_correlation_id},
                    exc_info=True
                )
                # Continue with next post

        return had_activity

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

        # Calculate cutoff timestamp for max age filter
        import time
        current_time = time.time()
        max_age_seconds = self.max_post_age_hours * 3600
        cutoff_timestamp = current_time - max_age_seconds

        # Filter already-seen posts and posts older than max_post_age_hours
        unseen_posts = []
        skipped_old = 0
        for post in all_posts:
            # Check post age first (cheaper than DB lookup)
            post_created = post.get("created_utc", 0)
            if post_created < cutoff_timestamp:
                skipped_old += 1
                continue

            # Use t3_ prefix to match how parent_id is stored in interactions
            reddit_id = f"t3_{post['id']}"

            # Check if we've already interacted with this post
            interactions = await self.memory_store.search_interactions(
                persona_id=persona_id,
                reddit_id=reddit_id
            )

            if not interactions:
                unseen_posts.append(post)

        if skipped_old > 0:
            logger.debug(
                f"Skipped {skipped_old} posts older than {self.max_post_age_hours} hours",
                extra={"persona_id": persona_id}
            )

        logger.debug(
            f"Perceived {len(all_posts)} posts, {len(unseen_posts)} unseen (skipped {skipped_old} old)",
            extra={"persona_id": persona_id, "subreddits": target_subreddits}
        )

        return unseen_posts

    async def perceive_replies(self, persona_id: str) -> List[Dict[str, Any]]:
        """
        Perception phase: Check for replies to agent's comments.

        Fetches inbox replies, filters out already-processed replies,
        and fetches the agent's original comment for context.

        Args:
            persona_id: UUID of persona

        Returns:
            List of new reply dictionaries with conversation context:
            [
                {
                    "id": "reply_id",
                    "body": "Reply text",
                    "author": "replying_user",
                    "parent_id": "t1_our_comment_id",
                    "link_id": "t3_post_id",
                    "subreddit": "SubredditName",
                    "created_utc": 1700000000,
                    "score": 5,
                    "permalink": "/r/...",
                    "is_new": true,
                    "our_comment": {...},  # Our original comment dict
                    "conversation_depth": 2  # Depth in the reply chain
                },
                ...
            ]

        Raises:
            ConnectionError: If Reddit API unreachable
        """
        # Fetch inbox replies
        all_replies = await self.reddit_client.get_inbox_replies(limit=25)

        if not all_replies:
            return []

        # Filter to only new/unread replies
        new_replies = [r for r in all_replies if r.get("is_new", False)]

        if not new_replies:
            logger.debug(
                f"No new inbox replies for persona {persona_id}",
                extra={"persona_id": persona_id, "total_replies": len(all_replies)}
            )
            return []

        # Filter out already-processed replies and enrich with context
        eligible_replies = []
        replies_to_mark_read = []

        for reply in new_replies:
            reply_reddit_id = f"t1_{reply['id']}"

            # Check if we've already responded to this reply
            existing_interactions = await self.memory_store.search_interactions(
                persona_id=persona_id,
                reddit_id=reply_reddit_id
            )

            if existing_interactions:
                # Already processed, just mark as read
                replies_to_mark_read.append(reply_reddit_id)
                continue

            # Get our original comment (the parent of this reply)
            parent_id = reply.get("parent_id", "")
            if not parent_id.startswith("t1_"):
                # Reply is to a post, not our comment - skip
                replies_to_mark_read.append(reply_reddit_id)
                continue

            # Fetch our original comment
            our_comment = await self.reddit_client.get_comment(parent_id)
            if not our_comment:
                # Our comment was deleted/removed
                replies_to_mark_read.append(reply_reddit_id)
                continue

            # Calculate conversation depth by counting parent chain
            conversation_depth = await self._calculate_conversation_depth(parent_id)

            # Check max conversation depth
            if conversation_depth >= self.max_conversation_depth:
                logger.debug(
                    f"Skipping reply {reply['id']} - max conversation depth ({self.max_conversation_depth}) reached",
                    extra={"persona_id": persona_id, "depth": conversation_depth}
                )
                replies_to_mark_read.append(reply_reddit_id)
                continue

            # Enrich reply with context
            reply["our_comment"] = our_comment
            reply["conversation_depth"] = conversation_depth
            eligible_replies.append(reply)

        # Mark processed replies as read
        if replies_to_mark_read:
            try:
                await self.reddit_client.mark_read(replies_to_mark_read)
            except Exception as e:
                logger.warning(f"Failed to mark replies as read: {e}")

        logger.debug(
            f"Perceived {len(all_replies)} inbox replies, {len(eligible_replies)} eligible",
            extra={"persona_id": persona_id}
        )

        return eligible_replies

    async def _calculate_conversation_depth(
        self,
        comment_id: str
    ) -> int:
        """
        Calculate the depth of a comment in the reply chain.

        Counts how many parent comments exist between this comment
        and the original post.

        Args:
            comment_id: Reddit comment ID (with t1_ prefix)

        Returns:
            Depth in the reply chain (0 = direct reply to post, 1 = reply to comment, etc.)
        """
        depth = 0
        current_id = comment_id
        max_depth_check = 20  # Safety limit

        while depth < max_depth_check:
            if current_id.startswith("t3_"):
                # Reached the post
                break

            if not current_id.startswith("t1_"):
                break

            # Fetch the parent comment
            comment = await self.reddit_client.get_comment(current_id)
            if not comment:
                break

            parent_id = comment.get("parent_id", "")
            if not parent_id:
                break

            current_id = parent_id
            depth += 1

        return depth

    async def process_reply(
        self,
        persona_id: str,
        reply: Dict[str, Any],
        correlation_id: str
    ) -> Dict[str, Any]:
        """
        Process a reply to one of the agent's comments.

        Builds conversation context including the original comment and the reply,
        uses the existing retrieval pipeline for beliefs/past interactions,
        generates a response, runs it through moderation, and posts or queues it.

        Args:
            persona_id: UUID of persona
            reply: Reply dictionary with conversation context from perceive_replies
            correlation_id: Request correlation ID

        Returns:
            Result dict:
            {
                "action": "posted" | "queued" | "dropped",
                "reddit_id": "t1_..." (if posted),
                "queue_id": "..." (if queued),
                "reason": "..." (if dropped)
            }

        Raises:
            Exception: Propagates any processing errors
        """
        our_comment = reply.get("our_comment", {})
        conversation_depth = reply.get("conversation_depth", 1)

        logger.info(
            f"Processing reply {reply['id']} to our comment {our_comment.get('id', 'unknown')}",
            extra={
                "persona_id": persona_id,
                "correlation_id": correlation_id,
                "conversation_depth": conversation_depth
            }
        )

        # Build thread context for retrieval
        thread_context = {
            "title": f"Reply conversation in r/{reply.get('subreddit', '')}",
            "body": "",  # Will be populated with conversation context
            "subreddit": reply.get("subreddit", ""),
            "reddit_id": reply["id"],
            "url": f"https://reddit.com{reply.get('permalink', '')}",
            "is_reply": True,
            "conversation_context": {
                "our_comment": our_comment.get("body", ""),
                "their_reply": reply.get("body", ""),
                "depth": conversation_depth
            }
        }

        # Assemble context using existing retrieval pipeline
        context = await self.retrieval.assemble_context(
            persona_id=persona_id,
            thread_context=thread_context
        )

        logger.debug(
            f"Assembled context for reply {reply['id']}: {context.get('token_count', 0)} tokens",
            extra={"persona_id": persona_id, "correlation_id": correlation_id}
        )

        # Generate draft response for the reply
        draft = await self._generate_reply_draft(
            persona_id=persona_id,
            reply=reply,
            context=context,
            correlation_id=correlation_id
        )

        logger.info(
            f"Generated draft for reply {reply['id']}: {len(draft['text'])} chars",
            extra={
                "persona_id": persona_id,
                "correlation_id": correlation_id,
                "tokens_in": draft["tokens_in"],
                "tokens_out": draft["tokens_out"],
                "cost": draft["cost"],
            }
        )

        # Check consistency with beliefs
        consistency_result = await self.check_draft_consistency(
            draft["text"],
            context.get("beliefs", []),
            correlation_id
        )

        if not consistency_result["is_consistent"]:
            logger.warning(
                f"Reply draft for {reply['id']} conflicts with beliefs: {consistency_result['explanation']}",
                extra={
                    "persona_id": persona_id,
                    "correlation_id": correlation_id,
                    "conflicts": consistency_result["conflicts"]
                }
            )

        # Moderate the draft
        decision = await self._moderate_reply_draft(
            persona_id=persona_id,
            draft=draft["text"],
            reply=reply,
            correlation_id=correlation_id
        )

        logger.info(
            f"Moderation decision for reply {reply['id']}: {decision['action']}",
            extra={"persona_id": persona_id, "correlation_id": correlation_id, "decision": decision}
        )

        # Execute action
        result = await self._execute_reply_action(
            persona_id=persona_id,
            draft=draft["text"],
            reply=reply,
            decision=decision,
            correlation_id=correlation_id
        )

        # Mark the reply as read after processing
        try:
            await self.reddit_client.mark_read([f"t1_{reply['id']}"])
        except Exception as e:
            logger.warning(f"Failed to mark reply {reply['id']} as read: {e}")

        return result

    async def _generate_reply_draft(
        self,
        persona_id: str,
        reply: Dict[str, Any],
        context: Dict[str, Any],
        correlation_id: str
    ) -> Dict[str, Any]:
        """
        Generate a draft response to a reply.

        Similar to generate_draft but with conversation-specific prompting.

        Args:
            persona_id: UUID of persona
            reply: Reply dictionary with our_comment context
            context: Assembled context from retrieval
            correlation_id: Request correlation ID

        Returns:
            Draft response dict (same structure as generate_draft)
        """
        # Load persona
        persona = await self.memory_store.get_persona(persona_id)

        # Build system prompt
        config = persona.get("config", {})
        system_prompt = self._build_system_prompt(config)

        # Assemble rich prompt from context
        assembled_prompt = await self.retrieval.assemble_prompt(persona, context)

        # Build conversation context
        our_comment = reply.get("our_comment", {})
        conversation_depth = reply.get("conversation_depth", 1)

        # User message with conversation context
        user_message = f"""
{assembled_prompt}

---

**CONVERSATION CONTEXT:**

**Your previous comment** (what you said):
```
{our_comment.get('body', '[Comment not available]')}
```

**Their reply** (what they're responding with):
```
{reply.get('body', '')}
```

**Conversation depth**: {conversation_depth} levels deep in r/{reply.get('subreddit', '')}

---

**Task**: Draft a Reddit reply responding to their comment above.

IMPORTANT:
- You are continuing a conversation - acknowledge what they said
- Use the LENGTH definitions (SHORT/MEDIUM/LONG) - replies should usually be SHORT
- Stay consistent with what you said in your previous comment
- Follow your writing rules exactly
- Maintain your convictions and beliefs
- Output ONLY the reply text, nothing else
"""

        # Generate response using LLM
        # Lower max_tokens as safety net for replies
        response = await self.llm_client.generate_response(
            system_prompt=system_prompt,
            context={},
            user_message=user_message,
            tools=AGENT_TOOLS,
            temperature=0.7,
            max_tokens=128000,
            correlation_id=correlation_id
        )

        # Track metrics
        total_tokens_in = response.get("tokens_in", 0)
        total_tokens_out = response.get("tokens_out", 0)
        total_cost = response.get("cost", 0.0)
        tool_calls_made = 0

        # Build messages for potential tool call continuation
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        if response.get("tool_calls"):
            messages.append({
                "role": "assistant",
                "content": response.get("text", ""),
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": tc["type"],
                        "function": tc["function"]
                    }
                    for tc in response["tool_calls"]
                ]
            })

        # Handle tool calls
        iteration = 0
        while response.get("tool_calls") and iteration < MAX_TOOL_ITERATIONS:
            iteration += 1
            tool_calls = response["tool_calls"]
            tool_calls_made += len(tool_calls)

            logger.info(
                f"Processing {len(tool_calls)} tool call(s) for reply (iteration {iteration})",
                extra={
                    "correlation_id": correlation_id,
                    "tool_names": [tc["function"]["name"] for tc in tool_calls],
                }
            )

            tool_results = await self.tool_executor.execute_tool_calls(
                tool_calls=tool_calls,
                correlation_id=correlation_id
            )

            response = await self.llm_client.continue_with_tool_results(
                messages=messages,
                tool_results=tool_results,
                tools=AGENT_TOOLS,
                temperature=0.7,
                max_tokens=128000,
                correlation_id=correlation_id
            )

            total_tokens_in += response.get("tokens_in", 0)
            total_tokens_out += response.get("tokens_out", 0)
            total_cost += response.get("cost", 0.0)

            if response.get("tool_calls"):
                for result in tool_results:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": result["tool_call_id"],
                        "content": result["content"]
                    })
                messages.append({
                    "role": "assistant",
                    "content": response.get("text", ""),
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": tc["type"],
                            "function": tc["function"]
                        }
                        for tc in response["tool_calls"]
                    ]
                })

        return {
            "text": response.get("text", ""),
            "model": response.get("model", "unknown"),
            "tokens_in": total_tokens_in,
            "tokens_out": total_tokens_out,
            "total_tokens": total_tokens_in + total_tokens_out,
            "cost": total_cost,
            "tool_calls_made": tool_calls_made,
            "finish_reason": response.get("finish_reason", "unknown"),
        }

    async def _moderate_reply_draft(
        self,
        persona_id: str,
        draft: str,
        reply: Dict[str, Any],
        correlation_id: str
    ) -> Dict[str, Any]:
        """
        Moderate a reply draft and decide action.

        Args:
            persona_id: UUID of persona
            draft: Draft text to moderate
            reply: Reply dictionary
            correlation_id: Request correlation ID

        Returns:
            Decision dict (same structure as moderate_draft)
        """
        context = {
            "subreddit": reply.get("subreddit", ""),
            "post_type": "reply",
            "parent_id": f"t1_{reply['id']}",
        }

        evaluation = await self.moderation.evaluate_content(
            persona_id=persona_id,
            content=draft,
            context=context
        )

        auto_enabled = await self.moderation.is_auto_posting_enabled(persona_id)

        if evaluation["action"] == "block":
            action = "drop"
            logger.warning(
                f"Reply draft blocked by moderation: {evaluation['flags']}",
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

    async def _execute_reply_action(
        self,
        persona_id: str,
        draft: str,
        reply: Dict[str, Any],
        decision: Dict[str, Any],
        correlation_id: str
    ) -> Dict[str, Any]:
        """
        Execute action based on moderation decision for a reply.

        Args:
            persona_id: UUID of persona
            draft: Draft text
            reply: Reply dictionary
            decision: Decision dict from _moderate_reply_draft
            correlation_id: Request correlation ID

        Returns:
            Result dict with action taken
        """
        action = decision["action"]
        parent_id = f"t1_{reply['id']}"  # Reply to their comment

        if action == "post_now":
            try:
                reddit_id = await self.reddit_client.reply(
                    parent_id=parent_id,
                    content=draft
                )

                # Log interaction
                await self.memory_store.log_interaction(
                    persona_id=persona_id,
                    content=draft,
                    interaction_type="reply",
                    metadata={
                        "reddit_id": reddit_id,
                        "parent_id": parent_id,
                        "subreddit": reply.get("subreddit", ""),
                        "correlation_id": correlation_id,
                        "auto_posted": True,
                        "conversation_depth": reply.get("conversation_depth", 1),
                        "in_reply_to": reply.get("body", "")[:200]  # First 200 chars for context
                    }
                )

                logger.info(
                    f"Posted reply {reddit_id} to Reddit",
                    extra={"persona_id": persona_id, "correlation_id": correlation_id}
                )

                return {
                    "action": "posted",
                    "reddit_id": reddit_id
                }

            except Exception as e:
                logger.error(
                    f"Failed to post reply to Reddit: {e}",
                    extra={"persona_id": persona_id, "correlation_id": correlation_id},
                    exc_info=True
                )
                action = "queue"

        if action == "queue":
            # Analyze interaction for belief evolution proposals
            our_comment = reply.get("our_comment", {})
            thread_context = {
                "subreddit": reply.get("subreddit", ""),
                "title": f"Reply conversation",
                "body": reply.get("body", ""),
                "parent_comment": our_comment.get("body", "")
            }

            belief_proposals = await analyze_interaction_for_beliefs(
                persona_id=persona_id,
                draft_content=draft,
                thread_context=thread_context,
                llm_client=self.llm_client,
                memory_store=self.memory_store,
                correlation_id=correlation_id
            )

            metadata = {
                "post_type": "reply",
                "target_subreddit": reply.get("subreddit", ""),
                "parent_id": parent_id,
                "correlation_id": correlation_id,
                "evaluation": decision["evaluation"],
                "belief_proposals": belief_proposals.to_dict(),
                "conversation_depth": reply.get("conversation_depth", 1),
                "original_reply": {
                    "body": reply.get("body", ""),
                    "author": reply.get("author", ""),
                    "reddit_id": reply.get("id", "")
                },
                "our_original_comment": {
                    "body": our_comment.get("body", ""),
                    "reddit_id": our_comment.get("id", "")
                }
            }

            queue_id = await self.moderation.enqueue_for_review(
                persona_id=persona_id,
                content=draft,
                metadata=metadata
            )

            logger.info(
                f"Enqueued reply draft for review: {queue_id}",
                extra={
                    "persona_id": persona_id,
                    "correlation_id": correlation_id,
                    "belief_update_count": len(belief_proposals.updates),
                }
            )

            return {
                "action": "queued",
                "queue_id": queue_id
            }

        # action == "drop"
        reason = ", ".join(decision["evaluation"].get("flags", ["blocked"]))
        logger.info(
            f"Dropped reply draft: {reason}",
            extra={"persona_id": persona_id, "correlation_id": correlation_id}
        )

        return {
            "action": "dropped",
            "reason": reason
        }

    def _calculate_engagement_score(self, post: Dict[str, Any]) -> float:
        """
        Calculate weighted engagement score for a post.

        Formula: score_weight * upvotes + comment_weight * num_comments

        Args:
            post: Post dictionary from Reddit with 'score' and 'num_comments'

        Returns:
            Weighted engagement score (higher = more engaging)
        """
        score = post.get("score", 1)
        num_comments = post.get("num_comments", 0)

        score_weight = self.engagement_config.get("score_weight", 1.0)
        comment_weight = self.engagement_config.get("comment_weight", 2.0)

        return (score_weight * score) + (comment_weight * num_comments)

    def _engagement_probability(self, engagement_score: float) -> float:
        """
        Convert engagement score to response probability using sigmoid scaling.

        Low-engagement posts get min_probability, high-engagement posts approach
        max_probability, with smooth transition around the midpoint.

        Args:
            engagement_score: Score from _calculate_engagement_score

        Returns:
            Probability between min_probability and max_probability
        """
        min_prob = self.engagement_config.get("min_probability", 0.1)
        max_prob = self.engagement_config.get("max_probability", 0.8)
        midpoint = self.engagement_config.get("probability_midpoint", 20.0)

        # Avoid division by zero
        if midpoint <= 0:
            midpoint = 20.0

        # Normalize around midpoint and apply sigmoid
        x = (engagement_score - midpoint) / midpoint
        sigmoid = 1 / (1 + math.exp(-x * 3))  # steepness factor of 3

        return min_prob + (max_prob - min_prob) * sigmoid

    async def should_respond(self, persona_id: str, post: Dict[str, Any]) -> bool:
        """
        Decision phase: Decide if agent should respond to post.

        Checks:
        1. Post is not by this persona (avoid self-replies)
        2. Post matches interest keywords (if configured)
        3. Engagement-weighted sampling (higher engagement = higher probability)

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

        # Check 3: Engagement-weighted sampling
        engagement_score = self._calculate_engagement_score(post)
        response_prob = self._engagement_probability(engagement_score)

        if random.random() > response_prob:
            logger.debug(
                f"Skipping post {post['id']} (engagement sampling: score={engagement_score:.1f}, prob={response_prob:.2f})",
                extra={
                    "persona_id": persona_id,
                    "post_id": post["id"],
                    "reason": "engagement_sampling",
                    "engagement_score": engagement_score,
                    "response_probability": response_prob
                }
            )
            return False

        logger.info(
            f"Post {post['id']} eligible for response (engagement={engagement_score:.1f}, prob={response_prob:.2f})",
            extra={
                "persona_id": persona_id,
                "post_id": post["id"],
                "engagement_score": engagement_score,
                "response_probability": response_prob
            }
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
        Generate draft response using LLM with tool calling support.

        Builds system prompt from persona config and calls LLM client
        to generate a response based on assembled context. If the LLM
        requests tool calls (e.g., fetch_url), executes them and continues
        the conversation until a final response is generated.

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
                "cost": 0.0234,
                "tool_calls_made": 2  # Number of tool calls during generation
            }

        Raises:
            Exception: LLM API errors or context assembly errors
        """
        # Load persona
        persona = await self.memory_store.get_persona(persona_id)

        # Build system prompt (high-level safety and role guidelines)
        config = persona.get("config", {})
        system_prompt = self._build_system_prompt(config)

        # Assemble rich prompt from context (includes personality_profile, writing_rules, voice_examples)
        assembled_prompt = await self.retrieval.assemble_prompt(persona, context)

        # User message with full context
        thread = context.get("thread", {})
        user_message = f"""
{assembled_prompt}

---

**Task**: Draft a Reddit comment in response to this post in r/{thread.get('subreddit')}.

IMPORTANT:
- Use the LENGTH definitions (SHORT/MEDIUM/LONG) provided in the system instructions
- Get to the point immediately
- Follow your writing rules exactly
- Stay consistent with your beliefs and past statements above
- Maintain your convictions - don't contradict yourself
- Output ONLY the comment text, nothing else
"""

        # Initial LLM call with tools enabled
        # Lower max_tokens as safety net
        response = await self.llm_client.generate_response(
            system_prompt=system_prompt,
            context={},  # Context is now in user_message via assembled_prompt
            user_message=user_message,
            tools=AGENT_TOOLS,  # Enable tool calling
            temperature=0.7,
            max_tokens=128000,
            correlation_id=correlation_id
        )

        # Track metrics
        total_tokens_in = response.get("tokens_in", 0)
        total_tokens_out = response.get("tokens_out", 0)
        total_cost = response.get("cost", 0.0)
        tool_calls_made = 0

        # Build messages for potential continuation
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        # If there are tool calls, add assistant message with them
        if response.get("tool_calls"):
            messages.append({
                "role": "assistant",
                "content": response.get("text", ""),
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": tc["type"],
                        "function": tc["function"]
                    }
                    for tc in response["tool_calls"]
                ]
            })

        # Handle tool calls in a loop
        iteration = 0
        while response.get("tool_calls") and iteration < MAX_TOOL_ITERATIONS:
            iteration += 1
            tool_calls = response["tool_calls"]
            tool_calls_made += len(tool_calls)

            logger.info(
                f"Processing {len(tool_calls)} tool call(s) (iteration {iteration})",
                extra={
                    "correlation_id": correlation_id,
                    "tool_names": [tc["function"]["name"] for tc in tool_calls],
                    "iteration": iteration
                }
            )

            # Execute all tool calls
            tool_results = await self.tool_executor.execute_tool_calls(
                tool_calls=tool_calls,
                correlation_id=correlation_id
            )

            # Continue conversation with tool results
            response = await self.llm_client.continue_with_tool_results(
                messages=messages,
                tool_results=tool_results,
                tools=AGENT_TOOLS,  # Allow more tool calls if needed
                temperature=0.7,
                max_tokens=128000,
                correlation_id=correlation_id
            )

            # Accumulate metrics
            total_tokens_in += response.get("tokens_in", 0)
            total_tokens_out += response.get("tokens_out", 0)
            total_cost += response.get("cost", 0.0)

            # Update messages for potential next iteration
            if response.get("tool_calls"):
                # Add tool results and new assistant message to history
                for result in tool_results:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": result["tool_call_id"],
                        "content": result["content"]
                    })
                messages.append({
                    "role": "assistant",
                    "content": response.get("text", ""),
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": tc["type"],
                            "function": tc["function"]
                        }
                        for tc in response["tool_calls"]
                    ]
                })

        if iteration >= MAX_TOOL_ITERATIONS and response.get("tool_calls"):
            logger.warning(
                f"Max tool iterations ({MAX_TOOL_ITERATIONS}) reached, using partial response",
                extra={"correlation_id": correlation_id}
            )

        # Build final result
        result = {
            "text": response.get("text", ""),
            "model": response.get("model", "unknown"),
            "tokens_in": total_tokens_in,
            "tokens_out": total_tokens_out,
            "total_tokens": total_tokens_in + total_tokens_out,
            "cost": total_cost,
            "tool_calls_made": tool_calls_made,
            "finish_reason": response.get("finish_reason", "unknown"),
        }

        if tool_calls_made > 0:
            logger.info(
                f"Draft generation completed with {tool_calls_made} tool call(s)",
                extra={
                    "correlation_id": correlation_id,
                    "tool_calls_made": tool_calls_made,
                    "total_tokens": result["total_tokens"],
                    "total_cost": total_cost
                }
            )

        return result

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

            # Enqueue for review with belief proposals and original post context
            metadata = {
                "post_type": "comment",
                "target_subreddit": post["subreddit"],
                "parent_id": parent_id,
                "correlation_id": correlation_id,
                "evaluation": decision["evaluation"],
                "belief_proposals": belief_proposals.to_dict(),
                "original_post": {
                    "title": post.get("title", ""),
                    "body": post.get("selftext", ""),
                    "url": post.get("url", ""),
                    "reddit_id": post.get("id", ""),
                    "author": post.get("author", "")
                }
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
        writing_rules = config.get("writing_rules", [])

        prompt = f"""You are a Reddit user with the following characteristics:

Tone: {tone}
Style: {style}
Core Values: {", ".join(values) if values else "None specified"}

LENGTH DEFINITIONS (STRICT):
- SHORT: 10-20 words, ONE brief sentence
- MEDIUM: 2-3 sentences, ~30-50 words
- LONG: 3-4 sentences, ~60-100 words (use sparingly)

Default to SHORT. Follow your writing rules for when to use each length.

CRITICAL INSTRUCTIONS:
- Write like a real Reddit user, not an AI assistant
- Get to the point quickly - no unnecessary preamble or filler
- Follow ALL writing rules in the context below - they define your voice
- Stay true to your beliefs and persona
- Be respectful and follow Reddit etiquette

Never:
- Write walls of text or rambling responses
- Use generic AI-sounding phrases
- Share personal information
- Engage in harassment or hate speech
- Spread misinformation
- Violate Reddit's content policy
"""
        # Add writing rules directly to system prompt for emphasis
        if writing_rules:
            prompt += "\nYOUR WRITING RULES (MUST FOLLOW):\n"
            for rule in writing_rules:
                prompt += f"- {rule}\n"

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

    def _calculate_next_delay(self, had_activity: bool, was_burst: bool) -> tuple:
        """
        Calculate next sleep delay with natural timing patterns.

        Combines time-of-day awareness with activity bursts for human-like timing:
        - Active hours (8am-11pm): 2-4 hour delays
        - Night hours (11pm-8am): 5-8 hour delays
        - After activity: 20% chance of a quick 15-45 min follow-up (burst)
        - All delays have ±20% jitter for unpredictability

        Args:
            had_activity: Whether the last cycle posted/replied to anything
            was_burst: Whether the last delay was a burst (prevents consecutive bursts)

        Returns:
            tuple: (delay_seconds, is_burst)
        """
        hour = datetime.now().hour

        # Check if we should burst (quick follow-up after activity)
        # Only burst if: had activity, wasn't already a burst, and random chance hits
        if had_activity and not was_burst and random.random() < self.burst_probability:
            base_delay = random.uniform(15, 45) * 60  # 15-45 minutes
            is_burst = True
        else:
            # Normal timing based on time of day
            if self.active_hours_start <= hour < self.active_hours_end:
                # Active hours: 2-4 hours
                base_delay = random.uniform(2, 4) * 3600
            else:
                # Night hours: 5-8 hours
                base_delay = random.uniform(5, 8) * 3600
            is_burst = False

        # Add jitter (±20%) for unpredictability
        jitter = random.uniform(-0.2, 0.2)
        final_delay = base_delay * (1 + jitter)

        return final_delay, is_burst

    def _log_persona_config_summary(self, persona: Dict[str, Any], config: Dict[str, Any]) -> None:
        """
        Log a summary of persona config fields for verification.

        Shows first ~50 chars of each field to verify correct persona is loaded.

        Args:
            persona: Persona dict with basic info
            config: Persona config dict with settings
        """
        def truncate(text: Any, length: int = 50) -> str:
            """Truncate text to specified length with ellipsis."""
            if text is None:
                return "(not set)"
            if isinstance(text, list):
                if not text:
                    return "(empty list)"
                return f"[{len(text)} items] {str(text[0])[:30]}..."
            text_str = str(text)
            if len(text_str) <= length:
                return text_str
            return text_str[:length] + "..."

        summary = {
            "display_name": persona.get("display_name"),
            "reddit_username": persona.get("reddit_username"),
            "tone": config.get("tone"),
            "style": config.get("style"),
            "core_values": truncate(config.get("values") or config.get("core_values")),
            "personality_profile": truncate(config.get("personality_profile")),
            "writing_rules": truncate(config.get("writing_rules")),
            "voice_examples": truncate(config.get("voice_examples")),
            "target_subreddits": truncate(config.get("target_subreddits")),
            "interest_keywords": truncate(config.get("interest_keywords")),
        }

        logger.info(
            f"Persona config loaded: {persona.get('display_name', persona.get('reddit_username'))}",
            extra={"persona_config_summary": summary}
        )

        # Also log human-readable summary
        logger.info(
            f"  - tone: {summary['tone']}, style: {summary['style']}"
        )
        logger.info(
            f"  - personality_profile: {summary['personality_profile']}"
        )
        logger.info(
            f"  - writing_rules: {summary['writing_rules']}"
        )
        logger.info(
            f"  - voice_examples: {summary['voice_examples']}"
        )
        logger.info(
            f"  - target_subreddits: {summary['target_subreddits']}"
        )


async def run_agent(
    persona_id: str,
    reddit_client: IRedditClient,
    llm_client: ILLMClient,
    memory_store: IMemoryStore,
    retrieval: RetrievalCoordinator,
    moderation: ModerationService,
    tool_executor: Optional[ToolExecutor] = None,
    stop_event: Optional[asyncio.Event] = None,
    interval_seconds: int = 14400,
    max_conversation_depth: int = 5
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
        tool_executor: Optional tool executor (auto-created if None)
        stop_event: Optional stop event
        interval_seconds: Seconds between cycles (default: 14400 = 4 hours)
        max_conversation_depth: Maximum reply chain depth (default: 5)

    Raises:
        ValueError: If persona not found or dependencies invalid
    """
    loop = AgentLoop(
        reddit_client=reddit_client,
        llm_client=llm_client,
        memory_store=memory_store,
        retrieval=retrieval,
        moderation=moderation,
        tool_executor=tool_executor,
        interval_seconds=interval_seconds,
        max_conversation_depth=max_conversation_depth
    )

    await loop.run(persona_id, stop_event)
