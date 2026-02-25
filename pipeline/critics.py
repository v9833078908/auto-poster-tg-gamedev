"""Critic agents for Phase 4."""
import json
import re
from typing import Dict, Any
from pathlib import Path

from pipeline.base import BaseAgent
from llm.client import LLMClient


class CriticAgent(BaseAgent):
    """Generic critic agent that can be instantiated with different prompts."""

    def __init__(
        self,
        llm_client: LLMClient,
        prompt_path: Path,
        critic_name: str
    ):
        """
        Initialize critic agent.

        Args:
            llm_client: LLM client instance
            prompt_path: Path to critic prompt
            critic_name: Name of the critic (for logging)
        """
        super().__init__(llm_client, prompt_path)
        self.critic_name = critic_name

    async def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run critic analysis on draft.

        Args:
            context: Context with draft post and optionally research data
                - draft: The draft post text
                - research: Research data (for fact checker)

        Returns:
            Critique dictionary (JSON parsed)
        """
        draft = context.get("draft", "")

        # Build user message
        user_message = f"# Черновик поста\n\n{draft}\n\n"

        # Add research data if available (for fact checker)
        if context.get("research"):
            research = context["research"]
            user_message += "\n# Research Data (для верификации фактов)\n\n"
            user_message += f"```json\n{json.dumps(research, ensure_ascii=False, indent=2)}\n```\n\n"

        user_message += "Проанализируй черновик и верни JSON-отчёт."

        # Get critique from Claude
        response = await self.llm.generate(
            system_prompt=self.system_prompt,
            user_message=user_message,
            max_tokens=2048
        )

        # Parse JSON response
        critique = self._parse_json(response)

        critique["critic_name"] = self.critic_name
        return critique

    def _parse_json(self, response: str) -> Dict[str, Any]:
        """Try multiple strategies to extract JSON from LLM response."""
        # 1. Direct parse
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass

        # 2. Strip markdown code block  ```json ... ```
        code_block = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response, re.DOTALL)
        if code_block:
            try:
                return json.loads(code_block.group(1))
            except json.JSONDecodeError:
                pass

        # 3. Grab the largest {...} block
        brace_match = re.search(r'\{.*\}', response, re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group())
            except json.JSONDecodeError:
                pass

        # 4. Fallback — return raw response so pipeline doesn't crash
        return {
            "error": f"Failed to parse JSON from {self.critic_name}",
            "raw_response": response[:500],
        }
