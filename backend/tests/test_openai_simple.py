"""Simple test to diagnose OpenAI client issues"""
import asyncio
from openai import AsyncOpenAI

async def test():
    print("Testing AsyncOpenAI initialization...")
    try:
        client = AsyncOpenAI(
            api_key="test-key",
            base_url="https://openrouter.ai/api/v1"
        )
        print("✓ Client created successfully")
        print(f"Client type: {type(client)}")
        print(f"Base URL: {client.base_url}")
    except Exception as e:
        print(f"✗ Error: {e}")
        print(f"Error type: {type(e).__name__}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())
