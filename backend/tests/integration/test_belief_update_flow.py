"""
Integration test for full belief update flow.

Tests the complete Bayesian belief update pipeline including:
- Initial belief creation
- Evidence-based updates (weak, moderate, strong)
- Locked stance enforcement
- Stance version history tracking
- Audit log integrity

Uses real database connections and SQLAlchemy models.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

from app.models import BeliefNode, StanceVersion, BeliefUpdate, EvidenceLink, Persona
from app.services.belief_updater import BeliefUpdater, EvidenceStrength
from app.repositories.memory_repository import MemoryRepository


@pytest.mark.asyncio
async def test_full_belief_update_flow(db_session: AsyncSession):
    """
    Integration test: Full belief update flow from creation to evolution.

    Scenario:
    1. Create test persona
    2. Create initial belief with confidence 0.6
    3. Apply weak counter-evidence → confidence should drop to ~0.55
    4. Apply strong supporting evidence → confidence should rise to ~0.75
    5. Lock the stance
    6. Attempt update → should be rejected (PermissionError)
    7. Verify stance version history shows evolution
    8. Verify audit log contains all changes

    This test validates:
    - Bayesian confidence calculation correctness
    - Stance versioning (current → deprecated → new current)
    - Locked stance enforcement
    - Audit trail completeness
    - Database transaction atomicity
    """
    # Arrange - Create test persona
    persona_id = str(uuid.uuid4())
    persona = Persona(
        id=persona_id,
        reddit_username="test_agent",
        display_name="Test Agent",
        config={"tone": "neutral"}
    )
    db_session.add(persona)
    await db_session.flush()

    # Create initial belief
    belief_id = str(uuid.uuid4())
    belief = BeliefNode(
        id=belief_id,
        persona_id=persona_id,
        title="Climate change is urgent",
        summary="Climate change requires immediate action to prevent catastrophic consequences.",
        current_confidence=0.6,
        tags='["climate", "environment", "science"]'
    )
    db_session.add(belief)

    # Create initial stance version
    initial_stance_id = str(uuid.uuid4())
    initial_stance = StanceVersion(
        id=initial_stance_id,
        persona_id=persona_id,
        belief_id=belief_id,
        text="Climate change requires immediate action",
        confidence=0.6,
        status="current",
        rationale="Initial position based on scientific consensus"
    )
    db_session.add(initial_stance)
    await db_session.commit()

    # Initialize belief updater with memory repository
    memory_repo = MemoryRepository(db_session)
    updater = BeliefUpdater(memory_repo)

    # Act - Step 1: Apply weak counter-evidence
    new_conf_1 = await updater.update_from_evidence(
        persona_id=persona_id,
        belief_id=belief_id,
        evidence_strength=EvidenceStrength.WEAK,
        reason="Anecdotal comment questioned urgency",
        direction="decrease",
        updated_by="test_system"
    )

    # Refresh belief from DB
    await db_session.refresh(belief)

    # Assert Step 1
    assert new_conf_1 < 0.6, "Weak counter-evidence should decrease confidence"
    assert new_conf_1 > 0.5, "Weak evidence should have small effect"
    assert belief.current_confidence == new_conf_1, "Belief node should be updated"

    # Verify stance version 1 was deprecated
    from sqlalchemy import select
    stmt = select(StanceVersion).where(
        StanceVersion.belief_id == belief_id,
        StanceVersion.status == "deprecated"
    ).order_by(StanceVersion.created_at.desc())
    result = await db_session.execute(stmt)
    deprecated_stances = result.scalars().all()
    assert len(deprecated_stances) == 1, "Original stance should be deprecated"
    assert deprecated_stances[0].id == initial_stance_id

    # Verify new current stance was created
    stmt = select(StanceVersion).where(
        StanceVersion.belief_id == belief_id,
        StanceVersion.status == "current"
    ).order_by(StanceVersion.created_at.desc())
    result = await db_session.execute(stmt)
    current_stances = result.scalars().all()
    assert len(current_stances) == 1, "Should have exactly one current stance"
    assert current_stances[0].confidence == new_conf_1

    # Verify audit log entry was created
    stmt = select(BeliefUpdate).where(
        BeliefUpdate.belief_id == belief_id,
        BeliefUpdate.trigger_type == "evidence"
    ).order_by(BeliefUpdate.created_at.desc())
    result = await db_session.execute(stmt)
    updates = result.scalars().all()
    assert len(updates) == 1, "Should have one audit log entry"
    assert updates[0].updated_by == "test_system"
    assert "Anecdotal comment" in updates[0].reason

    # Act - Step 2: Apply strong supporting evidence
    new_conf_2 = await updater.update_from_evidence(
        persona_id=persona_id,
        belief_id=belief_id,
        evidence_strength=EvidenceStrength.STRONG,
        reason="Major IPCC report confirms urgency with robust data",
        direction="increase",
        updated_by="test_system"
    )

    await db_session.refresh(belief)

    # Assert Step 2
    assert new_conf_2 > new_conf_1, "Strong supporting evidence should increase confidence"
    assert new_conf_2 > 0.7, "Strong evidence should have significant effect"
    assert belief.current_confidence == new_conf_2

    # Verify stance version history now has 3 versions (initial, after step 1, after step 2)
    stmt = select(StanceVersion).where(
        StanceVersion.belief_id == belief_id
    ).order_by(StanceVersion.created_at.asc())
    result = await db_session.execute(stmt)
    all_stances = result.scalars().all()
    assert len(all_stances) == 3, "Should have 3 stance versions (initial + 2 updates)"

    # Verify evolution: initial -> deprecated, version 2 -> deprecated, version 3 -> current
    assert all_stances[0].status == "deprecated"
    assert all_stances[0].confidence == 0.6
    assert all_stances[1].status == "deprecated"
    assert all_stances[1].confidence == new_conf_1
    assert all_stances[2].status == "current"
    assert all_stances[2].confidence == new_conf_2

    # Verify audit log has 2 entries
    stmt = select(BeliefUpdate).where(
        BeliefUpdate.belief_id == belief_id
    ).order_by(BeliefUpdate.created_at.asc())
    result = await db_session.execute(stmt)
    all_updates = result.scalars().all()
    assert len(all_updates) == 2, "Should have 2 audit log entries"
    assert "Anecdotal" in all_updates[0].reason
    assert "IPCC report" in all_updates[1].reason

    # Act - Step 3: Lock the current stance
    current_stance = all_stances[2]
    current_stance.status = "locked"
    await db_session.commit()

    # Act - Step 4: Attempt update on locked stance
    with pytest.raises(PermissionError, match="locked"):
        await updater.update_from_evidence(
            persona_id=persona_id,
            belief_id=belief_id,
            evidence_strength=EvidenceStrength.MODERATE,
            reason="Should be rejected",
            direction="increase",
            updated_by="test_system"
        )

    # Assert Step 4: No new stance or audit entry should be created
    stmt = select(StanceVersion).where(
        StanceVersion.belief_id == belief_id
    )
    result = await db_session.execute(stmt)
    all_stances_after_lock = result.scalars().all()
    assert len(all_stances_after_lock) == 3, "No new stance should be created after lock rejection"

    stmt = select(BeliefUpdate).where(
        BeliefUpdate.belief_id == belief_id
    )
    result = await db_session.execute(stmt)
    all_updates_after_lock = result.scalars().all()
    assert len(all_updates_after_lock) == 2, "No new audit entry after lock rejection"

    # Final verification: Belief node confidence unchanged after rejected update
    await db_session.refresh(belief)
    assert belief.current_confidence == new_conf_2, "Confidence should be unchanged after locked update attempt"


@pytest.mark.asyncio
async def test_conflict_based_update_with_thresholds(db_session: AsyncSession):
    """
    Integration test: Conflict-based updates respect confidence thresholds.

    Tests the "strong statements require strong proofs" principle:
    - High confidence (>0.8): Only strong evidence updates
    - Moderate confidence (0.5-0.8): Automatic updates allowed
    - Low confidence (<0.5): Updates freely
    """
    # Arrange - Create persona
    persona_id = str(uuid.uuid4())
    persona = Persona(
        id=persona_id,
        reddit_username="test_agent_2",
        display_name="Test Agent 2",
        config={"tone": "neutral"}
    )
    db_session.add(persona)
    await db_session.flush()

    # Create high-confidence belief
    high_belief_id = str(uuid.uuid4())
    high_belief = BeliefNode(
        id=high_belief_id,
        persona_id=persona_id,
        title="High confidence belief",
        summary="Very confident about this",
        current_confidence=0.85,
        tags='["test"]'
    )
    db_session.add(high_belief)

    high_stance = StanceVersion(
        id=str(uuid.uuid4()),
        persona_id=persona_id,
        belief_id=high_belief_id,
        text="I am very confident",
        confidence=0.85,
        status="current",
        rationale="Strong evidence base"
    )
    db_session.add(high_stance)

    # Create moderate-confidence belief
    mod_belief_id = str(uuid.uuid4())
    mod_belief = BeliefNode(
        id=mod_belief_id,
        persona_id=persona_id,
        title="Moderate confidence belief",
        summary="Somewhat confident",
        current_confidence=0.65,
        tags='["test"]'
    )
    db_session.add(mod_belief)

    mod_stance = StanceVersion(
        id=str(uuid.uuid4()),
        persona_id=persona_id,
        belief_id=mod_belief_id,
        text="Moderately confident",
        confidence=0.65,
        status="current",
        rationale="Some evidence"
    )
    db_session.add(mod_stance)

    await db_session.commit()

    memory_repo = MemoryRepository(db_session)
    updater = BeliefUpdater(memory_repo)

    # Act & Assert - High confidence + weak evidence = rejected
    conflict_weak = {
        "explanation": "Weak conflict with high confidence belief",
        "evidence_strength": "weak"
    }

    applied = await updater.update_from_conflict(
        persona_id=persona_id,
        belief_id=high_belief_id,
        conflict_info=conflict_weak,
        updated_by="test_system"
    )

    assert applied is False, "High confidence belief should reject weak evidence"

    # Act & Assert - High confidence + strong evidence = accepted
    conflict_strong = {
        "explanation": "Strong conflict with high confidence belief",
        "evidence_strength": "strong"
    }

    applied = await updater.update_from_conflict(
        persona_id=persona_id,
        belief_id=high_belief_id,
        conflict_info=conflict_strong,
        updated_by="test_system"
    )

    assert applied is True, "High confidence belief should accept strong evidence"

    await db_session.refresh(high_belief)
    assert high_belief.current_confidence < 0.85, "Confidence should be reduced after strong conflict"

    # Act & Assert - Moderate confidence + moderate evidence = accepted
    conflict_moderate = {
        "explanation": "Moderate conflict",
        "evidence_strength": "moderate"
    }

    applied = await updater.update_from_conflict(
        persona_id=persona_id,
        belief_id=mod_belief_id,
        conflict_info=conflict_moderate,
        updated_by="test_system"
    )

    assert applied is True, "Moderate confidence belief should allow automatic adjustment"

    await db_session.refresh(mod_belief)
    assert mod_belief.current_confidence < 0.65, "Confidence should be adjusted"


@pytest.mark.asyncio
async def test_evidence_linking_integration(db_session: AsyncSession):
    """
    Integration test: Evidence links are created and tracked alongside belief updates.

    Validates that evidence can be linked to beliefs and retrieved in belief history.
    """
    # Arrange
    persona_id = str(uuid.uuid4())
    persona = Persona(
        id=persona_id,
        reddit_username="test_agent_3",
        display_name="Test Agent 3",
        config={"tone": "neutral"}
    )
    db_session.add(persona)
    await db_session.flush()

    belief_id = str(uuid.uuid4())
    belief = BeliefNode(
        id=belief_id,
        persona_id=persona_id,
        title="Belief with evidence",
        summary="This belief has evidence links",
        current_confidence=0.5,
        tags='["test"]'
    )
    db_session.add(belief)

    stance = StanceVersion(
        id=str(uuid.uuid4()),
        persona_id=persona_id,
        belief_id=belief_id,
        text="Initial stance",
        confidence=0.5,
        status="current",
        rationale="Initial"
    )
    db_session.add(stance)
    await db_session.commit()

    memory_repo = MemoryRepository(db_session)
    updater = BeliefUpdater(memory_repo)

    # Act - Add evidence links
    evidence_1 = EvidenceLink(
        id=str(uuid.uuid4()),
        persona_id=persona_id,
        belief_id=belief_id,
        source_type="reddit_comment",
        source_ref="t1_abc123",
        strength="moderate"
    )
    db_session.add(evidence_1)

    evidence_2 = EvidenceLink(
        id=str(uuid.uuid4()),
        persona_id=persona_id,
        belief_id=belief_id,
        source_type="external_link",
        source_ref="https://example.com/study",
        strength="strong"
    )
    db_session.add(evidence_2)
    await db_session.commit()

    # Update belief based on evidence
    await updater.update_from_evidence(
        persona_id=persona_id,
        belief_id=belief_id,
        evidence_strength=EvidenceStrength.STRONG,
        reason=f"Strong evidence from {evidence_2.source_ref}",
        direction="increase",
        updated_by="test_system"
    )

    # Assert - Fetch belief with stances and evidence
    belief_data = await memory_repo.get_belief_with_stances(
        persona_id=persona_id,
        belief_id=belief_id
    )

    assert len(belief_data["evidence"]) == 2, "Should have 2 evidence links"
    assert belief_data["evidence"][0]["strength"] == "strong"
    assert belief_data["evidence"][1]["strength"] == "moderate"

    assert len(belief_data["stances"]) == 2, "Should have 2 stance versions (initial + updated)"
    assert belief_data["stances"][0]["status"] == "current"
    assert belief_data["stances"][0]["confidence"] > 0.5

    assert len(belief_data["updates"]) == 1, "Should have 1 audit log entry"
    assert "Strong evidence" in belief_data["updates"][0]["reason"]
