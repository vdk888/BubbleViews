"""
Bayesian Belief Updater Service

Implements Bayesian-style belief updates based on evidence strength and conflict detection.
Follows the principle: "Strong statements require strong proofs."

Key features:
- Evidence-based confidence updates with Bayesian reasoning
- Locked stance enforcement (prevents unauthorized updates)
- Stance version tracking with deprecation
- Audit logging for all updates
- Conflict resolution based on belief confidence thresholds

Mathematical Foundation:
    Uses Bayesian update approximation where:
    - Prior: current_confidence
    - Evidence: strength-weighted likelihood
    - Posterior: updated confidence with logistic smoothing

    For evidence E with strength s:
    - P(belief | E) ∝ P(E | belief) × P(belief)
    - Simplified: new_conf = logistic_update(current_conf, delta(s), direction)

Evidence strength deltas (from MVP spec):
    - weak: 0.05 (minor adjustment, anecdotal evidence)
    - moderate: 0.10 (notable shift, credible sources)
    - strong: 0.20 (significant change, robust evidence)
"""

import math
import logging
from typing import Dict, Optional, Any, Literal
from enum import Enum

from app.services.interfaces.memory_store import IMemoryStore

logger = logging.getLogger(__name__)


class EvidenceStrength(str, Enum):
    """Evidence strength categories with corresponding confidence deltas."""
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"


# Evidence strength to confidence delta mapping
EVIDENCE_DELTA = {
    EvidenceStrength.WEAK: 0.05,
    EvidenceStrength.MODERATE: 0.10,
    EvidenceStrength.STRONG: 0.20,
}

# Direction of belief update
UpdateDirection = Literal["increase", "decrease"]

# Conflict thresholds
HIGH_CONFIDENCE_THRESHOLD = 0.8  # Beliefs above this require strong evidence to change
MODERATE_CONFIDENCE_THRESHOLD = 0.5  # Beliefs above this allow automatic adjustment


class BeliefUpdater:
    """
    Bayesian belief updater with evidence-based confidence adjustments.

    Manages the agent's epistemic state by:
    1. Updating belief confidence based on evidence strength
    2. Enforcing locked stance policies
    3. Creating versioned stance history
    4. Logging all changes for audit trails
    5. Resolving conflicts between drafts and beliefs

    The updater follows Bayesian principles where strong claims require
    strong evidence, and confidence updates are proportional to evidence quality.
    """

    def __init__(self, memory_store: IMemoryStore):
        """
        Initialize belief updater.

        Args:
            memory_store: Memory store instance for belief operations
        """
        self.memory_store = memory_store

    def calculate_new_confidence(
        self,
        current_confidence: float,
        evidence_strength: EvidenceStrength,
        direction: UpdateDirection
    ) -> float:
        """
        Calculate updated confidence using Bayesian-inspired logistic update.

        Uses a logistic function to ensure smooth transitions and avoid
        extreme confidence values (0 or 1) unless overwhelming evidence.

        Mathematical approach:
        1. Convert confidence to log-odds: odds = conf / (1 - conf)
        2. Apply evidence delta in log-odds space
        3. Convert back to probability with logistic function

        This approach ensures:
        - Diminishing returns near 0 and 1 (harder to reach certainty)
        - Proportional updates in the middle range
        - Symmetric behavior for increase/decrease

        Args:
            current_confidence: Current belief confidence (0.0-1.0)
            evidence_strength: Strength of new evidence
            direction: Whether evidence supports ("increase") or contradicts ("decrease")

        Returns:
            Updated confidence clamped to [0.01, 0.99]

        Raises:
            ValueError: If current_confidence out of range

        Example:
            >>> updater.calculate_new_confidence(0.6, EvidenceStrength.MODERATE, "increase")
            0.68  # Moderate evidence increases confidence from 0.6 to 0.68
        """
        if not 0 <= current_confidence <= 1:
            raise ValueError(f"current_confidence must be in [0, 1], got {current_confidence}")

        # Get evidence delta
        delta = EVIDENCE_DELTA[evidence_strength]

        # Handle extreme cases to avoid log(0)
        if current_confidence <= 0.01:
            current_confidence = 0.01
        elif current_confidence >= 0.99:
            current_confidence = 0.99

        # Convert confidence to log-odds
        # odds = p / (1 - p)
        current_odds = current_confidence / (1 - current_confidence)
        log_odds = math.log(current_odds)

        # Apply evidence in log-odds space
        # Increase = positive delta, decrease = negative delta
        if direction == "increase":
            new_log_odds = log_odds + delta * 5  # Scale factor for noticeable effect
        else:  # decrease
            new_log_odds = log_odds - delta * 5

        # Convert back to probability using logistic function
        # p = 1 / (1 + exp(-log_odds)) = exp(log_odds) / (1 + exp(log_odds))
        new_confidence = 1 / (1 + math.exp(-new_log_odds))

        # Clamp to [0.01, 0.99] to avoid absolute certainty
        new_confidence = max(0.01, min(0.99, new_confidence))

        logger.debug(
            f"Confidence update: {current_confidence:.3f} -> {new_confidence:.3f} "
            f"(strength={evidence_strength.value}, direction={direction}, delta={delta})"
        )

        return round(new_confidence, 3)

    async def update_from_evidence(
        self,
        persona_id: str,
        belief_id: str,
        evidence_strength: EvidenceStrength,
        reason: str,
        direction: UpdateDirection = "increase",
        updated_by: str = "system"
    ) -> float:
        """
        Update belief confidence based on new evidence.

        Performs Bayesian-style confidence update, enforcing locked stance
        policies and creating versioned stance history.

        Process:
        1. Fetch current belief and stance
        2. Check if stance is locked (reject if locked)
        3. Calculate new confidence using Bayesian update
        4. Create new stance version
        5. Update belief node confidence
        6. Log update to audit trail

        Args:
            persona_id: UUID of persona
            belief_id: UUID of belief to update
            evidence_strength: Strength of evidence (weak, moderate, strong)
            reason: Human-readable reason for update
            direction: Whether evidence supports or contradicts belief (default: "increase")
            updated_by: Who/what triggered the update (default: "system")

        Returns:
            New confidence value after update

        Raises:
            ValueError: If belief not found or persona mismatch
            PermissionError: If current stance is locked

        Example:
            >>> new_conf = await updater.update_from_evidence(
            ...     persona_id="uuid-123",
            ...     belief_id="uuid-456",
            ...     evidence_strength=EvidenceStrength.MODERATE,
            ...     reason="User provided credible source from Nature journal",
            ...     direction="increase"
            ... )
            >>> print(new_conf)  # 0.75 (increased from 0.65)
        """
        # Fetch belief with current stance
        belief_data = await self.memory_store.get_belief_with_stances(
            persona_id=persona_id,
            belief_id=belief_id
        )

        belief = belief_data["belief"]
        stances = belief_data["stances"]

        # Check for current OR locked stance
        current_stance = next((s for s in stances if s["status"] in ["current", "locked"]), None)
        if not current_stance:
            raise ValueError(f"No current or locked stance found for belief {belief_id}")

        # If stance is locked, reject update
        if current_stance["status"] == "locked":
            logger.warning(
                f"Attempted update to locked stance: belief={belief_id}, persona={persona_id}",
                extra={"belief_id": belief_id, "persona_id": persona_id, "updated_by": updated_by}
            )
            raise PermissionError(
                f"Cannot update belief {belief_id}: stance is locked. "
                f"Unlock the stance or use manual override."
            )

        # Get current confidence
        current_confidence = belief["current_confidence"]
        if current_confidence is None:
            current_confidence = 0.5  # Default prior

        # Calculate new confidence
        new_confidence = self.calculate_new_confidence(
            current_confidence=current_confidence,
            evidence_strength=evidence_strength,
            direction=direction
        )

        # Prepare stance update
        stance_text = current_stance["text"]  # Keep same text, update confidence
        rationale = (
            f"{reason} "
            f"(Evidence: {evidence_strength.value}, Direction: {direction}, "
            f"Confidence: {current_confidence:.3f} → {new_confidence:.3f})"
        )

        # Update stance version (creates new version, marks old as deprecated, logs to audit)
        new_stance_id = await self.memory_store.update_stance_version(
            persona_id=persona_id,
            belief_id=belief_id,
            text=stance_text,
            confidence=new_confidence,
            rationale=rationale,
            updated_by=updated_by
        )

        logger.info(
            f"Updated belief confidence: {current_confidence:.3f} -> {new_confidence:.3f}",
            extra={
                "persona_id": persona_id,
                "belief_id": belief_id,
                "stance_id": new_stance_id,
                "evidence_strength": evidence_strength.value,
                "direction": direction,
                "updated_by": updated_by
            }
        )

        return new_confidence

    async def update_from_conflict(
        self,
        persona_id: str,
        belief_id: str,
        conflict_info: Dict[str, Any],
        updated_by: str = "system"
    ) -> bool:
        """
        Update belief based on detected conflict between draft and beliefs.

        Implements conflict resolution policy:
        - High confidence beliefs (>0.8): Only update with strong evidence
        - Moderate confidence beliefs (0.5-0.8): Allow automatic adjustment
        - Low confidence beliefs (<0.5): Update freely

        Process:
        1. Fetch current belief
        2. Evaluate conflict severity and evidence strength
        3. Apply confidence thresholds
        4. Update if policy allows, otherwise log for admin review

        Args:
            persona_id: UUID of persona
            belief_id: UUID of belief in conflict
            conflict_info: Dictionary with conflict details:
                {
                    "draft_text": "The conflicting draft statement",
                    "explanation": "Why there's a conflict",
                    "evidence_strength": "weak" | "moderate" | "strong",
                    "suggested_confidence": float  # Optional new confidence
                }
            updated_by: Who/what triggered the update (default: "system")

        Returns:
            True if update was applied, False if rejected/queued for review

        Raises:
            ValueError: If belief not found or conflict_info invalid

        Example:
            >>> conflict = {
            ...     "draft_text": "Climate change may not be urgent",
            ...     "explanation": "Draft contradicts belief about urgency",
            ...     "evidence_strength": "weak",
            ...     "suggested_confidence": 0.7
            ... }
            >>> applied = await updater.update_from_conflict(
            ...     persona_id="uuid-123",
            ...     belief_id="uuid-456",
            ...     conflict_info=conflict
            ... )
            >>> print(applied)  # False (weak evidence vs high confidence belief)
        """
        # Validate conflict_info
        required_fields = ["explanation", "evidence_strength"]
        if not all(field in conflict_info for field in required_fields):
            raise ValueError(f"conflict_info must contain: {required_fields}")

        # Fetch belief
        belief_data = await self.memory_store.get_belief_with_stances(
            persona_id=persona_id,
            belief_id=belief_id
        )

        belief = belief_data["belief"]
        current_confidence = belief["current_confidence"] or 0.5

        # Parse evidence strength
        try:
            evidence_strength = EvidenceStrength(conflict_info["evidence_strength"])
        except ValueError:
            logger.error(f"Invalid evidence_strength: {conflict_info['evidence_strength']}")
            raise ValueError(
                f"evidence_strength must be one of: {[e.value for e in EvidenceStrength]}"
            )

        # Apply conflict resolution policy
        if current_confidence >= HIGH_CONFIDENCE_THRESHOLD:
            # High confidence: require strong evidence
            if evidence_strength == EvidenceStrength.STRONG:
                logger.info(
                    f"High-confidence belief conflict: applying update with strong evidence",
                    extra={
                        "persona_id": persona_id,
                        "belief_id": belief_id,
                        "current_confidence": current_confidence,
                        "evidence_strength": evidence_strength.value
                    }
                )
                # Reduce confidence by half of strong delta (cautious update)
                new_confidence = self.calculate_new_confidence(
                    current_confidence=current_confidence,
                    evidence_strength=EvidenceStrength.MODERATE,  # More cautious
                    direction="decrease"
                )
                reason = f"Conflict detected: {conflict_info['explanation']} (strong evidence provided)"
            else:
                # Weak or moderate evidence: queue for admin review
                logger.warning(
                    f"High-confidence belief conflict rejected: insufficient evidence",
                    extra={
                        "persona_id": persona_id,
                        "belief_id": belief_id,
                        "current_confidence": current_confidence,
                        "evidence_strength": evidence_strength.value,
                        "explanation": conflict_info["explanation"]
                    }
                )
                return False

        elif current_confidence >= MODERATE_CONFIDENCE_THRESHOLD:
            # Moderate confidence: allow automatic adjustment
            logger.info(
                f"Moderate-confidence belief conflict: applying automatic adjustment",
                extra={
                    "persona_id": persona_id,
                    "belief_id": belief_id,
                    "current_confidence": current_confidence,
                    "evidence_strength": evidence_strength.value
                }
            )
            new_confidence = self.calculate_new_confidence(
                current_confidence=current_confidence,
                evidence_strength=evidence_strength,
                direction="decrease"
            )
            reason = f"Conflict detected: {conflict_info['explanation']}"

        else:
            # Low confidence: update freely
            logger.info(
                f"Low-confidence belief conflict: updating freely",
                extra={
                    "persona_id": persona_id,
                    "belief_id": belief_id,
                    "current_confidence": current_confidence,
                    "evidence_strength": evidence_strength.value
                }
            )
            new_confidence = self.calculate_new_confidence(
                current_confidence=current_confidence,
                evidence_strength=evidence_strength,
                direction="decrease"
            )
            reason = f"Conflict detected: {conflict_info['explanation']}"

        # Apply update
        stances = belief_data["stances"]
        current_stance = next((s for s in stances if s["status"] in ["current", "locked"]), None)

        if not current_stance:
            raise ValueError(f"No current or locked stance found for belief {belief_id}")

        # Check if locked
        if current_stance["status"] == "locked":
            logger.warning(
                f"Conflict update blocked: stance is locked",
                extra={"belief_id": belief_id, "persona_id": persona_id}
            )
            return False

        # Update stance
        rationale = (
            f"{reason} "
            f"(Conflict resolution: {current_confidence:.3f} → {new_confidence:.3f})"
        )

        await self.memory_store.update_stance_version(
            persona_id=persona_id,
            belief_id=belief_id,
            text=current_stance["text"],
            confidence=new_confidence,
            rationale=rationale,
            updated_by=updated_by
        )

        logger.info(
            f"Applied conflict-based update: {current_confidence:.3f} -> {new_confidence:.3f}",
            extra={
                "persona_id": persona_id,
                "belief_id": belief_id,
                "evidence_strength": evidence_strength.value,
                "updated_by": updated_by
            }
        )

        return True

    async def nudge_confidence(
        self,
        persona_id: str,
        belief_id: str,
        direction: UpdateDirection,
        amount: float = 0.1,
        reason: str = "Manual nudge",
        updated_by: str = "admin"
    ) -> float:
        """
        Manually nudge belief confidence up or down.

        Convenience method for manual adjustments without evidence classification.
        Useful for dashboard "nudge" feature.

        Args:
            persona_id: UUID of persona
            belief_id: UUID of belief
            direction: "increase" or "decrease"
            amount: Confidence delta (default: 0.1, equivalent to moderate evidence)
            reason: Reason for nudge (default: "Manual nudge")
            updated_by: Who made the nudge (default: "admin")

        Returns:
            New confidence value

        Raises:
            ValueError: If belief not found or amount out of range
            PermissionError: If stance is locked

        Example:
            >>> new_conf = await updater.nudge_confidence(
            ...     persona_id="uuid-123",
            ...     belief_id="uuid-456",
            ...     direction="increase",
            ...     amount=0.1,
            ...     reason="User feedback indicates stronger support"
            ... )
        """
        if not 0 < amount <= 0.5:
            raise ValueError(f"amount must be in (0, 0.5], got {amount}")

        # Map amount to evidence strength (approximate)
        if amount <= 0.05:
            evidence_strength = EvidenceStrength.WEAK
        elif amount <= 0.15:
            evidence_strength = EvidenceStrength.MODERATE
        else:
            evidence_strength = EvidenceStrength.STRONG

        return await self.update_from_evidence(
            persona_id=persona_id,
            belief_id=belief_id,
            evidence_strength=evidence_strength,
            reason=reason,
            direction=direction,
            updated_by=updated_by
        )

    async def manual_update(
        self,
        persona_id: str,
        belief_id: str,
        confidence: Optional[float] = None,
        text: Optional[str] = None,
        rationale: str = "Manual update",
        updated_by: str = "admin"
    ) -> float:
        """
        Manually update belief with specific confidence and/or text.

        Unlike evidence-based updates, this allows direct setting of confidence
        values. Useful for dashboard manual override feature.

        Args:
            persona_id: UUID of persona
            belief_id: UUID of belief
            confidence: New confidence value (if None, keeps current)
            text: New stance text (if None, keeps current)
            rationale: Reason for manual update
            updated_by: Who made the update (default: "admin")

        Returns:
            New confidence value

        Raises:
            ValueError: If belief not found or confidence out of range
            PermissionError: If stance is locked

        Example:
            >>> new_conf = await updater.manual_update(
            ...     persona_id="uuid-123",
            ...     belief_id="uuid-456",
            ...     confidence=0.9,
            ...     rationale="Admin override based on new research"
            ... )
        """
        # Validate confidence if provided
        if confidence is not None and not (0.0 <= confidence <= 1.0):
            raise ValueError(f"confidence must be between 0.0 and 1.0, got {confidence}")

        # Fetch belief with current stance
        belief_data = await self.memory_store.get_belief_with_stances(
            persona_id=persona_id,
            belief_id=belief_id
        )

        belief = belief_data["belief"]
        stances = belief_data["stances"]

        # Check for current OR locked stance
        current_stance = next((s for s in stances if s["status"] in ["current", "locked"]), None)
        if not current_stance:
            raise ValueError(f"No current or locked stance found for belief {belief_id}")

        # If stance is locked, reject update (manual override can still be forced via unlock first)
        if current_stance["status"] == "locked":
            logger.warning(
                f"Attempted manual update to locked stance: belief={belief_id}, persona={persona_id}",
                extra={"belief_id": belief_id, "persona_id": persona_id, "updated_by": updated_by}
            )
            raise PermissionError(
                f"Cannot update belief {belief_id}: stance is locked. "
                f"Unlock the stance first to allow updates."
            )

        # Determine new values (use current if not provided)
        new_confidence = confidence if confidence is not None else belief["current_confidence"]
        new_text = text if text is not None else current_stance["text"]

        # Use memory store to create new stance version
        await self.memory_store.update_stance_version(
            persona_id=persona_id,
            belief_id=belief_id,
            text=new_text,
            confidence=new_confidence,
            rationale=rationale,
            updated_by=updated_by
        )

        logger.info(
            f"Manual belief update completed: belief={belief_id}, "
            f"old_conf={belief['current_confidence']:.3f}, new_conf={new_confidence:.3f}",
            extra={
                "belief_id": belief_id,
                "persona_id": persona_id,
                "old_confidence": belief["current_confidence"],
                "new_confidence": new_confidence,
                "updated_by": updated_by,
                "trigger_type": "manual"
            }
        )

        return new_confidence
