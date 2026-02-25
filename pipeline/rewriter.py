"""Rewriter agent for Phase 4."""
import json
from typing import Dict, Any, List
from pathlib import Path

from pipeline.base import BaseAgent
from llm.client import LLMClient


class RewriterAgent(BaseAgent):
    """Agent that rewrites draft based on critiques."""

    async def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run rewriting phase.

        Args:
            context: Context with draft and critiques
                - draft: Original draft text
                - critiques: List of 4 critique dictionaries
                - research: Original research data (optional)

        Returns:
            Dictionary with final post
        """
        draft = context.get("draft", "")
        critiques = context.get("critiques", [])

        # Build user message
        user_message = self._build_user_message(draft, critiques)

        # Generate rewritten post
        final_post = await self.llm.generate(
            system_prompt=self.system_prompt,
            user_message=user_message,
            max_tokens=2048,
            temperature=0.7
        )

        return {
            "final_post": final_post.strip(),
            "draft": draft,
            "critiques": critiques
        }

    def _build_user_message(self, draft: str, critiques: List[Dict[str, Any]]) -> str:
        """
        Build user message with draft and all critiques.

        Args:
            draft: Original draft
            critiques: List of critique dictionaries

        Returns:
            Formatted user message
        """
        message = f"# Черновик поста\n\n{draft}\n\n"
        message += "# Отчёты критиков\n\n"

        for critique in critiques:
            critic_name = critique.get("critic_name", "Unknown Critic")
            message += f"## {critic_name}\n\n"
            message += f"```json\n{json.dumps(critique, ensure_ascii=False, indent=2)}\n```\n\n"

        message += "# Твоя задача\n\n"
        message += "Переписать пост, учитывая ВСЕ замечания критиков. Верни только финальный текст поста."

        return message
