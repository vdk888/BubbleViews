"""
Retrieval Coordinator Service

Assembles context for LLM prompts by orchestrating retrieval from multiple sources:
- Belief graph (current stances and relations)
- Past self-comments (via FAISS semantic search)
- Evidence links supporting beliefs
- URL extraction from persona profiles and thread content

Implements token budget enforcement to stay within LLM context limits.
"""

import re
from typing import Dict, List, Optional, Any, Tuple
import tiktoken

from app.services.interfaces.memory_store import IMemoryStore
from app.services.embedding import EmbeddingService


def extract_markdown_links(text: str) -> List[Dict[str, str]]:
    """
    Extract markdown links from text.

    Parses [description](url) patterns and returns structured list.

    Args:
        text: Text containing markdown links

    Returns:
        List of dicts with 'description' and 'url' keys:
        [
            {"description": "this article", "url": "https://example.com/article"},
            ...
        ]
    """
    if not text:
        return []

    # Pattern matches [description](url) - handles nested brackets and various URL chars
    pattern = r'\[([^\]]+)\]\(([^)]+)\)'
    matches = re.findall(pattern, text)

    links = []
    seen_urls = set()  # Deduplicate by URL

    for description, url in matches:
        url = url.strip()
        # Skip empty URLs or duplicates
        if not url or url in seen_urls:
            continue

        # Basic URL validation - must start with http(s)://
        if not url.startswith(('http://', 'https://')):
            continue

        seen_urls.add(url)
        links.append({
            "description": description.strip(),
            "url": url
        })

    return links


def extract_urls_from_context(
    personality_profile: str | None,
    writing_rules: List[str] | None,
    thread_content: str | None
) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    """
    Extract URLs from persona context and thread content.

    Separates URLs into two categories for clearer LLM presentation.

    Args:
        personality_profile: Persona's background/personality text
        writing_rules: List of writing rules
        thread_content: Combined thread title/body/comment text

    Returns:
        Tuple of (persona_urls, thread_urls)
    """
    persona_urls = []
    thread_urls = []

    # Extract from personality profile
    if personality_profile:
        persona_urls.extend(extract_markdown_links(personality_profile))

    # Extract from writing rules
    if writing_rules:
        for rule in writing_rules:
            persona_urls.extend(extract_markdown_links(rule))

    # Extract from thread content
    if thread_content:
        thread_urls.extend(extract_markdown_links(thread_content))

    return persona_urls, thread_urls


# Token budget configuration
DEFAULT_TOKEN_BUDGET = 3000
PERSONA_SECTION_TOKENS = 500
BELIEFS_SECTION_TOKENS = 1500
HISTORY_SECTION_TOKENS = 800
THREAD_CONTEXT_TOKENS = 200


class RetrievalCoordinator:
    """
    Coordinates retrieval of context for agent decision-making.

    Assembles structured context from:
    1. Persona configuration
    2. Relevant beliefs with current stances
    3. Semantically similar past interactions
    4. Evidence supporting beliefs

    Enforces token budget to ensure context fits within LLM limits.
    """

    def __init__(
        self,
        memory_store: IMemoryStore,
        embedding_service: EmbeddingService,
        token_budget: int = DEFAULT_TOKEN_BUDGET
    ):
        """
        Initialize retrieval coordinator.

        Args:
            memory_store: Memory store instance for belief/interaction queries
            embedding_service: Embedding service for semantic search
            token_budget: Maximum tokens for assembled context (default: 3000)
        """
        self.memory_store = memory_store
        self.embedding_service = embedding_service
        self.token_budget = token_budget

        # Initialize tokenizer for token counting (using cl100k_base for GPT-4 compatibility)
        try:
            self.tokenizer = tiktoken.get_encoding("cl100k_base")
        except Exception:
            # Fallback if tiktoken not available
            self.tokenizer = None

    def _count_tokens(self, text: str) -> int:
        """
        Count tokens in text.

        Args:
            text: Text to count tokens in

        Returns:
            Number of tokens (approximate if tokenizer unavailable)
        """
        if self.tokenizer:
            return len(self.tokenizer.encode(text))
        else:
            # Rough approximation: 1 token ≈ 4 characters
            return len(text) // 4

    async def get_belief_context(
        self,
        persona_id: str,
        tags: Optional[List[str]] = None,
        min_confidence: float = 0.5
    ) -> Dict[str, Any]:
        """
        Retrieve belief graph context for persona.

        Fetches relevant beliefs with current stances and relations,
        optionally filtered by tags.

        Args:
            persona_id: UUID of persona
            tags: Optional list of tags to filter beliefs
            min_confidence: Minimum confidence threshold (default: 0.5)

        Returns:
            Dictionary with structure:
            {
                "beliefs": [
                    {
                        "id": "belief-uuid",
                        "title": "Belief title",
                        "summary": "Description",
                        "confidence": 0.85,
                        "tags": ["tag1", "tag2"],
                        "current_stance": {
                            "text": "Current stance text",
                            "confidence": 0.85,
                            "rationale": "Why this stance"
                        }
                    },
                    ...
                ],
                "relations": [
                    {
                        "source_id": "belief-uuid-1",
                        "target_id": "belief-uuid-2",
                        "relation": "supports",
                        "weight": 0.7
                    },
                    ...
                ]
            }
        """
        # Query belief graph
        belief_graph = await self.memory_store.query_belief_graph(
            persona_id=persona_id,
            tags=tags,
            min_confidence=min_confidence
        )

        # Extract nodes and edges
        nodes = belief_graph.get("nodes", [])
        edges = belief_graph.get("edges", [])

        # For each belief, fetch current stance (already in current_confidence)
        # We'll enrich with stance text if needed
        beliefs = []
        for node in nodes:
            belief = {
                "id": node["id"],
                "title": node["title"],
                "summary": node["summary"],
                "confidence": node["confidence"],
                "tags": node["tags"],
            }
            beliefs.append(belief)

        return {
            "beliefs": beliefs,
            "relations": edges
        }

    async def get_past_comments(
        self,
        persona_id: str,
        query_text: str,
        limit: int = 5,
        subreddit: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve semantically similar past comments.

        Uses FAISS index to find past interactions similar to query text.

        Args:
            persona_id: UUID of persona
            query_text: Text to search for similar interactions
            limit: Maximum number of results (default: 5)
            subreddit: Optional subreddit filter

        Returns:
            List of similar past interactions:
            [
                {
                    "id": "interaction-uuid",
                    "content": "The interaction text",
                    "reddit_id": "t1_abc123",
                    "subreddit": "AskReddit",
                    "similarity_score": 0.87,
                    "created_at": "2025-11-24T..."
                },
                ...
            ]
        """
        # Search interaction history
        results = await self.memory_store.search_history(
            persona_id=persona_id,
            query=query_text,
            limit=limit,
            subreddit=subreddit
        )

        return results

    async def get_evidence_for_beliefs(
        self,
        persona_id: str,
        belief_ids: List[str],
        limit_per_belief: int = 2
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Retrieve evidence links for a list of beliefs.

        Fetches top N evidence links for each belief to support context.

        Args:
            persona_id: UUID of persona
            belief_ids: List of belief UUIDs to fetch evidence for
            limit_per_belief: Max evidence links per belief (default: 2)

        Returns:
            Dictionary mapping belief_id to evidence list:
            {
                "belief-uuid-1": [
                    {
                        "id": "evidence-uuid",
                        "source_type": "reddit_comment",
                        "source_ref": "t1_abc123",
                        "strength": "strong"
                    },
                    ...
                ],
                ...
            }
        """
        evidence_map = {}

        for belief_id in belief_ids:
            try:
                # Fetch belief with evidence
                belief_data = await self.memory_store.get_belief_with_stances(
                    persona_id=persona_id,
                    belief_id=belief_id
                )

                # Extract evidence (already sorted by created_at DESC)
                evidence = belief_data.get("evidence", [])

                # Limit to top N
                evidence_map[belief_id] = evidence[:limit_per_belief]

            except ValueError:
                # Belief not found or permission error
                evidence_map[belief_id] = []

        return evidence_map

    async def assemble_context(
        self,
        persona_id: str,
        thread_context: Dict[str, Any],
        tags: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Assemble complete context for LLM prompt.

        Orchestrates retrieval from all sources and enforces token budget.

        Args:
            persona_id: UUID of persona
            thread_context: Reddit thread context
                {
                    "title": "Post title",
                    "body": "Post body",
                    "comment": "Parent comment if replying",
                    "subreddit": "AskReddit",
                    "topic_tags": ["climate", "science"]  # Optional
                }
            tags: Optional tags to filter beliefs (overrides thread_context tags)

        Returns:
            Assembled context dictionary:
            {
                "beliefs": [...],
                "relations": [...],
                "past_statements": [...],
                "evidence": {...},
                "thread": {...},
                "token_count": 2850
            }

        Raises:
            ValueError: If persona not found or thread_context missing required fields
        """
        # Validate thread_context
        if "subreddit" not in thread_context:
            raise ValueError("thread_context must contain 'subreddit'")

        # Extract topic tags from thread or use provided tags
        topic_tags = tags or thread_context.get("topic_tags", [])

        # Build query text for semantic search (combine title + body + comment)
        query_parts = []
        if "title" in thread_context:
            query_parts.append(thread_context["title"])
        if "body" in thread_context:
            query_parts.append(thread_context["body"])
        if "comment" in thread_context:
            query_parts.append(thread_context["comment"])

        query_text = " ".join(query_parts).strip()

        # 1. Retrieve belief graph context
        belief_context = await self.get_belief_context(
            persona_id=persona_id,
            tags=topic_tags if topic_tags else None,
            min_confidence=0.5
        )

        beliefs = belief_context["beliefs"]
        relations = belief_context["relations"]

        # 2. Retrieve past self-comments
        past_statements = await self.get_past_comments(
            persona_id=persona_id,
            query_text=query_text,
            limit=5,
            subreddit=thread_context.get("subreddit")
        )

        # 3. Retrieve evidence for top beliefs
        belief_ids = [b["id"] for b in beliefs[:5]]  # Top 5 beliefs
        evidence_map = await self.get_evidence_for_beliefs(
            persona_id=persona_id,
            belief_ids=belief_ids,
            limit_per_belief=2
        )

        # 4. Assemble and enforce token budget
        assembled = {
            "beliefs": beliefs,
            "relations": relations,
            "past_statements": past_statements,
            "evidence": evidence_map,
            "thread": thread_context,
        }

        # Prune if over budget
        assembled = self._enforce_token_budget(assembled)

        # Add final token count
        assembled["token_count"] = self._count_context_tokens(assembled)

        return assembled

    def _count_context_tokens(self, context: Dict[str, Any]) -> int:
        """
        Count total tokens in assembled context.

        Args:
            context: Assembled context dictionary

        Returns:
            Approximate token count
        """
        # Convert to string representation for counting
        import json

        # Simplified token counting: just count beliefs + past_statements + thread
        beliefs_text = json.dumps(context.get("beliefs", []))
        past_text = json.dumps(context.get("past_statements", []))
        thread_text = json.dumps(context.get("thread", {}))
        evidence_text = json.dumps(context.get("evidence", {}))

        total_tokens = (
            self._count_tokens(beliefs_text) +
            self._count_tokens(past_text) +
            self._count_tokens(thread_text) +
            self._count_tokens(evidence_text)
        )

        return total_tokens

    def _enforce_token_budget(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prune context to fit within token budget.

        Priority: persona > high-confidence beliefs > recent past statements

        Args:
            context: Assembled context dictionary

        Returns:
            Pruned context dictionary
        """
        current_tokens = self._count_context_tokens(context)

        if current_tokens <= self.token_budget:
            return context

        # Prune past_statements first
        past_statements = context["past_statements"]
        while len(past_statements) > 0 and current_tokens > self.token_budget:
            past_statements.pop()  # Remove least similar (last in list)
            current_tokens = self._count_context_tokens(context)

        # Prune low-confidence beliefs
        beliefs = context["beliefs"]
        if current_tokens > self.token_budget:
            # Sort by confidence DESC, keep top N
            beliefs.sort(key=lambda b: b["confidence"], reverse=True)
            while len(beliefs) > 1 and current_tokens > self.token_budget:
                beliefs.pop()  # Remove lowest confidence
                current_tokens = self._count_context_tokens(context)

        # Prune evidence if still over budget
        evidence_map = context["evidence"]
        if current_tokens > self.token_budget:
            # Remove evidence for low-confidence beliefs
            for belief_id in list(evidence_map.keys()):
                if current_tokens <= self.token_budget:
                    break
                evidence_map[belief_id] = []
                current_tokens = self._count_context_tokens(context)

        return context

    async def assemble_prompt(
        self,
        persona_config: Dict[str, Any],
        context: Dict[str, Any]
    ) -> str:
        """
        Assemble LLM prompt from persona and context.

        Builds structured prompt with sections:
        1. Persona description (with rich personality profile)
        2. Writing rules (behavioral constraints)
        3. Voice examples (few-shot demonstrations)
        4. Current beliefs with confidence
        5. Past relevant statements
        6. Thread context

        Args:
            persona_config: Persona configuration
                {
                    "reddit_username": "user123",
                    "display_name": "Agent Name",
                    "config": {
                        "tone": "witty",
                        "style": "informal",
                        "values": ["evidence-based", "open-minded"],
                        "personality_profile": "Rich backstory...",
                        "writing_rules": ["Never use emojis", ...],
                        "voice_examples": ["Example response...", ...]
                    }
                }
            context: Assembled context from assemble_context()

        Returns:
            Formatted prompt string
        """
        sections = []

        # 1. Persona Section (enhanced with rich personality)
        persona_name = persona_config.get("display_name", "Agent")
        config = persona_config.get("config", {})
        tone = config.get("tone", "neutral")
        style = config.get("style", "casual")
        values = config.get("values", config.get("core_values", []))
        personality_profile = config.get("personality_profile", "")
        writing_rules = config.get("writing_rules", [])
        voice_examples = config.get("voice_examples", [])

        # Build enhanced persona section
        persona_section = f"""# Persona
You are {persona_name}."""

        # Add rich personality profile if available
        if personality_profile:
            persona_section += f"""

## Background & Personality
{personality_profile}"""

        # Add communication style section
        persona_section += f"""

## Communication Style
- Tone: {tone}
- Style: {style}
- Core values: {", ".join(values) if values else "none specified"}"""

        sections.append(persona_section)

        # 2. Writing Rules Section (MUST follow these)
        if writing_rules:
            rules_section = "# Writing Rules (MUST follow these)\n"
            for i, rule in enumerate(writing_rules, 1):
                rules_section += f"{i}. {rule}\n"
            rules_section += """
These rules define your authentic voice. Follow them consistently to maintain
your unique personality and avoid sounding robotic or generic."""
            sections.append(rules_section)

        # 3. Voice Examples Section (few-shot demonstrations)
        if voice_examples:
            examples_section = "# Voice Examples\n"
            examples_section += """These examples demonstrate your authentic voice and style.
Use them as reference for tone, phrasing, and personality:\n\n"""
            for i, example in enumerate(voice_examples, 1):
                examples_section += f"Example {i}:\n\"{example}\"\n\n"
            sections.append(examples_section)

        # 4. Beliefs Section
        beliefs = context.get("beliefs", [])
        if beliefs:
            beliefs_section = "# Current Beliefs\n"
            for belief in beliefs[:10]:  # Top 10 beliefs
                title = belief["title"]
                confidence = belief["confidence"]
                beliefs_section += f"- {title} (confidence: {confidence:.2f})\n"
            sections.append(beliefs_section)

        # 5. Past Statements Section
        past_statements = context.get("past_statements", [])
        if past_statements:
            history_section = "# Past Statements on Similar Topics\n"
            history_section += "Your previous responses on related topics (stay consistent):\n"
            for stmt in past_statements[:3]:  # Top 3 most similar
                content = stmt["content"][:200]  # Truncate
                similarity = stmt["similarity_score"]
                history_section += f"- [{similarity:.2f}] {content}...\n"
            sections.append(history_section)

        # 6. Thread Context Section
        thread = context.get("thread", {})
        thread_section = "# Current Thread\n"
        if "title" in thread:
            thread_section += f"Post Title: {thread['title']}\n"
        if "body" in thread:
            body = thread["body"][:500]  # Truncate long posts
            thread_section += f"Post Body: {body}...\n"
        if "comment" in thread:
            comment = thread["comment"][:300]
            thread_section += f"Parent Comment: {comment}...\n"
        thread_section += f"Subreddit: r/{thread.get('subreddit', 'unknown')}\n"
        sections.append(thread_section)

        # 7. Available Reference URLs Section (for tool calling)
        # Extract URLs from persona profile, writing rules, and thread content
        thread_content = " ".join([
            thread.get("title", ""),
            thread.get("body", ""),
            thread.get("comment", "")
        ])

        persona_urls, thread_urls = extract_urls_from_context(
            personality_profile=personality_profile,
            writing_rules=writing_rules,
            thread_content=thread_content
        )

        # Only add section if there are URLs
        if persona_urls or thread_urls:
            urls_section = "# Available Reference URLs\n"
            urls_section += """If any of these URLs are relevant to your response, you can use the
fetch_url tool to read their content. Only fetch if the information would significantly
improve your response.\n\n"""

            if persona_urls:
                urls_section += "From your background/persona:\n"
                for link in persona_urls[:5]:  # Limit to 5 persona URLs
                    urls_section += f'- "{link["description"]}" -> {link["url"]}\n'
                urls_section += "\n"

            if thread_urls:
                urls_section += "From the current thread:\n"
                for link in thread_urls[:5]:  # Limit to 5 thread URLs
                    urls_section += f'- "{link["description"]}" -> {link["url"]}\n'

            sections.append(urls_section)

        # Assemble final prompt
        prompt = "\n\n".join(sections)
        return prompt
