"""Base agent class for pipeline."""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any

from llm.client import LLMClient
from utils.prompt_loader import load_prompt


class BaseAgent(ABC):
    """Abstract base class for all pipeline agents."""

    def __init__(self, llm_client: LLMClient, prompt_path: Path):
        """
        Initialize agent.

        Args:
            llm_client: LLM client instance
            prompt_path: Path to system prompt file
        """
        self.llm = llm_client
        self.system_prompt = load_prompt(prompt_path)

    @abstractmethod
    async def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run the agent with given context.

        Args:
            context: Input context dictionary

        Returns:
            Output dictionary with agent results
        """
        pass
