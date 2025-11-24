"""
Governor Service

Provides introspective analysis and explanation of the agent's reasoning,
belief evolution, and past actions. Used by the Governor chat interface.

This service does NOT modify agent state - it only reads and explains.
Belief adjustment proposals must be approved by admins via separate endpoints.
"""

import re
import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

from app.services.interfaces.memory_store import IMemoryStore
from app.services.interfaces.llm_client import ILLMClient
from app.prompts.governor import format_governor_context

logger = logging.getLogger(__name__)


class GovernorQueryIntent:
    """Query intent classification"""
    BELIEF_HISTORY = "belief_history"
    INTERACTION_SEARCH = "interaction_search"
    REASONING_EXPLANATION = "reasoning_explanation"
    BELIEF_ANALYSIS = "belief_analysis"
    GENERAL = "general"


async def build_governor_context(
    persona_id: str,
    question: str,
    memory_store: IMemoryStore
) -> Dict[str, Any]:
    """
    Build context for governor query based on question intent.

    Analyzes the question to determine what information to retrieve:
    - Belief history queries → fetch belief update logs
    - Interaction search → search past interactions
    - Reasoning explanation → find specific interaction + context
    - General → provide overview

    Args:
        persona_id: UUID of persona
        question: User's question
        memory_store: Memory store instance

    Returns:
        Dict with relevant context:
        {
            "intent": "belief_history" | "interaction_search" | ...,
            "persona": {...},
            "beliefs": {...},
            "interactions": [...],
            "belief_history": [...],  # If belief history query
            "target_interaction": {...}  # If reasoning explanation
        }
    """
    # Classify intent
    intent = classify_query_intent(question)

    # Always include persona and belief graph
    from app.models.persona import Persona
    from sqlalchemy import select
    from app.core.database import async_session_maker

    async with async_session_maker() as session:
        stmt = select(Persona).where(Persona.id == persona_id)
        result = await session.execute(stmt)
        persona = result.scalar_one_or_none()

        if not persona:
            raise ValueError(f"Persona {persona_id} not found")

        persona_dict = {
            "id": persona.id,
            "reddit_username": persona.reddit_username,
            "display_name": persona.display_name,
            "config": persona.get_config()
        }

    # Fetch belief graph
    belief_graph = await memory_store.query_belief_graph(
        persona_id=persona_id,
        min_confidence=0.0  # Include all beliefs for governor
    )

    context = {
        "intent": intent,
        "persona": persona_dict,
        "beliefs": belief_graph,
        "interactions": []
    }

    # Intent-specific retrieval
    if intent == GovernorQueryIntent.BELIEF_HISTORY:
        # Extract belief ID or topic from question
        belief_id = extract_belief_from_question(question, belief_graph)
        if belief_id:
            try:
                belief_data = await memory_store.get_belief_with_stances(
                    persona_id=persona_id,
                    belief_id=belief_id
                )
                context["belief_history"] = belief_data
            except ValueError:
                logger.warning(f"Belief {belief_id} not found for governor query")
                context["belief_history"] = None
        else:
            context["belief_history"] = None

    elif intent == GovernorQueryIntent.INTERACTION_SEARCH:
        # Search interaction history
        search_results = await memory_store.search_history(
            persona_id=persona_id,
            query=question,
            limit=10
        )
        context["interactions"] = search_results

    elif intent == GovernorQueryIntent.REASONING_EXPLANATION:
        # Try to find specific interaction mentioned in question
        reddit_id = extract_reddit_id_from_question(question)
        if reddit_id:
            # Fetch specific interaction
            from app.models.interaction import Interaction
            from sqlalchemy import and_

            async with async_session_maker() as session:
                stmt = select(Interaction).where(
                    and_(
                        Interaction.reddit_id == reddit_id,
                        Interaction.persona_id == persona_id
                    )
                )
                result = await session.execute(stmt)
                interaction = result.scalar_one_or_none()

                if interaction:
                    context["target_interaction"] = {
                        "id": interaction.id,
                        "content": interaction.content,
                        "interaction_type": interaction.interaction_type,
                        "reddit_id": interaction.reddit_id,
                        "subreddit": interaction.subreddit,
                        "metadata": interaction.get_metadata(),
                        "created_at": interaction.created_at.isoformat()
                    }
                else:
                    logger.warning(f"Interaction {reddit_id} not found")
                    context["target_interaction"] = None
        else:
            # Search for interactions matching the question
            search_results = await memory_store.search_history(
                persona_id=persona_id,
                query=question,
                limit=5
            )
            context["interactions"] = search_results

    elif intent == GovernorQueryIntent.BELIEF_ANALYSIS:
        # Fetch recent belief updates
        from app.models.belief import BeliefUpdate
        from sqlalchemy import desc

        async with async_session_maker() as session:
            stmt = (
                select(BeliefUpdate)
                .where(BeliefUpdate.persona_id == persona_id)
                .order_by(desc(BeliefUpdate.created_at))
                .limit(20)
            )
            result = await session.execute(stmt)
            updates = result.scalars().all()

            context["recent_updates"] = [
                {
                    "belief_id": upd.belief_id,
                    "old_value": upd.get_old_value(),
                    "new_value": upd.get_new_value(),
                    "reason": upd.reason,
                    "trigger_type": upd.trigger_type,
                    "updated_by": upd.updated_by,
                    "created_at": upd.created_at.isoformat()
                }
                for upd in updates
            ]

    else:
        # General query - provide recent interactions
        search_results = await memory_store.search_history(
            persona_id=persona_id,
            query=question,
            limit=5
        )
        context["interactions"] = search_results

    return context


def classify_query_intent(question: str) -> str:
    """
    Classify user question to determine retrieval strategy.

    Args:
        question: User's question

    Returns:
        Intent string (one of GovernorQueryIntent values)
    """
    question_lower = question.lower()

    # Belief history keywords (more specific patterns)
    belief_history_keywords = [
        "how did", "change", "evolve", "history",
        "confidence", "update"
    ]

    # Interaction search keywords (check first - more specific)
    interaction_search_keywords = [
        "show", "find", "posts about", "comments about", "said about",
        "discussed", "mentioned", "posts", "comments"
    ]

    # Reasoning explanation keywords
    reasoning_keywords = [
        "why did", "explain", "reason", "what made you",
        "how come", "why", "t1_", "t3_"  # Reddit ID patterns
    ]

    # Belief analysis keywords (check for "should" + belief context)
    analysis_keywords = [
        "should", "adjust", "recommend", "propose", "suggest",
        "analysis", "evaluate"
    ]

    # Check in specific order with more specific patterns
    # 1. Reasoning explanation (most specific - includes Reddit IDs)
    if any(kw in question_lower for kw in reasoning_keywords):
        return GovernorQueryIntent.REASONING_EXPLANATION

    # 2. Interaction search (look for posts/comments/show/find)
    if any(kw in question_lower for kw in interaction_search_keywords):
        return GovernorQueryIntent.INTERACTION_SEARCH

    # 3. Belief analysis (should/recommend/adjust/evaluate)
    if any(kw in question_lower for kw in analysis_keywords):
        # Check if it's also about belief context
        if "belief" in question_lower or "stance" in question_lower or "position" in question_lower:
            return GovernorQueryIntent.BELIEF_ANALYSIS

    # 4. Belief history (how did X change/evolve)
    if any(kw in question_lower for kw in belief_history_keywords):
        return GovernorQueryIntent.BELIEF_HISTORY

    return GovernorQueryIntent.GENERAL


def extract_belief_from_question(question: str, belief_graph: Dict) -> Optional[str]:
    """
    Extract belief ID or find matching belief from question.

    Args:
        question: User's question
        belief_graph: Belief graph dict with nodes

    Returns:
        Belief ID if found, None otherwise
    """
    # Try to extract UUID pattern
    uuid_pattern = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
    match = re.search(uuid_pattern, question, re.IGNORECASE)
    if match:
        return match.group(0)

    # Try to match belief titles
    question_lower = question.lower()
    beliefs = belief_graph.get('nodes', [])

    for belief in beliefs:
        title_lower = belief['title'].lower()
        # Check if belief title is mentioned in question
        if title_lower in question_lower or any(
            word in question_lower for word in title_lower.split() if len(word) > 4
        ):
            return belief['id']

    return None


def extract_reddit_id_from_question(question: str) -> Optional[str]:
    """
    Extract Reddit ID (t1_, t3_, etc.) from question.

    Args:
        question: User's question

    Returns:
        Reddit ID if found, None otherwise
    """
    # Match patterns like t1_abc123, t3_xyz789
    reddit_id_pattern = r't[0-9]_[a-z0-9]+'
    match = re.search(reddit_id_pattern, question, re.IGNORECASE)
    if match:
        return match.group(0)

    return None


def extract_proposal(llm_response: str) -> Optional[Dict]:
    """
    Extract belief adjustment proposal from LLM response.

    Looks for JSON block with "belief_adjustment" type in the response.

    Args:
        llm_response: LLM's response text

    Returns:
        Proposal dict if found, None otherwise
    """
    # Look for JSON block with "belief_adjustment" type
    # Try to find JSON object (handle both single and multi-line)
    json_pattern = r'\{[^{}]*"type"\s*:\s*"belief_adjustment"[^{}]*\}'

    # First try simple pattern
    match = re.search(json_pattern, llm_response, re.DOTALL)

    if not match:
        # Try to find nested JSON
        # Find all potential JSON blocks
        start_idx = 0
        while True:
            start = llm_response.find('{', start_idx)
            if start == -1:
                break

            # Find matching closing brace
            depth = 0
            for i in range(start, len(llm_response)):
                if llm_response[i] == '{':
                    depth += 1
                elif llm_response[i] == '}':
                    depth -= 1
                    if depth == 0:
                        # Found a complete JSON block
                        json_str = llm_response[start:i+1]
                        try:
                            obj = json.loads(json_str)
                            if obj.get('type') == 'belief_adjustment':
                                return obj
                        except json.JSONDecodeError:
                            pass
                        break

            start_idx = start + 1

        return None

    json_str = match.group(0)
    try:
        proposal = json.loads(json_str)

        # Validate required fields
        required_fields = ['belief_id', 'current_confidence', 'proposed_confidence', 'reason']
        if all(field in proposal for field in required_fields):
            return proposal
    except json.JSONDecodeError:
        logger.warning(f"Failed to parse proposal JSON: {json_str}")

    return None


def extract_sources(llm_response: str) -> List[Dict]:
    """
    Extract source citations from LLM response.

    Looks for interaction IDs, belief IDs, or reddit links mentioned in response.

    Args:
        llm_response: LLM's response text

    Returns:
        List of source dicts with type and ID
    """
    sources = []

    # Extract UUIDs (likely belief or interaction IDs)
    uuid_pattern = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
    uuids = re.findall(uuid_pattern, llm_response, re.IGNORECASE)

    for uuid in uuids:
        sources.append({
            "type": "id_reference",
            "id": uuid
        })

    # Extract Reddit IDs
    reddit_id_pattern = r't[0-9]_[a-z0-9]+'
    reddit_ids = re.findall(reddit_id_pattern, llm_response, re.IGNORECASE)

    for reddit_id in reddit_ids:
        sources.append({
            "type": "reddit_id",
            "id": reddit_id
        })

    return sources


async def query_governor(
    persona_id: str,
    question: str,
    memory_store: IMemoryStore,
    llm_client: ILLMClient
) -> Dict[str, Any]:
    """
    Execute governor query with full context retrieval and LLM analysis.

    Args:
        persona_id: UUID of persona
        question: User's question
        memory_store: Memory store instance
        llm_client: LLM client instance

    Returns:
        Dict with:
        {
            "answer": "...",
            "sources": [...],
            "proposal": {...} or None,
            "intent": "...",
            "tokens_used": 123,
            "cost": 0.001
        }
    """
    # Build context
    context = await build_governor_context(
        persona_id=persona_id,
        question=question,
        memory_store=memory_store
    )

    # Format governor prompt
    system_prompt = format_governor_context(
        persona_config=context["persona"],
        belief_graph=context["beliefs"],
        interaction_history=context.get("interactions", [])
    )

    # Generate response
    response = await llm_client.generate_response(
        system_prompt=system_prompt,
        context=context,
        user_message=question,
        temperature=0.5,  # Moderate creativity
        max_tokens=800  # Allow detailed explanations
    )

    # Extract proposal if present
    proposal = extract_proposal(response["text"])

    # Extract sources
    sources = extract_sources(response["text"])

    return {
        "answer": response["text"],
        "sources": sources,
        "proposal": proposal,
        "intent": context["intent"],
        "tokens_used": response["total_tokens"],
        "cost": response["cost"],
        "model": response["model"]
    }
