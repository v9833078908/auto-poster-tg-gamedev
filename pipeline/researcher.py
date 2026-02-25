"""Research agent for Phase 2."""
import json
import re
from typing import Dict, Any
from pathlib import Path

from pipeline.base import BaseAgent
from llm.client import LLMClient
from research.tavily_client import TavilySearchClient
from utils.topic_config import TopicConfig


class ResearchAgent(BaseAgent):
    """Agent that performs web research using Tavily and Claude."""

    def __init__(
        self,
        llm_client: LLMClient,
        tavily_client: TavilySearchClient,
        prompt_path: Path,
        topic: TopicConfig,
    ):
        super().__init__(llm_client, prompt_path)
        self.tavily = tavily_client
        self.topic = topic

    async def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run research phase.

        Args:
            context: User answers from FSM

        Returns:
            Research results with sources, stats, tools, examples, summary
        """
        search_query = self._generate_search_query(context)

        # Search with gamedev focus, prefer recent results
        search_results = await self.tavily.search(
            query=search_query,
            max_results=5,
            search_depth="advanced",
            topic="news",
            time_range="month",
        )

        # If news search returned few results, do a general search too
        if len(search_results) < 3:
            general_results = await self.tavily.search(
                query=search_query,
                max_results=5,
                search_depth="advanced",
                topic="general",
                time_range="year",
            )
            # Merge, avoiding duplicates
            seen_urls = {r["url"] for r in search_results}
            for r in general_results:
                if r["url"] not in seen_urls:
                    search_results.append(r)
                    seen_urls.add(r["url"])

        sources_text = self._format_sources(search_results)
        user_message = self._build_user_message(context, sources_text)

        response = await self.llm.generate(
            system_prompt=self.system_prompt,
            user_message=user_message,
            max_tokens=8192
        )

        research_data = self._parse_json(response)
        return research_data

    def _parse_json(self, response: str) -> dict:
        """Try multiple strategies to extract JSON from LLM response."""
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass

        code_block = re.search(r'```(?:json)?\s*(\{.*\})\s*```', response, re.DOTALL)
        if code_block:
            try:
                return json.loads(code_block.group(1))
            except json.JSONDecodeError:
                pass

        brace_match = re.search(r'\{.*\}', response, re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group())
            except json.JSONDecodeError:
                pass

        raise ValueError(f"Failed to parse research JSON from response: {response[:200]}")

    def _generate_search_query(self, context: Dict[str, Any]) -> str:
        """Generate search query from user context using topic config."""
        content_type = context.get("topic_angle", "")
        key_takeaway = context.get("key_takeaway", "")
        extra = context.get("extra_points", "")
        return self.topic.search_query_for(content_type, key_takeaway, extra)

    def _format_sources(self, search_results: list) -> str:
        """Format search results for Claude."""
        formatted = []
        for i, result in enumerate(search_results, 1):
            formatted.append(
                f"### Источник {i}\n"
                f"**URL:** {result['url']}\n"
                f"**Title:** {result['title']}\n"
                f"**Content:** {result['content']}\n"
                f"**Relevance Score:** {result['score']}\n"
            )

        return "\n\n".join(formatted)

    def _build_user_message(self, context: Dict[str, Any], sources: str) -> str:
        """Build user message for Claude."""
        message = f"""# Контекст поста

**Тип контента:** {self.topic.content_type_label(context.get('topic_angle', ''))}
**Фокус:** {self.topic.audience_label(context.get('audience', ''))}
**Главная мысль:** {context.get('key_takeaway', '')}
"""

        if context.get('extra_points'):
            message += f"**Дополнительно:** {context['extra_points']}\n"

        message += f"\n# Найденные источники\n\n{sources}\n\n"
        message += "# Твоя задача\n\nПроанализируй источники и создай структурированный JSON-отчёт."

        return message
