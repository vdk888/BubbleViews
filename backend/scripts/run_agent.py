"""
Run Agent Loop CLI Script

Starts the autonomous Reddit AI agent loop for a specific persona.
Monitors Reddit, generates responses, and posts or enqueues content.

Usage:
    python scripts/run_agent.py --persona-id YOUR_PERSONA_UUID

Requirements:
    - Valid .env file with Reddit and OpenRouter credentials
    - Persona must exist in database
    - Target subreddits configured for the persona
"""

import asyncio
import argparse
import logging
import os
import signal
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dotenv import load_dotenv

from app.core.config import settings
from app.core.database import async_session_maker
from app.services.reddit_client import AsyncPRAWClient
from app.services.llm_client import OpenRouterClient
from app.services.memory_store import SQLiteMemoryStore
from app.services.retrieval import RetrievalCoordinator
from app.services.moderation import ModerationService
from app.agent.loop import AgentLoop

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('agent_loop.log')
    ]
)

logger = logging.getLogger(__name__)


def parse_args():
    """
    Parse command line arguments.

    Returns:
        Parsed arguments with persona_id and optional configuration
    """
    parser = argparse.ArgumentParser(
        description='Run the autonomous Reddit AI agent loop',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Start agent for a specific persona
    python scripts/run_agent.py --persona-id 8a48aee3-1359-4a5e-a052-6523aca2d0b1

    # Start agent with custom interval
    python scripts/run_agent.py --persona-id YOUR_UUID --interval 120

    # Start agent with custom response probability
    python scripts/run_agent.py --persona-id YOUR_UUID --probability 0.5

Environment Variables:
    REDDIT_CLIENT_ID       - Reddit app client ID
    REDDIT_CLIENT_SECRET   - Reddit app client secret
    REDDIT_USER_AGENT      - Reddit user agent string
    REDDIT_USERNAME        - Reddit account username
    REDDIT_PASSWORD        - Reddit account password
    OPENROUTER_API_KEY     - OpenRouter API key
    DATABASE_URL           - Database connection string

    See .env.example for full configuration options.
        """
    )

    parser.add_argument(
        '--persona-id',
        type=str,
        required=True,
        help='UUID of the persona to run the agent for'
    )

    parser.add_argument(
        '--interval',
        type=int,
        default=60,
        help='Seconds between perception cycles (default: 60)'
    )

    parser.add_argument(
        '--max-posts',
        type=int,
        default=5,
        help='Maximum posts to process per cycle (default: 5)'
    )

    parser.add_argument(
        '--probability',
        type=float,
        default=0.3,
        help='Probability of responding to eligible posts (default: 0.3)'
    )

    parser.add_argument(
        '--env-file',
        type=str,
        default='.env',
        help='Path to .env file (default: .env)'
    )

    return parser.parse_args()


async def initialize_services():
    """
    Initialize all required services with proper configuration.

    Returns:
        Tuple of (reddit_client, llm_client, memory_store, retrieval, moderation)

    Raises:
        ValueError: If required environment variables are missing
        ConnectionError: If service initialization fails
    """
    logger.info("Initializing services...")

    # Validate required environment variables
    required_vars = [
        'REDDIT_CLIENT_ID',
        'REDDIT_CLIENT_SECRET',
        'REDDIT_USER_AGENT',
        'REDDIT_USERNAME',
        'REDDIT_PASSWORD',
        'OPENROUTER_API_KEY',
    ]

    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        raise ValueError(
            f"Missing required environment variables: {', '.join(missing_vars)}\n"
            f"Please check your .env file and ensure all credentials are set."
        )

    # Initialize Reddit client
    try:
        reddit_client = AsyncPRAWClient(
            client_id=os.getenv('REDDIT_CLIENT_ID'),
            client_secret=os.getenv('REDDIT_CLIENT_SECRET'),
            user_agent=os.getenv('REDDIT_USER_AGENT'),
            username=os.getenv('REDDIT_USERNAME'),
            password=os.getenv('REDDIT_PASSWORD'),
        )
        logger.info("Reddit client initialized")
    except Exception as e:
        raise ConnectionError(f"Failed to initialize Reddit client: {e}")

    # Initialize LLM client
    try:
        llm_client = OpenRouterClient()
        logger.info("LLM client initialized")
    except Exception as e:
        raise ConnectionError(f"Failed to initialize LLM client: {e}")

    # Initialize memory store
    try:
        memory_store = SQLiteMemoryStore(session_maker=async_session_maker)
        logger.info("Memory store initialized")
    except Exception as e:
        raise ConnectionError(f"Failed to initialize memory store: {e}")

    # Initialize retrieval coordinator
    try:
        retrieval = RetrievalCoordinator(
            memory_store=memory_store,
            llm_client=llm_client
        )
        logger.info("Retrieval coordinator initialized")
    except Exception as e:
        raise ConnectionError(f"Failed to initialize retrieval coordinator: {e}")

    # Initialize moderation service
    try:
        moderation = ModerationService(session_maker=async_session_maker)
        logger.info("Moderation service initialized")
    except Exception as e:
        raise ConnectionError(f"Failed to initialize moderation service: {e}")

    return reddit_client, llm_client, memory_store, retrieval, moderation


async def main():
    """
    Main entry point for agent loop.

    Sets up services, initializes agent loop, and handles graceful shutdown.
    """
    args = parse_args()

    # Load environment variables
    env_file = Path(args.env_file)
    if not env_file.exists():
        logger.error(f"Environment file not found: {env_file}")
        logger.error("Please copy .env.example to .env and configure your credentials")
        sys.exit(1)

    load_dotenv(dotenv_path=env_file)
    logger.info(f"Loaded environment from {env_file}")

    # Print banner
    print("=" * 80)
    print("Reddit AI Agent - Autonomous Loop")
    print("=" * 80)
    print(f"Persona ID: {args.persona_id}")
    print(f"Interval: {args.interval}s")
    print(f"Max posts per cycle: {args.max_posts}")
    print(f"Response probability: {args.probability}")
    print("=" * 80)
    print()

    # Initialize services
    try:
        reddit_client, llm_client, memory_store, retrieval, moderation = await initialize_services()
    except Exception as e:
        logger.error(f"Failed to initialize services: {e}")
        sys.exit(1)

    # Verify persona exists
    try:
        persona = await memory_store.get_persona(args.persona_id)
        logger.info(f"Loaded persona: {persona['reddit_username']} ({persona['display_name']})")
        print(f"Running agent for: u/{persona['reddit_username']}")
        print()

        # Check target subreddits
        config = persona.get('config', {})
        target_subreddits = config.get('target_subreddits', [])
        if not target_subreddits:
            logger.warning("No target_subreddits configured for this persona!")
            logger.warning("The agent will not monitor any subreddits.")
            logger.warning("Please configure target_subreddits in the Settings UI.")
            print("WARNING: No target subreddits configured. Agent will idle.")
            print("Please configure target subreddits in the dashboard Settings page.")
            print()
        else:
            logger.info(f"Target subreddits: {', '.join(target_subreddits)}")
            print(f"Monitoring subreddits: {', '.join(target_subreddits)}")
            print()
    except ValueError as e:
        logger.error(f"Persona not found: {e}")
        logger.error("Please create a persona in the dashboard first")
        sys.exit(1)

    # Create agent loop
    agent_loop = AgentLoop(
        reddit_client=reddit_client,
        llm_client=llm_client,
        memory_store=memory_store,
        retrieval=retrieval,
        moderation=moderation,
        interval_seconds=args.interval,
        max_posts_per_cycle=args.max_posts,
        response_probability=args.probability,
    )

    # Create stop event for graceful shutdown
    stop_event = asyncio.Event()

    # Setup signal handlers for graceful shutdown
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        print()
        print("Shutting down gracefully... (press Ctrl+C again to force)")
        stop_event.set()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Run agent loop
    try:
        logger.info("Starting agent loop...")
        print("Agent loop started. Press Ctrl+C to stop.")
        print("-" * 80)
        print()

        await agent_loop.run(
            persona_id=args.persona_id,
            stop_event=stop_event
        )

    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error(f"Agent loop crashed: {e}", exc_info=True)
        sys.exit(1)
    finally:
        # Cleanup
        logger.info("Cleaning up resources...")
        await reddit_client.close()
        logger.info("Reddit client closed")

        print()
        print("-" * 80)
        print("Agent loop stopped.")
        print("=" * 80)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nForced shutdown.")
        sys.exit(0)
