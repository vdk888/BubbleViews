import requests
from typing import Dict
from ..exceptions import APIError
import logging
import asyncio
import json

logger = logging.getLogger(__name__)

class McKennaAnalyzer:
    def __init__(self, api_key: str):
        """Initialize McKenna analyzer with OpenRouter API key."""
        self.api_key = api_key
        self.api_url = "https://openrouter.ai/api/v1/chat/completions"

    async def analyze_news(self, news_item: Dict) -> str:
        """
        Generate Terence McKenna-style analysis for a news item.

        Args:
            news_item: Dictionary containing news item data

        Returns:
            str: Generated analysis
        """
        try:
            # Enhanced prompt for better McKenna-style analysis
            prompt = f"""You are channeling Terence McKenna, the renowned ethnobotanist, psychonaut, and philosophical thinker. 
            Analyze this news story through your unique perspective, incorporating:

            1. The concept of timewave zero and the acceleration of novelty
            2. The archaic revival and return to shamanic consciousness
            3. The role of psychedelics in human evolution
            4. Your theories about language, consciousness, and technology
            5. Your characteristic speaking style, including your unique vocabulary and cadence

            News Story: {news_item['title']}
            Source: r/{news_item['subreddit']}

            Provide a deep, McKenna-style analysis that connects this current event to your broader theories about human consciousness, 
            technology, and the approaching transcendental object at the end of time. Use your characteristic mix of scientific terminology, 
            philosophical concepts, and psychedelic insights."""

            async with asyncio.timeout(30):  # Add timeout for API calls
                response = requests.post(
                    self.api_url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://github.com/BubbleViews",  # Identifier for API usage
                        "X-Title": "BubbleViews News Analyzer"  # Application identifier
                    },
                    json={
                        "model": "gemini-2.0-flash",
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.7,  # Add some creativity while maintaining coherence
                        "max_tokens": 1000,  # Ensure we get a detailed analysis
                    }
                )

                if response.status_code != 200:
                    error_msg = f"OpenRouter API request failed with status {response.status_code}: {response.text}"
                    logger.error(error_msg)
                    raise APIError(error_msg)

                try:
                    content = response.json()['choices'][0]['message']['content']
                    if not content.strip():
                        raise APIError("Empty response from OpenRouter API")
                    return content
                except (KeyError, json.JSONDecodeError) as e:
                    raise APIError(f"Invalid response format from OpenRouter API: {str(e)}")

        except asyncio.TimeoutError:
            error_msg = "Timeout while calling OpenRouter API"
            logger.error(error_msg)
            raise APIError(error_msg)
        except Exception as e:
            logger.error(f"Error generating McKenna analysis: {str(e)}")
            raise APIError(f"Failed to generate analysis: {str(e)}")