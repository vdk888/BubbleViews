"""
Unit tests for BeliefUpdater service.

Tests Bayesian belief updating logic including:
- Evidence-based confidence calculations
- Locked stance enforcement
- Conflict resolution policies
- Stance versioning
- Audit logging

Follows AAA (Arrange, Act, Assert) test structure.
"""

import pytest
import math
from unittest.mock import AsyncMock, MagicMock

from app.services.belief_updater import (
    BeliefUpdater,
    EvidenceStrength,
    EVIDENCE_DELTA,
    HIGH_CONFIDENCE_THRESHOLD,
    MODERATE_CONFIDENCE_THRESHOLD,
)


# Mock IMemoryStore for testing
class MockMemoryStore:
    """Mock memory store for testing belief updater."""

    def __init__(self):
        self.get_belief_with_stances = AsyncMock()
        self.update_stance_version = AsyncMock()


class TestCalculateNewConfidence:
    """Test suite for Bayesian confidence calculation."""

    def test_weak_evidence_increase(self):
        """Test weak evidence increases confidence moderately."""
        # Arrange
        updater = BeliefUpdater(MockMemoryStore())
        current = 0.6

        # Act
        new_conf = updater.calculate_new_confidence(
            current_confidence=current,
            evidence_strength=EvidenceStrength.WEAK,
            direction="increase"
        )

        # Assert
        assert new_conf > current
        assert new_conf < current + 0.1  # Small increase
        assert 0 < new_conf < 1

    def test_moderate_evidence_increase(self):
        """Test moderate evidence increases confidence notably."""
        # Arrange
        updater = BeliefUpdater(MockMemoryStore())
        current = 0.6

        # Act
        new_conf = updater.calculate_new_confidence(
            current_confidence=current,
            evidence_strength=EvidenceStrength.MODERATE,
            direction="increase"
        )

        # Assert
        assert new_conf > current
        assert new_conf - current > 0.05  # Notable increase
        assert 0 < new_conf < 1

    def test_strong_evidence_increase(self):
        """Test strong evidence increases confidence significantly."""
        # Arrange
        updater = BeliefUpdater(MockMemoryStore())
        current = 0.6

        # Act
        new_conf = updater.calculate_new_confidence(
            current_confidence=current,
            evidence_strength=EvidenceStrength.STRONG,
            direction="increase"
        )

        # Assert
        assert new_conf > current
        assert new_conf - current > 0.10  # Significant increase
        assert 0 < new_conf < 1

    def test_weak_evidence_decrease(self):
        """Test weak counter-evidence decreases confidence moderately."""
        # Arrange
        updater = BeliefUpdater(MockMemoryStore())
        current = 0.6

        # Act
        new_conf = updater.calculate_new_confidence(
            current_confidence=current,
            evidence_strength=EvidenceStrength.WEAK,
            direction="decrease"
        )

        # Assert
        assert new_conf < current
        assert current - new_conf < 0.1  # Small decrease
        assert 0 < new_conf < 1

    def test_strong_evidence_decrease(self):
        """Test strong counter-evidence decreases confidence significantly."""
        # Arrange
        updater = BeliefUpdater(MockMemoryStore())
        current = 0.8

        # Act
        new_conf = updater.calculate_new_confidence(
            current_confidence=current,
            evidence_strength=EvidenceStrength.STRONG,
            direction="decrease"
        )

        # Assert
        assert new_conf < current
        assert current - new_conf > 0.10  # Significant decrease
        assert 0 < new_conf < 1

    def test_confidence_clamped_to_valid_range(self):
        """Test confidence is clamped to [0.01, 0.99] to avoid extremes."""
        # Arrange
        updater = BeliefUpdater(MockMemoryStore())

        # Act - Try to push very high confidence even higher
        new_conf_high = updater.calculate_new_confidence(
            current_confidence=0.95,
            evidence_strength=EvidenceStrength.STRONG,
            direction="increase"
        )

        # Try to push very low confidence even lower
        new_conf_low = updater.calculate_new_confidence(
            current_confidence=0.05,
            evidence_strength=EvidenceStrength.STRONG,
            direction="decrease"
        )

        # Assert
        assert new_conf_high <= 0.99
        assert new_conf_low >= 0.01

    def test_logistic_update_symmetry(self):
        """Test that increase and decrease operations are roughly symmetric."""
        # Arrange
        updater = BeliefUpdater(MockMemoryStore())
        current = 0.5

        # Act
        increased = updater.calculate_new_confidence(
            current_confidence=current,
            evidence_strength=EvidenceStrength.MODERATE,
            direction="increase"
        )

        # Apply same strength decrease from increased value
        back_down = updater.calculate_new_confidence(
            current_confidence=increased,
            evidence_strength=EvidenceStrength.MODERATE,
            direction="decrease"
        )

        # Assert - Should be close to original (within 0.05 tolerance)
        assert abs(back_down - current) < 0.05

    def test_invalid_confidence_raises_error(self):
        """Test that out-of-range confidence raises ValueError."""
        # Arrange
        updater = BeliefUpdater(MockMemoryStore())

        # Act & Assert
        with pytest.raises(ValueError, match="must be in"):
            updater.calculate_new_confidence(
                current_confidence=1.5,
                evidence_strength=EvidenceStrength.WEAK,
                direction="increase"
            )

        with pytest.raises(ValueError, match="must be in"):
            updater.calculate_new_confidence(
                current_confidence=-0.1,
                evidence_strength=EvidenceStrength.WEAK,
                direction="decrease"
            )


class TestUpdateFromEvidence:
    """Test suite for evidence-based belief updates."""

    @pytest.mark.asyncio
    async def test_update_increases_confidence(self):
        """Test that supporting evidence increases confidence."""
        # Arrange
        mock_store = MockMemoryStore()
        updater = BeliefUpdater(mock_store)

        persona_id = "persona-123"
        belief_id = "belief-456"

        # Mock belief data
        mock_store.get_belief_with_stances.return_value = {
            "belief": {
                "id": belief_id,
                "title": "Climate change is real",
                "current_confidence": 0.7,
            },
            "stances": [
                {
                    "id": "stance-789",
                    "text": "Climate change is driven by human activity",
                    "confidence": 0.7,
                    "status": "current",
                }
            ],
            "evidence": [],
            "updates": []
        }

        mock_store.update_stance_version.return_value = "new-stance-uuid"

        # Act
        new_confidence = await updater.update_from_evidence(
            persona_id=persona_id,
            belief_id=belief_id,
            evidence_strength=EvidenceStrength.MODERATE,
            reason="New peer-reviewed study confirms hypothesis",
            direction="increase"
        )

        # Assert
        assert new_confidence > 0.7
        mock_store.get_belief_with_stances.assert_called_once_with(
            persona_id=persona_id,
            belief_id=belief_id
        )
        mock_store.update_stance_version.assert_called_once()

        # Check call arguments
        call_args = mock_store.update_stance_version.call_args
        assert call_args.kwargs["persona_id"] == persona_id
        assert call_args.kwargs["belief_id"] == belief_id
        assert call_args.kwargs["confidence"] == new_confidence
        assert "peer-reviewed study" in call_args.kwargs["rationale"]

    @pytest.mark.asyncio
    async def test_update_decreases_confidence(self):
        """Test that counter-evidence decreases confidence."""
        # Arrange
        mock_store = MockMemoryStore()
        updater = BeliefUpdater(mock_store)

        persona_id = "persona-123"
        belief_id = "belief-456"

        mock_store.get_belief_with_stances.return_value = {
            "belief": {
                "id": belief_id,
                "title": "Belief X",
                "current_confidence": 0.8,
            },
            "stances": [
                {
                    "id": "stance-789",
                    "text": "Position on X",
                    "confidence": 0.8,
                    "status": "current",
                }
            ],
            "evidence": [],
            "updates": []
        }

        mock_store.update_stance_version.return_value = "new-stance-uuid"

        # Act
        new_confidence = await updater.update_from_evidence(
            persona_id=persona_id,
            belief_id=belief_id,
            evidence_strength=EvidenceStrength.STRONG,
            reason="Contradictory evidence from multiple sources",
            direction="decrease"
        )

        # Assert
        assert new_confidence < 0.8
        mock_store.update_stance_version.assert_called_once()

    @pytest.mark.asyncio
    async def test_locked_stance_raises_permission_error(self):
        """Test that updating a locked stance raises PermissionError."""
        # Arrange
        mock_store = MockMemoryStore()
        updater = BeliefUpdater(mock_store)

        persona_id = "persona-123"
        belief_id = "belief-456"

        # Mock locked stance
        mock_store.get_belief_with_stances.return_value = {
            "belief": {
                "id": belief_id,
                "title": "Core belief",
                "current_confidence": 0.9,
            },
            "stances": [
                {
                    "id": "stance-789",
                    "text": "This is a locked stance",
                    "confidence": 0.9,
                    "status": "locked",  # Locked status
                }
            ],
            "evidence": [],
            "updates": []
        }

        # Act & Assert
        with pytest.raises(PermissionError, match="locked"):
            await updater.update_from_evidence(
                persona_id=persona_id,
                belief_id=belief_id,
                evidence_strength=EvidenceStrength.STRONG,
                reason="Trying to update locked stance",
                direction="increase"
            )

        # Verify no update was attempted
        mock_store.update_stance_version.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_current_stance_raises_error(self):
        """Test that missing current stance raises ValueError."""
        # Arrange
        mock_store = MockMemoryStore()
        updater = BeliefUpdater(mock_store)

        persona_id = "persona-123"
        belief_id = "belief-456"

        # Mock belief with no current stance
        mock_store.get_belief_with_stances.return_value = {
            "belief": {
                "id": belief_id,
                "title": "Belief",
                "current_confidence": 0.5,
            },
            "stances": [
                {
                    "id": "stance-789",
                    "text": "Old deprecated stance",
                    "confidence": 0.5,
                    "status": "deprecated",
                }
            ],
            "evidence": [],
            "updates": []
        }

        # Act & Assert
        with pytest.raises(ValueError, match="No current or locked stance"):
            await updater.update_from_evidence(
                persona_id=persona_id,
                belief_id=belief_id,
                evidence_strength=EvidenceStrength.WEAK,
                reason="Update attempt",
                direction="increase"
            )

    @pytest.mark.asyncio
    async def test_default_confidence_used_if_none(self):
        """Test that default confidence 0.5 is used if current_confidence is None."""
        # Arrange
        mock_store = MockMemoryStore()
        updater = BeliefUpdater(mock_store)

        persona_id = "persona-123"
        belief_id = "belief-456"

        # Mock belief with None confidence
        mock_store.get_belief_with_stances.return_value = {
            "belief": {
                "id": belief_id,
                "title": "New belief",
                "current_confidence": None,  # No prior confidence
            },
            "stances": [
                {
                    "id": "stance-789",
                    "text": "Initial stance",
                    "confidence": None,
                    "status": "current",
                }
            ],
            "evidence": [],
            "updates": []
        }

        mock_store.update_stance_version.return_value = "new-stance-uuid"

        # Act
        new_confidence = await updater.update_from_evidence(
            persona_id=persona_id,
            belief_id=belief_id,
            evidence_strength=EvidenceStrength.MODERATE,
            reason="First evidence",
            direction="increase"
        )

        # Assert - Should be higher than default 0.5
        assert new_confidence > 0.5
        mock_store.update_stance_version.assert_called_once()


class TestUpdateFromConflict:
    """Test suite for conflict-based belief updates."""

    @pytest.mark.asyncio
    async def test_high_confidence_weak_evidence_rejected(self):
        """Test high-confidence belief rejects weak counter-evidence."""
        # Arrange
        mock_store = MockMemoryStore()
        updater = BeliefUpdater(mock_store)

        persona_id = "persona-123"
        belief_id = "belief-456"

        # Mock high-confidence belief
        mock_store.get_belief_with_stances.return_value = {
            "belief": {
                "id": belief_id,
                "title": "Strong belief",
                "current_confidence": 0.9,  # High confidence
            },
            "stances": [
                {
                    "id": "stance-789",
                    "text": "I am very confident about this",
                    "confidence": 0.9,
                    "status": "current",
                }
            ],
            "evidence": [],
            "updates": []
        }

        conflict_info = {
            "draft_text": "Maybe this isn't true",
            "explanation": "Draft conflicts with high-confidence belief",
            "evidence_strength": "weak",  # Weak evidence
        }

        # Act
        applied = await updater.update_from_conflict(
            persona_id=persona_id,
            belief_id=belief_id,
            conflict_info=conflict_info
        )

        # Assert - Should be rejected
        assert applied is False
        mock_store.update_stance_version.assert_not_called()

    @pytest.mark.asyncio
    async def test_high_confidence_strong_evidence_accepted(self):
        """Test high-confidence belief accepts strong counter-evidence."""
        # Arrange
        mock_store = MockMemoryStore()
        updater = BeliefUpdater(mock_store)

        persona_id = "persona-123"
        belief_id = "belief-456"

        mock_store.get_belief_with_stances.return_value = {
            "belief": {
                "id": belief_id,
                "title": "Strong belief",
                "current_confidence": 0.85,
            },
            "stances": [
                {
                    "id": "stance-789",
                    "text": "High confidence stance",
                    "confidence": 0.85,
                    "status": "current",
                }
            ],
            "evidence": [],
            "updates": []
        }

        mock_store.update_stance_version.return_value = "new-stance-uuid"

        conflict_info = {
            "draft_text": "Robust evidence contradicts this",
            "explanation": "Strong counter-evidence found",
            "evidence_strength": "strong",  # Strong evidence
        }

        # Act
        applied = await updater.update_from_conflict(
            persona_id=persona_id,
            belief_id=belief_id,
            conflict_info=conflict_info
        )

        # Assert - Should be accepted
        assert applied is True
        mock_store.update_stance_version.assert_called_once()

    @pytest.mark.asyncio
    async def test_moderate_confidence_auto_adjustment(self):
        """Test moderate-confidence belief allows automatic adjustment."""
        # Arrange
        mock_store = MockMemoryStore()
        updater = BeliefUpdater(mock_store)

        persona_id = "persona-123"
        belief_id = "belief-456"

        mock_store.get_belief_with_stances.return_value = {
            "belief": {
                "id": belief_id,
                "title": "Moderate belief",
                "current_confidence": 0.65,  # Moderate
            },
            "stances": [
                {
                    "id": "stance-789",
                    "text": "Moderate confidence stance",
                    "confidence": 0.65,
                    "status": "current",
                }
            ],
            "evidence": [],
            "updates": []
        }

        mock_store.update_stance_version.return_value = "new-stance-uuid"

        conflict_info = {
            "draft_text": "Some counter-evidence",
            "explanation": "Moderate conflict",
            "evidence_strength": "moderate",
        }

        # Act
        applied = await updater.update_from_conflict(
            persona_id=persona_id,
            belief_id=belief_id,
            conflict_info=conflict_info
        )

        # Assert
        assert applied is True
        mock_store.update_stance_version.assert_called_once()

    @pytest.mark.asyncio
    async def test_low_confidence_updates_freely(self):
        """Test low-confidence belief updates freely with any evidence."""
        # Arrange
        mock_store = MockMemoryStore()
        updater = BeliefUpdater(mock_store)

        persona_id = "persona-123"
        belief_id = "belief-456"

        mock_store.get_belief_with_stances.return_value = {
            "belief": {
                "id": belief_id,
                "title": "Low confidence belief",
                "current_confidence": 0.3,  # Low
            },
            "stances": [
                {
                    "id": "stance-789",
                    "text": "Uncertain stance",
                    "confidence": 0.3,
                    "status": "current",
                }
            ],
            "evidence": [],
            "updates": []
        }

        mock_store.update_stance_version.return_value = "new-stance-uuid"

        conflict_info = {
            "draft_text": "New perspective",
            "explanation": "Low-confidence conflict",
            "evidence_strength": "weak",  # Even weak evidence is accepted
        }

        # Act
        applied = await updater.update_from_conflict(
            persona_id=persona_id,
            belief_id=belief_id,
            conflict_info=conflict_info
        )

        # Assert
        assert applied is True
        mock_store.update_stance_version.assert_called_once()

    @pytest.mark.asyncio
    async def test_locked_stance_rejected(self):
        """Test that locked stance prevents conflict-based updates."""
        # Arrange
        mock_store = MockMemoryStore()
        updater = BeliefUpdater(mock_store)

        persona_id = "persona-123"
        belief_id = "belief-456"

        mock_store.get_belief_with_stances.return_value = {
            "belief": {
                "id": belief_id,
                "title": "Locked belief",
                "current_confidence": 0.5,
            },
            "stances": [
                {
                    "id": "stance-789",
                    "text": "Locked stance",
                    "confidence": 0.5,
                    "status": "locked",  # Locked
                }
            ],
            "evidence": [],
            "updates": []
        }

        conflict_info = {
            "draft_text": "Conflict",
            "explanation": "Trying to update locked",
            "evidence_strength": "strong",
        }

        # Act
        applied = await updater.update_from_conflict(
            persona_id=persona_id,
            belief_id=belief_id,
            conflict_info=conflict_info
        )

        # Assert
        assert applied is False
        mock_store.update_stance_version.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_evidence_strength_raises_error(self):
        """Test that invalid evidence_strength raises ValueError."""
        # Arrange
        mock_store = MockMemoryStore()
        updater = BeliefUpdater(mock_store)

        persona_id = "persona-123"
        belief_id = "belief-456"

        mock_store.get_belief_with_stances.return_value = {
            "belief": {
                "id": belief_id,
                "title": "Belief",
                "current_confidence": 0.5,
            },
            "stances": [
                {
                    "id": "stance-789",
                    "text": "Stance",
                    "confidence": 0.5,
                    "status": "current",
                }
            ],
            "evidence": [],
            "updates": []
        }

        conflict_info = {
            "draft_text": "Conflict",
            "explanation": "Invalid strength",
            "evidence_strength": "invalid",  # Invalid
        }

        # Act & Assert
        with pytest.raises(ValueError, match="evidence_strength must be one of"):
            await updater.update_from_conflict(
                persona_id=persona_id,
                belief_id=belief_id,
                conflict_info=conflict_info
            )

    @pytest.mark.asyncio
    async def test_missing_required_fields_raises_error(self):
        """Test that missing required fields in conflict_info raises ValueError."""
        # Arrange
        mock_store = MockMemoryStore()
        updater = BeliefUpdater(mock_store)

        persona_id = "persona-123"
        belief_id = "belief-456"

        # Missing explanation
        conflict_info = {
            "draft_text": "Conflict",
            "evidence_strength": "weak",
        }

        # Act & Assert
        with pytest.raises(ValueError, match="must contain"):
            await updater.update_from_conflict(
                persona_id=persona_id,
                belief_id=belief_id,
                conflict_info=conflict_info
            )


class TestNudgeConfidence:
    """Test suite for manual confidence nudging."""

    @pytest.mark.asyncio
    async def test_nudge_increase(self):
        """Test manual nudge increases confidence."""
        # Arrange
        mock_store = MockMemoryStore()
        updater = BeliefUpdater(mock_store)

        persona_id = "persona-123"
        belief_id = "belief-456"

        mock_store.get_belief_with_stances.return_value = {
            "belief": {
                "id": belief_id,
                "title": "Belief",
                "current_confidence": 0.6,
            },
            "stances": [
                {
                    "id": "stance-789",
                    "text": "Stance",
                    "confidence": 0.6,
                    "status": "current",
                }
            ],
            "evidence": [],
            "updates": []
        }

        mock_store.update_stance_version.return_value = "new-stance-uuid"

        # Act
        new_confidence = await updater.nudge_confidence(
            persona_id=persona_id,
            belief_id=belief_id,
            direction="increase",
            amount=0.1,
            reason="Manual adjustment based on user feedback"
        )

        # Assert
        assert new_confidence > 0.6
        mock_store.update_stance_version.assert_called_once()

    @pytest.mark.asyncio
    async def test_nudge_decrease(self):
        """Test manual nudge decreases confidence."""
        # Arrange
        mock_store = MockMemoryStore()
        updater = BeliefUpdater(mock_store)

        persona_id = "persona-123"
        belief_id = "belief-456"

        mock_store.get_belief_with_stances.return_value = {
            "belief": {
                "id": belief_id,
                "title": "Belief",
                "current_confidence": 0.7,
            },
            "stances": [
                {
                    "id": "stance-789",
                    "text": "Stance",
                    "confidence": 0.7,
                    "status": "current",
                }
            ],
            "evidence": [],
            "updates": []
        }

        mock_store.update_stance_version.return_value = "new-stance-uuid"

        # Act
        new_confidence = await updater.nudge_confidence(
            persona_id=persona_id,
            belief_id=belief_id,
            direction="decrease",
            amount=0.15,
            reason="Less confident after reflection"
        )

        # Assert
        assert new_confidence < 0.7
        mock_store.update_stance_version.assert_called_once()

    @pytest.mark.asyncio
    async def test_invalid_amount_raises_error(self):
        """Test that invalid nudge amount raises ValueError."""
        # Arrange
        mock_store = MockMemoryStore()
        updater = BeliefUpdater(mock_store)

        persona_id = "persona-123"
        belief_id = "belief-456"

        # Act & Assert - amount too large
        with pytest.raises(ValueError, match="amount must be in"):
            await updater.nudge_confidence(
                persona_id=persona_id,
                belief_id=belief_id,
                direction="increase",
                amount=0.6,  # Too large
                reason="Invalid nudge"
            )

        # amount zero or negative
        with pytest.raises(ValueError, match="amount must be in"):
            await updater.nudge_confidence(
                persona_id=persona_id,
                belief_id=belief_id,
                direction="increase",
                amount=0.0,  # Zero
                reason="Invalid nudge"
            )
