"""
Belief Analyzer Service

Analyzes Reddit interactions to propose belief updates and new belief creation.
Called when drafts are queued for moderation to suggest how beliefs should evolve
based on the interaction.

Key features:
- LLM-powered analysis of draft responses against existing beliefs
- Proposes confidence updates (max 3) and new beliefs (max 1) per interaction
- Validates proposals against existing belief graph
- Structured JSON output with reasoning
"""

import json
import logging
import os
import re
import uuid
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional

from app.services.interfaces.llm_client import ILLMClient
from app.services.interfaces.memory_store import IMemoryStore

logger = logging.getLogger(__name__)

# LLM configuration for belief analysis
BELIEF_ANALYSIS_MODEL = os.getenv("BELIEF_ANALYSIS_MODEL", "anthropic/claude-haiku-4.5")
BELIEF_ANALYSIS_TEMPERATURE = 0.4  # Moderate creativity for analysis
BELIEF_ANALYSIS_MAX_TOKENS = 2000  # Room for detailed proposals

# Valid evidence strengths for Bayesian updates
VALID_EVIDENCE_STRENGTHS = {"weak", "moderate", "strong"}


@dataclass
class BeliefUpdateProposal:
    """Proposal to update an existing belief's confidence."""
    belief_id: str
    belief_title: str
    current_confidence: float
    proposed_confidence: float
    reason: str
    evidence_strength: str  # weak, moderate, strong

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class NewBeliefProposal:
    """Proposal to create a new belief."""
    title: str
    summary: str
    initial_confidence: float
    tags: List[str]
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BeliefProposals:
    """Container for all belief proposals from an interaction."""
    updates: List[BeliefUpdateProposal]
    new_belief: Optional[NewBeliefProposal]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "updates": [u.to_dict() for u in self.updates],
            "new_belief": self.new_belief.to_dict() if self.new_belief else None
        }

    @classmethod
    def empty(cls) -> "BeliefProposals":
        """Return empty proposals (no changes)."""
        return cls(updates=[], new_belief=None)


async def analyze_interaction_for_beliefs(
    persona_id: str,
    draft_content: str,
    thread_context: Dict[str, Any],
    llm_client: ILLMClient,
    memory_store: IMemoryStore,
    correlation_id: Optional[str] = None,
) -> BeliefProposals:
    """
    Analyze a Reddit interaction and propose belief changes.

    Examines the draft response in context of the thread being replied to,
    compares against the persona's existing beliefs, and proposes:
    - Up to 3 confidence updates for existing beliefs
    - Up to 1 new belief creation

    Args:
        persona_id: UUID of the persona
        draft_content: The draft comment/reply content
        thread_context: Dict with thread info (title, body, parent_comment, subreddit)
        llm_client: LLM client for analysis
        memory_store: Memory store for fetching belief graph
        correlation_id: Optional request ID for tracing

    Returns:
        BeliefProposals with validated update and creation proposals
    """
    if correlation_id is None:
        correlation_id = str(uuid.uuid4())

    logger.info(
        "Analyzing interaction for belief evolution",
        extra={
            "correlation_id": correlation_id,
            "persona_id": persona_id,
            "draft_length": len(draft_content),
            "subreddit": thread_context.get("subreddit", "unknown")
        }
    )

    # Fetch current belief graph
    try:
        belief_graph = await memory_store.query_belief_graph(
            persona_id=persona_id,
            min_confidence=0.0  # Include all beliefs
        )
        existing_beliefs = belief_graph.get("nodes", [])
    except Exception as e:
        logger.error(
            "Failed to fetch belief graph for analysis",
            extra={
                "correlation_id": correlation_id,
                "persona_id": persona_id,
                "error": str(e)
            }
        )
        return BeliefProposals.empty()

    logger.info(
        "Fetched belief graph for analysis",
        extra={
            "correlation_id": correlation_id,
            "belief_count": len(existing_beliefs)
        }
    )

    # Build prompts
    system_prompt = _build_system_prompt()
    context = _build_context(draft_content, thread_context, existing_beliefs)
    user_message = _build_user_message()

    try:
        # Call LLM for analysis
        response = await llm_client.generate_response(
            system_prompt=system_prompt,
            context=context,
            user_message=user_message,
            temperature=BELIEF_ANALYSIS_TEMPERATURE,
            max_tokens=BELIEF_ANALYSIS_MAX_TOKENS,
            correlation_id=correlation_id,
            model=BELIEF_ANALYSIS_MODEL
        )

        # Parse and validate response
        proposals = _parse_llm_response(
            response_text=response.get("text", ""),
            existing_beliefs=existing_beliefs,
            correlation_id=correlation_id
        )

        logger.info(
            "Belief analysis completed",
            extra={
                "correlation_id": correlation_id,
                "persona_id": persona_id,
                "update_count": len(proposals.updates),
                "has_new_belief": proposals.new_belief is not None,
                "tokens_used": response.get("total_tokens", 0),
                "cost": response.get("cost", 0.0)
            }
        )

        return proposals

    except Exception as e:
        logger.error(
            "Failed to analyze interaction for beliefs",
            extra={
                "correlation_id": correlation_id,
                "persona_id": persona_id,
                "error": str(e),
                "error_type": type(e).__name__
            },
            exc_info=True
        )
        return BeliefProposals.empty()


def _build_system_prompt() -> str:
    """Build system prompt for belief analysis."""
    return """You are an AI belief evolution analyst. Your task is to analyze how a Reddit interaction
should affect an AI agent's belief system.

Given a draft response and the thread context, determine:
1. Which existing beliefs are reinforced or challenged by this interaction (max 3 updates)
2. Whether any genuinely new belief should be formed (max 1 new belief)

For UPDATES to existing beliefs:
- Only propose changes when there's clear evidence in the interaction
- Confidence should increase if the response reinforces a belief
- Confidence should decrease if the response contradicts or questions a belief
- Use evidence_strength to indicate how strongly the interaction supports the change:
  - "weak": Minor relevance (confidence change ~5%)
  - "moderate": Clear relevance (confidence change ~10%)
  - "strong": Direct evidence (confidence change ~20%)

For NEW beliefs:
- Only propose if the interaction reveals a genuinely novel stance
- Must be distinct from existing beliefs (not just a variation)
- Initial confidence should reflect certainty (0.5-0.8 typical)

Be conservative - not every interaction needs to change beliefs.
Quality over quantity. If no changes are warranted, return empty arrays."""


def _build_context(
    draft_content: str,
    thread_context: Dict[str, Any],
    existing_beliefs: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Build context dict for LLM prompt."""
    # Summarize existing beliefs
    beliefs_summary = []
    for belief in existing_beliefs:
        beliefs_summary.append({
            "id": belief.get("id", ""),
            "title": belief.get("title", ""),
            "summary": belief.get("summary", ""),
            "confidence": belief.get("confidence", 0.5)
        })

    return {
        "draft_response": draft_content,
        "thread": {
            "subreddit": thread_context.get("subreddit", ""),
            "title": thread_context.get("title", ""),
            "body": thread_context.get("body", "")[:500] if thread_context.get("body") else "",
            "parent_comment": thread_context.get("parent_comment", "")[:300] if thread_context.get("parent_comment") else ""
        },
        "existing_beliefs": beliefs_summary
    }


def _build_user_message() -> str:
    """Build user message for LLM prompt."""
    return """Analyze the draft response in the context of the Reddit thread.
Compare against the existing beliefs and propose:
1. Up to 3 belief confidence UPDATES (if warranted)
2. Up to 1 NEW belief (if genuinely novel stance emerges)

Return your response as JSON with this exact structure:
{
  "updates": [
    {
      "belief_id": "uuid-of-existing-belief",
      "belief_title": "Title of the belief",
      "current_confidence": 0.7,
      "proposed_confidence": 0.8,
      "reason": "Brief explanation of why this interaction affects this belief",
      "evidence_strength": "moderate"
    }
  ],
  "new_belief": {
    "title": "Concise title for new belief",
    "summary": "Detailed description of the new belief stance",
    "initial_confidence": 0.6,
    "tags": ["relevant", "tags"],
    "reason": "Why this interaction warrants a new belief"
  }
}

If no updates are warranted, use: "updates": []
If no new belief is warranted, use: "new_belief": null

Important:
- Be selective - only propose changes with clear evidence
- Confidence changes should be proportional to evidence strength
- New beliefs must be genuinely distinct from existing ones"""


def _parse_llm_response(
    response_text: str,
    existing_beliefs: List[Dict[str, Any]],
    correlation_id: str
) -> BeliefProposals:
    """
    Parse and validate LLM response into BeliefProposals.

    Args:
        response_text: Raw LLM response text
        existing_beliefs: List of existing beliefs for validation
        correlation_id: Request ID for logging

    Returns:
        Validated BeliefProposals
    """
    # Build lookup for validation
    valid_belief_ids = {b.get("id") for b in existing_beliefs}
    belief_id_to_data = {b.get("id"): b for b in existing_beliefs}

    try:
        # Extract JSON from response
        json_data = _extract_json_object(response_text)

        if not json_data:
            logger.warning(
                "No valid JSON found in belief analysis response",
                extra={
                    "correlation_id": correlation_id,
                    "response_length": len(response_text)
                }
            )
            return BeliefProposals.empty()

        # Parse updates (max 3)
        updates = []
        raw_updates = json_data.get("updates", [])
        for item in raw_updates[:3]:  # Enforce max 3
            update = _validate_update_proposal(
                item=item,
                valid_belief_ids=valid_belief_ids,
                belief_id_to_data=belief_id_to_data,
                correlation_id=correlation_id
            )
            if update:
                updates.append(update)

        # Parse new belief (max 1)
        new_belief = None
        raw_new_belief = json_data.get("new_belief")
        if raw_new_belief:
            new_belief = _validate_new_belief_proposal(
                item=raw_new_belief,
                existing_beliefs=existing_beliefs,
                correlation_id=correlation_id
            )

        return BeliefProposals(updates=updates, new_belief=new_belief)

    except json.JSONDecodeError as e:
        logger.warning(
            "Failed to parse belief analysis response as JSON",
            extra={
                "correlation_id": correlation_id,
                "error": str(e),
                "response_preview": response_text[:300]
            }
        )
        return BeliefProposals.empty()


def _extract_json_object(text: str) -> Optional[Dict]:
    """
    Extract JSON object from LLM response text.

    Handles responses that may have text before/after the JSON.
    """
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find JSON object in text
    # Look for outermost { }
    brace_count = 0
    start_idx = None
    for i, char in enumerate(text):
        if char == '{':
            if brace_count == 0:
                start_idx = i
            brace_count += 1
        elif char == '}':
            brace_count -= 1
            if brace_count == 0 and start_idx is not None:
                try:
                    return json.loads(text[start_idx:i + 1])
                except json.JSONDecodeError:
                    continue

    return None


def _validate_update_proposal(
    item: Dict,
    valid_belief_ids: set,
    belief_id_to_data: Dict,
    correlation_id: str
) -> Optional[BeliefUpdateProposal]:
    """Validate a single belief update proposal."""
    try:
        belief_id = item.get("belief_id", "")

        # Must reference existing belief
        if belief_id not in valid_belief_ids:
            logger.debug(
                "Update proposal references non-existent belief",
                extra={
                    "correlation_id": correlation_id,
                    "belief_id": belief_id
                }
            )
            return None

        # Get current confidence from actual belief
        actual_belief = belief_id_to_data.get(belief_id, {})
        current_confidence = actual_belief.get("confidence", 0.5)

        # Parse proposed confidence
        proposed_confidence = float(item.get("proposed_confidence", current_confidence))
        proposed_confidence = max(0.01, min(0.99, proposed_confidence))  # Clamp to valid range

        # Skip if no meaningful change
        if abs(proposed_confidence - current_confidence) < 0.02:
            logger.debug(
                "Update proposal has negligible confidence change",
                extra={
                    "correlation_id": correlation_id,
                    "belief_id": belief_id,
                    "current": current_confidence,
                    "proposed": proposed_confidence
                }
            )
            return None

        # Validate evidence strength
        evidence_strength = item.get("evidence_strength", "moderate").lower()
        if evidence_strength not in VALID_EVIDENCE_STRENGTHS:
            evidence_strength = "moderate"

        return BeliefUpdateProposal(
            belief_id=belief_id,
            belief_title=actual_belief.get("title", item.get("belief_title", "")),
            current_confidence=current_confidence,
            proposed_confidence=proposed_confidence,
            reason=str(item.get("reason", ""))[:500],
            evidence_strength=evidence_strength
        )

    except (ValueError, TypeError) as e:
        logger.debug(
            "Failed to validate update proposal",
            extra={
                "correlation_id": correlation_id,
                "error": str(e),
                "item": str(item)[:200]
            }
        )
        return None


def _validate_new_belief_proposal(
    item: Dict,
    existing_beliefs: List[Dict],
    correlation_id: str
) -> Optional[NewBeliefProposal]:
    """Validate a new belief proposal."""
    try:
        title = str(item.get("title", "")).strip()
        summary = str(item.get("summary", "")).strip()

        # Must have title and summary
        if not title or len(title) < 3:
            logger.debug(
                "New belief proposal missing or too short title",
                extra={"correlation_id": correlation_id}
            )
            return None

        if not summary or len(summary) < 10:
            logger.debug(
                "New belief proposal missing or too short summary",
                extra={"correlation_id": correlation_id}
            )
            return None

        # Check for duplicates (simple title similarity)
        title_lower = title.lower()
        for existing in existing_beliefs:
            existing_title = existing.get("title", "").lower()
            if _titles_too_similar(title_lower, existing_title):
                logger.debug(
                    "New belief proposal too similar to existing belief",
                    extra={
                        "correlation_id": correlation_id,
                        "new_title": title,
                        "existing_title": existing.get("title", "")
                    }
                )
                return None

        # Parse confidence
        initial_confidence = float(item.get("initial_confidence", 0.6))
        initial_confidence = max(0.3, min(0.9, initial_confidence))  # Reasonable range for new beliefs

        # Parse tags
        raw_tags = item.get("tags", [])
        tags = [str(t).strip() for t in raw_tags if isinstance(t, str)][:5]  # Max 5 tags

        return NewBeliefProposal(
            title=title[:500],  # Enforce max length
            summary=summary[:2000],
            initial_confidence=initial_confidence,
            tags=tags,
            reason=str(item.get("reason", ""))[:500]
        )

    except (ValueError, TypeError) as e:
        logger.debug(
            "Failed to validate new belief proposal",
            extra={
                "correlation_id": correlation_id,
                "error": str(e),
                "item": str(item)[:200]
            }
        )
        return None


def _titles_too_similar(title1: str, title2: str) -> bool:
    """
    Check if two titles are too similar (potential duplicate).

    Uses simple word overlap heuristic.
    """
    words1 = set(title1.split())
    words2 = set(title2.split())

    if not words1 or not words2:
        return False

    # Calculate Jaccard similarity
    intersection = len(words1 & words2)
    union = len(words1 | words2)

    if union == 0:
        return False

    similarity = intersection / union
    return similarity > 0.7  # 70% word overlap = too similar
