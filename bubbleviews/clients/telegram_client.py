import telegram
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from ..exceptions import APIError
import logging
import asyncio
import backoff

logger = logging.getLogger(__name__)

class TelegramClient:
    def __init__(self, config: dict):
        """Initialize Telegram client with configuration."""
        try:
            self.bot = telegram.Bot(token=config['token'])
            self.chat_id = config['chat_id']
        except Exception as e:
            raise APIError(f"Failed to initialize Telegram client: {str(e)}")

    @backoff.on_exception(
        backoff.expo,
        (asyncio.TimeoutError, telegram.error.TelegramError),
        max_tries=3,
        max_time=30
    )
    async def send_validation_message(self, news_item: dict, analysis: str) -> None:
        """Send a validation message to Telegram with retry logic."""
        try:
            # Format message for better readability
            message = f"""
📰 *{news_item['title']}*

McKenna's Analysis:
{analysis}

Reply with:
/post - to share across platforms
/skip - to skip this analysis
            """

            markup = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("Post", callback_data="post"),
                    InlineKeyboardButton("Don't Post", callback_data="skip")
                ]
            ])

            # Create a task for sending the message
            async def send_message():
                try:
                    await self.bot.send_message(
                        chat_id=self.chat_id,
                        text=message,
                        parse_mode='Markdown',
                        reply_markup=markup
                    )
                    logger.info("Successfully sent validation message to Telegram")
                except telegram.error.TimedOut as e:
                    logger.error(f"Telegram API timeout: {str(e)}")
                    raise asyncio.TimeoutError("Telegram API timeout")
                except telegram.error.TelegramError as e:
                    logger.error(f"Telegram API error: {str(e)}")
                    raise APIError(f"Telegram API error: {str(e)}")

            # Execute the send_message task with timeout
            async with asyncio.timeout(30):
                await send_message()

        except asyncio.TimeoutError:
            logger.error("Timeout sending Telegram message")
            raise APIError("Timeout sending Telegram message")
        except Exception as e:
            logger.error(f"Error sending Telegram message: {str(e)}")
            raise APIError(f"Failed to send Telegram message: {str(e)}")