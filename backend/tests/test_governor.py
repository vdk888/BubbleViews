"""
Tests for Governor Service and API Endpoints

Tests the governor's ability to provide introspective analysis of the agent's
reasoning, belief evolution, and past interactions.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.governor import (
    classify_query_intent,
    extract_belief_from_question,
    extract_reddit_id_from_question,
    extract_proposal,
    extract_sources,
    GovernorQueryIntent,
)


class TestIntentClassification:
    """Test query intent classification"""

    def test_classify_belief_history_intent(self):
        """Test belief history queries are classified correctly"""
        questions = [
            "How did my belief about climate change evolve?",
            "What changed my confidence in cryptocurrency?",
            "When did my stance on nuclear energy update?",
        ]

        for question in questions:
            intent = classify_query_intent(question)
            assert intent == GovernorQueryIntent.BELIEF_HISTORY

    def test_classify_interaction_search_intent(self):
        """Test interaction search queries are classified correctly"""
        questions = [
            "Show posts about Bitcoin",
            "Find comments I made about AI",
            "Show me all posts where I discussed climate",
        ]

        for question in questions:
            intent = classify_query_intent(question)
            assert intent == GovernorQueryIntent.INTERACTION_SEARCH

    def test_classify_reasoning_explanation_intent(self):
        """Test reasoning explanation queries are classified correctly"""
        questions = [
            "Why did you say X in that thread?",
            "Explain your reasoning for comment t1_abc123",
            "What made you post that response?",
        ]

        for question in questions:
            intent = classify_query_intent(question)
            assert intent == GovernorQueryIntent.REASONING_EXPLANATION

    def test_classify_belief_analysis_intent(self):
        """Test belief analysis queries are classified correctly"""
        questions = [
            "Should I adjust my stance on AI safety?",
            "Recommend changes to my belief about regulations",
            "Evaluate my position on renewable energy",
        ]

        for question in questions:
            intent = classify_query_intent(question)
            assert intent == GovernorQueryIntent.BELIEF_ANALYSIS

    def test_classify_general_intent(self):
        """Test general queries default to GENERAL intent"""
        questions = [
            "What do you think?",
            "Tell me about yourself",
            "Give me a summary",
        ]

        for question in questions:
            intent = classify_query_intent(question)
            assert intent == GovernorQueryIntent.GENERAL


class TestExtractionFunctions:
    """Test extraction helper functions"""

    def test_extract_belief_from_uuid(self):
        """Test extracting belief ID from UUID in question"""
        belief_graph = {"nodes": []}
        question = "Show history for belief 12345678-1234-1234-1234-123456789abc"

        belief_id = extract_belief_from_question(question, belief_graph)
        assert belief_id == "12345678-1234-1234-1234-123456789abc"

    def test_extract_belief_from_title(self):
        """Test extracting belief ID by matching title"""
        belief_graph = {
            "nodes": [
                {"id": "belief-1", "title": "Climate change is real"},
                {"id": "belief-2", "title": "Nuclear energy is safe"},
            ]
        }

        question = "How did my belief about climate change evolve?"
        belief_id = extract_belief_from_question(question, belief_graph)
        assert belief_id == "belief-1"

    def test_extract_belief_no_match(self):
        """Test no match returns None"""
        belief_graph = {"nodes": []}
        question = "Random question with no belief reference"

        belief_id = extract_belief_from_question(question, belief_graph)
        assert belief_id is None

    def test_extract_reddit_id_t1(self):
        """Test extracting comment ID (t1_)"""
        question = "Why did you post comment t1_abc123?"

        reddit_id = extract_reddit_id_from_question(question)
        assert reddit_id == "t1_abc123"

    def test_extract_reddit_id_t3(self):
        """Test extracting submission ID (t3_)"""
        question = "Explain your post t3_xyz789"

        reddit_id = extract_reddit_id_from_question(question)
        assert reddit_id == "t3_xyz789"

    def test_extract_reddit_id_no_match(self):
        """Test no match returns None"""
        question = "General question without reddit ID"

        reddit_id = extract_reddit_id_from_question(question)
        assert reddit_id is None


class TestProposalExtraction:
    """Test proposal extraction from LLM responses"""

    def test_extract_valid_proposal(self):
        """Test extracting valid JSON proposal"""
        response = """
Based on the evidence, I propose:

{
  "type": "belief_adjustment",
  "belief_id": "belief-123",
  "current_confidence": 0.7,
  "proposed_confidence": 0.8,
  "reason": "New supporting evidence found",
  "evidence": ["interaction-1", "interaction-2"]
}

This adjustment is warranted because...
"""

        proposal = extract_proposal(response)
        assert proposal is not None
        assert proposal["type"] == "belief_adjustment"
        assert proposal["belief_id"] == "belief-123"
        assert proposal["current_confidence"] == 0.7
        assert proposal["proposed_confidence"] == 0.8
        assert len(proposal["evidence"]) == 2

    def test_extract_proposal_missing_fields(self):
        """Test incomplete proposal is rejected"""
        response = """
{
  "type": "belief_adjustment",
  "belief_id": "belief-123"
}
"""

        proposal = extract_proposal(response)
        # Missing required fields, should return None
        assert proposal is None

    def test_extract_no_proposal(self):
        """Test no proposal in response"""
        response = "This is just a regular response with no proposal."

        proposal = extract_proposal(response)
        assert proposal is None


class TestSourceExtraction:
    """Test source citation extraction"""

    def test_extract_uuid_sources(self):
        """Test extracting UUID references"""
        response = "Based on belief 12345678-1234-1234-1234-123456789abc and interaction 87654321-4321-4321-4321-987654321fed"

        sources = extract_sources(response)
        assert len(sources) == 2
        assert sources[0]["type"] == "id_reference"
        assert sources[1]["type"] == "id_reference"

    def test_extract_reddit_id_sources(self):
        """Test extracting Reddit ID references"""
        response = "See comment t1_abc123 and post t3_xyz789"

        sources = extract_sources(response)
        assert len(sources) == 2
        assert sources[0]["type"] == "reddit_id"
        assert sources[0]["id"] == "t1_abc123"
        assert sources[1]["type"] == "reddit_id"
        assert sources[1]["id"] == "t3_xyz789"

    def test_extract_no_sources(self):
        """Test response with no sources"""
        response = "Generic response without any references"

        sources = extract_sources(response)
        assert len(sources) == 0


@pytest.mark.asyncio
class TestGovernorAPI:
    """Test Governor API endpoints (integration)"""

    @pytest.fixture
    def mock_dependencies(self):
        """Mock dependencies for API tests"""
        memory_store = AsyncMock()
        llm_client = AsyncMock()
        current_user = MagicMock()
        current_user.id = "user-123"
        current_user.username = "admin"

        return {
            "memory_store": memory_store,
            "llm_client": llm_client,
            "current_user": current_user,
        }

    async def test_query_governor_success(self, mock_dependencies):
        """Test successful governor query"""
        # Setup mocks
        mock_dependencies["memory_store"].query_belief_graph.return_value = {
            "nodes": [],
            "edges": []
        }
        mock_dependencies["memory_store"].search_history.return_value = []

        mock_dependencies["llm_client"].generate_response.return_value = {
            "text": "This is the governor's analysis...",
            "total_tokens": 500,
            "cost": 0.001,
            "model": "test-model"
        }

        # Import and call the endpoint function
        from app.api.v1.governor import query_governor_endpoint, GovernorQueryRequest

        with patch("app.api.v1.governor.query_governor") as mock_query:
            mock_query.return_value = {
                "answer": "Governor response",
                "sources": [],
                "proposal": None,
                "intent": "general",
                "tokens_used": 500,
                "cost": 0.001,
                "model": "test-model"
            }

            request = GovernorQueryRequest(
                persona_id="persona-123",
                question="What is your current belief about AI?"
            )

            response = await query_governor_endpoint(
                request=request,
                memory_store=mock_dependencies["memory_store"],
                llm_client=mock_dependencies["llm_client"],
                current_user=mock_dependencies["current_user"]
            )

            assert response.answer == "Governor response"
            assert response.intent == "general"
            assert response.proposal is None

    async def test_approve_proposal_success(self, mock_dependencies):
        """Test successful proposal approval"""
        # Setup mocks
        mock_dependencies["memory_store"].get_belief_with_stances.return_value = {
            "belief": {"id": "belief-123"},
            "stances": [
                {
                    "text": "Current stance",
                    "confidence": 0.7,
                    "status": "current"
                }
            ]
        }
        mock_dependencies["memory_store"].update_stance_version.return_value = "new-stance-123"

        from app.api.v1.governor import approve_proposal_endpoint, ApproveProposalRequest

        request = ApproveProposalRequest(
            persona_id="persona-123",
            belief_id="belief-123",
            proposed_confidence=0.8,
            reason="Test approval",
            approved=True
        )

        response = await approve_proposal_endpoint(
            request=request,
            memory_store=mock_dependencies["memory_store"],
            belief_updater=AsyncMock(),
            current_user=mock_dependencies["current_user"]
        )

        assert response.status == "approved"
        assert response.belief_id == "belief-123"

    async def test_reject_proposal(self, mock_dependencies):
        """Test proposal rejection"""
        from app.api.v1.governor import approve_proposal_endpoint, ApproveProposalRequest

        request = ApproveProposalRequest(
            persona_id="persona-123",
            belief_id="belief-123",
            proposed_confidence=0.8,
            reason="Test rejection",
            approved=False
        )

        response = await approve_proposal_endpoint(
            request=request,
            memory_store=mock_dependencies["memory_store"],
            belief_updater=AsyncMock(),
            current_user=mock_dependencies["current_user"]
        )

        assert response.status == "rejected"
        assert response.belief_id is None
