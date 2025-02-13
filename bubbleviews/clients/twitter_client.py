import tweepy
from ..exceptions import APIError
import logging

logger = logging.getLogger(__name__)

class TwitterClient:
    def __init__(self, config: dict):
        """Initialize Twitter client with configuration."""
        try:
            self.client = tweepy.Client(
                bearer_token=config['bearer_token'],
                consumer_key=config['api_key'],
                consumer_secret=config['api_secret'],
                access_token=config['access_token'],
                access_token_secret=config['access_token_secret']
            )
        except Exception as e:
            raise APIError(f"Failed to initialize Twitter client: {str(e)}")

    async def post_tweet(self, text: str) -> None:
        """Post a tweet."""
        try:
            # Ensure tweet is within character limit
            if len(text) > 280:
                text = text[:277] + "..."
            
            self.client.create_tweet(text=text)
            logger.info("Successfully posted tweet")
        except Exception as e:
            logger.error(f"Error posting tweet: {str(e)}")
            raise APIError(f"Failed to post tweet: {str(e)}")
