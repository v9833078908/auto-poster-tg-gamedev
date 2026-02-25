"""Topic configuration loader."""
import json
from pathlib import Path
from typing import Dict, Any, List


class TopicConfig:
    """Holds all topic-specific configuration loaded from a JSON file."""

    def __init__(self, config: Dict[str, Any]):
        self.channel_name: str = config["channel_name"]
        self.channel_description: str = config["channel_description"]

        # content_types: [{"key": "tool_review", "label": "🔧 Обзор инструмента"}, ...]
        self.content_types: List[Dict] = config["content_types"]

        # audiences: [{"key": "indie", "label": "🎯 Инди студии"}, ...]
        self.audiences: List[Dict] = config["audiences"]

        # search_queries per content type key
        self.search_queries: Dict[str, str] = config["search_queries"]

        # generic context appended to all search queries
        self.search_context: str = config.get("search_context", "")

        # list of queries used for content plan research
        self.research_queries: List[str] = config["research_queries"]

    # Convenience helpers

    def content_type_label(self, key: str) -> str:
        """Return human-readable label for a content type key."""
        for ct in self.content_types:
            if ct["key"] == key:
                return ct["label"]
        return key

    def audience_label(self, key: str) -> str:
        """Return human-readable label for an audience key."""
        for a in self.audiences:
            if a["key"] == key:
                return a["label"]
        return key

    def search_query_for(self, content_type_key: str, key_takeaway: str, extra: str = "") -> str:
        """Build a full search query for the given content type (max 380 chars)."""
        base = self.search_queries.get(content_type_key, key_takeaway)
        parts = [base, key_takeaway]
        if extra:
            parts.append(extra)
        if self.search_context:
            parts.append(self.search_context)
        query = " ".join(parts)
        return query[:380]


def load_topic_config(path: Path) -> TopicConfig:
    """Load topic configuration from a JSON file."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return TopicConfig(data)
