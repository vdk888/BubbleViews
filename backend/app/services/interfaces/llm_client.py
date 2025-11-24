"""
LLM Client Interface Contract.

Defines the contract for LLM interactions with OpenRouter or other providers.
This interface ensures consistent behavior across different LLM implementations.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional


class ILLMClient(ABC):
    """Contract for LLM interactions"""

    @abstractmethod
    async def generate_response(
        self,
        system_prompt: str,
        context: Dict,
        user_message: str,
        tools: Optional[List[Dict]] = None
    ) -> Dict:
        """
        Generate LLM response with optional tool use.

        Args:
            system_prompt: System-level instructions for the LLM
            context: Contextual information (beliefs, history, etc.)
            user_message: User's message or prompt
            tools: Optional list of tool definitions for function calling

        Returns:
            Dict containing:
                - text: Generated response text
                - model: Model used for generation
                - tokens: Total tokens used
                - cost: Estimated cost in USD
        """
        pass

    @abstractmethod
    async def check_consistency(
        self,
        draft_response: str,
        beliefs: List[Dict]
    ) -> Dict:
        """
        Check if draft aligns with belief graph.

        Args:
            draft_response: Draft response to validate
            beliefs: List of belief dictionaries with 'text' and 'confidence'

        Returns:
            Dict containing:
                - is_consistent: Boolean indicating consistency
                - conflicts: List of conflicting belief IDs
                - explanation: Brief explanation of conflicts
                - tokens: Total tokens used
                - cost: Estimated cost in USD
        """
        pass
