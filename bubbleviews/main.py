import asyncio
import logging
from typing import Dict
from .config import load_config
from .clients.reddit_client import RedditClient
from .clients.telegram_client import TelegramClient
from .clients.twitter_client import TwitterClient
from .analysis.news_analyzer import NewsAnalyzer
from .ai.mckenna_analyzer import McKennaAnalyzer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class BubbleViews:
    def __init__(self):
        """Initialize BubbleViews application."""
        self.config = load_config()
        self.setup_clients()
        self.setup_analyzers()

    def setup_clients(self):
        """Initialize API clients with configuration."""
        try:
            self.reddit_client = RedditClient(self.config.reddit.model_dump())
            self.telegram_client = TelegramClient(self.config.telegram.model_dump())
            self.twitter_client = TwitterClient(self.config.twitter.model_dump())
        except Exception as e:
            logger.error(f"Failed to initialize clients: {str(e)}")
            raise

    def setup_analyzers(self):
        """Initialize analysis components."""
        try:
            self.news_analyzer = NewsAnalyzer(self.reddit_client)
            self.mckenna_analyzer = McKennaAnalyzer(self.config.openrouter.api_key)
        except Exception as e:
            logger.error(f"Failed to initialize analyzers: {str(e)}")
            raise

    async def process_news_item(self, news_item):
        """Process a single news item."""
        try:
            # Get McKenna's analysis
            analysis = await self.mckenna_analyzer.analyze_news(news_item.model_dump())

            # Send to Telegram for validation
            await self.telegram_client.send_validation_message(
                news_item.model_dump(),
                analysis
            )

            logger.info(f"Successfully processed news item: {news_item.title}")
            return True
        except Exception as e:
            logger.error(f"Error processing news item: {str(e)}")
            return False

    async def process_news_cycle(self):
        """Process one complete news cycle with proper async handling."""
        try:
            # Get top news
            news_items = await self.news_analyzer.get_top_news()
            if not news_items:
                logger.warning("No news items found in this cycle")
                return

            # Process each news item with individual timeouts
            for news_item in news_items:
                try:
                    async with asyncio.timeout(360):  # 6 minutes per item
                        success = await self.process_news_item(news_item)
                        if success:
                            # Wait before processing next item
                            await asyncio.sleep(300)  # 5 minutes
                except asyncio.TimeoutError:
                    logger.error(f"Timeout processing news item: {news_item.title}")
                    continue
                except Exception as e:
                    logger.error(f"Error in news cycle: {str(e)}")
                    continue

        except Exception as e:
            logger.error(f"Error in news cycle: {str(e)}")
            await asyncio.sleep(600)  # 10 minutes on error

    async def run(self):
        """Run the main application loop with improved error handling."""
        while True:
            try:
                await self.process_news_cycle()
                await asyncio.sleep(3600)  # 1 hour between cycles
            except Exception as e:
                logger.error(f"Error in main loop: {str(e)}")
                await asyncio.sleep(600)  # 10 minutes on error

def main():
    """Main entry point for the application."""
    try:
        app = BubbleViews()
        asyncio.run(app.run())
    except KeyboardInterrupt:
        logger.info("Application shutdown requested")
    except Exception as e:
        logger.error(f"Application crashed: {str(e)}")
        raise

if __name__ == "__main__":
    main()