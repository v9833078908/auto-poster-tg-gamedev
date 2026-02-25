"""JSON file storage utilities."""
import json
import aiofiles
from pathlib import Path
from typing import Any, Dict, List
from datetime import datetime


class JsonStore:
    """CRUD operations for JSON files."""

    @staticmethod
    async def save(file_path: Path, data: Dict[str, Any]) -> None:
        """
        Save data to JSON file.

        Args:
            file_path: Path to save the file
            data: Data to save

        Raises:
            IOError: If file cannot be written
        """
        # Ensure directory exists
        file_path.parent.mkdir(parents=True, exist_ok=True)

        async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(data, ensure_ascii=False, indent=2))

    @staticmethod
    async def read(file_path: Path) -> Dict[str, Any]:
        """
        Read data from JSON file.

        Args:
            file_path: Path to the file

        Returns:
            Parsed JSON data

        Raises:
            FileNotFoundError: If file doesn't exist
            json.JSONDecodeError: If file is not valid JSON
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
            content = await f.read()
            return json.loads(content)

    @staticmethod
    async def move(source: Path, destination: Path) -> None:
        """
        Move file from source to destination.

        Args:
            source: Source file path
            destination: Destination file path

        Raises:
            FileNotFoundError: If source file doesn't exist
        """
        if not source.exists():
            raise FileNotFoundError(f"Source file not found: {source}")

        # Ensure destination directory exists
        destination.parent.mkdir(parents=True, exist_ok=True)

        # Read and write (aiofiles doesn't have async rename)
        data = await JsonStore.read(source)
        await JsonStore.save(destination, data)
        source.unlink()  # Delete source

    @staticmethod
    async def list_files(directory: Path, pattern: str = "*.json") -> List[Path]:
        """
        List all JSON files in directory.

        Args:
            directory: Directory to search
            pattern: File pattern (default: *.json)

        Returns:
            List of file paths sorted by modification time (oldest first)
        """
        if not directory.exists():
            return []

        files = list(directory.glob(pattern))
        return sorted(files, key=lambda p: p.stat().st_mtime)

    @staticmethod
    def generate_filename(prefix: str = "post") -> str:
        """
        Generate unique filename with timestamp.

        Args:
            prefix: Filename prefix

        Returns:
            Filename in format: prefix_YYYYMMDD_HHMMSS.json
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{prefix}_{timestamp}.json"
