"""
Relationship Suggester Service

Uses LLM to suggest relationships between a new belief and existing beliefs
in the persona's knowledge graph. Provides intelligent auto-linking capabilities
for belief creation.

Key features:
- LLM-powered relationship detection (supports, contradicts, depends_on, evidence_for)
- Validation of suggested relationships (persona isolation, valid relations, weight ranges)
- Structured JSON output from LLM with reasoning
- Correlation ID logging for observability
"""

import json
import logging
import uuid
import os
from typing import List, Dict, Any, Optional

from app.services.interfaces.llm_client import ILLMClient
from app.schemas.beliefs import RelationshipSuggestion

logger = logging.getLogger(__name__)

# Valid relation types for belief edges
VALID_RELATIONS = {"supports", "contradicts", "depends_on", "evidence_for"}

# LLM configuration for relationship suggestion
RELATIONSHIP_MODEL = os.getenv("RELATIONSHIP_MODEL", "anthropic/claude-haiku-4.5")
RELATIONSHIP_TEMPERATURE = 0.3  # Deterministic suggestions
RELATIONSHIP_MAX_TOKENS = 1500  # Increased for structured JSON output with reasoning


async def suggest_relationships(
    persona_id: str,
    belief_title: str,
    belief_summary: str,
    existing_beliefs: List[Dict[str, Any]],
    llm_client: ILLMClient,
    max_suggestions: int = 5,
    correlation_id: Optional[str] = None,
) -> List[RelationshipSuggestion]:
    """
    Suggest relationships between a new belief and existing beliefs.

    Uses LLM to analyze semantic relationships between beliefs and suggest
    meaningful connections in the knowledge graph.

    Args:
        persona_id: UUID of the persona (for validation/logging)
        belief_title: Title of the new belief
        belief_summary: Summary/description of the new belief
        existing_beliefs: List of existing belief dicts with id, title, summary
        llm_client: LLM client instance for generating suggestions
        max_suggestions: Maximum number of suggestions to return (default 5)
        correlation_id: Optional request ID for tracing

    Returns:
        List of RelationshipSuggestion objects (up to max_suggestions)

    Note:
        - Returns empty list if no existing beliefs or LLM fails
        - Validates suggestions: only same persona, valid relations, weight 0.0-1.0
        - Logs with correlation IDs for observability
    """
    if correlation_id is None:
        correlation_id = str(uuid.uuid4())

    # Early return if no existing beliefs to compare
    if not existing_beliefs:
        logger.info(
            "No existing beliefs to suggest relationships with",
            extra={
                "correlation_id": correlation_id,
                "persona_id": persona_id,
                "belief_title": belief_title
            }
        )
        return []

    logger.info(
        "Suggesting relationships for new belief",
        extra={
            "correlation_id": correlation_id,
            "persona_id": persona_id,
            "belief_title": belief_title,
            "existing_belief_count": len(existing_beliefs),
            "max_suggestions": max_suggestions
        }
    )

    # Build prompt for LLM
    system_prompt = _build_system_prompt()
    context = _build_context(belief_title, belief_summary, existing_beliefs)
    user_message = _build_user_message(belief_title, max_suggestions)

    try:
        # Call LLM for suggestions using Claude Haiku for better structured JSON output
        response = await llm_client.generate_response(
            system_prompt=system_prompt,
            context=context,
            user_message=user_message,
            temperature=RELATIONSHIP_TEMPERATURE,
            max_tokens=RELATIONSHIP_MAX_TOKENS,
            correlation_id=correlation_id,
            model=RELATIONSHIP_MODEL  # Use Claude Haiku instead of default GPT
        )

        # Parse and validate LLM response
        suggestions = _parse_llm_response(
            response_text=response.get("text", ""),
            existing_beliefs=existing_beliefs,
            max_suggestions=max_suggestions,
            correlation_id=correlation_id
        )

        logger.info(
            "Relationship suggestions generated",
            extra={
                "correlation_id": correlation_id,
                "persona_id": persona_id,
                "suggestion_count": len(suggestions),
                "tokens_used": response.get("total_tokens", 0),
                "cost": response.get("cost", 0.0)
            }
        )

        return suggestions

    except Exception as e:
        logger.error(
            "Failed to generate relationship suggestions",
            extra={
                "correlation_id": correlation_id,
                "persona_id": persona_id,
                "error": str(e),
                "error_type": type(e).__name__
            },
            exc_info=True
        )
        # Return empty list on failure - don't block belief creation
        return []


def _build_system_prompt() -> str:
    """Build the system prompt for relationship suggestion."""
    return """You are an expert knowledge graph analyst. Your task is to analyze relationships
between beliefs in an AI agent's knowledge graph.

You will be given a NEW belief and a list of EXISTING beliefs. For each potential relationship,
you must determine:
1. Whether a meaningful relationship exists
2. The type of relationship (supports, contradicts, depends_on, evidence_for)
3. The strength of the relationship (0.0-1.0)
4. A brief reasoning for the suggestion

Relationship types:
- supports: The new belief reinforces or agrees with the existing belief
- contradicts: The new belief conflicts with or opposes the existing belief
- depends_on: The new belief relies on or assumes the existing belief is true
- evidence_for: The new belief provides evidence or examples supporting the existing belief

Weight guidelines:
- 0.1-0.3: Weak relationship (tangentially related)
- 0.4-0.6: Moderate relationship (meaningfully connected)
- 0.7-0.9: Strong relationship (closely related or directly impacts)
- 1.0: Reserved for extremely strong, definitive relationships

Be selective - only suggest relationships that are genuinely meaningful.
Not every belief pair needs a relationship."""


def _build_context(
    belief_title: str,
    belief_summary: str,
    existing_beliefs: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Build the context dict for LLM prompt."""
    existing_summary = []
    for belief in existing_beliefs:
        existing_summary.append({
            "id": belief.get("id", ""),
            "title": belief.get("title", ""),
            "summary": belief.get("summary", ""),
            "confidence": belief.get("confidence", 0.5)
        })

    return {
        "new_belief": {
            "title": belief_title,
            "summary": belief_summary
        },
        "existing_beliefs": existing_summary
    }


def _build_user_message(belief_title: str, max_suggestions: int) -> str:
    """Build the user message for LLM prompt."""
    return f"""Analyze the NEW belief and suggest up to {max_suggestions} relationships with
the EXISTING beliefs provided in the context.

Return your response as a JSON array of suggestions. Each suggestion must have:
- target_belief_id: The UUID of the related existing belief
- target_belief_title: The title of the related existing belief
- relation: One of "supports", "contradicts", "depends_on", "evidence_for"
- weight: A float between 0.0 and 1.0
- reasoning: A brief (1-2 sentence) explanation

Example format:
[
  {{
    "target_belief_id": "uuid-here",
    "target_belief_title": "Example Belief",
    "relation": "supports",
    "weight": 0.7,
    "reasoning": "The new belief about X directly reinforces the existing belief about Y."
  }}
]

If no meaningful relationships exist, return an empty array: []

Important: Only include relationships that are genuinely meaningful. Quality over quantity."""


def _parse_llm_response(
    response_text: str,
    existing_beliefs: List[Dict[str, Any]],
    max_suggestions: int,
    correlation_id: str
) -> List[RelationshipSuggestion]:
    """
    Parse and validate LLM response into RelationshipSuggestion objects.

    Args:
        response_text: Raw LLM response text
        existing_beliefs: List of existing beliefs (for validation)
        max_suggestions: Maximum number of suggestions to return
        correlation_id: Request ID for logging

    Returns:
        List of validated RelationshipSuggestion objects
    """
    suggestions = []

    # Build set of valid belief IDs for validation
    valid_belief_ids = {b.get("id") for b in existing_beliefs}
    belief_id_to_title = {b.get("id"): b.get("title", "") for b in existing_beliefs}

    try:
        # Try to extract JSON from response
        json_data = _extract_json_array(response_text)

        if not json_data:
            logger.warning(
                "No valid JSON array found in LLM response",
                extra={
                    "correlation_id": correlation_id,
                    "response_length": len(response_text)
                }
            )
            return []

        for item in json_data:
            if len(suggestions) >= max_suggestions:
                break

            # Validate each suggestion
            suggestion = _validate_suggestion(
                item=item,
                valid_belief_ids=valid_belief_ids,
                belief_id_to_title=belief_id_to_title,
                correlation_id=correlation_id
            )

            if suggestion:
                suggestions.append(suggestion)

    except json.JSONDecodeError as e:
        logger.warning(
            "Failed to parse LLM response as JSON",
            extra={
                "correlation_id": correlation_id,
                "error": str(e),
                "response_preview": response_text[:200]
            }
        )

    return suggestions


def _extract_json_array(text: str) -> Optional[List[Dict]]:
    """
    Extract JSON array from LLM response text.

    Handles various response formats including markdown code blocks.

    Args:
        text: Raw LLM response text

    Returns:
        Parsed JSON array or None if extraction fails
    """
    # Try direct parse first
    try:
        data = json.loads(text.strip())
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass

    # Try to find JSON array in markdown code block
    import re
    code_block_pattern = r'```(?:json)?\s*(\[[\s\S]*?\])\s*```'
    match = re.search(code_block_pattern, text)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Try to find raw JSON array
    array_pattern = r'\[[\s\S]*?\]'
    matches = re.findall(array_pattern, text)
    for match_text in matches:
        try:
            data = json.loads(match_text)
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            continue

    return None


def _validate_suggestion(
    item: Dict[str, Any],
    valid_belief_ids: set,
    belief_id_to_title: Dict[str, str],
    correlation_id: str
) -> Optional[RelationshipSuggestion]:
    """
    Validate a single suggestion from LLM response.

    Args:
        item: Raw suggestion dict from LLM
        valid_belief_ids: Set of valid belief UUIDs
        belief_id_to_title: Mapping of belief ID to title
        correlation_id: Request ID for logging

    Returns:
        RelationshipSuggestion if valid, None otherwise
    """
    try:
        # Extract fields
        target_id = item.get("target_belief_id", "")
        relation = item.get("relation", "")
        weight = item.get("weight", 0.5)
        reasoning = item.get("reasoning", "")

        # Validate target_belief_id exists in persona's beliefs
        if target_id not in valid_belief_ids:
            logger.debug(
                "Suggestion rejected: invalid target_belief_id",
                extra={
                    "correlation_id": correlation_id,
                    "target_id": target_id
                }
            )
            return None

        # Validate relation type
        if relation not in VALID_RELATIONS:
            logger.debug(
                "Suggestion rejected: invalid relation type",
                extra={
                    "correlation_id": correlation_id,
                    "relation": relation
                }
            )
            return None

        # Validate weight range
        try:
            weight = float(weight)
            if not 0.0 <= weight <= 1.0:
                weight = max(0.0, min(1.0, weight))  # Clamp to valid range
        except (ValueError, TypeError):
            weight = 0.5  # Default weight

        # Get actual title from our data (don't trust LLM's title)
        target_title = belief_id_to_title.get(target_id, item.get("target_belief_title", ""))

        # Ensure reasoning is a string
        if not isinstance(reasoning, str):
            reasoning = str(reasoning) if reasoning else "Relationship detected by LLM analysis"

        return RelationshipSuggestion(
            target_belief_id=target_id,
            target_belief_title=target_title,
            relation=relation,
            weight=round(weight, 2),
            reasoning=reasoning
        )

    except Exception as e:
        logger.debug(
            "Failed to validate suggestion",
            extra={
                "correlation_id": correlation_id,
                "error": str(e),
                "item": str(item)[:200]
            }
        )
        return None
