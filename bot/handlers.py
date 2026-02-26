"""Telegram bot handlers for gamedev AI post creation."""
import asyncio
import html
from pathlib import Path
import structlog
from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from bot.states import PostCreation, ContentPlanFlow, AutopostFlow, EditPostFlow

logger = structlog.get_logger("handlers")

router = Router()

# Global references (set in main.py)
orchestrator = None
publish_scheduler = None
content_planner = None
topic = None  # TopicConfig instance

# Running pipeline tasks per user (user_id -> asyncio.Task)
_running_tasks: dict[int, asyncio.Task] = {}


# /start command
@router.message(Command("start"))
async def cmd_start(message: Message):
    """Handle /start command."""
    await message.answer(
        "🎮 Привет! Я помогу создать пост для GameDev AI канала.\n\n"
        "Доступные команды:\n"
        "/newpost — создать новый пост\n"
        "/contentplan — сгенерировать контент-план на неделю\n"
        "/editplan — редактировать текущий контент-план\n"
        "/autopost — создать пост по следующей теме из плана\n"
        "/publish — опубликовать следующий пост из очереди\n"
        "/queue — показать очередь постов\n"
        "/edit — редактировать пост (очередь или опубликованные)\n"
        "/cancel — отменить текущее действие"
    )


# /newpost command - start FSM
@router.message(Command("newpost"))
async def cmd_newpost(message: Message, state: FSMContext):
    """Start new post creation flow."""
    logger.info("cmd_newpost", user_id=message.from_user.id)
    await state.clear()

    buttons = [
        [InlineKeyboardButton(text=ct["label"], callback_data=f"angle:{ct['key']}")]
        for ct in topic.content_types
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await message.answer(
        "📝 Создаём новый пост!\n\n"
        "**Шаг 1/5:** Тип контента?",
        reply_markup=keyboard
    )
    await state.set_state(PostCreation.waiting_topic_angle)


# Handle topic/angle selection
@router.callback_query(PostCreation.waiting_topic_angle, F.data.startswith("angle:"))
async def process_topic_angle(callback: CallbackQuery, state: FSMContext):
    """Handle content type selection."""
    angle = callback.data.split(":")[1]

    await state.update_data(topic_angle=angle)

    aud_buttons = [
        [InlineKeyboardButton(text=a["label"], callback_data=f"audience:{a['key']}")]
        for a in topic.audiences
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=aud_buttons)

    await callback.message.edit_text(
        f"✅ Тип: {topic.content_type_label(angle)}\n\n"
        "**Шаг 2/5:** Для какой аудитории?"
    )
    await callback.message.answer(
        "Выберите фокус аудитории:",
        reply_markup=keyboard
    )
    await state.set_state(PostCreation.waiting_audience)
    await callback.answer()


# Handle audience selection
@router.callback_query(PostCreation.waiting_audience, F.data.startswith("audience:"))
async def process_audience(callback: CallbackQuery, state: FSMContext):
    """Handle audience selection."""
    audience = callback.data.split(":")[1]

    await state.update_data(audience=audience)

    await callback.message.edit_text(
        f"✅ Аудитория: {topic.audience_label(audience)}\n\n"
        "**Шаг 3/5:** Главная мысль"
    )
    await callback.message.answer(
        "Напишите главную мысль поста в 1-2 предложениях.\n"
        "Пример: \"Unity выпустили новый AI-плагин для процедурной генерации\""
    )
    await state.set_state(PostCreation.waiting_key_takeaway)
    await callback.answer()


# Handle key takeaway text input
@router.message(PostCreation.waiting_key_takeaway, F.text)
async def process_key_takeaway(message: Message, state: FSMContext):
    """Handle key takeaway input."""
    await state.update_data(key_takeaway=message.text)

    await message.answer(
        "✅ Главная мысль сохранена\n\n"
        "**Шаг 4/5:** Дополнительные детали (опционально)\n\n"
        "Конкретные инструменты, студии, ссылки, цифры?\n"
        "Или /skip чтобы пропустить."
    )
    await state.set_state(PostCreation.waiting_extra_points)


# Handle extra points or skip
@router.message(PostCreation.waiting_extra_points, F.text)
async def process_extra_points(message: Message, state: FSMContext):
    """Handle extra points input or skip."""
    if message.text == "/skip":
        await state.update_data(extra_points=None)
    else:
        await state.update_data(extra_points=message.text)

    data = await state.get_data()

    summary = (
        "📋 **Резюме поста:**\n\n"
        f"**Тип:** {topic.content_type_label(data['topic_angle'])}\n"
        f"**Аудитория:** {topic.audience_label(data['audience'])}\n"
        f"**Главная мысль:** {data['key_takeaway']}\n"
    )

    if data.get('extra_points'):
        summary += f"**Дополнительно:** {data['extra_points']}\n"

    summary += "\n**Шаг 5/5:** Подтверждение"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Создать пост", callback_data="confirm:yes")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="confirm:no")],
    ])

    await message.answer(summary, reply_markup=keyboard)
    await state.set_state(PostCreation.confirm)


# Handle confirmation
@router.callback_query(PostCreation.confirm, F.data.startswith("confirm:"))
async def process_confirmation(callback: CallbackQuery, state: FSMContext):
    """Handle post creation confirmation."""
    confirmed = callback.data.split(":")[1] == "yes"

    if not confirmed:
        await callback.message.edit_text("❌ Создание поста отменено.")
        await state.clear()
        await callback.answer()
        return

    data = await state.get_data()

    await callback.message.edit_text(
        "✅ Запускаю пайплайн...\n\n"
        "Это займёт 2-5 минут. Буду держать в курсе! ⏳"
    )
    await callback.answer()

    async def send_progress(message: str):
        try:
            await callback.message.answer(message)
        except Exception as e:
            logger.warning("progress_send_failed", error=str(e))

    try:
        if orchestrator is None:
            await callback.message.answer(
                "⚠️ Orchestrator не инициализирован."
            )
            await state.clear()
            return

        result = await orchestrator.run_pipeline(data, send_progress)

        final_post = result["final_post"]
        logger.info("pipeline_finished", run_id=result.get("run_id"), changelog=result.get("changelog"))

        await callback.message.answer(
            "🎉 <b>Пайплайн завершён!</b>\n\n"
            "👀 Превью:\n\n" + final_post,
            parse_mode="HTML"
        )

    except Exception as e:
        logger.error("pipeline_failed", error=str(e), exc_info=True)
        await callback.message.answer(
            f"❌ Ошибка при создании поста:\n\n<code>{str(e)[:500]}</code>",
            parse_mode="HTML"
        )

    await state.clear()


# /publish command — immediate publish
@router.message(Command("publish"))
async def cmd_publish(message: Message, state: FSMContext):
    """Immediately publish next post from queue."""
    await state.clear()
    logger.info("cmd_publish", user_id=message.from_user.id)
    if publish_scheduler is None:
        await message.answer("⚠️ Scheduler не инициализирован.")
        return

    try:
        queue = await orchestrator.publisher.list_queue()
        pending_count = len(queue)

        if pending_count == 0:
            await message.answer("📋 Очередь пуста. Создай посты через /autopost или /newpost.")
            return

        await message.answer(
            f"📤 <b>Публикую в канал...</b>\n\n"
            f"В очереди: {pending_count} постов",
            parse_mode="HTML"
        )

        result = await publish_scheduler.publisher.get_next_post()
        if result:
            queue_file, post_data = result
            preview = html.escape(post_data.get("final_post", "")[:200])

            await publish_scheduler.publish_next_post()
            logger.info("post_published", file=queue_file.name)

            await message.answer(
                f"✅ <b>Опубликовано в канал!</b>\n\n"
                f"👀 Превью:\n{preview}...",
                parse_mode="HTML"
            )

            # Mark content plan topic as used (published)
            user_answers = post_data.get("user_answers", {})
            plan_topic_id = user_answers.get("plan_topic_id")
            plan_file_str = user_answers.get("plan_file", "")
            if plan_topic_id is not None and content_planner:
                plan_file = Path(plan_file_str) if plan_file_str else None
                await content_planner.mark_topic_used(plan_topic_id, plan_file)
    except Exception as e:
        await message.answer(
            f"❌ Ошибка публикации:\n\n<code>{str(e)[:500]}</code>",
            parse_mode="HTML"
        )


# /contentplan command — generate weekly content plan
@router.message(Command("contentplan"))
async def cmd_contentplan(message: Message, state: FSMContext):
    """Generate weekly content plan by researching trending gamedev AI topics."""
    logger.info("cmd_contentplan", user_id=message.from_user.id)
    if content_planner is None:
        await message.answer("⚠️ Content planner не инициализирован.")
        return

    force = bool(message.text and "force" in message.text.lower())
    await state.clear()

    # Warn if there's already an active plan with pending topics
    if not force:
        existing = await content_planner.get_latest_plan()
        if existing:
            pending = [d for d in existing.get("days", []) if d.get("status") == "pending"]
            queued = [d for d in existing.get("days", []) if d.get("status") == "queued"]
            if pending or queued:
                topics_left = len(pending) + len(queued)
                await message.answer(
                    f"⚠️ <b>Уже есть активный план</b> с {topics_left} незавершёнными темами "
                    f"({len(pending)} pending, {len(queued)} в очереди).\n\n"
                    f"📁 <code>{existing['file']}</code>\n\n"
                    f"Чтобы всё равно создать новый план — отправь /contentplan force.\n"
                    f"Чтобы продолжить текущий — используй /autopost.",
                    parse_mode="HTML"
                )
                return

    await message.answer(
        "🗓 Генерирую контент-план на неделю...\n"
        "Ищу актуальные темы по ИИ в геймдеве. Это займёт 1-2 минуты."
    )

    try:
        plan = await content_planner.generate_weekly_plan()

        response = "🗓 <b>Контент-план на неделю:</b>\n\n"
        for day in plan["days"]:
            response += (
                f"<b>{day['day']}</b> — {day['type_label']}\n"
                f"📌 {day['theme']}\n"
                f"💡 {day['angle']}\n\n"
            )
        response += f"📁 Сохранён: <code>{plan['file']}</code>"

        logger.info("contentplan_generated", file=plan.get("file"), days=len(plan.get("days", [])))
        await message.answer(response, parse_mode="HTML")

        await state.update_data(current_plan=plan)
        await message.answer(
            "💬 <b>Дай фидбек по плану:</b>\n\n"
            "Напиши что изменить — какие темы слабые, что добавить.\n"
            "Или /approve чтобы принять план как есть.",
            parse_mode="HTML"
        )
        await state.set_state(ContentPlanFlow.waiting_feedback)

    except Exception as e:
        await message.answer(
            f"❌ Ошибка генерации плана:\n\n<code>{str(e)[:500]}</code>",
            parse_mode="HTML"
        )


@router.message(ContentPlanFlow.waiting_feedback, Command("approve"))
async def cmd_approve_plan(message: Message, state: FSMContext):
    """Accept the content plan as-is."""
    data = await state.get_data()
    plan = data.get("current_plan", {})
    pending = sum(1 for d in plan.get("days", []) if d.get("status") == "pending")
    await state.clear()
    logger.info("contentplan_approved", pending_topics=pending, user_id=message.from_user.id)
    await message.answer(
        f"✅ <b>План принят!</b>\n\n"
        f"📋 {pending} тем в плане.\n"
        f"Запускай /autopost чтобы создавать посты по очереди.",
        parse_mode="HTML"
    )


@router.message(
    ContentPlanFlow.waiting_feedback,
    F.text,
    F.text.func(lambda t: not t.startswith("/")),
)
async def process_contentplan_feedback(message: Message, state: FSMContext):
    """Handle content plan feedback (plain text only; commands fall through)."""
    feedback = message.text
    data = await state.get_data()
    current_plan = data.get("current_plan")

    await message.answer("🔍 Ищу новые источники и обновляю план... (~1 мин)")

    try:
        refined = await content_planner.refine_plan(current_plan, feedback)

        response = "🗓 <b>Обновлённый контент-план:</b>\n\n"
        for day in refined["days"]:
            response += (
                f"<b>{day['day']}</b> — {day['type_label']}\n"
                f"📌 {day['theme']}\n"
                f"💡 {day['angle']}\n\n"
            )
        response += f"📁 Сохранён: <code>{refined['file']}</code>"

        await message.answer(response, parse_mode="HTML")
        await state.update_data(current_plan=refined)
        await message.answer(
            "💬 Ещё фидбек — или /approve чтобы принять план."
        )
    except Exception as e:
        await message.answer(
            f"❌ Ошибка обновления плана:\n\n<code>{str(e)[:500]}</code>",
            parse_mode="HTML"
        )


# /editplan command — start feedback loop on existing content plan
@router.message(Command("editplan"))
async def cmd_editplan(message: Message, state: FSMContext):
    """Load the latest content plan and enter the feedback loop."""
    if content_planner is None:
        await message.answer("⚠️ Content planner не инициализирован.")
        return

    await state.clear()

    plan = await content_planner.get_latest_plan()
    if not plan:
        await message.answer(
            "📋 Нет сохранённого плана. Сначала создай план: /contentplan"
        )
        return

    status_icons = {"pending": "⏳", "queued": "🔄", "used": "✅"}

    response = "🗓 <b>Текущий контент-план:</b>\n\n"
    for day in plan.get("days", []):
        icon = status_icons.get(day.get("status", "pending"), "⏳")
        response += (
            f"<b>{day['day']}</b> — {day['type_label']} {icon}\n"
            f"📌 {day['theme']}\n"
            f"💡 {day['angle']}\n\n"
        )
    response += f"📁 <code>{plan['file']}</code>"

    await message.answer(response, parse_mode="HTML")

    await state.update_data(current_plan=plan)
    await message.answer(
        "💬 <b>Дай фидбек по плану:</b>\n\n"
        "Напиши что изменить — какие темы слабые, что добавить.\n"
        "Или /approve чтобы принять план как есть.",
        parse_mode="HTML"
    )
    await state.set_state(ContentPlanFlow.waiting_feedback)


# /autopost command — create post from content plan
@router.message(Command("autopost"))
async def cmd_autopost(message: Message, state: FSMContext):
    """Auto-create next post from content plan."""
    await state.clear()  # exit any lingering FSM state (e.g. feedback loop)
    logger.info("cmd_autopost", user_id=message.from_user.id)

    if content_planner is None or orchestrator is None:
        await message.answer("⚠️ Не инициализирован.")
        return

    user_id = message.from_user.id

    # Prevent double-run
    existing = _running_tasks.get(user_id)
    if existing and not existing.done():
        await message.answer("⚠️ Пайплайн уже запущен. Отправь /cancel чтобы остановить.")
        return

    await message.answer("🤖 Беру следующую тему из контент-плана...")

    next_topic = await content_planner.get_next_topic()
    if not next_topic:
        await message.answer("📋 Все темы из плана уже использованы. Сгенерируйте новый: /contentplan")
        return

    await message.answer(
        f"📌 Тема: <b>{next_topic['theme']}</b>\n"
        f"Тип: {next_topic['type_label']}\n\n"
        "⏳ Запускаю пайплайн... (отправь /cancel чтобы остановить)",
        parse_mode="HTML"
    )

    plan_file = next_topic.get("_plan_file")
    await content_planner.mark_topic_queued(next_topic["id"], plan_file)

    context = {
        "topic_angle": next_topic["type"],
        "audience": next_topic.get("audience", "all"),
        "key_takeaway": next_topic["theme"],
        "extra_points": next_topic.get("angle", None),
        "plan_topic_id": next_topic["id"],
        "plan_file": str(plan_file) if plan_file else "",
    }

    async def send_progress(msg: str):
        try:
            await message.answer(msg)
        except Exception:
            pass

    async def run_pipeline():
        try:
            result = await orchestrator.run_pipeline(context, send_progress)
            await message.answer(
                "🎉 <b>Пост создан!</b>\n\n"
                "👀 Превью:\n\n" + result["final_post"],
                parse_mode="HTML"
            )
        except asyncio.CancelledError:
            # Revert topic to pending so it can be picked up next time
            await content_planner.mark_topic_pending(next_topic["id"], plan_file)
            logger.info("autopost_cancelled", user_id=user_id, topic=next_topic["theme"])
            raise
        except Exception as e:
            logger.error("autopost_failed", error=str(e), user_id=user_id)
            # Revert topic so it can be retried next time
            await content_planner.mark_topic_pending(next_topic["id"], plan_file)
            await message.answer(
                f"❌ Ошибка: <code>{str(e)[:500]}</code>",
                parse_mode="HTML"
            )
        finally:
            _running_tasks.pop(user_id, None)
            await state.clear()

    task = asyncio.create_task(run_pipeline())
    _running_tasks[user_id] = task
    await state.set_state(AutopostFlow.running)


# /cancel command
@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    """Cancel current operation."""
    current_state = await state.get_state()

    if current_state == AutopostFlow.running.state:
        user_id = message.from_user.id
        task = _running_tasks.pop(user_id, None)
        if task and not task.done():
            task.cancel()
        await state.clear()
        await message.answer("🛑 Генерация поста отменена.")
        return

    if current_state is None:
        await message.answer("Нечего отменять.")
        return

    await state.clear()
    await message.answer("✅ Действие отменено.")


# /queue command
@router.message(Command("queue"))
async def cmd_queue(message: Message, state: FSMContext):
    """Show posts in queue."""
    await state.clear()
    if orchestrator is None:
        await message.answer("⚠️ Orchestrator не инициализирован.")
        return

    try:
        queue = await orchestrator.publisher.list_queue()
        published = await orchestrator.publisher.list_published()

        response = (
            f"📋 <b>Статус очереди:</b>\n"
            f"✅ Опубликовано: {len(published)}\n"
            f"⏳ В очереди: {len(queue)}\n\n"
        )

        if not queue:
            response += "Очередь пуста. Создай посты через /autopost или /newpost."
            await message.answer(response, parse_mode="HTML")
            return

        response += "<b>Ожидают публикации:</b>\n\n"
        for i, post in enumerate(queue, 1):
            preview = html.escape(post.get("preview", ""))
            response += f"{i}. <code>{post['filename']}</code>\n"
            response += f"   Добавлен: {post['queued_at']}\n"
            response += f"   Превью: {preview}\n\n"

        await message.answer(response, parse_mode="HTML")

    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")


# ── /edit command — edit posts in queue or published ──────────────────

@router.message(Command("edit"))
async def cmd_edit(message: Message, state: FSMContext):
    """Start post editing flow: choose queue or published."""
    await state.clear()
    logger.info("cmd_edit", user_id=message.from_user.id)

    if orchestrator is None:
        await message.answer("⚠️ Orchestrator не инициализирован.")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Из очереди", callback_data="editsrc:queue")],
        [InlineKeyboardButton(text="✅ Опубликованные", callback_data="editsrc:published")],
    ])
    await message.answer("Какой пост редактировать?", reply_markup=keyboard)
    await state.set_state(EditPostFlow.choosing_source)


@router.callback_query(EditPostFlow.choosing_source, F.data.startswith("editsrc:"))
async def edit_choose_source(callback: CallbackQuery, state: FSMContext):
    """Handle source selection (queue or published)."""
    source = callback.data.split(":")[1]
    publisher = orchestrator.publisher

    if source == "queue":
        posts = await publisher.list_queue()
        directory = publisher.queue_dir
    else:
        posts = await publisher.list_published_detailed()
        directory = publisher.published_dir

    if not posts:
        await callback.message.edit_text("Постов нет.")
        await state.clear()
        await callback.answer()
        return

    await state.update_data(edit_source=source, edit_dir=str(directory))

    buttons = []
    text = f"<b>{'Очередь' if source == 'queue' else 'Опубликованные'}:</b>\n\n"
    for i, post in enumerate(posts):
        preview = html.escape(post.get("preview", ""))
        text += f"{i + 1}. {preview}\n\n"
        buttons.append([
            InlineKeyboardButton(
                text=f"{i + 1}. {post['filename'][:30]}",
                callback_data=f"editpick:{post['filename']}"
            )
        ])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await state.set_state(EditPostFlow.choosing_post)
    await callback.answer()


@router.callback_query(EditPostFlow.choosing_post, F.data.startswith("editpick:"))
async def edit_pick_post(callback: CallbackQuery, state: FSMContext):
    """Show full post text and ask for new version."""
    filename = callback.data.split(":", 1)[1]
    data = await state.get_data()
    directory = Path(data["edit_dir"])
    publisher = orchestrator.publisher

    post_data = await publisher.get_post_by_filename(directory, filename)
    if not post_data:
        await callback.message.edit_text("Пост не найден.")
        await state.clear()
        await callback.answer()
        return

    await state.update_data(edit_filename=filename)

    final_post = post_data.get("final_post", "")

    # Telegram messages have 4096 char limit — truncate if needed
    if len(final_post) > 3500:
        display = final_post[:3500] + "\n\n<i>... (обрезано)</i>"
    else:
        display = final_post

    await callback.message.edit_text(
        f"<b>Текущий текст поста:</b>\n\n{display}",
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
    await callback.message.answer(
        "Отправь новый текст поста целиком (HTML-разметка поддерживается).\n"
        "Или /cancel для отмены."
    )
    await state.set_state(EditPostFlow.editing)
    await callback.answer()


@router.message(EditPostFlow.editing, F.text, F.text.func(lambda t: not t.startswith("/")))
async def edit_save_post(message: Message, state: FSMContext):
    """Save edited post text."""
    new_text = message.text
    data = await state.get_data()
    source = data["edit_source"]
    directory = Path(data["edit_dir"])
    filename = data["edit_filename"]
    publisher = orchestrator.publisher

    try:
        # Save to JSON
        await publisher.update_post(directory, filename, new_text)

        # If published, also edit the message in the channel
        if source == "published":
            post_data = await publisher.get_post_by_filename(directory, filename)
            msg_id = post_data.get("message_id") if post_data else None
            if msg_id and publish_scheduler:
                try:
                    await publish_scheduler.bot.edit_message_text(
                        chat_id=publish_scheduler.channel_id,
                        message_id=msg_id,
                        text=new_text,
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                    )
                    await message.answer("✅ Пост обновлён в файле и в канале!")
                except Exception as e:
                    logger.warning("channel_edit_failed", error=str(e))
                    await message.answer(
                        f"✅ Пост обновлён в файле.\n"
                        f"⚠️ Не удалось обновить в канале: <code>{html.escape(str(e)[:200])}</code>",
                        parse_mode="HTML"
                    )
            else:
                await message.answer(
                    "✅ Пост обновлён в файле.\n"
                    "⚠️ message_id не сохранён — не могу обновить в канале."
                )
        else:
            await message.answer("✅ Пост в очереди обновлён!")

    except Exception as e:
        logger.error("edit_save_failed", error=str(e))
        await message.answer(
            f"❌ Ошибка сохранения: <code>{html.escape(str(e)[:300])}</code>",
            parse_mode="HTML"
        )

    await state.clear()
