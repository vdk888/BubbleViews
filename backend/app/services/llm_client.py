"""
OpenRouter LLM Client Implementation.

Provides OpenAI-compatible API client for OpenRouter with dual-model support:
- GPT-5.1-mini for fast, cheap response generation
- Claude-4.5-Haiku for accurate, cheap consistency checking

Features:
- Exponential backoff retry logic for rate limits
- Cost tracking per request
- Token usage monitoring
- Correlation ID logging for observability
"""

import asyncio
import json
import logging
import uuid
from typing import Dict, List, Optional

from openai import AsyncOpenAI, APIError, RateLimitError, APIConnectionError

from app.core.config import settings
from app.services.interfaces.llm_client import ILLMClient

logger = logging.getLogger(__name__)


class OpenRouterClient(ILLMClient):
    """OpenRouter LLM client (OpenAI-compatible API)"""

    # OpenRouter pricing (per 1M tokens)
    # Updated January 2025 - check https://openrouter.ai/docs/models for latest pricing
    PRICING = {
        # OpenAI Models
        "openai/gpt-4o-mini": {
            "input": 0.15 / 1_000_000,
            "output": 0.60 / 1_000_000
        },
        "openai/gpt-5.1-mini": {
            "input": 0.15 / 1_000_000,
            "output": 0.60 / 1_000_000
        },
        "openai/gpt-4o": {
            "input": 2.50 / 1_000_000,
            "output": 10.00 / 1_000_000
        },
        # Anthropic Models
        "anthropic/claude-3.5-haiku": {
            "input": 0.25 / 1_000_000,
            "output": 1.25 / 1_000_000
        },
        "anthropic/claude-4.5-haiku": {
            "input": 0.25 / 1_000_000,
            "output": 1.25 / 1_000_000
        },
        "anthropic/claude-3.5-sonnet": {
            "input": 3.00 / 1_000_000,
            "output": 15.00 / 1_000_000
        },
    }

    # Retry configuration
    MAX_RETRIES = 3
    BASE_DELAY = 1.0  # seconds
    MAX_DELAY = 60.0  # seconds

    def __init__(self):
        """Initialize OpenRouter client with settings from config"""
        self.client = AsyncOpenAI(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            default_headers={
                "HTTP-Referer": "https://github.com/your-repo",  # Optional
                "X-Title": "Reddit AI Agent"  # Optional
            }
        )
        self.response_model = settings.response_model
        self.consistency_model = settings.consistency_model

        logger.info(
            "OpenRouterClient initialized",
            extra={
                "response_model": self.response_model,
                "consistency_model": self.consistency_model,
                "base_url": settings.openrouter_base_url
            }
        )

    async def generate_response(
        self,
        system_prompt: str,
        context: Dict,
        user_message: str,
        tools: Optional[List[Dict]] = None,
        temperature: float = 0.7,
        max_tokens: int = 500,
        correlation_id: Optional[str] = None,
        model: Optional[str] = None,
    ) -> Dict:
        """
        Generate response using configured LLM model (default: GPT-5.1-mini).

        Uses exponential backoff retry logic for rate limits and transient errors.

        Args:
            system_prompt: System-level instructions (persona, rules, safety)
            context: Dict with persona, beliefs, past comments, thread data
            user_message: The actual question/prompt for the LLM
            tools: Optional list of tool definitions (OpenAI function format)
            temperature: Sampling temperature (0-1, default 0.7 for drafting)
            max_tokens: Maximum tokens in response (default 500)
            correlation_id: Optional request ID for tracing
            model: Optional model override (default: self.response_model)

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
        """
        if correlation_id is None:
            correlation_id = str(uuid.uuid4())

        # Use provided model or fall back to default
        model_to_use = model or self.response_model

        logger.info(
            "Generating response",
            extra={
                "correlation_id": correlation_id,
                "model": model_to_use,
                "system_prompt_length": len(system_prompt),
                "user_message_length": len(user_message),
                "temperature": temperature,
                "max_tokens": max_tokens,
                "has_tools": tools is not None
            }
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"Context: {json.dumps(context)}\n\nMessage: {user_message}"
            }
        ]

        try:
            response = await self._call_with_retry(
                model=model_to_use,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools
            )

            # Extract tool calls if present
            tool_calls = []
            if response.choices[0].message.tool_calls:
                tool_calls = [
                    {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    }
                    for tc in response.choices[0].message.tool_calls
                ]

            result = {
                "text": response.choices[0].message.content or "",
                "model": self.response_model,
                "tokens_in": response.usage.prompt_tokens,
                "tokens_out": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
                "cost": self.calculate_cost(
                    self.response_model,
                    response.usage.prompt_tokens,
                    response.usage.completion_tokens
                ),
                "tool_calls": tool_calls,
                "finish_reason": response.choices[0].finish_reason,
                "correlation_id": correlation_id
            }

            logger.info(
                "Response generated successfully",
                extra={
                    "correlation_id": correlation_id,
                    "tokens_in": result["tokens_in"],
                    "tokens_out": result["tokens_out"],
                    "total_tokens": result["total_tokens"],
                    "cost": result["cost"],
                    "finish_reason": result["finish_reason"],
                    "response_length": len(result["text"]),
                    "tool_call_count": len(tool_calls)
                }
            )

            return result

        except Exception as e:
            logger.error(
                "Failed to generate response",
                extra={
                    "correlation_id": correlation_id,
                    "error": str(e),
                    "error_type": type(e).__name__
                },
                exc_info=True
            )
            raise

    async def check_consistency(
        self,
        draft_response: str,
        beliefs: List[Dict],
        correlation_id: Optional[str] = None,
    ) -> Dict:
        """
        Check if draft response is consistent with agent's beliefs.

        Uses secondary model (Claude-4.5-Haiku) for accurate, deterministic checking.

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
        """
        if correlation_id is None:
            correlation_id = str(uuid.uuid4())

        logger.info(
            "Checking consistency",
            extra={
                "correlation_id": correlation_id,
                "model": self.consistency_model,
                "draft_length": len(draft_response),
                "belief_count": len(beliefs)
            }
        )

        belief_summary = "\n".join([
            f"- ID: {b.get('id', 'unknown')}, "
            f"Text: {b.get('text', b.get('summary', 'Unknown'))}, "
            f"Confidence: {b.get('confidence', 0.0):.2f}"
            for b in beliefs
        ])

        prompt = f"""You are a consistency checker. Analyze if the draft response contradicts any beliefs.

Agent's Current Beliefs:
{belief_summary}

Draft Response to Check:
{draft_response}

Respond with JSON containing:
{{
  "is_consistent": true/false,
  "conflicts": ["belief_id1", "belief_id2", ...],
  "explanation": "brief explanation of any conflicts found",
  "confidence": 0.0-1.0 (your confidence in this assessment)
}}

If no conflicts are found, set is_consistent to true and conflicts to an empty array."""

        try:
            response = await self._call_with_retry(
                model=self.consistency_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=200,
                response_format={"type": "json_object"}
            )

            # Parse JSON response
            result = json.loads(response.choices[0].message.content)
            result["model"] = self.consistency_model
            result["tokens_in"] = response.usage.prompt_tokens
            result["tokens_out"] = response.usage.completion_tokens
            result["cost"] = self.calculate_cost(
                self.consistency_model,
                response.usage.prompt_tokens,
                response.usage.completion_tokens
            )
            result["correlation_id"] = correlation_id

            # Ensure required fields exist with defaults
            result.setdefault("is_consistent", False)
            result.setdefault("conflicts", [])
            result.setdefault("explanation", "")
            result.setdefault("confidence", 0.5)

            logger.info(
                "Consistency check completed",
                extra={
                    "correlation_id": correlation_id,
                    "is_consistent": result["is_consistent"],
                    "conflict_count": len(result["conflicts"]),
                    "confidence": result["confidence"],
                    "tokens_in": result["tokens_in"],
                    "tokens_out": result["tokens_out"],
                    "cost": result["cost"]
                }
            )

            return result

        except json.JSONDecodeError as e:
            logger.error(
                "Failed to parse consistency check response",
                extra={
                    "correlation_id": correlation_id,
                    "error": str(e),
                    "raw_response": response.choices[0].message.content if response else None
                },
                exc_info=True
            )
            # Return safe default
            return {
                "is_consistent": False,
                "conflicts": [],
                "explanation": "Failed to parse consistency check response",
                "model": self.consistency_model,
                "tokens_in": 0,
                "tokens_out": 0,
                "cost": 0.0,
                "confidence": 0.0,
                "correlation_id": correlation_id,
                "error": str(e)
            }

        except Exception as e:
            logger.error(
                "Failed to check consistency",
                extra={
                    "correlation_id": correlation_id,
                    "error": str(e),
                    "error_type": type(e).__name__
                },
                exc_info=True
            )
            raise

    async def continue_with_tool_results(
        self,
        messages: List[Dict],
        tool_results: List[Dict],
        tools: Optional[List[Dict]] = None,
        temperature: float = 0.7,
        max_tokens: int = 500,
        correlation_id: Optional[str] = None,
        model: Optional[str] = None,
    ) -> Dict:
        """
        Continue LLM conversation after tool execution.

        Called after the LLM requests tool calls and we've executed them.
        Appends tool results to messages and gets the next response.

        Args:
            messages: The conversation history (will be extended with tool results)
            tool_results: List of tool result dicts:
                [{"tool_call_id": "...", "role": "tool", "content": "..."}]
            tools: Optional tool definitions for potential additional calls
            temperature: Sampling temperature (default 0.7)
            max_tokens: Maximum tokens in response (default 500)
            correlation_id: Optional request ID for tracing
            model: Optional model override

        Returns:
            Dict with same structure as generate_response()
        """
        if correlation_id is None:
            correlation_id = str(uuid.uuid4())

        model_to_use = model or self.response_model

        logger.info(
            "Continuing with tool results",
            extra={
                "correlation_id": correlation_id,
                "model": model_to_use,
                "tool_result_count": len(tool_results),
                "message_count": len(messages),
            }
        )

        # Build extended messages with tool results
        extended_messages = list(messages)  # Copy original messages

        # Add each tool result as a message
        for result in tool_results:
            extended_messages.append({
                "role": "tool",
                "tool_call_id": result["tool_call_id"],
                "content": result["content"]
            })

        try:
            response = await self._call_with_retry(
                model=model_to_use,
                messages=extended_messages,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools
            )

            # Extract tool calls if present
            tool_calls = []
            if response.choices[0].message.tool_calls:
                tool_calls = [
                    {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    }
                    for tc in response.choices[0].message.tool_calls
                ]

            result = {
                "text": response.choices[0].message.content or "",
                "model": model_to_use,
                "tokens_in": response.usage.prompt_tokens,
                "tokens_out": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
                "cost": self.calculate_cost(
                    model_to_use,
                    response.usage.prompt_tokens,
                    response.usage.completion_tokens
                ),
                "tool_calls": tool_calls,
                "finish_reason": response.choices[0].finish_reason,
                "correlation_id": correlation_id,
                # Include updated messages for potential further tool calls
                "messages": extended_messages + [{
                    "role": "assistant",
                    "content": response.choices[0].message.content,
                    "tool_calls": response.choices[0].message.tool_calls
                }] if response.choices[0].message.tool_calls else extended_messages
            }

            logger.info(
                "Tool result continuation completed",
                extra={
                    "correlation_id": correlation_id,
                    "tokens_in": result["tokens_in"],
                    "tokens_out": result["tokens_out"],
                    "cost": result["cost"],
                    "finish_reason": result["finish_reason"],
                    "tool_call_count": len(tool_calls)
                }
            )

            return result

        except Exception as e:
            logger.error(
                "Failed to continue with tool results",
                extra={
                    "correlation_id": correlation_id,
                    "error": str(e),
                    "error_type": type(e).__name__
                },
                exc_info=True
            )
            raise

    async def _call_with_retry(
        self,
        model: str,
        messages: List[Dict],
        temperature: float,
        max_tokens: int,
        tools: Optional[List[Dict]] = None,
        response_format: Optional[Dict] = None
    ):
        """
        Call OpenRouter API with exponential backoff retry logic.

        Handles:
        - RateLimitError: Exponential backoff
        - APIConnectionError: Retry with backoff
        - Other APIErrors: Retry once

        Args:
            model: Model identifier
            messages: Chat messages
            temperature: Sampling temperature
            max_tokens: Max tokens to generate
            tools: Optional tool definitions
            response_format: Optional response format specification

        Returns:
            API response object

        Raises:
            APIError: If all retries fail
        """
        last_error = None

        for attempt in range(self.MAX_RETRIES):
            try:
                # Build request parameters
                params = {
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens
                }

                if tools:
                    params["tools"] = tools

                if response_format:
                    params["response_format"] = response_format

                # Make API call
                response = await self.client.chat.completions.create(**params)
                return response

            except RateLimitError as e:
                last_error = e
                delay = min(
                    self.BASE_DELAY * (2 ** attempt),
                    self.MAX_DELAY
                )
                logger.warning(
                    "Rate limit hit, retrying",
                    extra={
                        "attempt": attempt + 1,
                        "max_retries": self.MAX_RETRIES,
                        "delay": delay,
                        "error": str(e)
                    }
                )
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(delay)
                continue

            except APIConnectionError as e:
                last_error = e
                delay = min(
                    self.BASE_DELAY * (2 ** attempt),
                    self.MAX_DELAY
                )
                logger.warning(
                    "API connection error, retrying",
                    extra={
                        "attempt": attempt + 1,
                        "max_retries": self.MAX_RETRIES,
                        "delay": delay,
                        "error": str(e)
                    }
                )
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(delay)
                continue

            except APIError as e:
                last_error = e
                logger.warning(
                    "API error occurred",
                    extra={
                        "attempt": attempt + 1,
                        "max_retries": self.MAX_RETRIES,
                        "error": str(e),
                        "error_type": type(e).__name__
                    }
                )
                # Only retry once for generic API errors
                if attempt < 1:
                    await asyncio.sleep(self.BASE_DELAY)
                    continue
                raise

        # All retries exhausted
        logger.error(
            "All retry attempts exhausted",
            extra={
                "max_retries": self.MAX_RETRIES,
                "last_error": str(last_error),
                "error_type": type(last_error).__name__
            }
        )
        raise last_error

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
            Cost in USD (rounded to 6 decimal places)

        Note:
            Pricing table is maintained in PRICING class constant and should be
            updated as provider pricing changes.
        """
        if model not in self.PRICING:
            logger.warning(
                "Unknown model pricing",
                extra={
                    "model": model,
                    "available_models": list(self.PRICING.keys())
                }
            )
            return 0.0

        pricing = self.PRICING[model]
        cost = (
            tokens_in * pricing["input"] +
            tokens_out * pricing["output"]
        )
        return round(cost, 6)
