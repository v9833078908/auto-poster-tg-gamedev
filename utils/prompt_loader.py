"""Utility for loading prompt files."""
from pathlib import Path


def load_prompt(prompt_path: Path) -> str:
    """
    Load prompt content from a markdown file.

    Args:
        prompt_path: Path to the prompt file

    Returns:
        Content of the prompt file as a string

    Raises:
        FileNotFoundError: If prompt file doesn't exist
    """
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")

    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()
