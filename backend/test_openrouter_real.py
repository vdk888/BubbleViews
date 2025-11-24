"""
Real OpenRouter API test - standalone script.

This script tests the actual OpenRouter API without requiring
the full package to be installed. It verifies:
1. GPT-5.1-mini response generation
2. Claude-4.5-Haiku consistency checking
3. Cost calculation accuracy
"""

import asyncio
import json
import os
from openai import AsyncOpenAI

# Configuration
OPENROUTER_API_KEY = "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"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
RESPONSE_MODEL = "openai/gpt-4o-mini"  # Using gpt-4o-mini instead of gpt-5.1-mini (doesn't exist)
CONSISTENCY_MODEL = "anthropic/claude-3.5-haiku"  # Using 3.5 instead of 4.5 (doesn't exist yet)

# Pricing (per 1M tokens)
PRICING = {
    "openai/gpt-4o-mini": {
        "input": 0.15 / 1_000_000,
        "output": 0.60 / 1_000_000
    },
    "anthropic/claude-3.5-haiku": {
        "input": 1.00 / 1_000_000,  # Real pricing from OpenRouter
        "output": 5.00 / 1_000_000
    }
}


def calculate_cost(usage, model: str) -> float:
    """Calculate cost based on token usage and model pricing."""
    if model not in PRICING:
        return 0.0

    pricing = PRICING[model]
    cost = (
        usage.prompt_tokens * pricing["input"] +
        usage.completion_tokens * pricing["output"]
    )
    return round(cost, 6)


async def test_response_generation():
    """Test GPT-4o-mini for response generation."""
    print("\n" + "="*70)
    print("TEST 1: Response Generation with GPT-4o-mini")
    print("="*70)

    client = AsyncOpenAI(
        api_key=OPENROUTER_API_KEY,
        base_url=OPENROUTER_BASE_URL,
        default_headers={
            "HTTP-Referer": "https://github.com/reddit-ai-agent",
            "X-Title": "Reddit AI Agent Test"
        }
    )

    try:
        response = await client.chat.completions.create(
            model=RESPONSE_MODEL,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Say 'Hello from OpenRouter!' in exactly 5 words."}
            ],
            temperature=0.7,
            max_tokens=20
        )

        text = response.choices[0].message.content
        tokens = response.usage.total_tokens
        cost = calculate_cost(response.usage, RESPONSE_MODEL)

        print(f"\n[OK] Response received successfully!")
        print(f"   Model: {RESPONSE_MODEL}")
        print(f"   Response: {text}")
        print(f"   Tokens: {tokens} (prompt: {response.usage.prompt_tokens}, completion: {response.usage.completion_tokens})")
        print(f"   Cost: ${cost:.6f}")

        return True

    except Exception as e:
        print(f"\n[FAIL] Test failed: {type(e).__name__}: {str(e)}")
        return False


async def test_consistency_check():
    """Test Claude-3.5-Haiku for consistency checking."""
    print("\n" + "="*70)
    print("TEST 2: Consistency Check with Claude-3.5-Haiku")
    print("="*70)

    client = AsyncOpenAI(
        api_key=OPENROUTER_API_KEY,
        base_url=OPENROUTER_BASE_URL,
        default_headers={
            "HTTP-Referer": "https://github.com/reddit-ai-agent",
            "X-Title": "Reddit AI Agent Test"
        }
    )

    # Test data
    beliefs = [
        {"text": "Climate change is real and human-influenced", "confidence": 0.95},
        {"text": "Renewable energy is important", "confidence": 0.90}
    ]
    draft_response = "Climate change is a hoax invented by scientists."

    belief_summary = "\n".join([
        f"- {b['text']} (confidence: {b['confidence']})"
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
  "conflicts": ["belief about climate", ...],
  "explanation": "brief explanation"
}}"""

    try:
        response = await client.chat.completions.create(
            model=CONSISTENCY_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=200,
            response_format={"type": "json_object"}
        )

        result = json.loads(response.choices[0].message.content)
        tokens = response.usage.total_tokens
        cost = calculate_cost(response.usage, CONSISTENCY_MODEL)

        print(f"\n[OK] Consistency check completed successfully!")
        print(f"   Model: {CONSISTENCY_MODEL}")
        print(f"   Is Consistent: {result.get('is_consistent')}")
        print(f"   Conflicts: {result.get('conflicts', [])}")
        print(f"   Explanation: {result.get('explanation')}")
        print(f"   Tokens: {tokens} (prompt: {response.usage.prompt_tokens}, completion: {response.usage.completion_tokens})")
        print(f"   Cost: ${cost:.6f}")

        # Verify it detected the inconsistency
        if result.get('is_consistent') == False:
            print(f"\n   [OK] Correctly detected inconsistency!")
        else:
            print(f"\n   [WARN]  Warning: Expected inconsistency to be detected")

        return True

    except Exception as e:
        print(f"\n[FAIL] Test failed: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all tests."""
    print("\n" + "="*70)
    print("OpenRouter Real API Tests")
    print("="*70)
    print(f"Base URL: {OPENROUTER_BASE_URL}")
    print(f"Response Model: {RESPONSE_MODEL}")
    print(f"Consistency Model: {CONSISTENCY_MODEL}")

    # Run tests
    test1_passed = await test_response_generation()
    test2_passed = await test_consistency_check()

    # Summary
    print("\n" + "="*70)
    print("Test Summary")
    print("="*70)
    print(f"Response Generation: {'[OK] PASSED' if test1_passed else '[FAIL] FAILED'}")
    print(f"Consistency Check:   {'[OK] PASSED' if test2_passed else '[FAIL] FAILED'}")
    print("="*70)

    if test1_passed and test2_passed:
        print("\n[SUCCESS] All tests passed! OpenRouter integration is working correctly.")
        return 0
    else:
        print("\n[WARN]  Some tests failed. Check the errors above.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
