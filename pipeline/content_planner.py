"""Content planner for weekly content plan generation."""
import json
import re
import logging
from typing import Dict, Any, Optional
from pathlib import Path
from datetime import datetime

from llm.client import LLMClient
from research.tavily_client import TavilySearchClient
from storage.json_store import JsonStore
from utils.prompt_loader import load_prompt
from utils.topic_config import TopicConfig

logger = logging.getLogger(__name__)


class ContentPlanner:
    """Generates weekly content plans by researching trending topics."""

    def __init__(
        self,
        llm_client: LLMClient,
        tavily_client: TavilySearchClient,
        prompt_path: Path,
        plans_dir: Path,
        topic: TopicConfig,
    ):
        self.llm = llm_client
        self.tavily = tavily_client
        self.plans_dir = plans_dir
        self.topic = topic
        self.store = JsonStore()
        self.system_prompt = load_prompt(prompt_path)

        self.plans_dir.mkdir(parents=True, exist_ok=True)

    async def generate_weekly_plan(self) -> Dict[str, Any]:
        """
        Research trending topics and generate a 7-day content plan.

        Returns:
            Plan dict with days list and saved file path
        """
        # Step 1: Research current trends from topic config queries
        all_results = []
        for query in self.topic.research_queries:
            try:
                results = await self.tavily.search(
                    query=query,
                    max_results=3,
                    search_depth="advanced",
                    topic="news",
                    time_range="week",
                )
                all_results.extend(results)
            except Exception as e:
                logger.warning(f"Search failed for '{query}': {e}")

        # Deduplicate by URL
        seen_urls = set()
        unique_results = []
        for r in all_results:
            if r["url"] not in seen_urls:
                unique_results.append(r)
                seen_urls.add(r["url"])

        # Step 2: Format sources for Claude
        sources_text = ""
        for i, result in enumerate(unique_results[:15], 1):
            sources_text += (
                f"### Источник {i}\n"
                f"**URL:** {result['url']}\n"
                f"**Title:** {result['title']}\n"
                f"**Content:** {result['content'][:300]}\n\n"
            )

        # Step 3: Ask Claude to generate content plan
        user_message = f"""# Актуальные новости и тренды — {self.topic.channel_name}

{sources_text}

# Задача

На основе этих источников, составь контент-план на 7 дней (Понедельник-Воскресенье).
Канал: {self.topic.channel_description}
Каждый день — один пост. Чередуй типы контента. Используй конкретные данные из источников.
"""

        response = await self.llm.generate(
            system_prompt=self.system_prompt,
            user_message=user_message,
            max_tokens=4096,
            temperature=0.7,
        )

        # Parse JSON
        try:
            plan_data = json.loads(response)
        except json.JSONDecodeError:
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                plan_data = json.loads(json_match.group())
            else:
                raise ValueError("Failed to parse content plan JSON")

        # Add IDs and status to each day
        for i, day in enumerate(plan_data.get("days", [])):
            day["id"] = i
            day["status"] = "pending"

        # Save plan
        filename = f"plan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        file_path = self.plans_dir / filename

        plan_data["created_at"] = datetime.now().isoformat()
        plan_data["status"] = "active"

        await self.store.save(file_path, plan_data)
        plan_data["file"] = filename

        logger.info(f"Content plan generated: {filename}")
        return plan_data

    async def get_next_topic(self) -> Optional[Dict[str, Any]]:
        """
        Get next unused topic from the latest active content plan.

        Returns:
            Next topic dict or None if all used
        """
        # Find latest plan
        plans = await self.store.list_files(self.plans_dir)
        if not plans:
            return None

        # Read latest plan (most recent)
        latest_plan = plans[-1]
        plan_data = await self.store.read(latest_plan)

        # Find first pending topic (skip queued and used)
        for day in plan_data.get("days", []):
            if day.get("status") == "pending":
                day["_plan_file"] = latest_plan
                return day

        return None

    async def refine_plan(self, current_plan: Dict, feedback: str) -> Dict:
        """
        Refine existing plan based on user feedback + new Tavily searches.

        Args:
            current_plan: Current plan dict
            feedback: Free-text feedback from user

        Returns:
            Updated plan dict with saved file path
        """
        # New Tavily searches with feedback context
        all_results = []
        for query in self.topic.research_queries:
            try:
                results = await self.tavily.search(
                    query=query,
                    max_results=3,
                    search_depth="advanced",
                    topic="news",
                    time_range="week",
                )
                all_results.extend(results)
            except Exception as e:
                logger.warning(f"Search failed for '{query}': {e}")

        seen_urls = set()
        unique_results = []
        for r in all_results:
            if r["url"] not in seen_urls:
                unique_results.append(r)
                seen_urls.add(r["url"])

        sources_text = ""
        for i, result in enumerate(unique_results[:15], 1):
            sources_text += (
                f"### Источник {i}\n"
                f"**URL:** {result['url']}\n"
                f"**Title:** {result['title']}\n"
                f"**Content:** {result['content'][:300]}\n\n"
            )

        current_plan_text = "\n".join(
            f"**{d['day']}** — {d['type_label']}: {d['theme']}"
            for d in current_plan.get("days", [])
        )

        user_message = f"""# Текущий контент-план

{current_plan_text}

# Фидбек от редактора

{feedback}

# Свежие источники для замены слабых тем

{sources_text}

# Задача

Пересмотри контент-план с учётом фидбека и свежих источников.
Сохрани темы, которые хороши. Замени слабые на более сильные из новых источников.
Канал: {self.topic.channel_description}
Верни обновлённый JSON в том же формате.
"""

        response = await self.llm.generate(
            system_prompt=self.system_prompt,
            user_message=user_message,
            max_tokens=4096,
            temperature=0.7,
        )

        try:
            plan_data = json.loads(response)
        except json.JSONDecodeError:
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                plan_data = json.loads(json_match.group())
            else:
                raise ValueError("Failed to parse refined plan JSON")

        # Preserve queued/used statuses from the current plan by topic ID
        preserved = {
            d["id"]: d
            for d in current_plan.get("days", [])
            if d.get("status") in ("queued", "used")
        }

        for i, day in enumerate(plan_data.get("days", [])):
            day["id"] = i
            old = preserved.get(i)
            if old:
                # Keep the slot status so we don't re-queue what's already in flight
                day["status"] = old["status"]
                for key in ("queued_at", "used_at"):
                    if key in old:
                        day[key] = old[key]
            else:
                day["status"] = "pending"

        # Overwrite the SAME file — don't create a new one, statuses must survive refinement
        current_file = current_plan.get("_file_path") or current_plan.get("file")
        if current_file:
            file_path = Path(current_file) if not Path(current_file).is_absolute() else Path(current_file)
            if not file_path.is_absolute():
                file_path = self.plans_dir / file_path
        else:
            file_path = self.plans_dir / f"plan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        plan_data["refined_at"] = datetime.now().isoformat()
        plan_data["status"] = "active"

        await self.store.save(file_path, plan_data)
        plan_data["file"] = file_path.name
        plan_data["_file_path"] = str(file_path)

        logger.info(f"Content plan refined in-place: {file_path.name}")
        return plan_data

    async def get_latest_plan(self) -> Optional[Dict[str, Any]]:
        """Return the latest saved content plan, or None if no plans exist."""
        plans = await self.store.list_files(self.plans_dir)
        if not plans:
            return None

        latest = plans[-1]
        plan_data = await self.store.read(latest)
        plan_data["file"] = latest.name
        plan_data["_file_path"] = str(latest)
        return plan_data

    async def _resolve_plan_file(self, plan_file: Optional[Path]) -> Optional[Path]:
        """Return plan_file if it exists, otherwise fall back to the latest plan file."""
        if plan_file is not None and plan_file.exists():
            return plan_file
        plans = await self.store.list_files(self.plans_dir)
        return plans[-1] if plans else None

    async def mark_topic_pending(self, topic_id: int, plan_file: Optional[Path] = None) -> None:
        """Revert a topic back to pending (e.g. pipeline was cancelled)."""
        file = await self._resolve_plan_file(plan_file)
        if not file:
            return

        plan_data = await self.store.read(file)
        for day in plan_data.get("days", []):
            if day.get("id") == topic_id:
                day["status"] = "pending"
                day.pop("queued_at", None)
                break

        await self.store.save(file, plan_data)

    async def mark_topic_queued(self, topic_id: int, plan_file: Optional[Path] = None) -> None:
        """Mark a topic as queued (post created, not yet published)."""
        file = await self._resolve_plan_file(plan_file)
        if not file:
            return

        plan_data = await self.store.read(file)
        for day in plan_data.get("days", []):
            if day.get("id") == topic_id:
                day["status"] = "queued"
                day["queued_at"] = datetime.now().isoformat()
                break

        await self.store.save(file, plan_data)

    async def mark_topic_used(self, topic_id: int, plan_file: Optional[Path] = None) -> None:
        """Mark a topic as used (post published to channel)."""
        file = await self._resolve_plan_file(plan_file)
        if not file:
            return

        plan_data = await self.store.read(file)
        for day in plan_data.get("days", []):
            if day.get("id") == topic_id:
                day["status"] = "used"
                day["used_at"] = datetime.now().isoformat()
                break

        await self.store.save(file, plan_data)
