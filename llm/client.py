"""AsyncAnthropic client wrapper."""
import anthropic
from anthropic import AsyncAnthropic


class LLMClient:
    """Wrapper for AsyncAnthropic client."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6"):
        """
        Initialize LLM client.

        Args:
            api_key: Anthropic API key
            model: Claude model ID to use
        """
        self.client = AsyncAnthropic(api_key=api_key)
        self.model = model

    async def generate(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 4096,
        temperature: float = 1.0
    ) -> str:
        """
        Generate text using Claude.

        Args:
            system_prompt: System prompt to set context
            user_message: User message to respond to
            max_tokens: Maximum tokens to generate
            temperature: Temperature for generation (0-1)

        Returns:
            Generated text content

        Raises:
            anthropic.APIError: If API call fails
        """
        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )
            return response.content[0].text
        except anthropic.APIError as e:
            raise RuntimeError(f"LLM API error: {e}") from e
