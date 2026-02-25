"""Configuration loader from environment variables."""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
load_dotenv()


class Settings:
    """Application settings."""

    def __init__(self):
        self.bot_token = os.getenv("BOT_TOKEN")
        self.channel_id = os.getenv("CHANNEL_ID")
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
        self.tavily_api_key = os.getenv("TAVILY_API_KEY")
        self.admin_telegram_id = os.getenv("ADMIN_TELEGRAM_ID")
        self.publish_hour = int(os.getenv("PUBLISH_HOUR", "19"))
        self.claude_model = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
        self.topic_config = os.getenv("TOPIC_CONFIG", "topic.json")
        self.log_level = os.getenv("LOG_LEVEL", "INFO")

        # Paths
        self.base_dir = Path(__file__).parent
        self.topic_config_path = self.base_dir / self.topic_config
        self.data_dir = self.base_dir / "data"
        self.queue_dir = self.data_dir / "queue"
        self.published_dir = self.data_dir / "published"
        self.drafts_dir = self.data_dir / "drafts"
        self.logs_dir = self.data_dir / "logs"
        self.prompts_dir = self.base_dir / "prompts"

    def validate(self):
        """Validate that all required settings are present."""
        required = [
            "bot_token",
            "channel_id",
            "anthropic_api_key",
            "tavily_api_key",
            "admin_telegram_id"
        ]
        missing = [field for field in required if not getattr(self, field)]
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")


def load_settings() -> Settings:
    """Load and validate application settings."""
    settings = Settings()
    settings.validate()
    return settings
