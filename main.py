"""Main entry point for the Telegram bot."""
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from config import load_settings
from bot import handlers
from bot.middlewares import AdminOnlyMiddleware
from llm.client import LLMClient
from research.tavily_client import TavilySearchClient
from pipeline.orchestrator import PipelineOrchestrator
from pipeline.content_planner import ContentPlanner
from scheduler.publish_job import PublishScheduler
from utils.topic_config import load_topic_config
from utils.logger import setup_logging, get_logger


async def main():
    """Main function to start the bot."""
    settings = load_settings()
    setup_logging(settings.log_level)
    logger = get_logger("main")
    logger.info("settings_loaded", model=settings.claude_model, log_level=settings.log_level)

    bot = Bot(token=settings.bot_token)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # Initialize clients
    llm_client = LLMClient(
        api_key=settings.anthropic_api_key,
        model=settings.claude_model
    )
    tavily_client = TavilySearchClient(api_key=settings.tavily_api_key)
    logger.info("clients_initialized", model=settings.claude_model)

    # Load topic configuration
    topic = load_topic_config(settings.topic_config_path)
    logger.info("topic_loaded", channel=topic.channel_name)

    # Initialize pipeline orchestrator
    orchestrator = PipelineOrchestrator(
        llm_client=llm_client,
        tavily_client=tavily_client,
        prompts_dir=settings.prompts_dir,
        queue_dir=settings.queue_dir,
        published_dir=settings.published_dir,
        drafts_dir=settings.drafts_dir,
        logs_dir=settings.logs_dir,
        topic=topic,
    )
    logger.info("orchestrator_initialized")

    # Initialize content planner
    content_planner = ContentPlanner(
        llm_client=llm_client,
        tavily_client=tavily_client,
        prompt_path=settings.prompts_dir / "content_planner.md",
        plans_dir=settings.data_dir / "content_plans",
        topic=topic,
    )
    logger.info("content_planner_initialized")

    # Initialize scheduler
    scheduler = PublishScheduler(
        bot=bot,
        channel_id=settings.channel_id,
        queue_dir=settings.queue_dir,
        published_dir=settings.published_dir,
        publish_hour=settings.publish_hour
    )
    scheduler.start()
    logger.info("scheduler_started", publish_hour=settings.publish_hour)

    # Set global references in handlers
    handlers.orchestrator = orchestrator
    handlers.publish_scheduler = scheduler
    handlers.content_planner = content_planner
    handlers.topic = topic

    # Set bot commands menu
    await bot.set_my_commands([
        BotCommand(command="newpost", description="Создать новый пост через пайплайн"),
        BotCommand(command="autopost", description="Авто-пост из контент-плана"),
        BotCommand(command="contentplan", description="Сгенерировать контент-план на неделю"),
        BotCommand(command="editplan", description="Редактировать текущий контент-план"),
        BotCommand(command="publish", description="Опубликовать следующий пост из очереди"),
        BotCommand(command="queue", description="Показать очередь постов"),
        BotCommand(command="cancel", description="Отменить текущее действие"),
    ])
    logger.info("bot_commands_set")

    # Register middleware and router
    dp.message.middleware(AdminOnlyMiddleware(settings.admin_telegram_id))
    dp.include_router(handlers.router)

    logger.info("bot_starting", bot_username="ai_pmf_bot")

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        scheduler.stop()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
