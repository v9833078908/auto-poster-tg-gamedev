"""Pipeline orchestrator to run all 5 phases."""
import asyncio
import uuid
from typing import Dict, Any, Callable, Awaitable
from pathlib import Path

import structlog

from llm.client import LLMClient
from research.tavily_client import TavilySearchClient
from pipeline.researcher import ResearchAgent
from utils.topic_config import TopicConfig
from pipeline.writer import WriterAgent
from pipeline.critics import CriticAgent
from pipeline.rewriter import RewriterAgent
from pipeline.publisher import Publisher
from utils.changelog import Changelog

logger = structlog.get_logger("orchestrator")


class PipelineOrchestrator:
    """Orchestrates the entire 5-phase pipeline."""

    def __init__(
        self,
        llm_client: LLMClient,
        tavily_client: TavilySearchClient,
        prompts_dir: Path,
        queue_dir: Path,
        published_dir: Path,
        drafts_dir: Path,
        logs_dir: Path,
        topic: TopicConfig | None = None,
    ):
        self.llm = llm_client
        self.prompts_dir = prompts_dir
        self.drafts_dir = drafts_dir
        self.logs_dir = logs_dir

        self.researcher = ResearchAgent(
            llm_client=llm_client,
            tavily_client=tavily_client,
            prompt_path=prompts_dir / "researcher.md",
            topic=topic,
        )
        self.writer = WriterAgent(
            llm_client=llm_client,
            prompt_path=prompts_dir / "writer.md",
            writing_guide_path=prompts_dir / "writing_guide.md"
        )
        self.generic_detector = CriticAgent(
            llm_client=llm_client,
            prompt_path=prompts_dir / "critics" / "generic_detector.md",
            critic_name="Generic AI Detector"
        )
        self.rhythm_analyzer = CriticAgent(
            llm_client=llm_client,
            prompt_path=prompts_dir / "critics" / "rhythm_analyzer.md",
            critic_name="Rhythm Analyzer"
        )
        self.specificity_checker = CriticAgent(
            llm_client=llm_client,
            prompt_path=prompts_dir / "critics" / "specificity_checker.md",
            critic_name="Specificity Checker"
        )
        self.fact_checker = CriticAgent(
            llm_client=llm_client,
            prompt_path=prompts_dir / "critics" / "fact_checker.md",
            critic_name="Fact Checker"
        )
        self.rewriter = RewriterAgent(
            llm_client=llm_client,
            prompt_path=prompts_dir / "rewriter.md"
        )
        self.publisher = Publisher(
            queue_dir=queue_dir,
            published_dir=published_dir
        )

    async def run_pipeline(
        self,
        user_answers: Dict[str, Any],
        progress_callback: Callable[[str], Awaitable[None]] | None = None
    ) -> Dict[str, Any]:
        """
        Run the complete 5-phase pipeline.

        Returns:
            Final pipeline results with post and metadata
        """
        run_id = uuid.uuid4().hex[:12]
        cl = Changelog(self.logs_dir, run_id)

        # Bind run_id to all structlog calls within this coroutine
        structlog.contextvars.bind_contextvars(run_id=run_id)

        log = logger.bind(run_id=run_id, topic=user_answers.get("key_takeaway", ""))

        async def notify(msg: str) -> None:
            if progress_callback:
                await progress_callback(msg)

        await cl.log("pipeline", "start", topic=user_answers.get("key_takeaway", ""))
        log.info("pipeline_start")

        try:
            # ── Phase 2: Research ──────────────────────────────────────
            await notify("🔍 Фаза 2/5: Ищу источники...")
            await cl.phase_start("research")
            log.info("phase_start", phase="research")

            research = await self.researcher.run(user_answers)

            await cl.phase_done("research", sources=len(research.get("sources", [])))
            log.info("phase_done", phase="research", sources=len(research.get("sources", [])))
            await notify("✅ Исследование завершено")

            # ── Phase 3: Writer ────────────────────────────────────────
            await notify("✍️ Фаза 3/5: Пишу черновик...")
            await cl.phase_start("writer")
            log.info("phase_start", phase="writer")

            context = {**user_answers, "research": research}
            draft_result = await self.writer.run(context)
            draft = draft_result["draft"]

            await cl.phase_done("writer", draft_chars=len(draft))
            log.info("phase_done", phase="writer", draft_chars=len(draft))
            await notify("✅ Черновик готов")

            # ── Phase 4a: Critics (parallel) ───────────────────────────
            await notify("🔍 Фаза 4/5: Критики проверяют...")
            await cl.phase_start("critics")
            log.info("phase_start", phase="critics")

            draft_context = {"draft": draft, "research": research}
            critiques = await asyncio.gather(
                self.generic_detector.run(draft_context),
                self.rhythm_analyzer.run(draft_context),
                self.specificity_checker.run(draft_context),
                self.fact_checker.run(draft_context),
            )

            await cl.phase_done("critics", critics_count=len(critiques))
            log.info("phase_done", phase="critics", critics_count=len(critiques))
            await notify("✅ Критики завершили проверку")

            # ── Phase 4b: Rewriter ─────────────────────────────────────
            await notify("📝 Переписываю с учётом замечаний...")
            await cl.phase_start("rewriter")
            log.info("phase_start", phase="rewriter")

            rewrite_context = {
                "draft": draft,
                "critiques": list(critiques),
                "research": research,
            }
            final_result = await self.rewriter.run(rewrite_context)
            final_post = final_result["final_post"]

            await cl.phase_done("rewriter", final_chars=len(final_post))
            log.info("phase_done", phase="rewriter", final_chars=len(final_post))
            await notify("✅ Финальная версия готова")

            # ── Phase 5: Queue ─────────────────────────────────────────
            await notify("📬 Фаза 5/5: Ставлю в очередь...")
            await cl.phase_start("publisher")
            log.info("phase_start", phase="publisher")

            post_data = {
                "final_post": final_post,
                "draft": draft,
                "research": research,
                "critiques": list(critiques),
                "user_answers": user_answers,
            }
            queue_file = await self.publisher.queue(post_data)

            await cl.phase_done("publisher", queue_file=queue_file.name)
            log.info("phase_done", phase="publisher", queue_file=queue_file.name)
            await notify(f"✅ Пост добавлен в очередь: {queue_file.name}")

            # ── Done ───────────────────────────────────────────────────
            await cl.pipeline_done(queue_file=queue_file.name)
            log.info("pipeline_done", queue_file=queue_file.name)

            structlog.contextvars.unbind_contextvars("run_id")

            return {
                "run_id": run_id,
                "status": "success",
                "final_post": final_post,
                "queue_file": str(queue_file),
                "changelog": str(cl.file),
                "metadata": post_data,
            }

        except Exception as e:
            await cl.log("pipeline", "error", error=str(e))
            log.error("pipeline_error", error=str(e), exc_info=True)
            structlog.contextvars.unbind_contextvars("run_id")
            await notify(f"❌ Ошибка: {str(e)}")
            raise
