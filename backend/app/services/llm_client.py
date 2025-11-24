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
    PRICING = {
        "openai/gpt-5.1-mini": {
            "input": 0.15 / 1_000_000,
            "output": 0.60 / 1_000_000
        },
        "anthropic/claude-4.5-haiku": {
            "input": 0.25 / 1_000_000,
            "output": 1.25 / 1_000_000
        },
        "anthropic/claude-3.5-haiku": {
            "input": 0.25 / 1_000_000,
            "output": 1.25 / 1_000_000
        }
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
        tools: Optional[List[Dict]] = None
    ) -> Dict:
        """
        Generate response using GPT-5.1-mini (fast, cheap).

        Uses exponential backoff retry logic for rate limits and transient errors.

        Args:
            system_prompt: System-level instructions
            context: Contextual information
            user_message: User's message
            tools: Optional tool definitions

        Returns:
            Dict with text, model, tokens, and cost
        """
        correlation_id = str(uuid.uuid4())
        logger.info(
            "Generating response",
            extra={
                "correlation_id": correlation_id,
                "model": self.response_model,
                "system_prompt_length": len(system_prompt),
                "user_message_length": len(user_message),
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
                model=self.response_model,
                messages=messages,
                temperature=0.7,
                max_tokens=500,
                tools=tools
            )

            result = {
                "text": response.choices[0].message.content,
                "model": self.response_model,
                "tokens": response.usage.total_tokens,
                "cost": self._calculate_cost(response.usage, self.response_model),
                "correlation_id": correlation_id
            }

            logger.info(
                "Response generated successfully",
                extra={
                    "correlation_id": correlation_id,
                    "tokens": result["tokens"],
                    "cost": result["cost"],
                    "response_length": len(result["text"])
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
        beliefs: List[Dict]
    ) -> Dict:
        """
        Check consistency using Claude-4.5-Haiku (cheaper for checks).

        Args:
            draft_response: Draft response to validate
            beliefs: List of belief dicts with 'text' and 'confidence'

        Returns:
            Dict with is_consistent, conflicts, explanation, tokens, and cost
        """
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
            f"- {b.get('text', b.get('summary', 'Unknown'))} (confidence: {b.get('confidence', 0.0)})"
            for b in beliefs
        ])

        prompt = f"""You are a consistency checker. Analyze if the draft response contradicts any beliefs.

Beliefs:
{belief_summary}

Draft Response:
{draft_response}

Respond with JSON:
{{
  "is_consistent": true/false,
  "conflicts": ["belief_id1", ...],
  "explanation": "brief explanation"
}}"""

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
            result["tokens"] = response.usage.total_tokens
            result["cost"] = self._calculate_cost(response.usage, self.consistency_model)
            result["correlation_id"] = correlation_id

            logger.info(
                "Consistency check completed",
                extra={
                    "correlation_id": correlation_id,
                    "is_consistent": result.get("is_consistent"),
                    "conflict_count": len(result.get("conflicts", [])),
                    "tokens": result["tokens"],
                    "cost": result["cost"]
                }
            )

            return result

        except json.JSONDecodeError as e:
            logger.error(
                "Failed to parse consistency check response",
                extra={
                    "correlation_id": correlation_id,
                    "error": str(e)
                },
                exc_info=True
            )
            # Return safe default
            return {
                "is_consistent": False,
                "conflicts": [],
                "explanation": "Failed to parse consistency check response",
                "tokens": 0,
                "cost": 0.0,
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

    def _calculate_cost(self, usage, model: str) -> float:
        """
        Calculate cost based on token usage and model pricing.

        Args:
            usage: Usage object from API response
            model: Model identifier

        Returns:
            Cost in USD (rounded to 6 decimal places)
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
            usage.prompt_tokens * pricing["input"] +
            usage.completion_tokens * pricing["output"]
        )
        return round(cost, 6)
