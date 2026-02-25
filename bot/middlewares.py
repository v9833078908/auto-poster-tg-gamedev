"""Middleware for admin-only access."""
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message


class AdminOnlyMiddleware(BaseMiddleware):
    """Middleware to restrict bot access to admin user only."""

    def __init__(self, admin_id: str):
        """
        Initialize middleware.

        Args:
            admin_id: Telegram user ID of the admin
        """
        super().__init__()
        self.admin_id = int(admin_id)

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        """
        Check if user is admin before processing message.

        Args:
            handler: Next handler in chain
            event: Telegram message event
            data: Handler data

        Returns:
            Handler result or None if user is not admin
        """
        if event.from_user.id != self.admin_id:
            await event.answer("⛔ У вас нет доступа к этому боту.")
            return

        return await handler(event, data)
