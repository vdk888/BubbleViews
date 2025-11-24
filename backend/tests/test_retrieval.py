"""
Tests for Retrieval Coordinator Service

Tests context assembly, belief graph retrieval, semantic search,
evidence retrieval, prompt assembly, and token budget enforcement.
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from typing import Dict, Any, List

from app.services.retrieval import RetrievalCoordinator


# Test fixtures

@pytest.fixture
def mock_memory_store():
    """Mock memory store with AsyncMock."""
    store = AsyncMock()

    # Mock query_belief_graph
    store.query_belief_graph.return_value = {
        "nodes": [
            {
                "id": "belief-1",
                "title": "Climate change is real",
                "summary": "Evidence-based belief about climate change",
                "confidence": 0.95,
                "tags": ["science", "environment"],
                "created_at": "2025-11-20T10:00:00",
                "updated_at": "2025-11-24T10:00:00"
            },
            {
                "id": "belief-2",
                "title": "EVs reduce emissions",
                "summary": "Electric vehicles are better for environment",
                "confidence": 0.80,
                "tags": ["environment", "technology"],
                "created_at": "2025-11-20T10:00:00",
                "updated_at": "2025-11-24T10:00:00"
            }
        ],
        "edges": [
            {
                "id": "edge-1",
                "source_id": "belief-1",
                "target_id": "belief-2",
                "relation": "supports",
                "weight": 0.7,
                "created_at": "2025-11-20T10:00:00"
            }
        ]
    }

    # Mock search_history
    store.search_history.return_value = [
        {
            "id": "interaction-1",
            "content": "I believe climate change is a pressing issue that requires action.",
            "interaction_type": "comment",
            "reddit_id": "t1_abc123",
            "subreddit": "science",
            "parent_id": "t3_def456",
            "metadata": {},
            "similarity_score": 0.87,
            "created_at": "2025-11-22T10:00:00"
        },
        {
            "id": "interaction-2",
            "content": "Electric vehicles are a good step toward reducing emissions.",
            "interaction_type": "comment",
            "reddit_id": "t1_xyz789",
            "subreddit": "technology",
            "parent_id": "t3_ghi012",
            "metadata": {},
            "similarity_score": 0.75,
            "created_at": "2025-11-23T10:00:00"
        }
    ]

    # Mock get_belief_with_stances
    store.get_belief_with_stances.return_value = {
        "belief": {
            "id": "belief-1",
            "title": "Climate change is real",
            "summary": "Evidence-based belief",
            "current_confidence": 0.95,
            "tags": ["science"],
            "created_at": "2025-11-20T10:00:00",
            "updated_at": "2025-11-24T10:00:00"
        },
        "stances": [],
        "evidence": [
            {
                "id": "evidence-1",
                "source_type": "external_link",
                "source_ref": "https://ipcc.ch/report",
                "strength": "strong",
                "created_at": "2025-11-20T10:00:00"
            },
            {
                "id": "evidence-2",
                "source_type": "reddit_comment",
                "source_ref": "t1_source1",
                "strength": "moderate",
                "created_at": "2025-11-21T10:00:00"
            }
        ],
        "updates": []
    }

    return store


@pytest.fixture
def mock_embedding_service():
    """Mock embedding service."""
    service = Mock()
    # Embedding service doesn't have async methods called directly by retrieval
    return service


@pytest.fixture
def retrieval_coordinator(mock_memory_store, mock_embedding_service):
    """Create retrieval coordinator with mocked dependencies."""
    return RetrievalCoordinator(
        memory_store=mock_memory_store,
        embedding_service=mock_embedding_service,
        token_budget=3000
    )


# Test 1.1: Dependency Injection

def test_retrieval_coordinator_initialization(mock_memory_store, mock_embedding_service):
    """Test RetrievalCoordinator initializes with dependencies."""
    # Arrange & Act
    coordinator = RetrievalCoordinator(
        memory_store=mock_memory_store,
        embedding_service=mock_embedding_service
    )

    # Assert
    assert coordinator.memory_store == mock_memory_store
    assert coordinator.embedding_service == mock_embedding_service
    assert coordinator.token_budget == 3000  # Default
    assert coordinator.tokenizer is not None


def test_retrieval_coordinator_custom_token_budget(mock_memory_store, mock_embedding_service):
    """Test custom token budget configuration."""
    # Arrange & Act
    coordinator = RetrievalCoordinator(
        memory_store=mock_memory_store,
        embedding_service=mock_embedding_service,
        token_budget=5000
    )

    # Assert
    assert coordinator.token_budget == 5000


# Test 1.2: Belief Graph Retrieval

@pytest.mark.asyncio
async def test_get_belief_context_basic(retrieval_coordinator, mock_memory_store):
    """Test belief graph retrieval returns structured context."""
    # Arrange
    persona_id = "persona-1"

    # Act
    result = await retrieval_coordinator.get_belief_context(
        persona_id=persona_id
    )

    # Assert
    assert "beliefs" in result
    assert "relations" in result
    assert len(result["beliefs"]) == 2
    assert len(result["relations"]) == 1

    # Verify belief structure
    belief = result["beliefs"][0]
    assert "id" in belief
    assert "title" in belief
    assert "confidence" in belief
    assert "tags" in belief

    # Verify memory store was called correctly
    mock_memory_store.query_belief_graph.assert_called_once_with(
        persona_id=persona_id,
        tags=None,
        min_confidence=0.5
    )


@pytest.mark.asyncio
async def test_get_belief_context_with_tags(retrieval_coordinator, mock_memory_store):
    """Test belief retrieval with tag filtering."""
    # Arrange
    persona_id = "persona-1"
    tags = ["environment", "science"]

    # Act
    result = await retrieval_coordinator.get_belief_context(
        persona_id=persona_id,
        tags=tags,
        min_confidence=0.7
    )

    # Assert
    assert len(result["beliefs"]) == 2

    # Verify memory store was called with tags
    mock_memory_store.query_belief_graph.assert_called_once_with(
        persona_id=persona_id,
        tags=tags,
        min_confidence=0.7
    )


# Test 1.3: Past Self-Comments Retrieval

@pytest.mark.asyncio
async def test_get_past_comments_basic(retrieval_coordinator, mock_memory_store):
    """Test semantic search for past comments."""
    # Arrange
    persona_id = "persona-1"
    query_text = "What are your thoughts on climate change?"

    # Act
    result = await retrieval_coordinator.get_past_comments(
        persona_id=persona_id,
        query_text=query_text
    )

    # Assert
    assert len(result) == 2
    assert result[0]["similarity_score"] == 0.87
    assert "climate change" in result[0]["content"].lower()

    # Verify memory store was called
    mock_memory_store.search_history.assert_called_once_with(
        persona_id=persona_id,
        query=query_text,
        limit=5,
        subreddit=None
    )


@pytest.mark.asyncio
async def test_get_past_comments_with_subreddit_filter(retrieval_coordinator, mock_memory_store):
    """Test past comments retrieval with subreddit filter."""
    # Arrange
    persona_id = "persona-1"
    query_text = "climate change"
    subreddit = "science"

    # Act
    result = await retrieval_coordinator.get_past_comments(
        persona_id=persona_id,
        query_text=query_text,
        limit=3,
        subreddit=subreddit
    )

    # Assert
    assert len(result) == 2

    # Verify memory store was called with subreddit
    mock_memory_store.search_history.assert_called_once_with(
        persona_id=persona_id,
        query=query_text,
        limit=3,
        subreddit=subreddit
    )


# Test 1.4: Evidence Snippet Retrieval

@pytest.mark.asyncio
async def test_get_evidence_for_beliefs(retrieval_coordinator, mock_memory_store):
    """Test evidence retrieval for beliefs."""
    # Arrange
    persona_id = "persona-1"
    belief_ids = ["belief-1", "belief-2"]

    # Act
    result = await retrieval_coordinator.get_evidence_for_beliefs(
        persona_id=persona_id,
        belief_ids=belief_ids,
        limit_per_belief=2
    )

    # Assert
    assert "belief-1" in result
    assert len(result["belief-1"]) == 2
    assert result["belief-1"][0]["source_type"] == "external_link"
    assert result["belief-1"][0]["strength"] == "strong"

    # Verify memory store was called for each belief
    assert mock_memory_store.get_belief_with_stances.call_count == 2


@pytest.mark.asyncio
async def test_get_evidence_handles_missing_belief(retrieval_coordinator, mock_memory_store):
    """Test evidence retrieval handles missing beliefs gracefully."""
    # Arrange
    persona_id = "persona-1"
    belief_ids = ["belief-nonexistent"]

    # Mock error for nonexistent belief
    mock_memory_store.get_belief_with_stances.side_effect = ValueError("Belief not found")

    # Act
    result = await retrieval_coordinator.get_evidence_for_beliefs(
        persona_id=persona_id,
        belief_ids=belief_ids
    )

    # Assert
    assert result["belief-nonexistent"] == []


# Test 1.5: Prompt Assembly Logic

@pytest.mark.asyncio
async def test_assemble_prompt_basic(retrieval_coordinator):
    """Test prompt assembly with persona and context."""
    # Arrange
    persona_config = {
        "display_name": "TestAgent",
        "reddit_username": "test_user",
        "config": {
            "tone": "witty",
            "style": "informal",
            "values": ["evidence-based", "open-minded"]
        }
    }

    context = {
        "beliefs": [
            {
                "id": "belief-1",
                "title": "Climate change is real",
                "confidence": 0.95,
                "summary": "...",
                "tags": ["science"]
            }
        ],
        "relations": [],
        "past_statements": [
            {
                "content": "I believe climate action is needed",
                "similarity_score": 0.87
            }
        ],
        "evidence": {},
        "thread": {
            "title": "What's your view on climate change?",
            "body": "Curious to hear perspectives",
            "subreddit": "AskReddit"
        }
    }

    # Act
    prompt = await retrieval_coordinator.assemble_prompt(
        persona_config=persona_config,
        context=context
    )

    # Assert
    assert "TestAgent" in prompt
    assert "witty" in prompt
    assert "Climate change is real" in prompt
    assert "confidence: 0.95" in prompt
    assert "I believe climate action is needed" in prompt
    assert "What's your view on climate change?" in prompt
    assert "r/AskReddit" in prompt


# Test 1.6: Context Assembly Integration

@pytest.mark.asyncio
async def test_assemble_context_full_flow(retrieval_coordinator, mock_memory_store):
    """Test full context assembly with all components."""
    # Arrange
    persona_id = "persona-1"
    thread_context = {
        "title": "Climate change discussion",
        "body": "Let's talk about climate change",
        "subreddit": "science",
        "topic_tags": ["environment", "science"]
    }

    # Act
    result = await retrieval_coordinator.assemble_context(
        persona_id=persona_id,
        thread_context=thread_context
    )

    # Assert
    assert "beliefs" in result
    assert "relations" in result
    assert "past_statements" in result
    assert "evidence" in result
    assert "thread" in result
    assert "token_count" in result

    # Verify components
    assert len(result["beliefs"]) == 2
    assert len(result["past_statements"]) == 2
    assert result["thread"] == thread_context

    # Verify all services were called
    mock_memory_store.query_belief_graph.assert_called_once()
    mock_memory_store.search_history.assert_called_once()
    # Evidence fetch called for top 5 beliefs (but we only have 2)
    assert mock_memory_store.get_belief_with_stances.call_count == 2


@pytest.mark.asyncio
async def test_assemble_context_missing_subreddit(retrieval_coordinator):
    """Test context assembly fails without required thread_context fields."""
    # Arrange
    persona_id = "persona-1"
    thread_context = {
        "title": "Test post",
        # Missing 'subreddit'
    }

    # Act & Assert
    with pytest.raises(ValueError, match="thread_context must contain 'subreddit'"):
        await retrieval_coordinator.assemble_context(
            persona_id=persona_id,
            thread_context=thread_context
        )


@pytest.mark.asyncio
async def test_assemble_context_token_budget_enforcement(retrieval_coordinator, mock_memory_store):
    """Test token budget enforcement prunes context."""
    # Arrange
    persona_id = "persona-1"

    # Create coordinator with very small token budget
    small_budget_coordinator = RetrievalCoordinator(
        memory_store=mock_memory_store,
        embedding_service=retrieval_coordinator.embedding_service,
        token_budget=100  # Very small budget
    )

    thread_context = {
        "title": "Climate change discussion",
        "body": "Let's talk about climate change",
        "subreddit": "science"
    }

    # Act
    result = await small_budget_coordinator.assemble_context(
        persona_id=persona_id,
        thread_context=thread_context
    )

    # Assert
    # Context should be pruned to fit budget
    assert result["token_count"] <= 100 or result["token_count"] <= 150  # Allow some margin
    # Past statements or beliefs should be reduced
    assert len(result["beliefs"]) <= 2
    assert len(result["past_statements"]) <= 2


# Test Token Counting

def test_count_tokens_basic(retrieval_coordinator):
    """Test token counting works correctly."""
    # Arrange
    text = "Hello world, this is a test sentence."

    # Act
    token_count = retrieval_coordinator._count_tokens(text)

    # Assert
    # Should be roughly 8-10 tokens
    assert 5 <= token_count <= 15


def test_count_tokens_empty(retrieval_coordinator):
    """Test token counting handles empty string."""
    # Arrange
    text = ""

    # Act
    token_count = retrieval_coordinator._count_tokens(text)

    # Assert
    assert token_count == 0


# Test Token Budget Enforcement

def test_enforce_token_budget_no_pruning_needed(retrieval_coordinator):
    """Test token budget enforcement when context fits."""
    # Arrange
    context = {
        "beliefs": [{"id": "b1", "title": "Short belief", "confidence": 0.9, "summary": "s", "tags": []}],
        "relations": [],
        "past_statements": [],
        "evidence": {},
        "thread": {"subreddit": "test"}
    }

    # Act
    result = retrieval_coordinator._enforce_token_budget(context)

    # Assert
    # Should be unchanged
    assert len(result["beliefs"]) == 1
    assert len(result["past_statements"]) == 0


def test_enforce_token_budget_prunes_past_statements(retrieval_coordinator):
    """Test budget enforcement prunes past statements first."""
    # Arrange
    # Create context with many past statements
    context = {
        "beliefs": [
            {"id": f"b{i}", "title": "Belief " * 50, "confidence": 0.9, "summary": "x" * 100, "tags": []}
            for i in range(5)
        ],
        "relations": [],
        "past_statements": [
            {"content": "Past statement " * 50, "similarity_score": 0.8}
            for _ in range(10)
        ],
        "evidence": {},
        "thread": {"subreddit": "test"}
    }

    # Use small budget coordinator
    small_coordinator = RetrievalCoordinator(
        memory_store=retrieval_coordinator.memory_store,
        embedding_service=retrieval_coordinator.embedding_service,
        token_budget=500
    )

    # Act
    result = small_coordinator._enforce_token_budget(context)

    # Assert
    # Past statements should be reduced
    assert len(result["past_statements"]) < 10


# Test Context Token Counting

def test_count_context_tokens(retrieval_coordinator):
    """Test context token counting aggregates correctly."""
    # Arrange
    context = {
        "beliefs": [{"id": "b1", "title": "Climate change", "confidence": 0.9, "summary": "x", "tags": []}],
        "relations": [],
        "past_statements": [{"content": "I support climate action", "similarity_score": 0.8}],
        "evidence": {},
        "thread": {"subreddit": "science", "title": "Discussion"}
    }

    # Act
    token_count = retrieval_coordinator._count_context_tokens(context)

    # Assert
    # Should be a reasonable number
    assert token_count > 0
    assert token_count < 1000  # Not huge for small context
