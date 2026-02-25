"""Scheduler for publishing posts at 19:00 MSK daily."""
import logging
from pathlib import Path
from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from pipeline.publisher import Publisher

logger = logging.getLogger(__name__)


class PublishScheduler:
    """Scheduler for automated post publishing."""

    def __init__(
        self,
        bot: Bot,
        channel_id: str,
        queue_dir: Path,
        published_dir: Path,
        publish_hour: int = 19
    ):
        """
        Initialize publish scheduler.

        Args:
            bot: Telegram bot instance
            channel_id: Telegram channel ID
            queue_dir: Directory with queued posts
            published_dir: Directory for published posts
            publish_hour: Hour to publish (0-23), default 19
        """
        self.bot = bot
        self.channel_id = channel_id
        self.publisher = Publisher(queue_dir, published_dir)
        self.scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
        self.publish_hour = publish_hour

    async def publish_next_post(self):
        """Publish next post from queue."""
        try:
            # Get next post
            result = await self.publisher.get_next_post()

            if not result:
                logger.info("No posts in queue, skipping publish")
                return

            queue_file, post_data = result
            final_post = post_data.get("final_post", "")

            if not final_post:
                logger.error(f"Empty post in {queue_file.name}, skipping")
                return

            # Send to channel (no link previews)
            await self.bot.send_message(
                chat_id=self.channel_id,
                text=final_post,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
            logger.info(f"Published post to {self.channel_id}")

            # Mark as published
            published_file = await self.publisher.mark_published(queue_file)
            logger.info(f"Moved to published: {published_file.name}")

        except Exception as e:
            logger.error(f"Failed to publish post: {e}", exc_info=True)

    def start(self):
        """Start the scheduler."""
        # Schedule daily at publish_hour:00 MSK
        self.scheduler.add_job(
            self.publish_next_post,
            trigger=CronTrigger(hour=self.publish_hour, minute=0, timezone="Europe/Moscow"),
            id="publish_post",
            name="Publish next post from queue",
            replace_existing=True
        )

        self.scheduler.start()
        logger.info(f"Scheduler started: publishing daily at {self.publish_hour}:00 MSK")

    def stop(self):
        """Stop the scheduler."""
        self.scheduler.shutdown()
        logger.info("Scheduler stopped")
