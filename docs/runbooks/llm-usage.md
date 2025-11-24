# LLM Usage Runbook

## Overview

This runbook covers how to use the OpenRouter LLM client for response generation and consistency checking in the Reddit AI Agent.

## Architecture

The agent uses a dual-model strategy via OpenRouter:

- **GPT-5.1-mini**: Fast, cheap response generation ($0.15/1M input, $0.60/1M output)
- **Claude-4.5-Haiku**: Accurate, cheap consistency checking ($0.25/1M input, $1.25/1M output)

All LLM interactions go through the `ILLMClient` interface for testability and future model swapping.

## Usage

### Basic Response Generation

```python
from app.services.llm_client import OpenRouterClient

client = OpenRouterClient()

response = await client.generate_response(
    system_prompt="You are a helpful Reddit bot that engages thoughtfully.",
    context={
        "user_interests": ["technology", "AI"],
        "recent_posts": [...],
        "relevant_beliefs": [...]
    },
    user_message="Should I learn Rust or Go for systems programming?"
)

print(response['text'])        # Generated response
print(response['tokens'])      # Total tokens used
print(response['cost'])        # Cost in USD
print(response['correlation_id'])  # For log tracing
```

### Consistency Checking

```python
# Check if draft response aligns with agent's beliefs
consistency = await client.check_consistency(
    draft_response="Rust is definitely better than Go for all use cases.",
    beliefs=[
        {
            "text": "Rust has stronger memory safety guarantees",
            "confidence": 0.9
        },
        {
            "text": "Go is simpler and better for quick development",
            "confidence": 0.8
        }
    ]
)

if not consistency['is_consistent']:
    print(f"Conflicts found: {consistency['conflicts']}")
    print(f"Explanation: {consistency['explanation']}")
    # Regenerate or adjust response
```

### With Tool Use (Function Calling)

```python
tools = [
    {
        "type": "function",
        "function": {
            "name": "search_beliefs",
            "description": "Search agent's belief graph",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}}
                }
            }
        }
    }
]

response = await client.generate_response(
    system_prompt="You are a helpful assistant.",
    context={},
    user_message="What are my beliefs about climate change?",
    tools=tools
)
```

## Model Selection

Models are configured in `.env`:

```env
RESPONSE_MODEL=openai/gpt-5.1-mini
CONSISTENCY_MODEL=anthropic/claude-4.5-haiku
```

### Available Models

All OpenRouter models are supported. Popular options:

| Model | Use Case | Cost (per 1M tokens) |
|-------|----------|----------------------|
| openai/gpt-5.1-mini | Fast responses | $0.15 input, $0.60 output |
| anthropic/claude-4.5-haiku | Consistency checks | $0.25 input, $1.25 output |
| anthropic/claude-3.5-sonnet | Complex reasoning | $3.00 input, $15.00 output |
| openai/gpt-4-turbo | High quality | $10.00 input, $30.00 output |

### Switching Models

To switch models without code changes:

1. Update `.env`:
   ```env
   RESPONSE_MODEL=anthropic/claude-3.5-sonnet
   ```

2. Restart the application:
   ```bash
   systemctl restart reddit-agent
   ```

3. Monitor costs in logs:
   ```bash
   grep "cost" /var/log/reddit-agent/app.log | tail -100
   ```

## Cost Optimization

### Strategies

1. **Use cheap models for routine tasks**
   - GPT-5.1-mini for most responses
   - Claude-4.5-Haiku for consistency checks

2. **Cache frequently used prompts**
   - Store common belief summaries
   - Reuse context when possible

3. **Limit token usage**
   - Set appropriate `max_tokens` (default: 500 for responses, 200 for checks)
   - Use concise system prompts

4. **Batch consistency checks**
   - Check multiple drafts together when possible
   - Only check responses that will be posted

### Cost Tracking

Every LLM call includes cost information:

```python
response = await client.generate_response(...)
print(f"Cost: ${response['cost']:.6f}")
```

Aggregate costs from logs:

```bash
# Daily cost
grep "cost" /var/log/reddit-agent/app.log \
  | grep $(date +%Y-%m-%d) \
  | awk '{sum+=$NF} END {print "Total: $" sum}'
```

### Budget Alerts

Set up monitoring for daily costs:

```python
# In your monitoring system
DAILY_BUDGET = 0.50  # $0.50/day limit

if daily_cost > DAILY_BUDGET:
    send_alert(f"LLM costs exceeded budget: ${daily_cost}")
    # Optionally pause agent
```

## Token Usage Monitoring

### Understanding Token Counts

- **Input tokens**: System prompt + context + user message
- **Output tokens**: Generated response
- **Total tokens**: Input + output

Typical usage:
- Simple response: ~200-500 tokens ($0.0001)
- Consistency check: ~100-200 tokens ($0.00005)

### Reducing Token Usage

1. **Compress context**:
   ```python
   # Bad: Include full belief text
   context = {"beliefs": [b.full_text for b in beliefs]}

   # Good: Summarize beliefs
   context = {"beliefs": [b.summary for b in beliefs]}
   ```

2. **Limit history**:
   ```python
   # Only include last 5 interactions
   context["history"] = recent_interactions[:5]
   ```

3. **Use shorter prompts**:
   ```python
   # Bad: Verbose prompt
   system_prompt = """
   You are a highly intelligent and thoughtful Reddit bot
   that engages in meaningful discussions across various topics...
   """

   # Good: Concise prompt
   system_prompt = "You are a thoughtful Reddit bot. Be concise and helpful."
   ```

## Error Handling

### Retry Logic

The client automatically retries with exponential backoff:

- **Rate limits**: Retry up to 3 times with exponential backoff (1s, 2s, 4s)
- **Connection errors**: Same retry strategy
- **Other API errors**: Retry once

### Common Errors

#### 1. Rate Limit Exceeded

```
RateLimitError: Rate limit exceeded
```

**Solution**: Wait for retry or reduce request frequency.

#### 2. Invalid API Key

```
AuthenticationError: Invalid API key
```

**Solution**: Check `OPENROUTER_API_KEY` in `.env`.

#### 3. Model Not Found

```
NotFoundError: Model not found
```

**Solution**: Verify model name in OpenRouter catalog.

#### 4. Timeout

```
APIConnectionError: Request timed out
```

**Solution**: Check network connectivity. OpenRouter may be down.

### Handling Errors in Code

```python
from openai import APIError, RateLimitError

try:
    response = await client.generate_response(...)
except RateLimitError:
    # Wait and retry later
    await asyncio.sleep(60)
    response = await client.generate_response(...)
except APIError as e:
    # Log error and use fallback
    logger.error(f"LLM API error: {e}")
    response = {"text": "[Error generating response]"}
```

## Observability

### Structured Logging

Every LLM call logs structured data:

```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "level": "INFO",
  "message": "Response generated successfully",
  "correlation_id": "abc-123-def-456",
  "model": "openai/gpt-5.1-mini",
  "tokens": 342,
  "cost": 0.000154,
  "response_length": 250
}
```

### Correlation IDs

Each request gets a unique correlation ID for tracing:

```bash
# Trace a specific request
grep "abc-123-def-456" /var/log/reddit-agent/app.log
```

### Metrics to Monitor

1. **Token usage trends**
   ```bash
   grep "tokens" app.log | awk '{sum+=$10} END {print sum}'
   ```

2. **Cost per day**
   ```bash
   grep "cost" app.log | grep $(date +%Y-%m-%d) | awk '{sum+=$12} END {print sum}'
   ```

3. **Error rates**
   ```bash
   grep "Failed to generate" app.log | wc -l
   ```

4. **Average response time**
   ```bash
   grep "Response generated" app.log | awk '{sum+=$15} END {print sum/NR}'
   ```

## Troubleshooting

### Issue: High Costs

**Symptoms**: Daily costs exceeding $1

**Investigation**:
```bash
# Find most expensive calls
grep "cost" app.log | sort -k12 -rn | head -20
```

**Solutions**:
- Switch to cheaper models
- Reduce max_tokens
- Cache more aggressively
- Limit context size

### Issue: Slow Response Times

**Symptoms**: Requests taking >5 seconds

**Investigation**:
```bash
# Check response times
grep "Response generated" app.log | awk '{print $15}'
```

**Solutions**:
- Use faster models (GPT-5.1-mini)
- Reduce max_tokens
- Check OpenRouter status
- Consider caching

### Issue: Consistency Checks Failing

**Symptoms**: Most responses marked inconsistent

**Investigation**:
```python
# Check belief quality
consistency = await client.check_consistency(
    draft_response="...",
    beliefs=[...]
)
print(consistency['explanation'])
```

**Solutions**:
- Update beliefs to be more specific
- Adjust consistency prompt
- Use higher confidence threshold
- Review belief graph for conflicts

### Issue: JSON Parsing Errors

**Symptoms**: `JSONDecodeError` in consistency checks

**Investigation**:
```bash
grep "Failed to parse" app.log
```

**Solutions**:
- Model not returning valid JSON
- Add explicit JSON format instructions
- Use `response_format={"type": "json_object"}`
- Fall back to non-JSON parsing

## Testing

### Running Tests

```bash
cd backend
python tests/test_openrouter.py
```

### Writing Tests

```python
import pytest
from app.services.llm_client import OpenRouterClient

@pytest.mark.asyncio
async def test_generate_response():
    client = OpenRouterClient()
    response = await client.generate_response(
        system_prompt="Test prompt",
        context={},
        user_message="Test message"
    )

    assert "text" in response
    assert response["tokens"] > 0
    assert response["cost"] >= 0
```

### Mocking for Unit Tests

```python
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_with_mock():
    mock_response = {
        "text": "Mocked response",
        "tokens": 100,
        "cost": 0.0001
    }

    with patch.object(OpenRouterClient, "generate_response", return_value=mock_response):
        client = OpenRouterClient()
        response = await client.generate_response("", {}, "")
        assert response["text"] == "Mocked response"
```

## Best Practices

1. **Always track costs**: Log every LLM call with cost information
2. **Use correlation IDs**: Include in all logs for request tracing
3. **Set reasonable timeouts**: Don't wait forever for responses
4. **Handle errors gracefully**: Always have fallback behavior
5. **Monitor token usage**: Watch for unexpected spikes
6. **Test before deploying**: Verify models work with test script
7. **Cache when possible**: Reuse responses for similar queries
8. **Use cheap models**: Reserve expensive models for complex tasks
9. **Limit context size**: Only include necessary information
10. **Review costs weekly**: Adjust strategy based on usage patterns

## Security

1. **Never log API keys**: Use `OPENROUTER_API_KEY` from environment
2. **Rotate keys regularly**: Update keys every 90 days
3. **Use read-only keys**: If OpenRouter supports it
4. **Monitor for abuse**: Watch for unusual usage patterns
5. **Rate limit internally**: Prevent runaway costs

## References

- [OpenRouter Documentation](https://openrouter.ai/docs)
- [OpenRouter Pricing](https://openrouter.ai/models)
- [OpenAI API Reference](https://platform.openai.com/docs/api-reference) (compatible format)
- [Claude API Reference](https://docs.anthropic.com/claude/reference)

## Support

For issues with:
- **OpenRouter API**: contact@openrouter.ai
- **Agent implementation**: Check GitHub issues
- **Cost optimization**: Review this runbook's optimization section
