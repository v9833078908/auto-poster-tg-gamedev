"""Writer agent for Phase 3."""
import json
from typing import Dict, Any
from pathlib import Path

from pipeline.base import BaseAgent
from llm.client import LLMClient
from utils.prompt_loader import load_prompt


class WriterAgent(BaseAgent):
    """Agent that writes post draft based on research."""

    def __init__(
        self,
        llm_client: LLMClient,
        prompt_path: Path,
        writing_guide_path: Path
    ):
        """
        Initialize writer agent.

        Args:
            llm_client: LLM client instance
            prompt_path: Path to writer prompt
            writing_guide_path: Path to writing guide
        """
        super().__init__(llm_client, prompt_path)
        # Load writing guide and append to system prompt
        writing_guide = load_prompt(writing_guide_path)
        self.system_prompt = f"{self.system_prompt}\n\n# WRITING GUIDE\n\n{writing_guide}"

    async def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run writing phase.

        Args:
            context: Combined context with user answers and research results
                - topic_angle, audience, key_takeaway, extra_points (from FSM)
                - research: research results dictionary

        Returns:
            Dictionary with draft post
        """
        # Build user message
        user_message = self._build_user_message(context)

        # Generate draft
        draft = await self.llm.generate(
            system_prompt=self.system_prompt,
            user_message=user_message,
            max_tokens=2048,
            temperature=0.7
        )

        return {
            "draft": draft.strip(),
            "context": context
        }

    def _build_user_message(self, context: Dict[str, Any]) -> str:
        """
        Build user message for Claude.

        Args:
            context: Full context with user answers and research

        Returns:
            User message string
        """
        angle_labels = {
            "experience": "Мой опыт",
            "tutorial": "Tutorial",
            "concept": "Концепция/идея"
        }
        audience_labels = {
            "beginners": "Новички",
            "advanced": "Продвинутые",
            "founders": "Фаундеры"
        }

        message = f"""# Контекст поста

**Тип поста:** {angle_labels.get(context['topic_angle'], context['topic_angle'])}
**Аудитория:** {audience_labels.get(context['audience'], context['audience'])}
**Главная мысль:** {context['key_takeaway']}
"""

        if context.get('extra_points'):
            message += f"**Дополнительно:** {context['extra_points']}\n"

        # Add research results
        research = context.get('research', {})
        message += "\n# Результаты исследования\n\n"

        # Sources
        if research.get('sources'):
            message += "## Источники\n\n"
            for src in research['sources']:
                message += f"- **{src.get('title', 'N/A')}** ({src.get('url', 'N/A')})\n"
                if src.get('key_points'):
                    for point in src['key_points']:
                        message += f"  - {point}\n"
                message += "\n"

        # Stats
        if research.get('key_stats'):
            message += "## Ключевая статистика\n\n"
            for stat in research['key_stats']:
                message += f"- {stat.get('stat')} — [источник]({stat.get('source_url')})\n"
            message += "\n"

        # Examples
        if research.get('examples'):
            message += "## Примеры компаний\n\n"
            for example in research['examples']:
                message += f"- **{example.get('company')}:** {example.get('situation')} → {example.get('outcome')}\n"
            message += "\n"

        # Summary
        if research.get('summary'):
            message += f"## Резюме исследования\n\n{research['summary']}\n\n"

        message += "# Твоя задача\n\nНапиши черновик поста для Telegram, следуя гайду канала."

        return message
