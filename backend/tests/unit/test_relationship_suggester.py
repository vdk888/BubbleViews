"""
Unit tests for RelationshipSuggester service.

Tests LLM-powered relationship suggestion logic including:
- Suggest relationships with various belief combinations
- Validation (persona, relations, weights)
- Max suggestions limit
- LLM response parsing

Follows AAA (Arrange, Act, Assert) test structure.
"""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock

from app.services.relationship_suggester import (
    suggest_relationships,
    _build_system_prompt,
    _build_context,
    _build_user_message,
    _parse_llm_response,
    _extract_json_array,
    _validate_suggestion,
    VALID_RELATIONS,
)
from app.schemas.beliefs import RelationshipSuggestion


# Mock LLM Client for testing
class MockLLMClient:
    """Mock LLM client for testing relationship suggester."""

    def __init__(self):
        self.generate_response = AsyncMock()

    def set_response(self, text: str, tokens: int = 100, cost: float = 0.001):
        """Configure mock response."""
        self.generate_response.return_value = {
            "text": text,
            "model": "anthropic/claude-4.5-haiku",
            "tokens_in": tokens // 2,
            "tokens_out": tokens // 2,
            "total_tokens": tokens,
            "cost": cost,
            "tool_calls": [],
            "finish_reason": "stop"
        }


class TestSuggestRelationships:
    """Test suite for suggest_relationships function."""

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_existing_beliefs(self):
        """Test that empty list is returned when no existing beliefs."""
        # Arrange
        mock_client = MockLLMClient()
        persona_id = "persona-123"
        belief_title = "New belief"
        belief_summary = "New belief summary"
        existing_beliefs = []  # No existing beliefs

        # Act
        suggestions = await suggest_relationships(
            persona_id=persona_id,
            belief_title=belief_title,
            belief_summary=belief_summary,
            existing_beliefs=existing_beliefs,
            llm_client=mock_client
        )

        # Assert
        assert suggestions == []
        mock_client.generate_response.assert_not_called()

    @pytest.mark.asyncio
    async def test_suggests_relationships_with_valid_llm_response(self):
        """Test successful relationship suggestion with valid LLM response."""
        # Arrange
        mock_client = MockLLMClient()
        persona_id = "persona-123"
        belief_title = "Climate change requires action"
        belief_summary = "We should take immediate action to combat climate change."

        existing_beliefs = [
            {
                "id": "belief-001",
                "title": "Evidence-based reasoning",
                "summary": "Decisions should be based on scientific evidence.",
                "confidence": 0.9
            },
            {
                "id": "belief-002",
                "title": "Technology solves problems",
                "summary": "Technological innovation can solve major challenges.",
                "confidence": 0.7
            }
        ]

        # Mock LLM response with valid JSON
        llm_response = json.dumps([
            {
                "target_belief_id": "belief-001",
                "target_belief_title": "Evidence-based reasoning",
                "relation": "depends_on",
                "weight": 0.8,
                "reasoning": "Climate action should be based on scientific evidence."
            },
            {
                "target_belief_id": "belief-002",
                "target_belief_title": "Technology solves problems",
                "relation": "supports",
                "weight": 0.6,
                "reasoning": "Climate solutions often rely on technological innovation."
            }
        ])
        mock_client.set_response(llm_response)

        # Act
        suggestions = await suggest_relationships(
            persona_id=persona_id,
            belief_title=belief_title,
            belief_summary=belief_summary,
            existing_beliefs=existing_beliefs,
            llm_client=mock_client
        )

        # Assert
        assert len(suggestions) == 2
        assert suggestions[0].target_belief_id == "belief-001"
        assert suggestions[0].relation == "depends_on"
        assert suggestions[0].weight == 0.8
        assert suggestions[1].target_belief_id == "belief-002"
        assert suggestions[1].relation == "supports"

        mock_client.generate_response.assert_called_once()

    @pytest.mark.asyncio
    async def test_respects_max_suggestions_limit(self):
        """Test that max_suggestions limit is respected."""
        # Arrange
        mock_client = MockLLMClient()
        persona_id = "persona-123"

        existing_beliefs = [
            {"id": f"belief-{i}", "title": f"Belief {i}", "summary": f"Summary {i}", "confidence": 0.5}
            for i in range(10)
        ]

        # Mock LLM response with more suggestions than limit
        llm_response = json.dumps([
            {
                "target_belief_id": f"belief-{i}",
                "target_belief_title": f"Belief {i}",
                "relation": "supports",
                "weight": 0.5,
                "reasoning": f"Related to belief {i}"
            }
            for i in range(10)  # 10 suggestions
        ])
        mock_client.set_response(llm_response)

        # Act
        suggestions = await suggest_relationships(
            persona_id=persona_id,
            belief_title="New belief",
            belief_summary="New belief summary",
            existing_beliefs=existing_beliefs,
            llm_client=mock_client,
            max_suggestions=3  # Limit to 3
        )

        # Assert
        assert len(suggestions) <= 3

    @pytest.mark.asyncio
    async def test_filters_invalid_belief_ids(self):
        """Test that suggestions with invalid belief IDs are filtered out."""
        # Arrange
        mock_client = MockLLMClient()
        persona_id = "persona-123"

        existing_beliefs = [
            {"id": "belief-valid", "title": "Valid Belief", "summary": "Summary", "confidence": 0.5}
        ]

        # Mock LLM response with invalid belief ID
        llm_response = json.dumps([
            {
                "target_belief_id": "belief-invalid",  # Does not exist
                "target_belief_title": "Invalid Belief",
                "relation": "supports",
                "weight": 0.5,
                "reasoning": "Invalid reference"
            },
            {
                "target_belief_id": "belief-valid",  # Valid
                "target_belief_title": "Valid Belief",
                "relation": "supports",
                "weight": 0.7,
                "reasoning": "Valid reference"
            }
        ])
        mock_client.set_response(llm_response)

        # Act
        suggestions = await suggest_relationships(
            persona_id=persona_id,
            belief_title="New belief",
            belief_summary="Summary",
            existing_beliefs=existing_beliefs,
            llm_client=mock_client
        )

        # Assert
        assert len(suggestions) == 1
        assert suggestions[0].target_belief_id == "belief-valid"

    @pytest.mark.asyncio
    async def test_filters_invalid_relations(self):
        """Test that suggestions with invalid relation types are filtered out."""
        # Arrange
        mock_client = MockLLMClient()
        persona_id = "persona-123"

        existing_beliefs = [
            {"id": "belief-001", "title": "Belief 1", "summary": "Summary", "confidence": 0.5},
            {"id": "belief-002", "title": "Belief 2", "summary": "Summary", "confidence": 0.5}
        ]

        # Mock LLM response with invalid relation
        llm_response = json.dumps([
            {
                "target_belief_id": "belief-001",
                "target_belief_title": "Belief 1",
                "relation": "invalid_relation",  # Invalid
                "weight": 0.5,
                "reasoning": "Invalid relation type"
            },
            {
                "target_belief_id": "belief-002",
                "target_belief_title": "Belief 2",
                "relation": "supports",  # Valid
                "weight": 0.7,
                "reasoning": "Valid relation"
            }
        ])
        mock_client.set_response(llm_response)

        # Act
        suggestions = await suggest_relationships(
            persona_id=persona_id,
            belief_title="New belief",
            belief_summary="Summary",
            existing_beliefs=existing_beliefs,
            llm_client=mock_client
        )

        # Assert
        assert len(suggestions) == 1
        assert suggestions[0].target_belief_id == "belief-002"
        assert suggestions[0].relation == "supports"

    @pytest.mark.asyncio
    async def test_clamps_invalid_weights(self):
        """Test that out-of-range weights are clamped to valid range."""
        # Arrange
        mock_client = MockLLMClient()
        persona_id = "persona-123"

        existing_beliefs = [
            {"id": "belief-001", "title": "Belief 1", "summary": "Summary", "confidence": 0.5},
            {"id": "belief-002", "title": "Belief 2", "summary": "Summary", "confidence": 0.5}
        ]

        # Mock LLM response with out-of-range weights
        llm_response = json.dumps([
            {
                "target_belief_id": "belief-001",
                "target_belief_title": "Belief 1",
                "relation": "supports",
                "weight": 1.5,  # Too high
                "reasoning": "Weight too high"
            },
            {
                "target_belief_id": "belief-002",
                "target_belief_title": "Belief 2",
                "relation": "contradicts",
                "weight": -0.5,  # Too low
                "reasoning": "Weight too low"
            }
        ])
        mock_client.set_response(llm_response)

        # Act
        suggestions = await suggest_relationships(
            persona_id=persona_id,
            belief_title="New belief",
            belief_summary="Summary",
            existing_beliefs=existing_beliefs,
            llm_client=mock_client
        )

        # Assert
        assert len(suggestions) == 2
        assert 0.0 <= suggestions[0].weight <= 1.0
        assert 0.0 <= suggestions[1].weight <= 1.0

    @pytest.mark.asyncio
    async def test_handles_llm_failure_gracefully(self):
        """Test that LLM failure returns empty list instead of raising."""
        # Arrange
        mock_client = MockLLMClient()
        mock_client.generate_response.side_effect = Exception("LLM API error")

        existing_beliefs = [
            {"id": "belief-001", "title": "Belief 1", "summary": "Summary", "confidence": 0.5}
        ]

        # Act
        suggestions = await suggest_relationships(
            persona_id="persona-123",
            belief_title="New belief",
            belief_summary="Summary",
            existing_beliefs=existing_beliefs,
            llm_client=mock_client
        )

        # Assert
        assert suggestions == []

    @pytest.mark.asyncio
    async def test_handles_malformed_json_response(self):
        """Test that malformed JSON response returns empty list."""
        # Arrange
        mock_client = MockLLMClient()
        mock_client.set_response("This is not valid JSON at all")

        existing_beliefs = [
            {"id": "belief-001", "title": "Belief 1", "summary": "Summary", "confidence": 0.5}
        ]

        # Act
        suggestions = await suggest_relationships(
            persona_id="persona-123",
            belief_title="New belief",
            belief_summary="Summary",
            existing_beliefs=existing_beliefs,
            llm_client=mock_client
        )

        # Assert
        assert suggestions == []

    @pytest.mark.asyncio
    async def test_handles_empty_json_array(self):
        """Test that empty JSON array returns empty list."""
        # Arrange
        mock_client = MockLLMClient()
        mock_client.set_response("[]")

        existing_beliefs = [
            {"id": "belief-001", "title": "Belief 1", "summary": "Summary", "confidence": 0.5}
        ]

        # Act
        suggestions = await suggest_relationships(
            persona_id="persona-123",
            belief_title="New belief",
            belief_summary="Summary",
            existing_beliefs=existing_beliefs,
            llm_client=mock_client
        )

        # Assert
        assert suggestions == []


class TestExtractJsonArray:
    """Test suite for JSON extraction from LLM responses."""

    def test_extracts_plain_json_array(self):
        """Test extraction of plain JSON array."""
        # Arrange
        text = '[{"key": "value"}]'

        # Act
        result = _extract_json_array(text)

        # Assert
        assert result == [{"key": "value"}]

    def test_extracts_json_from_markdown_code_block(self):
        """Test extraction of JSON from markdown code block."""
        # Arrange
        text = '''Here are the suggestions:

```json
[
  {"target_belief_id": "abc", "relation": "supports", "weight": 0.5, "reasoning": "test"}
]
```

That's my analysis.'''

        # Act
        result = _extract_json_array(text)

        # Assert
        assert result is not None
        assert len(result) == 1
        assert result[0]["target_belief_id"] == "abc"

    def test_extracts_json_from_plain_code_block(self):
        """Test extraction of JSON from plain code block (no json marker)."""
        # Arrange
        text = '''```
[{"id": "123"}]
```'''

        # Act
        result = _extract_json_array(text)

        # Assert
        assert result == [{"id": "123"}]

    def test_returns_none_for_invalid_json(self):
        """Test that None is returned for invalid JSON."""
        # Arrange
        text = "This is just plain text with no JSON"

        # Act
        result = _extract_json_array(text)

        # Assert
        assert result is None

    def test_returns_none_for_json_object_not_array(self):
        """Test that None is returned when JSON is object, not array."""
        # Arrange
        text = '{"not": "an array"}'

        # Act
        result = _extract_json_array(text)

        # Assert
        assert result is None


class TestValidateSuggestion:
    """Test suite for individual suggestion validation."""

    def test_validates_valid_suggestion(self):
        """Test validation of a valid suggestion."""
        # Arrange
        item = {
            "target_belief_id": "belief-001",
            "target_belief_title": "Belief Title",
            "relation": "supports",
            "weight": 0.7,
            "reasoning": "Good connection"
        }
        valid_belief_ids = {"belief-001", "belief-002"}
        belief_id_to_title = {"belief-001": "Actual Title"}

        # Act
        result = _validate_suggestion(
            item=item,
            valid_belief_ids=valid_belief_ids,
            belief_id_to_title=belief_id_to_title,
            correlation_id="test-123"
        )

        # Assert
        assert result is not None
        assert isinstance(result, RelationshipSuggestion)
        assert result.target_belief_id == "belief-001"
        assert result.target_belief_title == "Actual Title"  # Uses our data, not LLM's
        assert result.relation == "supports"
        assert result.weight == 0.7
        assert result.reasoning == "Good connection"

    def test_rejects_invalid_belief_id(self):
        """Test that suggestion with invalid belief ID is rejected."""
        # Arrange
        item = {
            "target_belief_id": "nonexistent-belief",
            "target_belief_title": "Title",
            "relation": "supports",
            "weight": 0.5,
            "reasoning": "Test"
        }
        valid_belief_ids = {"belief-001"}
        belief_id_to_title = {"belief-001": "Title"}

        # Act
        result = _validate_suggestion(
            item=item,
            valid_belief_ids=valid_belief_ids,
            belief_id_to_title=belief_id_to_title,
            correlation_id="test-123"
        )

        # Assert
        assert result is None

    def test_rejects_invalid_relation(self):
        """Test that suggestion with invalid relation is rejected."""
        # Arrange
        item = {
            "target_belief_id": "belief-001",
            "target_belief_title": "Title",
            "relation": "invalid_relation",
            "weight": 0.5,
            "reasoning": "Test"
        }
        valid_belief_ids = {"belief-001"}
        belief_id_to_title = {"belief-001": "Title"}

        # Act
        result = _validate_suggestion(
            item=item,
            valid_belief_ids=valid_belief_ids,
            belief_id_to_title=belief_id_to_title,
            correlation_id="test-123"
        )

        # Assert
        assert result is None

    def test_all_valid_relations_accepted(self):
        """Test that all valid relation types are accepted."""
        # Arrange
        valid_belief_ids = {"belief-001"}
        belief_id_to_title = {"belief-001": "Title"}

        for relation in VALID_RELATIONS:
            item = {
                "target_belief_id": "belief-001",
                "target_belief_title": "Title",
                "relation": relation,
                "weight": 0.5,
                "reasoning": f"Testing {relation}"
            }

            # Act
            result = _validate_suggestion(
                item=item,
                valid_belief_ids=valid_belief_ids,
                belief_id_to_title=belief_id_to_title,
                correlation_id="test-123"
            )

            # Assert
            assert result is not None, f"Relation '{relation}' should be valid"
            assert result.relation == relation

    def test_clamps_high_weight(self):
        """Test that weight > 1.0 is clamped to 1.0."""
        # Arrange
        item = {
            "target_belief_id": "belief-001",
            "target_belief_title": "Title",
            "relation": "supports",
            "weight": 1.5,  # Too high
            "reasoning": "Test"
        }
        valid_belief_ids = {"belief-001"}
        belief_id_to_title = {"belief-001": "Title"}

        # Act
        result = _validate_suggestion(
            item=item,
            valid_belief_ids=valid_belief_ids,
            belief_id_to_title=belief_id_to_title,
            correlation_id="test-123"
        )

        # Assert
        assert result is not None
        assert result.weight == 1.0

    def test_clamps_low_weight(self):
        """Test that weight < 0.0 is clamped to 0.0."""
        # Arrange
        item = {
            "target_belief_id": "belief-001",
            "target_belief_title": "Title",
            "relation": "supports",
            "weight": -0.5,  # Too low
            "reasoning": "Test"
        }
        valid_belief_ids = {"belief-001"}
        belief_id_to_title = {"belief-001": "Title"}

        # Act
        result = _validate_suggestion(
            item=item,
            valid_belief_ids=valid_belief_ids,
            belief_id_to_title=belief_id_to_title,
            correlation_id="test-123"
        )

        # Assert
        assert result is not None
        assert result.weight == 0.0

    def test_default_weight_for_invalid_value(self):
        """Test that invalid weight value uses default 0.5."""
        # Arrange
        item = {
            "target_belief_id": "belief-001",
            "target_belief_title": "Title",
            "relation": "supports",
            "weight": "not a number",  # Invalid
            "reasoning": "Test"
        }
        valid_belief_ids = {"belief-001"}
        belief_id_to_title = {"belief-001": "Title"}

        # Act
        result = _validate_suggestion(
            item=item,
            valid_belief_ids=valid_belief_ids,
            belief_id_to_title=belief_id_to_title,
            correlation_id="test-123"
        )

        # Assert
        assert result is not None
        assert result.weight == 0.5


class TestBuildPromptFunctions:
    """Test suite for prompt building functions."""

    def test_build_system_prompt_contains_relations(self):
        """Test that system prompt mentions all relation types."""
        # Act
        prompt = _build_system_prompt()

        # Assert
        assert "supports" in prompt
        assert "contradicts" in prompt
        assert "depends_on" in prompt
        assert "evidence_for" in prompt

    def test_build_context_includes_new_belief(self):
        """Test that context includes new belief info."""
        # Arrange
        title = "Test Belief"
        summary = "Test Summary"
        existing_beliefs = []

        # Act
        context = _build_context(title, summary, existing_beliefs)

        # Assert
        assert context["new_belief"]["title"] == title
        assert context["new_belief"]["summary"] == summary

    def test_build_context_includes_existing_beliefs(self):
        """Test that context includes existing beliefs."""
        # Arrange
        existing_beliefs = [
            {"id": "b1", "title": "Belief 1", "summary": "Summary 1", "confidence": 0.8},
            {"id": "b2", "title": "Belief 2", "summary": "Summary 2", "confidence": 0.6}
        ]

        # Act
        context = _build_context("New", "New Summary", existing_beliefs)

        # Assert
        assert len(context["existing_beliefs"]) == 2
        assert context["existing_beliefs"][0]["id"] == "b1"
        assert context["existing_beliefs"][1]["id"] == "b2"

    def test_build_user_message_includes_max_suggestions(self):
        """Test that user message includes max_suggestions limit."""
        # Act
        message = _build_user_message("Test Belief", max_suggestions=3)

        # Assert
        assert "3" in message
        assert "up to 3 relationships" in message.lower() or "suggest up to 3" in message.lower()
