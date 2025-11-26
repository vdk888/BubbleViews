"""
Tests for automatic relationship creation when beliefs are approved.

Tests the auto-linking feature that creates BeliefEdge records when new beliefs
are created through moderation approval. Uses AAA (Arrange, Act, Assert) style.

Key test scenarios:
- Auto-relationship creation on approval
- Threshold filtering (only creates edges above weight threshold)
- Graceful handling when suggester fails
- No relationships created when no existing beliefs
- Disabled auto-linking via configuration
"""

import asyncio
import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from typing import List, Dict, Any

# Add backend to path for imports
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))


class MockRelationshipSuggestion:
    """Mock RelationshipSuggestion for testing."""
    def __init__(
        self,
        target_belief_id: str,
        target_belief_title: str,
        relation: str,
        weight: float,
        reasoning: str
    ):
        self.target_belief_id = target_belief_id
        self.target_belief_title = target_belief_title
        self.relation = relation
        self.weight = weight
        self.reasoning = reasoning


async def test_auto_relationship_creation_success():
    """
    Test that relationships are created when a new belief is approved.

    Arrange: Mock LLM client to return suggestions above threshold
    Act: Call _auto_create_relationships with valid parameters
    Assert: BeliefEdge records are created for suggestions above threshold
    """
    print("\n" + "="*70)
    print("TEST: Auto-Relationship Creation Success")
    print("="*70)

    try:
        # Arrange
        from app.api.v1.moderation import _auto_create_relationships

        persona_id = str(uuid.uuid4())
        new_belief_id = str(uuid.uuid4())
        existing_belief_1_id = str(uuid.uuid4())
        existing_belief_2_id = str(uuid.uuid4())

        # Mock existing beliefs
        mock_existing_beliefs = [
            MagicMock(
                id=existing_belief_1_id,
                title="Climate Change is Real",
                summary="Scientific evidence supports climate change",
                current_confidence=0.9,
                updated_at=MagicMock()
            ),
            MagicMock(
                id=existing_belief_2_id,
                title="Renewable Energy is Important",
                summary="We should invest in renewable energy",
                current_confidence=0.8,
                updated_at=MagicMock()
            ),
        ]

        # Mock suggestions from LLM
        mock_suggestions = [
            MockRelationshipSuggestion(
                target_belief_id=existing_belief_1_id,
                target_belief_title="Climate Change is Real",
                relation="supports",
                weight=0.75,
                reasoning="Both beliefs support environmental science"
            ),
            MockRelationshipSuggestion(
                target_belief_id=existing_belief_2_id,
                target_belief_title="Renewable Energy is Important",
                relation="depends_on",
                weight=0.6,
                reasoning="Belief about energy depends on climate understanding"
            ),
        ]

        # Mock database session
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_existing_beliefs
        mock_session.execute.return_value = mock_result

        mock_session_context = AsyncMock()
        mock_session_context.__aenter__.return_value = mock_session
        mock_session_context.__aexit__.return_value = None

        mock_begin = AsyncMock()
        mock_begin.__aenter__.return_value = None
        mock_begin.__aexit__.return_value = None
        mock_session.begin.return_value = mock_begin

        # Patch dependencies
        with patch('app.api.v1.moderation.async_session_maker') as mock_session_maker, \
             patch('app.api.v1.moderation.OpenRouterClient') as mock_llm_class, \
             patch('app.api.v1.moderation.suggest_relationships') as mock_suggest, \
             patch('app.api.v1.moderation.settings') as mock_settings:

            mock_session_maker.return_value = mock_session_context
            mock_llm_class.return_value = MagicMock()
            mock_suggest.return_value = mock_suggestions
            mock_settings.auto_link_beliefs = True
            mock_settings.auto_link_min_weight = 0.5

            # Act
            result = await _auto_create_relationships(
                persona_id=persona_id,
                new_belief_id=new_belief_id,
                belief_title="Carbon Emissions Need Reduction",
                belief_summary="We should reduce carbon emissions to combat climate change",
                correlation_id="test-correlation-123"
            )

            # Assert
            assert result["edges_created"] == 2, f"Expected 2 edges created, got {result['edges_created']}"
            assert result["suggestions_count"] == 2, f"Expected 2 suggestions, got {result['suggestions_count']}"
            assert len(result["errors"]) == 0, f"Expected no errors, got {result['errors']}"

            # Verify suggest_relationships was called correctly
            mock_suggest.assert_called_once()
            call_args = mock_suggest.call_args
            assert call_args.kwargs["persona_id"] == persona_id
            assert call_args.kwargs["belief_title"] == "Carbon Emissions Need Reduction"

            print(f"[OK] Created {result['edges_created']} edges")
            print(f"[OK] Received {result['suggestions_count']} suggestions")
            print(f"[OK] No errors occurred")
            print("\n[PASSED] Auto-relationship creation success test")
            return True

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_threshold_filtering():
    """
    Test that only suggestions above weight threshold create edges.

    Arrange: Mock LLM to return suggestions with varying weights
    Act: Call _auto_create_relationships with threshold of 0.5
    Assert: Only edges with weight >= 0.5 are created
    """
    print("\n" + "="*70)
    print("TEST: Threshold Filtering")
    print("="*70)

    try:
        from app.api.v1.moderation import _auto_create_relationships

        # Arrange
        persona_id = str(uuid.uuid4())
        new_belief_id = str(uuid.uuid4())

        # Mock existing beliefs
        mock_existing_beliefs = [
            MagicMock(
                id=str(uuid.uuid4()),
                title=f"Existing Belief {i}",
                summary=f"Summary {i}",
                current_confidence=0.7,
                updated_at=MagicMock()
            )
            for i in range(3)
        ]

        # Mock suggestions with varying weights
        mock_suggestions = [
            MockRelationshipSuggestion(
                target_belief_id=mock_existing_beliefs[0].id,
                target_belief_title="Existing Belief 0",
                relation="supports",
                weight=0.8,  # Above threshold
                reasoning="Strong relationship"
            ),
            MockRelationshipSuggestion(
                target_belief_id=mock_existing_beliefs[1].id,
                target_belief_title="Existing Belief 1",
                relation="contradicts",
                weight=0.3,  # Below threshold
                reasoning="Weak relationship"
            ),
            MockRelationshipSuggestion(
                target_belief_id=mock_existing_beliefs[2].id,
                target_belief_title="Existing Belief 2",
                relation="depends_on",
                weight=0.5,  # Equal to threshold
                reasoning="Moderate relationship"
            ),
        ]

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_existing_beliefs
        mock_session.execute.return_value = mock_result

        mock_session_context = AsyncMock()
        mock_session_context.__aenter__.return_value = mock_session
        mock_session_context.__aexit__.return_value = None

        mock_begin = AsyncMock()
        mock_begin.__aenter__.return_value = None
        mock_begin.__aexit__.return_value = None
        mock_session.begin.return_value = mock_begin

        with patch('app.api.v1.moderation.async_session_maker') as mock_session_maker, \
             patch('app.api.v1.moderation.OpenRouterClient') as mock_llm_class, \
             patch('app.api.v1.moderation.suggest_relationships') as mock_suggest, \
             patch('app.api.v1.moderation.settings') as mock_settings:

            mock_session_maker.return_value = mock_session_context
            mock_llm_class.return_value = MagicMock()
            mock_suggest.return_value = mock_suggestions
            mock_settings.auto_link_beliefs = True
            mock_settings.auto_link_min_weight = 0.5  # Threshold

            # Act
            result = await _auto_create_relationships(
                persona_id=persona_id,
                new_belief_id=new_belief_id,
                belief_title="Test Belief",
                belief_summary="Test summary",
            )

            # Assert - Only 2 edges should be created (weight >= 0.5)
            assert result["edges_created"] == 2, f"Expected 2 edges (0.8 and 0.5), got {result['edges_created']}"
            assert result["suggestions_count"] == 3, f"Expected 3 suggestions, got {result['suggestions_count']}"

            print(f"[OK] Filtered correctly: 2 of 3 suggestions created as edges")
            print(f"[OK] Weight 0.8: included (>= 0.5)")
            print(f"[OK] Weight 0.3: excluded (< 0.5)")
            print(f"[OK] Weight 0.5: included (= 0.5)")
            print("\n[PASSED] Threshold filtering test")
            return True

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_graceful_handling_on_suggester_failure():
    """
    Test that approval does not fail when relationship suggester fails.

    Arrange: Mock suggest_relationships to raise an exception
    Act: Call _auto_create_relationships
    Assert: Function returns gracefully with error logged but no exception
    """
    print("\n" + "="*70)
    print("TEST: Graceful Handling on Suggester Failure")
    print("="*70)

    try:
        from app.api.v1.moderation import _auto_create_relationships

        # Arrange
        persona_id = str(uuid.uuid4())
        new_belief_id = str(uuid.uuid4())

        mock_existing_beliefs = [
            MagicMock(
                id=str(uuid.uuid4()),
                title="Existing Belief",
                summary="Summary",
                current_confidence=0.7,
                updated_at=MagicMock()
            )
        ]

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_existing_beliefs
        mock_session.execute.return_value = mock_result

        mock_session_context = AsyncMock()
        mock_session_context.__aenter__.return_value = mock_session
        mock_session_context.__aexit__.return_value = None

        with patch('app.api.v1.moderation.async_session_maker') as mock_session_maker, \
             patch('app.api.v1.moderation.OpenRouterClient') as mock_llm_class, \
             patch('app.api.v1.moderation.suggest_relationships') as mock_suggest, \
             patch('app.api.v1.moderation.settings') as mock_settings:

            mock_session_maker.return_value = mock_session_context
            mock_llm_class.return_value = MagicMock()
            # Simulate LLM failure
            mock_suggest.side_effect = Exception("LLM API unavailable")
            mock_settings.auto_link_beliefs = True
            mock_settings.auto_link_min_weight = 0.5

            # Act - should not raise exception
            result = await _auto_create_relationships(
                persona_id=persona_id,
                new_belief_id=new_belief_id,
                belief_title="Test Belief",
                belief_summary="Test summary",
            )

            # Assert
            assert result["edges_created"] == 0, "No edges should be created on failure"
            assert len(result["errors"]) > 0, "Error should be logged"
            assert "Relationship creation" in result["errors"][0]

            print(f"[OK] No edges created: {result['edges_created']}")
            print(f"[OK] Error captured: {result['errors'][0][:50]}...")
            print(f"[OK] Function returned gracefully without raising exception")
            print("\n[PASSED] Graceful handling on suggester failure test")
            return True

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_no_relationships_when_no_existing_beliefs():
    """
    Test that no relationships are created when persona has no existing beliefs.

    Arrange: Mock database to return empty list of existing beliefs
    Act: Call _auto_create_relationships
    Assert: Returns early with 0 edges and no LLM call
    """
    print("\n" + "="*70)
    print("TEST: No Relationships When No Existing Beliefs")
    print("="*70)

    try:
        from app.api.v1.moderation import _auto_create_relationships

        # Arrange
        persona_id = str(uuid.uuid4())
        new_belief_id = str(uuid.uuid4())

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []  # No existing beliefs
        mock_session.execute.return_value = mock_result

        mock_session_context = AsyncMock()
        mock_session_context.__aenter__.return_value = mock_session
        mock_session_context.__aexit__.return_value = None

        with patch('app.api.v1.moderation.async_session_maker') as mock_session_maker, \
             patch('app.api.v1.moderation.OpenRouterClient') as mock_llm_class, \
             patch('app.api.v1.moderation.suggest_relationships') as mock_suggest, \
             patch('app.api.v1.moderation.settings') as mock_settings:

            mock_session_maker.return_value = mock_session_context
            mock_settings.auto_link_beliefs = True
            mock_settings.auto_link_min_weight = 0.5

            # Act
            result = await _auto_create_relationships(
                persona_id=persona_id,
                new_belief_id=new_belief_id,
                belief_title="Test Belief",
                belief_summary="Test summary",
            )

            # Assert
            assert result["edges_created"] == 0
            assert result["suggestions_count"] == 0
            assert len(result["errors"]) == 0

            # LLM should not be called when no existing beliefs
            mock_suggest.assert_not_called()
            mock_llm_class.assert_not_called()

            print(f"[OK] No edges created: {result['edges_created']}")
            print(f"[OK] No suggestions generated: {result['suggestions_count']}")
            print(f"[OK] LLM was not called (as expected)")
            print("\n[PASSED] No relationships when no existing beliefs test")
            return True

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_auto_link_disabled():
    """
    Test that auto-linking is skipped when disabled in settings.

    Arrange: Set auto_link_beliefs to False in settings
    Act: Call _apply_belief_changes with new_belief proposal
    Assert: No relationship creation is attempted
    """
    print("\n" + "="*70)
    print("TEST: Auto-Link Disabled")
    print("="*70)

    try:
        from app.api.v1.moderation import _apply_belief_changes

        # Arrange
        persona_id = str(uuid.uuid4())
        proposals = {
            "new_belief": {
                "title": "Test Belief",
                "summary": "Test summary",
                "initial_confidence": 0.6,
                "tags": ["test"],
                "reason": "Test reason"
            }
        }

        mock_session = AsyncMock()
        mock_session_context = AsyncMock()
        mock_session_context.__aenter__.return_value = mock_session
        mock_session_context.__aexit__.return_value = None

        mock_begin = AsyncMock()
        mock_begin.__aenter__.return_value = None
        mock_begin.__aexit__.return_value = None
        mock_session.begin.return_value = mock_begin

        with patch('app.api.v1.moderation.async_session_maker') as mock_session_maker, \
             patch('app.api.v1.moderation.SQLiteMemoryStore') as mock_memory, \
             patch('app.api.v1.moderation.BeliefUpdater') as mock_updater, \
             patch('app.api.v1.moderation._auto_create_relationships') as mock_auto_create, \
             patch('app.api.v1.moderation.settings') as mock_settings:

            mock_session_maker.return_value = mock_session_context
            mock_settings.auto_link_beliefs = False  # Disabled
            mock_settings.auto_link_min_weight = 0.5

            # Act
            result = await _apply_belief_changes(
                persona_id=persona_id,
                proposals=proposals,
                reviewer="test_admin",
                reddit_id="t1_abc123"
            )

            # Assert
            assert result["new_belief_created"] == True, "Belief should still be created"

            # Auto-create relationships should not be called
            mock_auto_create.assert_not_called()

            print(f"[OK] Belief created: {result['new_belief_created']}")
            print(f"[OK] Auto-create relationships was not called")
            print("\n[PASSED] Auto-link disabled test")
            return True

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_high_threshold_filters_all():
    """
    Test that high threshold filters out all suggestions.

    Arrange: Set min_weight to 0.9, return suggestions with weight < 0.9
    Act: Call _auto_create_relationships
    Assert: No edges created despite having suggestions
    """
    print("\n" + "="*70)
    print("TEST: High Threshold Filters All")
    print("="*70)

    try:
        from app.api.v1.moderation import _auto_create_relationships

        # Arrange
        persona_id = str(uuid.uuid4())
        new_belief_id = str(uuid.uuid4())

        mock_existing_beliefs = [
            MagicMock(
                id=str(uuid.uuid4()),
                title="Existing Belief",
                summary="Summary",
                current_confidence=0.7,
                updated_at=MagicMock()
            )
        ]

        # All suggestions below high threshold
        mock_suggestions = [
            MockRelationshipSuggestion(
                target_belief_id=mock_existing_beliefs[0].id,
                target_belief_title="Existing Belief",
                relation="supports",
                weight=0.7,  # Below 0.9 threshold
                reasoning="Moderate relationship"
            ),
        ]

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_existing_beliefs
        mock_session.execute.return_value = mock_result

        mock_session_context = AsyncMock()
        mock_session_context.__aenter__.return_value = mock_session
        mock_session_context.__aexit__.return_value = None

        with patch('app.api.v1.moderation.async_session_maker') as mock_session_maker, \
             patch('app.api.v1.moderation.OpenRouterClient') as mock_llm_class, \
             patch('app.api.v1.moderation.suggest_relationships') as mock_suggest, \
             patch('app.api.v1.moderation.settings') as mock_settings:

            mock_session_maker.return_value = mock_session_context
            mock_llm_class.return_value = MagicMock()
            mock_suggest.return_value = mock_suggestions
            mock_settings.auto_link_beliefs = True
            mock_settings.auto_link_min_weight = 0.9  # High threshold

            # Act
            result = await _auto_create_relationships(
                persona_id=persona_id,
                new_belief_id=new_belief_id,
                belief_title="Test Belief",
                belief_summary="Test summary",
            )

            # Assert
            assert result["edges_created"] == 0, "No edges should be created (all below threshold)"
            assert result["suggestions_count"] == 1, "Should have received 1 suggestion"

            print(f"[OK] No edges created: {result['edges_created']}")
            print(f"[OK] Suggestions received: {result['suggestions_count']}")
            print(f"[OK] High threshold (0.9) filtered out weight=0.7 suggestion")
            print("\n[PASSED] High threshold filters all test")
            return True

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all tests for auto-relationship creation."""
    print("\n" + "="*70)
    print("AUTO-RELATIONSHIP CREATION TEST SUITE")
    print("="*70)
    print("\nThese tests verify the automatic relationship creation feature")
    print("that links new beliefs to existing beliefs during moderation approval.\n")

    results = []

    # Test 1: Success case
    result1 = await test_auto_relationship_creation_success()
    results.append(("Auto-Relationship Creation Success", result1))

    # Test 2: Threshold filtering
    result2 = await test_threshold_filtering()
    results.append(("Threshold Filtering", result2))

    # Test 3: Graceful handling on failure
    result3 = await test_graceful_handling_on_suggester_failure()
    results.append(("Graceful Handling on Suggester Failure", result3))

    # Test 4: No existing beliefs
    result4 = await test_no_relationships_when_no_existing_beliefs()
    results.append(("No Relationships When No Existing Beliefs", result4))

    # Test 5: Auto-link disabled
    result5 = await test_auto_link_disabled()
    results.append(("Auto-Link Disabled", result5))

    # Test 6: High threshold
    result6 = await test_high_threshold_filters_all()
    results.append(("High Threshold Filters All", result6))

    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "PASSED [OK]" if result else "FAILED [X]"
        print(f"{test_name}: {status}")

    print("-" * 70)
    print(f"Results: {passed}/{total} tests passed")

    if passed == total:
        print("\nAll tests passed!")
        print("Auto-relationship creation feature is working correctly.")
        return 0
    else:
        print(f"\n{total - passed} test(s) failed. Check the errors above.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
