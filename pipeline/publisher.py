"""Publisher agent for Phase 5."""
from typing import Dict, Any
from pathlib import Path
from datetime import datetime

from storage.json_store import JsonStore


class Publisher:
    """Agent that handles post queuing and publishing."""

    def __init__(self, queue_dir: Path, published_dir: Path):
        """
        Initialize publisher.

        Args:
            queue_dir: Directory for queued posts
            published_dir: Directory for published posts
        """
        self.queue_dir = queue_dir
        self.published_dir = published_dir
        self.store = JsonStore()

    async def queue(self, post_data: Dict[str, Any]) -> Path:
        """
        Add post to queue.

        Args:
            post_data: Post data including final_post, draft, critiques, etc.

        Returns:
            Path to the queued post file
        """
        # Generate filename
        filename = self.store.generate_filename("post")
        file_path = self.queue_dir / filename

        # Add metadata
        post_data["queued_at"] = datetime.now().isoformat()
        post_data["status"] = "queued"

        # Save to queue
        await self.store.save(file_path, post_data)

        return file_path

    async def get_next_post(self) -> tuple[Path, Dict[str, Any]] | None:
        """
        Get next post from queue (oldest first).

        Returns:
            Tuple of (file_path, post_data) or None if queue is empty
        """
        files = await self.store.list_files(self.queue_dir)

        if not files:
            return None

        # Get oldest file
        oldest = files[0]
        post_data = await self.store.read(oldest)

        return oldest, post_data

    async def mark_published(self, queue_file: Path) -> Path:
        """
        Move post from queue to published.

        Args:
            queue_file: Path to queued post file

        Returns:
            New path in published directory
        """
        # Read post data
        post_data = await self.store.read(queue_file)

        # Update metadata
        post_data["status"] = "published"
        post_data["published_at"] = datetime.now().isoformat()

        # Generate new path in published dir
        published_file = self.published_dir / queue_file.name

        # Save to published
        await self.store.save(published_file, post_data)

        # Delete from queue
        queue_file.unlink()

        return published_file

    async def list_published(self) -> list[Dict[str, Any]]:
        """List all published posts."""
        files = await self.store.list_files(self.published_dir)
        return [{"filename": f.name} for f in files]

    async def list_queue(self) -> list[Dict[str, Any]]:
        """
        List all posts in queue.

        Returns:
            List of post summaries
        """
        files = await self.store.list_files(self.queue_dir)
        summaries = []

        for file_path in files:
            data = await self.store.read(file_path)
            summaries.append({
                "filename": file_path.name,
                "queued_at": data.get("queued_at"),
                "preview": data.get("final_post", "")[:100] + "..."
            })

        return summaries
