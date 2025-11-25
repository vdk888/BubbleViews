"""
LLM Client Interface Contract.

Defines the contract for LLM interactions with OpenRouter or other providers.
This interface ensures consistent behavior across different LLM implementations.

Key responsibilities:
- Response generation with context and tool support
- Consistency checking against belief graph
- Token usage tracking and cost calculation
- Structured error handling and retries
- Request/response logging with correlation IDs
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any


class ILLMClient(ABC):
    """
    Abstract base class for LLM clients.

    Implementations handle:
    - Prompt assembly and message formatting
    - API communication with LLM providers
    - Token usage tracking and cost calculation
    - Error handling and retries
    - Structured logging with correlation IDs
    """

    @abstractmethod
    async def generate_response(
        self,
        system_prompt: str,
        context: Dict[str, Any],
        user_message: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.7,
        max_tokens: int = 500,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate a response using the primary LLM model.

        Args:
            system_prompt: System-level instructions (persona, rules, safety)
            context: Dict with persona, beliefs, past comments, thread data
            user_message: The actual question/prompt for the LLM
            tools: Optional list of tool definitions (OpenAI function format)
            temperature: Sampling temperature (0-1, default 0.7 for drafting)
            max_tokens: Maximum tokens in response (default 500)
            correlation_id: Optional request ID for tracing

        Returns:
            Dict with:
                - text: Generated response text
                - model: Model name used
                - tokens_in: Prompt tokens consumed
                - tokens_out: Completion tokens generated
                - total_tokens: Sum of in + out
                - cost: Calculated cost in USD
                - tool_calls: List of tool calls if applicable
                - finish_reason: stop, length, tool_calls, etc.

        Raises:
            LLMAPIError: For API communication errors
            LLMRateLimitError: When rate limited (should retry)
            LLMAuthError: For authentication failures
        """
        pass

    @abstractmethod
    async def check_consistency(
        self,
        draft_response: str,
        beliefs: List[Dict[str, Any]],
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Check if draft response is consistent with agent's beliefs.

        Uses secondary model (typically more accurate, lower temp) to analyze
        whether the draft contradicts any held beliefs.

        Args:
            draft_response: The generated response text to check
            beliefs: List of belief dicts with {id, text, confidence, ...}
            correlation_id: Optional request ID for tracing

        Returns:
            Dict with:
                - is_consistent: bool, True if no conflicts found
                - conflicts: List of belief IDs that conflict
                - explanation: Natural language explanation of conflicts
                - model: Model name used for checking
                - tokens_in: Tokens consumed
                - tokens_out: Tokens generated
                - cost: Cost in USD
                - confidence: Optional confidence score (0-1)

        Raises:
            LLMAPIError: For API communication errors
            LLMRateLimitError: When rate limited
        """
        pass

    @abstractmethod
    async def continue_with_tool_results(
        self,
        messages: List[Dict[str, Any]],
        tool_results: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.7,
        max_tokens: int = 500,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Continue LLM conversation after tool execution.

        Called after the LLM requests tool calls and we've executed them.
        Sends the tool results back to get the final response.

        Args:
            messages: The conversation history up to and including the
                assistant message with tool_calls
            tool_results: List of tool result dicts in format:
                [
                    {
                        "tool_call_id": "call_abc123",
                        "role": "tool",
                        "content": "{...json result...}"
                    },
                    ...
                ]
            tools: Optional tool definitions (for potential additional calls)
            temperature: Sampling temperature (default 0.7)
            max_tokens: Maximum tokens in response (default 500)
            correlation_id: Optional request ID for tracing

        Returns:
            Dict with same structure as generate_response():
                - text: Generated response text
                - model: Model name used
                - tokens_in: Prompt tokens consumed
                - tokens_out: Completion tokens generated
                - total_tokens: Sum of in + out
                - cost: Calculated cost in USD
                - tool_calls: List of tool calls if LLM wants more tools
                - finish_reason: stop, length, tool_calls, etc.

        Raises:
            LLMAPIError: For API communication errors
        """
        pass

    @abstractmethod
    def calculate_cost(
        self,
        model: str,
        tokens_in: int,
        tokens_out: int,
    ) -> float:
        """
        Calculate cost for an LLM request.

        Args:
            model: Model identifier (e.g., "openai/gpt-5.1-mini")
            tokens_in: Number of input tokens
            tokens_out: Number of output tokens

        Returns:
            Cost in USD (float)

        Note:
            Pricing table should be maintained internally and updated
            as provider pricing changes.
        """
        pass
