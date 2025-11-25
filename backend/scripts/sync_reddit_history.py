"""
Sync Reddit history for a persona.

Fetches recent posts and comments from Reddit for a persona's account
and imports them into the interactions table.

Usage:
    python scripts/sync_reddit_history.py <persona_id>
    python scripts/sync_reddit_history.py --username <reddit_username>
"""

import asyncio
import sys
import os
import argparse
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import select
from app.core.database import async_session_maker
from app.models.persona import Persona
from app.models.interaction import Interaction

# Check for asyncpraw
try:
    import asyncpraw
except ImportError:
    print("Error: asyncpraw is required. Install with: pip install asyncpraw")
    sys.exit(1)


async def get_persona(persona_id: str = None, username: str = None):
    """Get persona by ID or username."""
    async with async_session_maker() as session:
        if persona_id:
            stmt = select(Persona).where(Persona.id == persona_id)
        elif username:
            stmt = select(Persona).where(Persona.reddit_username == username)
        else:
            raise ValueError("Must provide persona_id or username")

        result = await session.execute(stmt)
        return result.scalar_one_or_none()


async def sync_reddit_history(persona_id: str, reddit_username: str, limit: int = 50):
    """
    Sync Reddit history for a persona.

    Fetches recent submissions and comments from Reddit and stores them
    in the interactions table.
    """
    from app.core.config import settings

    # Check Reddit credentials
    if not settings.reddit_client_id or not settings.reddit_client_secret:
        print("Error: Reddit API credentials not configured in .env")
        print("Required: REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET")
        return

    print(f"\nConnecting to Reddit API...")

    # Create Reddit client
    reddit = asyncpraw.Reddit(
        client_id=settings.reddit_client_id,
        client_secret=settings.reddit_client_secret,
        user_agent=f"BubbleViews/{settings.app_name} sync script"
    )

    try:
        # Get redditor
        redditor = await reddit.redditor(reddit_username)

        # Check if user exists
        try:
            await redditor.load()
            print(f"Found Reddit user: u/{reddit_username}")
        except Exception as e:
            print(f"Error: Could not find Reddit user u/{reddit_username}: {e}")
            return

        async with async_session_maker() as session:
            # Get existing reddit_ids to avoid duplicates
            stmt = select(Interaction.reddit_id).where(Interaction.persona_id == persona_id)
            result = await session.execute(stmt)
            existing_ids = set(row[0] for row in result.fetchall())
            print(f"Found {len(existing_ids)} existing interactions in database")

            imported_count = 0
            skipped_count = 0

            # Fetch comments
            print(f"\nFetching recent comments...")
            async for comment in redditor.comments.new(limit=limit):
                reddit_id = f"t1_{comment.id}"

                if reddit_id in existing_ids:
                    skipped_count += 1
                    continue

                interaction = Interaction(
                    persona_id=persona_id,
                    content=comment.body,
                    interaction_type="comment",
                    reddit_id=reddit_id,
                    subreddit=comment.subreddit.display_name,
                    parent_id=comment.parent_id,
                    created_at=datetime.fromtimestamp(comment.created_utc),
                    metadata={
                        "karma": comment.score,
                        "awards": len(comment.all_awardings) if hasattr(comment, 'all_awardings') else 0,
                        "permalink": comment.permalink,
                        "synced_from_reddit": True
                    }
                )
                session.add(interaction)
                imported_count += 1
                print(f"  + Comment in r/{comment.subreddit.display_name}: {comment.body[:50]}...")

            # Fetch submissions (posts)
            print(f"\nFetching recent submissions...")
            async for submission in redditor.submissions.new(limit=limit):
                reddit_id = f"t3_{submission.id}"

                if reddit_id in existing_ids:
                    skipped_count += 1
                    continue

                content = submission.title
                if submission.selftext:
                    content += f"\n\n{submission.selftext}"

                interaction = Interaction(
                    persona_id=persona_id,
                    content=content,
                    interaction_type="post",
                    reddit_id=reddit_id,
                    subreddit=submission.subreddit.display_name,
                    parent_id=None,
                    created_at=datetime.fromtimestamp(submission.created_utc),
                    metadata={
                        "karma": submission.score,
                        "awards": len(submission.all_awardings) if hasattr(submission, 'all_awardings') else 0,
                        "comments": submission.num_comments,
                        "permalink": submission.permalink,
                        "synced_from_reddit": True
                    }
                )
                session.add(interaction)
                imported_count += 1
                print(f"  + Post in r/{submission.subreddit.display_name}: {submission.title[:50]}...")

            await session.commit()

            print(f"\n{'='*60}")
            print(f"Sync completed!")
            print(f"  Imported: {imported_count} new interactions")
            print(f"  Skipped: {skipped_count} (already in database)")
            print(f"{'='*60}")

    finally:
        await reddit.close()


async def main():
    parser = argparse.ArgumentParser(description="Sync Reddit history for a persona")
    parser.add_argument("persona_id", nargs="?", help="Persona UUID")
    parser.add_argument("--username", "-u", help="Reddit username to look up persona")
    parser.add_argument("--limit", "-l", type=int, default=50, help="Max items to fetch per type (default: 50)")

    args = parser.parse_args()

    if not args.persona_id and not args.username:
        parser.print_help()
        print("\nError: Must provide persona_id or --username")
        sys.exit(1)

    print("=" * 60)
    print("Reddit History Sync")
    print("=" * 60)

    # Get persona
    persona = await get_persona(persona_id=args.persona_id, username=args.username)

    if not persona:
        print(f"Error: Persona not found")
        sys.exit(1)

    print(f"\nPersona: {persona.display_name}")
    print(f"Reddit Username: {persona.reddit_username}")
    print(f"Persona ID: {persona.id}")

    await sync_reddit_history(
        persona_id=persona.id,
        reddit_username=persona.reddit_username,
        limit=args.limit
    )


if __name__ == "__main__":
    asyncio.run(main())
