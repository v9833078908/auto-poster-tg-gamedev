"""Per-run JSONL changelog for pipeline step tracing."""
import json
import aiofiles
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


class Changelog:
    """
    Append-only JSONL log for a single pipeline run.

    One file per run:  data/logs/run_YYYYMMDD_HHMMSS_<run_id[:8]>.jsonl
    Each line is a JSON event with run_id, timestamp, phase, event, and extras.

    Usage:
        cl = Changelog(logs_dir, run_id)
        await cl.phase_start("research", query="...")
        await cl.phase_done("research", sources=5)
        await cl.phase_error("writer", error="timeout")
    """

    def __init__(self, logs_dir: Path, run_id: str) -> None:
        self.run_id = run_id
        self._phase_starts: Dict[str, datetime] = {}
        self._run_start = datetime.now()

        logs_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.file = logs_dir / f"run_{ts}_{run_id[:8]}.jsonl"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def log(self, phase: str, event: str, **kwargs: Any) -> None:
        """Append a raw event entry."""
        entry: Dict[str, Any] = {
            "run_id": self.run_id,
            "ts": datetime.now().isoformat(),
            "phase": phase,
            "event": event,
            **kwargs,
        }
        async with aiofiles.open(self.file, "a") as f:
            await f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    async def phase_start(self, phase: str, **kwargs: Any) -> None:
        """Log phase start and record start time for duration tracking."""
        self._phase_starts[phase] = datetime.now()
        await self.log(phase, "start", **kwargs)

    async def phase_done(self, phase: str, **kwargs: Any) -> None:
        """Log phase completion with elapsed ms."""
        duration_ms = self._elapsed_ms(phase)
        await self.log(phase, "done", duration_ms=duration_ms, **kwargs)

    async def phase_error(self, phase: str, error: str, **kwargs: Any) -> None:
        """Log phase failure with elapsed ms and error message."""
        duration_ms = self._elapsed_ms(phase)
        await self.log(phase, "error", error=error, duration_ms=duration_ms, **kwargs)

    async def pipeline_done(self, **kwargs: Any) -> None:
        """Log overall pipeline completion with total elapsed ms."""
        total_ms = int(
            (datetime.now() - self._run_start).total_seconds() * 1000
        )
        await self.log("pipeline", "done", total_ms=total_ms, **kwargs)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _elapsed_ms(self, phase: str) -> Optional[int]:
        start = self._phase_starts.pop(phase, None)
        if start is None:
            return None
        return int((datetime.now() - start).total_seconds() * 1000)
